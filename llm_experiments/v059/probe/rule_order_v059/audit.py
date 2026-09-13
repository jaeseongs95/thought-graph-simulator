"""Reconstruct requests, identities, events, and choice measurements offline."""
from __future__ import annotations

from paired_probe_v049.runner import endpoint_base

from .contracts import *
from .measure import measure, match
from .plan import validate_plan
from .reporting import save_report, summarize
from .requests import request_bytes, schema_for
from .runner import call_failure, metadata_failure


REPORT_FILES = {'audit.json', 'summary.json', 'summary.ko.md'}


def audit_run(plan_path, out, *, write_report=False):
    try:
        require_external_plan(plan_path, out)
        report = _audit(plan_path, out)
        if write_report:
            save_report(out, report)
        return report
    except (ContractError, OSError, KeyError, ValueError, TypeError) as exc:
        # A failed audit must not follow a report-file or directory symlink while
        # trying to record the failure.  Preserve the suspect tree untouched.
        safe_report_root = (out.is_dir() and not out.is_symlink()
                            and not any(p.is_symlink() for p in out.rglob('*')))
        if write_report and safe_report_root:
            failed = {
                'contract': 'v059-audit-failure-r1',
                'data_integrity': False,
                'data_complete': False,
                'comparative_analysis_ready': False,
                'error': type(exc).__name__ + ': ' + str(exc),
            }
            write_json(out / 'audit.json', failed)
            write_json(out / 'summary.json', failed)
            (out / 'summary.ko.md').write_text(
                '# v059 감사 실패\n\n이전 PASS는 무효입니다. 요청·응답은 보존했습니다.\n\n'
                + failed['error'] + '\n', encoding='utf-8', newline='\n')
        raise


def _problem_from_request(raw):
    request = strict_json(raw)
    messages = request['messages']
    require(len(messages) == 1 and set(messages[0]) == {'role', 'content'}
            and messages[0]['role'] == 'user',
            'One merged user message required')
    content = messages[0]['content']
    require(isinstance(content, str)
            and content.count('\n\nproblem: ') == 1,
            'Problem boundary')
    return strict_json(content.rsplit('\n\nproblem: ', 1)[1].encode('utf-8'))


def _audit(plan_path, out):
    require(out.is_dir() and not out.is_symlink()
            and not any(p.is_symlink() for p in out.rglob('*')),
            'Run missing or contains a symlink')
    plan = read_plan_json(plan_path)
    validate_plan(plan)
    from .evidence import validate_reference_file

    validate_reference_file(out / 'baseline/v058_evidence.zip', plan)
    require(canonical(read_plan_json(out / 'plan.snapshot.json'))
            == canonical(plan), 'External plan and snapshot differ')
    manifest = read_json(out / 'run_manifest.json')
    status = read_json(out / 'status.json')
    manifest_keys = {
        'contract', 'plan_sha256', 'source_fingerprint', 'started_at',
        'python', 'platform', 'endpoint', 'evidence_kind',
        'new_model_inference', 'max_calls', 'retry_policy', 'warmup_calls',
    }
    require(set(manifest) == manifest_keys
            and manifest['contract'] == 'v059-run-manifest-r1',
            'Run manifest fields/contract')
    require(manifest['plan_sha256'] == plan['plan_sha256']
            and manifest['source_fingerprint'] == plan['source_fingerprint'],
            'Manifest plan/source changed')
    require(manifest['endpoint']
            == endpoint_base(plan['baseline']['config']['endpoint']),
            'Endpoint changed')
    require(manifest['evidence_kind'] == plan['reference']['evidence_kind']
            and manifest['new_model_inference']
            is (manifest['evidence_kind'] != 'synthetic_fixture'),
            'Evidence provenance changed')
    require(type(manifest['max_calls']) is int
            and manifest['max_calls'] == 40
            and manifest['retry_policy'] == 'none'
            and type(manifest['warmup_calls']) is int
            and manifest['warmup_calls'] == 0,
            'Execution policy changed')

    snapshot = out / 'source_snapshot'
    fingerprint = plan['source_fingerprint']
    require({p.relative_to(snapshot).as_posix()
             for p in snapshot.rglob('*') if p.is_file()} == set(fingerprint),
            'Source snapshot file set changed')
    for name, expected in fingerprint.items():
        require(sha((snapshot / name).read_bytes()) == expected,
                'Source snapshot changed: ' + name)

    status_keys = {
        'state', 'complete', 'recorded_actions', 'inference_calls',
        'event_tip', 'active_action', 'failure_stage', 'failure_kind',
        'failure_slot_id', 'error', 'finished_at',
    }
    require(set(status) == status_keys, 'Status fields changed')
    require(status['state'] in ('complete', 'incomplete', 'interrupted')
            and type(status['complete']) is bool,
            'Run status format')
    complete = status['complete']
    require(complete is (status['state'] == 'complete'),
            'Run state/complete contradiction')
    for key in ('recorded_actions', 'inference_calls'):
        require(type(status[key]) is int and status[key] >= 0,
                'Run count type')

    lines = (out / 'events.jsonl').read_bytes().splitlines()
    require(all(line.strip() for line in lines), 'Blank event line')
    events = [strict_json(line) for line in lines]
    require(len(events) == status['recorded_actions']
            and len(events) <= len(plan['actions']),
            'Event count changed')
    if complete:
        require(len(events) == 60 and status['inference_calls'] == 40
                and status['active_action'] is None,
                'Complete run is missing actions')
        require(all(status[key] is None for key in
                    ('failure_stage', 'failure_kind', 'failure_slot_id', 'error')),
                'Complete run retains a failure')
    else:
        require(isinstance(status['error'], str) and bool(status['error']),
                'Incomplete run lacks a reason')
        require(type(status['active_action']) is int
                and 0 <= status['active_action'] < len(plan['actions']),
                'Incomplete run lacks an active action')

    expected_files = {
        'plan.snapshot.json', 'run_manifest.json', 'status.json', 'events.jsonl',
        'baseline/v058_evidence.zip',
    } | {'source_snapshot/' + name for name in fingerprint}
    tip = plan['plan_sha256']
    observed = {}
    calls = []
    last_failure = None

    for index, event in enumerate(events):
        action = plan['actions'][index]
        require(canonical(event['action']) == canonical(action),
                'Frozen action order/model/condition changed')
        require(event['previous_hash'] == tip
                and event['event_hash'] == digest({
                    key: value for key, value in event.items()
                    if key != 'event_hash'}),
                'Event hash chain changed')
        tip = event['event_hash']
        base_fields = {'action', 'at', 'previous_hash', 'event_hash'}
        if action['kind'] == 'metadata':
            require(set(event) == base_fields | {'metadata_sha256'},
                    'Metadata event fields changed')
            name = 'metadata/' + action['id'] + '.json'
            expected_files.add(name)
            raw = (out / name).read_bytes()
            require(sha(raw) == event['metadata_sha256'],
                    'Metadata bytes changed')
            record = strict_json(raw)
            failure, error = metadata_failure(
                record, plan['identities']['candidate'])
        else:
            require(set(event) == base_fields | {
                'request_sha256', 'response_sha256', 'http_status',
                'transport_error', 'elapsed_ns'},
                'Call event fields changed')
            slot = action['slot']
            sid = slot['id']
            model = plan['identities']['candidate']['model']
            request_name = 'calls/' + sid + '/request.wire.json'
            response_name = 'calls/' + sid + '/response.raw.json'
            expected_files.update((request_name, response_name))
            request = (out / request_name).read_bytes()
            response = (out / response_name).read_bytes()
            require(sha(request) == event['request_sha256']
                    and sha(response) == event['response_sha256'],
                    'Request/response bytes changed')
            require(request == request_bytes(plan, slot)
                    and sha(request) == plan['request_hashes'][sid],
                    'Frozen request differs from executed request')
            require(type(event['http_status']) is int
                    and 0 <= event['http_status'] <= 599
                    and type(event['elapsed_ns']) is int
                    and event['elapsed_ns'] >= 0,
                    'HTTP field type')
            require(event['transport_error'] is None
                    or isinstance(event['transport_error'], str),
                    'Transport error type')
            failure, error = call_failure(
                response, event['http_status'], event['transport_error'], model)
            payload = None
            parse_error = None
            record_status = ('transport_error'
                             if failure == 'transport_error'
                             else 'invalid_response')
            if failure is None:
                try:
                    payload = decode_response(response, model, 'choice')
                    record_status = 'valid_payload'
                    try:
                        validate_payload(payload, schema_for(slot))
                    except ContractError as exc:
                        record_status = 'invalid_payload_schema'
                        parse_error = str(exc)
                except ContractError as exc:
                    parse_error = str(exc)
            elif failure == 'response_identity_error':
                record_status = 'response_identity_error'

            problem = _problem_from_request(request)
            measurement = measure(problem, payload, slot)
            matched = match(problem, measurement, slot)
            observed[sid] = {
                **slot,
                'observed': True,
                'measurement': measurement,
                'role_match': matched,
                'status': record_status,
                'parse_error': parse_error,
            }
            calls.append({
                **slot,
                'http_status': event['http_status'],
                'elapsed_ns': event['elapsed_ns'],
                'request_sha256': sha(request),
                'response_sha256': sha(response),
                **usage(response),
                **completion_metadata(response),
            })
        if failure:
            require(index == len(events) - 1 and not complete,
                    'Execution continued after a fatal failure')
            last_failure = (action, failure, error)

    require(tip == status['event_tip'], 'Event tip changed')
    if complete:
        require(len(calls) == status['inference_calls'],
                'Inference count changed')
    else:
        require(len(calls) <= status['inference_calls'] <= len(calls) + 1,
                'Incomplete inference-attempt count changed')
        if last_failure:
            action, failure, error = last_failure
            require(status['failure_stage'] == action['kind']
                    and status['failure_kind'] == failure
                    and status['failure_slot_id'] == action['id']
                    and status['error'] == error,
                    'Failure diagnosis differs from raw event')
            require(status['active_action'] == action['index']
                    and status['inference_calls'] == len(calls),
                    'Recorded failure action/count changed')
        else:
            require(status['failure_kind'] in
                    ('execution_error', 'user_interrupt'),
                    'Incomplete run failure kind')
            require(len(events) < len(plan['actions']),
                    'Unexplained failure after all actions')
            pending = plan['actions'][len(events)]
            require(status['active_action'] == len(events)
                    and status['failure_slot_id'] == pending['id']
                    and status['failure_stage'] == pending['kind'],
                    'Pending action changed')
            if pending['kind'] == 'call':
                name = 'calls/' + pending['id'] + '/request.wire.json'
                if (out / name).exists():
                    require((out / name).read_bytes()
                            == request_bytes(plan, pending['slot']),
                            'Interrupted request changed')
                    expected_files.add(name)
            require(status['inference_calls'] == len(calls)
                    or pending['kind'] == 'call',
                    'Metadata interruption counted as inference')

    actual_files = {p.relative_to(out).as_posix()
                    for p in out.rglob('*') if p.is_file()}
    require(actual_files - REPORT_FILES == expected_files,
            'Run file set changed: '
            + str(sorted((actual_files - REPORT_FILES) ^ expected_files)))
    trials = [observed.get(slot['id'], {
        **slot,
        'observed': False,
        'measurement': None,
        'role_match': None,
        'status': 'unexecuted',
        'parse_error': None,
    }) for slot in plan['slots']]
    result = summarize(plan, trials, calls, complete)
    result.update(
        data_integrity=True,
        data_complete=complete,
        comparative_analysis_ready=complete,
        evidence_kind=manifest['evidence_kind'],
        new_model_inference=manifest['new_model_inference'],
        inference_calls=status['inference_calls'],
        max_inference_calls=40,
        plan_sha256=plan['plan_sha256'],
        event_tip=tip,
        run_state=status['state'],
        run_error=status['error'],
        failure_stage=status['failure_stage'],
        failure_kind=status['failure_kind'],
        failure_slot_id=status['failure_slot_id'],
        trials=trials,
        calls=calls,
        source_fingerprint=fingerprint,
        reference_bundle_sha256=plan['reference']['bundle_sha256'],
    )
    return result
