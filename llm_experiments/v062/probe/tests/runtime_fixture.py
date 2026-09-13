"""Offline v062 fixtures; ``executed`` uses a local synthetic HTTP responder."""
from contextlib import contextmanager, redirect_stdout
from copy import deepcopy
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
import zipfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from construction_probe_v062 import DEPENDENCY_ROOT
from construction_probe_v062.contracts import b64, digest, sha, strict_json, wire, write_json
from construction_probe_v062.plan import make_plan


def reference():
    """Return the ten fixed K01/original/shallow/graph-choice source requests."""
    source = DEPENDENCY_ROOT / 'tests' / 'fixtures.py'
    spec = importlib.util.spec_from_file_location('v058_fixture_for_v062', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    previous = module.plan()
    slots = [slot for slot in previous['slots']
             if slot['model_key'] == 'candidate'
             and slot['problem_id'] == 'K01'
             and slot['arm'] == 'original'
             and slot['direction'] == 'shallow'
             and slot['mode'] == 'choice'
             and slot['sequence'] == 'graph_choice']
    result = {
        'contract': 'audited-v058-choice-r1',
        'bundle_sha256': 'a' * 64,
        'plan_sha256': previous['plan_sha256'],
        'event_tip': 'b' * 64,
        'recorded_calls': 80,
        'selected_calls': 10,
        'evidence_kind': 'synthetic_fixture',
        'config': deepcopy(previous['baseline']['config']),
        'identities': {'candidate': deepcopy(previous['identities']['candidate'])},
        'seeds': deepcopy(previous['seeds']),
        'slots': deepcopy(slots),
        'request_bank': {
            slot['id']: previous['reference']['request_bank'][slot['reference_slot_id']]
            for slot in slots
        },
        'independent_compared_fields': 1,
    }
    result['receipt_sha256'] = digest(result)
    return result


def problem_from_request(raw):
    request = strict_json(raw)
    return strict_json(request['messages'][0]['content'].rsplit(
        '\n\nproblem: ', 1)[1].encode('utf-8'))


def _v058_synthetic_plan(*, config_overrides=None, candidate_identity=None):
    """Construct the prior frozen plan in memory; it makes no HTTP calls."""
    from order_replay_v058.contracts import b64 as v058_b64
    from order_replay_v058.design import BOUNDARY_CELLS as v058_boundary_cells
    from order_replay_v058.plan import make_plan as make_v058_plan
    from order_replay_v058.requests import request_bytes as v058_request_bytes
    from selection_probe_v057.requests import request_bytes as v057_request_bytes
    from tests_v057.quick_fixture import plan as v057_plan

    previous = v057_plan()
    slots = [slot for slot in previous['slots'] if all(
        slot[key] == value for key, value in v058_boundary_cells[slot['model_key']].items())]
    result = {
        'contract': 'audited-v057-boundary-r1',
        'bundle_sha256': sha(b'synthetic-v057-baseline-only'),
        'plan_sha256': previous['plan_sha256'], 'event_tip': 'e' * 64,
        'recorded_calls': 480, 'selected_calls': 40,
        'evidence_kind': 'synthetic_fixture',
        'config': deepcopy(previous['baseline']['config']),
        'identities': deepcopy(previous['identities']), 'seeds': deepcopy(previous['seeds']),
        'slots': deepcopy(slots),
        'request_bank': {slot['id']: v058_b64(v057_request_bytes(previous, slot))
                         for slot in slots},
        'response_bank': {slot['id']: v058_b64(b'{"synthetic_provenance_only":true}')
                          for slot in slots},
        'independent_compared_fields': 1,
    }
    if config_overrides:
        result['config'].update(config_overrides)
    if candidate_identity is not None:
        result['identities']['candidate'] = deepcopy(candidate_identity)
    result['receipt_sha256'] = digest(result)
    return make_v058_plan(result)


def synthetic_v058_bundle(previous=None, *, mismatch_opposite=False):
    """Minimal manifest-bound prior evidence used only by synthetic v062 tests."""
    from order_replay_v058.requests import request_bytes as v058_request_bytes

    previous = previous or _v058_synthetic_plan()
    candidates = [slot for slot in previous['slots']
                  if slot['model_key'] == 'candidate' and slot['problem_id'] == 'K01'
                  and slot['arm'] == 'original' and slot['direction'] == 'shallow'
                  and slot['mode'] == 'choice']
    assert len(candidates) == 20
    files = {
        'external_plan/v058.plan.json': wire(previous),
        'run/summary.json': wire({
            'data_integrity': True, 'data_complete': True,
            'comparative_analysis_ready': True, 'inference_calls': 80,
            'event_tip': 'f' * 64, 'evidence_kind': 'synthetic_fixture',
        }),
    }
    changed = False
    for slot in candidates:
        raw = v058_request_bytes(previous, slot)
        if mismatch_opposite and not changed and slot['sequence'] == 'choice_graph':
            raw += b' '
            changed = True
        files['run/calls/' + slot['id'] + '/request.wire.json'] = raw
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
        archive.writestr('BUNDLE_MANIFEST.json', wire({
            'contract': 'v058-evidence-bundle-r1',
            'plan_sha256': previous['plan_sha256'], 'data_complete': True,
            'file_hashes': {name: sha(content) for name, content in files.items()},
        }))
    return stream.getvalue()


def reference_and_baseline(*, config_overrides=None, candidate_identity=None):
    """Return an audited-shape v058 receipt and its synthetic baseline bytes."""
    from order_replay_v058.requests import request_bytes as v058_request_bytes

    previous = _v058_synthetic_plan(
        config_overrides=config_overrides, candidate_identity=candidate_identity)
    baseline = synthetic_v058_bundle(previous)
    selected = [slot for slot in previous['slots']
                if slot['model_key'] == 'candidate' and slot['problem_id'] == 'K01'
                and slot['arm'] == 'original' and slot['direction'] == 'shallow'
                and slot['mode'] == 'choice' and slot['sequence'] == 'graph_choice']
    result = {
        'contract': 'audited-v058-choice-r1', 'bundle_sha256': sha(baseline),
        'plan_sha256': previous['plan_sha256'], 'event_tip': 'f' * 64,
        'recorded_calls': 80, 'selected_calls': 10,
        'evidence_kind': 'synthetic_fixture',
        'config': deepcopy(previous['baseline']['config']),
        'identities': {'candidate': deepcopy(previous['identities']['candidate'])},
        'seeds': deepcopy(previous['seeds']), 'slots': deepcopy(selected),
        'request_bank': {slot['id']: b64(v058_request_bytes(previous, slot))
                         for slot in selected},
        'independent_compared_fields': 1,
    }
    result['receipt_sha256'] = digest(result)
    return result, baseline


def _graph_answer(body, mode):
    """Synthetic exact-schema DAG response, selected only by the supplied target ID."""
    problem = strict_json(body['messages'][1]['content'][9:])
    target_k17 = '지정된 마지막 규칙 id k17를 사용한다.' in body['messages'][0]['content']
    if target_k17:
        payload = {
            'nodes': [
                {'id': 'goal', 'atom': problem['goal'], 'rule_id': 'k17', 'parents': ['bridge']},
                {'id': 'source', 'atom': 'Ca', 'rule_id': None, 'parents': []},
                {'id': 'bridge', 'atom': 'Cb', 'rule_id': 'k10', 'parents': ['source']},
            ], 'final_node_id': 'goal',
        }
    else:
        payload = {
            'nodes': [
                {'id': 'source', 'atom': 'Ca', 'rule_id': None, 'parents': []},
                {'id': 'goal', 'atom': problem['goal'], 'rule_id': 'k03', 'parents': ['source']},
            ], 'final_node_id': 'goal',
        }
    if mode == 'invalid_rule':
        payload['nodes'][0]['rule_id'] = 'unknown'
    elif mode == 'bad_final':
        payload['final_node_id'] = 'absent'
    elif mode == 'invalid_schema':
        payload['nodes'] = []
    return payload


@contextmanager
def executed(mode='perfect'):
    """Run the production runner against a local deterministic fixture, never Ollama."""
    from model_probe_v055.metadata import collect, identity
    from model_probe_v055.design import CANDIDATE
    from paired_probe_v049.runner import OllamaHTTP
    from construction_probe_v062.runner import execute
    from tests_v057 import fixtures as fixture_module

    with fixture_module.fake_server() as (state, endpoint), \
            tempfile.TemporaryDirectory(prefix='v062_test_') as temp:
        root = Path(temp)
        http = OllamaHTTP(endpoint, 2)
        candidate_identity = identity(collect(http, CANDIDATE), CANDIDATE)
        ref, baseline = reference_and_baseline(
            config_overrides={'endpoint': endpoint, 'timeout_seconds': 2},
            candidate_identity=candidate_identity)
        frozen = make_plan(ref)
        plan_path, run = root / 'plan.json', root / 'run'
        write_json(plan_path, frozen, exclusive=True)
        plan_path.with_suffix('.baseline.zip').write_bytes(baseline)
        state.requests.clear()
        state.http_requests.clear()
        state.mode = mode
        state.metadata_boundary = state.show_calls
        with patch.object(fixture_module, 'graph_answer', _graph_answer), \
                patch('construction_probe_v062.evidence.validate_reference_file',
                      return_value=ref), \
                redirect_stdout(io.StringIO()):
            report = execute(plan_path, run)
            yield root, plan_path, run, frozen, report, state
