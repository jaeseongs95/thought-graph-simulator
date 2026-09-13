"""Execute the frozen 40-call terminal-position schedule without retry or repair."""
from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

from paired_probe_v049.runner import OllamaHTTP
from model_probe_v055.metadata import collect, decode_metadata, identity

from .contracts import *
from .plan import validate_plan
from .requests import request_bytes


IDENTITY_FIELDS = {
    'model', 'digest', 'show_sha256', 'server', 'details', 'template',
    'parameters', 'model_info',
}


def comparable_identity(value):
    """Ignore only harmless ordering of unique Ollama parameter lines."""
    require(isinstance(value, dict) and set(value) == IDENTITY_FIELDS,
            'Model identity fields changed')
    require(isinstance(value['show_sha256'], str)
            and len(value['show_sha256']) == 64,
            'Show hash format')
    parameters = value['parameters']
    require(parameters is None or isinstance(parameters, str),
            'Model parameters format')
    result = {key: value[key]
              for key in IDENTITY_FIELDS - {'show_sha256', 'parameters'}}
    result['parameter_lines'] = (None if parameters is None
                                 else sorted(parameters.split('\n')))
    return result


def metadata_failure(record, expected):
    try:
        decode_metadata(record, expected['model'])
    except (ContractError, KeyError, TypeError, ValueError) as exc:
        return 'runtime_metadata_error', str(exc)
    try:
        current = identity(record, expected['model'])
        require(canonical(comparable_identity(current))
                == canonical(comparable_identity(expected)),
                'Frozen model digest/server/details/template/parameters/model_info changed')
    except (ContractError, KeyError, TypeError, ValueError) as exc:
        return 'runtime_identity_error', str(exc)
    return None, None


def call_failure(raw, status, error, expected_model):
    if status != 200 or error is not None:
        return 'transport_error', f'HTTP {status}: {error}'
    try:
        envelope = strict_json(raw)
    except ContractError:
        return None, None
    if (isinstance(envelope, dict)
            and isinstance(envelope.get('model'), str)
            and envelope['model'] != expected_model):
        return ('response_identity_error',
                'Response model differs from request model: ' + envelope['model'])
    return None, None


def execute(plan_path: Path, out: Path):
    plan = read_plan_json(plan_path)
    validate_plan(plan)
    require_external_plan(plan_path, out)
    from .evidence import validate_reference_file

    baseline_path = plan_path.with_suffix('.baseline.zip')
    validate_reference_file(baseline_path, plan)
    baseline_bytes = baseline_path.read_bytes()
    require(sha(baseline_bytes) == plan['reference']['bundle_sha256'],
            'v058 baseline ZIP changed before execution')
    require(not out.exists(), 'Existing run preserved; choose a new RunName: ' + str(out))

    config = plan['baseline']['config']
    http = OllamaHTTP(config['endpoint'], config.get('timeout_seconds', 300))
    out.mkdir(parents=True, exist_ok=False)
    (out / 'baseline').mkdir()
    (out / 'baseline/v058_evidence.zip').write_bytes(baseline_bytes)
    write_json(out / 'plan.snapshot.json', plan, exclusive=True)
    for name in plan['source_fingerprint']:
        dest = out / 'source_snapshot' / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(source_path(name).read_bytes())
    write_json(out / 'run_manifest.json', {
        'contract': 'v060-run-manifest-r1',
        'plan_sha256': plan['plan_sha256'],
        'source_fingerprint': source_fingerprint(),
        'started_at': utc_now(),
        'python': sys.version,
        'platform': platform.platform(),
        'endpoint': http.base,
        'evidence_kind': plan['reference']['evidence_kind'],
        'new_model_inference': plan['reference']['evidence_kind'] != 'synthetic_fixture',
        'max_calls': 40,
        'retry_policy': 'none',
        'warmup_calls': 0,
    }, exclusive=True)
    status = {
        'state': 'running',
        'complete': False,
        'recorded_actions': 0,
        'inference_calls': 0,
        'event_tip': plan['plan_sha256'],
        'active_action': None,
        'failure_stage': None,
        'failure_kind': None,
        'failure_slot_id': None,
        'error': None,
    }
    write_json(out / 'status.json', status)

    with (out / 'events.jsonl').open('xb') as stream:
        def persist():
            write_json(out / 'status.json', status)

        def append(event):
            event['previous_hash'] = status['event_tip']
            event['event_hash'] = digest(event)
            stream.write(wire(event) + b'\n')
            stream.flush()
            os.fsync(stream.fileno())
            status['recorded_actions'] += 1
            status['event_tip'] = event['event_hash']
            persist()

        try:
            for action in plan['actions']:
                status['active_action'] = action['index']
                persist()
                event = {'action': action, 'at': utc_now()}
                expected = plan['identities']['candidate']
                if action['kind'] == 'metadata':
                    record = collect(http, expected['model'])
                    path = out / 'metadata' / (action['id'] + '.json')
                    write_json(path, record, exclusive=True)
                    event['metadata_sha256'] = sha(path.read_bytes())
                    failure, error = metadata_failure(record, expected)
                else:
                    slot = action['slot']
                    folder = out / 'calls' / slot['id']
                    folder.mkdir(parents=True, exist_ok=False)
                    raw = request_bytes(plan, slot)
                    (folder / 'request.wire.json').write_bytes(raw)
                    status['inference_calls'] += 1
                    persist()
                    print(f'[{status["inference_calls"]}/40] {slot["id"]}', flush=True)
                    response = http.request('/api/chat', raw)
                    (folder / 'response.raw.json').write_bytes(response['raw'])
                    event.update(
                        request_sha256=sha(raw),
                        response_sha256=sha(response['raw']),
                        http_status=response['http_status'],
                        transport_error=response['error'],
                        elapsed_ns=response['elapsed_ns'],
                    )
                    failure, error = call_failure(
                        response['raw'], response['http_status'], response['error'],
                        expected['model'])
                append(event)
                if failure:
                    status.update(
                        state='incomplete',
                        failure_stage=action['kind'],
                        failure_kind=failure,
                        failure_slot_id=action['id'],
                        error=error,
                    )
                    break
            else:
                status.update(state='complete', complete=True, active_action=None)
        except KeyboardInterrupt:
            action = (plan['actions'][status['active_action']]
                      if status['active_action'] is not None else None)
            status.update(
                state='interrupted',
                failure_stage=action['kind'] if action else 'created',
                failure_kind='user_interrupt',
                failure_slot_id=action['id'] if action else None,
                error='User interrupted execution; automatic resume is disabled.',
            )
        except (ContractError, OSError, KeyError, ValueError, TypeError) as exc:
            action = (plan['actions'][status['active_action']]
                      if status['active_action'] is not None else None)
            status.update(
                state='incomplete',
                failure_stage=action['kind'] if action else 'created',
                failure_kind='execution_error',
                failure_slot_id=action['id'] if action else None,
                error=type(exc).__name__ + ': ' + str(exc),
            )
        finally:
            status['finished_at'] = utc_now()
            persist()

    from .audit import audit_run
    return audit_run(plan_path, out, write_report=True)
