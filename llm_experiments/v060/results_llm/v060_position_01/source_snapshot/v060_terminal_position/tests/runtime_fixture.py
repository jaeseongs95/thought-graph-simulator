"""Synthetic v060 runtime fixture; never accepted as research evidence."""
from contextlib import contextmanager, redirect_stdout
from copy import deepcopy
import io
from pathlib import Path
import sys
import tempfile
import zipfile
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import terminal_position_v060
from order_replay_v058.contracts import b64, digest, sha, strict_json, wire
from order_replay_v058.design import BOUNDARY_CELLS as V058_BOUNDARY_CELLS
from order_replay_v058.plan import make_plan as make_v058_plan
from order_replay_v058.requests import request_bytes as v058_request_bytes
from selection_probe_v057.requests import request_bytes as v057_request_bytes
from tests_v057.quick_fixture import plan as v057_plan

from terminal_position_v060.plan import make_plan


def _v058_synthetic_plan(*, config_overrides=None, candidate_identity=None):
    previous = v057_plan()
    slots = [s for s in previous['slots']
             if all(s[key] == value
                    for key, value in V058_BOUNDARY_CELLS[s['model_key']].items())]
    reference = {
        'contract': 'audited-v057-boundary-r1',
        'bundle_sha256': sha(b'synthetic-v057-baseline-only'),
        'plan_sha256': previous['plan_sha256'],
        'event_tip': 'e' * 64,
        'recorded_calls': 480,
        'selected_calls': 40,
        'evidence_kind': 'synthetic_fixture',
        'config': deepcopy(previous['baseline']['config']),
        'identities': deepcopy(previous['identities']),
        'seeds': deepcopy(previous['seeds']),
        'slots': deepcopy(slots),
        'request_bank': {s['id']: b64(v057_request_bytes(previous, s))
                         for s in slots},
        'response_bank': {s['id']: b64(b'{"synthetic_provenance_only":true}')
                          for s in slots},
        'independent_compared_fields': 1,
    }
    if config_overrides:
        reference['config'].update(config_overrides)
    if candidate_identity is not None:
        reference['identities']['candidate'] = deepcopy(candidate_identity)
    reference['receipt_sha256'] = digest(reference)
    return make_v058_plan(reference)


def synthetic_v058_bundle(previous=None, *, mismatch_opposite=False):
    """Build the smallest manifest-bound v058 container needed by import tests."""
    previous = previous or _v058_synthetic_plan()
    candidates = [s for s in previous['slots']
                  if s['model_key'] == 'candidate'
                  and s['problem_id'] == 'K01'
                  and s['arm'] == 'original'
                  and s['direction'] == 'shallow'
                  and s['mode'] == 'choice']
    assert len(candidates) == 20
    files = {
        'external_plan/v058.plan.json': wire(previous),
        'run/summary.json': wire({
            'data_integrity': True,
            'data_complete': True,
            'comparative_analysis_ready': True,
            'inference_calls': 80,
            'event_tip': 'f' * 64,
            'evidence_kind': 'synthetic_fixture',
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
            'plan_sha256': previous['plan_sha256'],
            'data_complete': True,
            'file_hashes': {name: sha(content) for name, content in files.items()},
        }))
    return stream.getvalue()


def reference_and_baseline(*, config_overrides=None, candidate_identity=None):
    previous = _v058_synthetic_plan(
        config_overrides=config_overrides,
        candidate_identity=candidate_identity)
    baseline = synthetic_v058_bundle(previous)
    selected = [s for s in previous['slots']
                if s['model_key'] == 'candidate'
                and s['problem_id'] == 'K01'
                and s['arm'] == 'original'
                and s['direction'] == 'shallow'
                and s['mode'] == 'choice'
                and s['sequence'] == 'graph_choice']
    bank = {slot['id']: b64(v058_request_bytes(previous, slot))
            for slot in selected}
    result = {
        'contract': 'audited-v058-choice-r1',
        'bundle_sha256': sha(baseline),
        'plan_sha256': previous['plan_sha256'],
        'event_tip': 'f' * 64,
        'recorded_calls': 80,
        'selected_calls': 10,
        'evidence_kind': 'synthetic_fixture',
        'config': deepcopy(previous['baseline']['config']),
        'identities': {
            'candidate': deepcopy(previous['identities']['candidate'])},
        'seeds': deepcopy(previous['seeds']),
        'slots': deepcopy(selected),
        'request_bank': bank,
        'independent_compared_fields': 1,
    }
    result['receipt_sha256'] = digest(result)
    return result, baseline


def reference():
    return reference_and_baseline()[0]


def plan():
    return make_plan(reference())


@contextmanager
def executed(mode='perfect'):
    from model_probe_v055.metadata import collect, identity
    from model_probe_v055.design import CANDIDATE
    from paired_probe_v049.runner import OllamaHTTP
    from terminal_position_v060.runner import execute
    from tests_v057.fixtures import fake_server

    with fake_server() as (state, endpoint), \
            tempfile.TemporaryDirectory(prefix='v060_test_') as temp:
        root = Path(temp)
        http = OllamaHTTP(endpoint, 2)
        candidate_identity = identity(collect(http, CANDIDATE), CANDIDATE)
        ref, baseline = reference_and_baseline(
            config_overrides={'endpoint': endpoint, 'timeout_seconds': 2},
            candidate_identity=candidate_identity)
        frozen = make_plan(ref)
        plan_path = root / 'plan.json'
        run = root / 'run'
        from terminal_position_v060.contracts import write_json
        write_json(plan_path, frozen, exclusive=True)
        plan_path.with_suffix('.baseline.zip').write_bytes(baseline)

        state.requests.clear()
        state.http_requests.clear()
        state.mode = mode
        state.metadata_boundary = state.show_calls
        with patch('terminal_position_v060.evidence.validate_reference_file',
                   return_value=ref):
            with redirect_stdout(io.StringIO()):
                report = execute(plan_path, run)
            yield root, plan_path, run, frozen, report, state


def request_problem(raw):
    request = strict_json(raw)
    text = request['messages'][0]['content']
    return strict_json(text.rsplit('\n\nproblem: ', 1)[1].encode('utf-8'))
