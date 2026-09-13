"""Synthetic fixtures. Baseline import is isolated explicitly in runner tests."""
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
import order_replay_v058
from order_replay_v058.contracts import b64, digest, sha, wire, write_json, strict_json, unb64
from order_replay_v058.design import BOUNDARY_CELLS
from order_replay_v058.plan import make_plan
from selection_probe_v057.requests import request_bytes as previous_request
from tests_v057.quick_fixture import plan as previous_plan


def reference():
    p = previous_plan()
    slots = [s for s in p['slots'] if all(s[k] == v for k, v in BOUNDARY_CELLS[s['model_key']].items())]
    ref = {'contract': 'audited-v057-boundary-r1', 'bundle_sha256': sha(b'synthetic-baseline-only'),
           'plan_sha256': p['plan_sha256'], 'event_tip': 'e' * 64, 'recorded_calls': 480,
           'selected_calls': 40, 'evidence_kind': 'synthetic_fixture',
           'config': deepcopy(p['baseline']['config']), 'identities': deepcopy(p['identities']),
           'seeds': deepcopy(p['seeds']), 'slots': deepcopy(slots),
           'request_bank': {s['id']: b64(previous_request(p, s)) for s in slots},
           'response_bank': {s['id']: b64(b'{"synthetic_provenance_only":true}') for s in slots},
           'independent_compared_fields': 1}
    ref['receipt_sha256'] = digest(ref)
    return ref


def plan():
    return make_plan(reference())


def synthetic_baseline(ref):
    """Minimal baseline container; prior-generation full audit is NOT exercised."""
    prior = previous_plan()
    bp = {'plan_sha256': ref['plan_sha256'], 'baseline': {'config': ref['config']},
          'identities': ref['identities'], 'seeds': ref['seeds'], 'slots': ref['slots'],
          **{k: prior[k] for k in ['problems', 'arms', 'rule_orders']}}
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('external_plan/v057.plan.json', wire(bp))
        archive.writestr('run/summary.json', wire({'event_tip': ref['event_tip'], 'evidence_kind': 'synthetic_fixture'}))
        for slot in ref['slots']:
            for filename, bank in [('request.wire.json', 'request_bank'), ('response.raw.json', 'response_bank')]:
                archive.writestr(f"run/calls/{slot['id']}/{filename}", unb64(ref[bank][slot['id']]))
    return stream.getvalue()


@contextmanager
def executed(mode='perfect'):
    from tests_v057.fixtures import fake_server, MODEL
    from paired_probe_v049.runner import OllamaHTTP
    from model_probe_v055.metadata import collect, identity
    from order_replay_v058.runner import execute
    with fake_server() as (state, endpoint), tempfile.TemporaryDirectory(prefix='v058_test_') as temp:
        root = Path(temp)
        ref = reference()
        ref['config']['endpoint'] = endpoint
        ref['config']['timeout_seconds'] = 2
        ref['config']['model'] = MODEL
        ref['identities']['reference']['model'] = MODEL
        for slot in ref['slots']:
            if slot['model_key'] == 'reference':
                body = strict_json(unb64(ref['request_bank'][slot['id']]))
                body['model'] = MODEL
                ref['request_bank'][slot['id']] = b64(wire(body))
        http = OllamaHTTP(endpoint, 2)
        for key, expected in list(ref['identities'].items()):
            ref['identities'][key] = identity(collect(http, expected['model']), expected['model'])
        baseline_bytes = synthetic_baseline(ref)
        ref['bundle_sha256'] = sha(baseline_bytes)
        ref.pop('receipt_sha256')
        ref['receipt_sha256'] = digest(ref)
        p = make_plan(ref)
        pp, run = root / 'plan.json', root / 'run'
        write_json(pp, p, exclusive=True)
        pp.with_suffix('.baseline.zip').write_bytes(baseline_bytes)
        state.requests.clear()
        state.http_requests.clear()
        state.mode = mode
        state.metadata_boundary = state.show_calls
        # The synthetic bank is not research evidence. Baseline validation alone
        # is replaced; real HTTP, metadata checks, scheduling, hashing and audit run.
        with patch('order_replay_v058.evidence.validate_reference_file', return_value=ref):
            with redirect_stdout(io.StringIO()):
                report = execute(pp, run)
            yield root, pp, run, p, report, state


def measured_trials(p, *, choice_sequence=None, absent=False):
    from order_probe_v054.design import problem_for
    from order_replay_v058.measure import measure, match
    from tests_v054.fixtures import first_path
    rows = []
    for s in p['slots']:
        if absent:
            rows.append({**s, 'observed': False, 'measurement': None, 'role_match': None,
                         'status': 'unexecuted', 'parse_error': None})
            continue
        pr = problem_for(s)
        if s['mode'] == 'graph':
            payload = first_path(pr)
        else:
            correct = choice_sequence is None or s['sequence'] == choice_sequence
            rid = ({'K01': 'k03', 'T02': 'r83'} if correct else {'K01': 'k17', 'T02': 'r69'})[s['problem_id']]
            payload = {'final_rule_id': rid}
        m = measure(pr, payload, s)
        rows.append({**s, 'observed': True, 'measurement': m, 'role_match': match(pr, m, s),
                     'status': 'valid_payload', 'parse_error': None})
    return rows
