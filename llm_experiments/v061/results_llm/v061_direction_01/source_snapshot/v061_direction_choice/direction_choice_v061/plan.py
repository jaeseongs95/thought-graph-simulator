"""Freeze audited v058 requests and the next experiment before inference."""
from copy import deepcopy
from .contracts import *
from .design import (MODELS, MODES, VARIANTS, SCHEDULE_SEED, MAX_CALLS,
                     RULE_ORDERS, BOUNDARY_CELLS, POLICY, schedule, actions)
from .requests import request_bytes, transform
from . import __version__

REF_FIELDS = {'contract', 'bundle_sha256', 'plan_sha256', 'event_tip', 'recorded_calls',
              'selected_calls', 'evidence_kind', 'config', 'identities', 'seeds',
              'slots', 'request_bank', 'independent_compared_fields', 'receipt_sha256'}


def validate_reference(ref):
    require(isinstance(ref, dict) and set(ref) == REF_FIELDS and ref['contract'] == 'audited-v058-choice-r1', 'Reference contract/fields')
    require(ref['receipt_sha256'] == digest({k: v for k, v in ref.items() if k != 'receipt_sha256'}), 'Reference receipt hash')
    require(type(ref['recorded_calls']) is int and ref['recorded_calls'] == 80
            and type(ref['selected_calls']) is int and ref['selected_calls'] == 10, 'Reference counts')
    require(len(ref['seeds']) == 10 and all(type(s) is int for s in ref['seeds'])
            and len(set(ref['seeds'])) == 10, 'Ten unique integer seeds')
    require(ref['evidence_kind'] in ('live_source_artifacts', 'synthetic_fixture'), 'Evidence kind')
    require(set(ref['identities']) == {'candidate'}, 'One candidate identity')
    require(type(ref['independent_compared_fields']) is int and ref['independent_compared_fields'] > 0, 'Independent evidence required')
    require(len(ref['slots']) == 10 and len({s['id'] for s in ref['slots']}) == 10
            and {s['seed'] for s in ref['slots']} == set(ref['seeds']), 'Source slots')
    require(set(ref['request_bank']) == {s['id'] for s in ref['slots']}, 'Source request bank')
    for slot in ref['slots']:
        require(slot['model_key'] == 'candidate' and slot['mode'] == 'choice'
                and slot['sequence'] == 'graph_choice'
                and all(slot[k] == v for k, v in BOUNDARY_CELLS['candidate'].items()), 'Selected source cell')
        raw = unb64(ref['request_bank'][slot['id']])
        q = strict_json(raw)
        require(q['model'] == ref['identities']['candidate']['model']
                and q['options']['seed'] == slot['seed'], 'Source model/seed')
        transform(raw, 'shallow')
        transform(raw, 'deep')


def make_plan(reference):
    validate_reference(reference)
    p = {'contract': 'direction-choice-v061-r1', 'software_version': __version__, 'created_at': utc_now(),
         'reference': deepcopy(reference), 'baseline': {'config': deepcopy(reference['config'])},
         'identities': deepcopy(reference['identities']), 'model_keys': list(MODELS), 'modes': list(MODES),
         'variants': list(VARIANTS), 'schedule_seed': SCHEDULE_SEED, 'rule_orders': deepcopy(RULE_ORDERS),
         'boundary_cells': deepcopy(BOUNDARY_CELLS), 'seeds': deepcopy(reference['seeds']),
         'max_calls': MAX_CALLS, 'policy': deepcopy(POLICY), 'slots': schedule(reference),
         'source_fingerprint': source_fingerprint()}
    p['actions'] = actions(p['slots'])
    p['request_hashes'] = {s['id']: sha(request_bytes(p, s)) for s in p['slots']}
    p['plan_sha256'] = digest(p)
    validate_plan(p)
    return p


def validate_plan(p, *, check_sources=True):
    fields = {'contract', 'software_version', 'created_at', 'reference', 'baseline', 'identities',
              'model_keys', 'modes', 'variants', 'schedule_seed', 'rule_orders', 'boundary_cells',
              'seeds', 'max_calls', 'policy', 'slots', 'actions', 'source_fingerprint',
              'request_hashes', 'plan_sha256'}
    require(isinstance(p, dict) and set(p) == fields, 'Plan fields')
    require(p['contract'] == 'direction-choice-v061-r1' and p['software_version'] == __version__, 'Plan contract/version')
    require(p['plan_sha256'] == digest({k: v for k, v in p.items() if k != 'plan_sha256'}), 'Plan hash')
    validate_reference(p['reference'])
    ref = p['reference']
    expected = {'baseline': {'config': ref['config']}, 'identities': ref['identities'],
                'model_keys': list(MODELS), 'modes': list(MODES), 'variants': list(VARIANTS),
                'schedule_seed': SCHEDULE_SEED, 'rule_orders': RULE_ORDERS, 'boundary_cells': BOUNDARY_CELLS,
                'seeds': ref['seeds'], 'max_calls': MAX_CALLS, 'policy': POLICY, 'slots': schedule(ref)}
    expected['actions'] = actions(expected['slots'])
    expected['request_hashes'] = {s['id']: sha(request_bytes(p, s)) for s in expected['slots']}
    for k, v in expected.items():
        require(canonical(p[k]) == canonical(v), 'Frozen condition changed: ' + k)
    require(len(p['slots']) == 40 and len(p['actions']) == 60, 'Experiment size')
    if check_sources:
        require(p['source_fingerprint'] == source_fingerprint(), 'Source changed since plan freeze')


def prepare(bundle, out):
    from .evidence import import_v058
    require(not out.exists() and not out.with_suffix('.baseline.zip').exists(), 'Existing plan/baseline preserved')
    reference = import_v058(bundle)
    plan = make_plan(reference)
    raw = bundle.read_bytes()
    require(sha(raw) == reference['bundle_sha256'], 'Baseline changed during preparation')
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.with_suffix('.baseline.zip').open('xb') as f:
        f.write(raw)
    write_json(out, plan, exclusive=True)
    require(canonical(read_plan_json(out)) == canonical(plan), 'Plan round-trip mismatch')
    return plan
