"""Freeze audited v058 choice requests before conditional graph construction."""
from copy import deepcopy

from . import __version__
from .contracts import *
from .design import (
    MODELS, MODES, VARIANTS, TARGET_RULES, SCHEDULE_SEED, MAX_CALLS,
    RULE_ORDER, BOUNDARY_CELLS, POLICY, schedule, actions,
)
from .requests import request_bytes, transform

REF_FIELDS = {
    'contract', 'bundle_sha256', 'plan_sha256', 'event_tip', 'recorded_calls',
    'selected_calls', 'evidence_kind', 'config', 'identities', 'seeds', 'slots',
    'request_bank', 'independent_compared_fields', 'receipt_sha256',
}


def validate_reference(ref):
    require(isinstance(ref, dict) and set(ref) == REF_FIELDS
            and ref['contract'] == 'audited-v058-choice-r1', 'Reference contract/fields')
    require(ref['receipt_sha256'] == digest({key: value for key, value in ref.items()
                                             if key != 'receipt_sha256'}), 'Reference receipt hash')
    require(type(ref['recorded_calls']) is int and ref['recorded_calls'] == 80
            and type(ref['selected_calls']) is int and ref['selected_calls'] == 10,
            'Reference counts')
    require(len(ref['seeds']) == 10 and all(type(seed) is int for seed in ref['seeds'])
            and len(set(ref['seeds'])) == 10, 'Ten unique integer seeds')
    require(ref['evidence_kind'] in ('live_source_artifacts', 'synthetic_fixture'),
            'Evidence kind')
    require(set(ref['identities']) == {'candidate'}, 'One candidate identity')
    require(type(ref['independent_compared_fields']) is int
            and ref['independent_compared_fields'] > 0, 'Independent evidence required')
    require(len(ref['slots']) == 10 and len({slot['id'] for slot in ref['slots']}) == 10
            and {slot['seed'] for slot in ref['slots']} == set(ref['seeds']),
            'Source slots')
    require(set(ref['request_bank']) == {slot['id'] for slot in ref['slots']},
            'Source request bank')
    for slot in ref['slots']:
        require(slot['model_key'] == 'candidate' and slot['mode'] == 'choice'
                and slot['sequence'] == 'graph_choice'
                and all(slot[key] == value for key, value in BOUNDARY_CELLS['candidate'].items()),
                'Selected v058 source cell')
        raw = unb64(ref['request_bank'][slot['id']])
        q = strict_json(raw)
        require(q['model'] == ref['identities']['candidate']['model']
                and q['options']['seed'] == slot['seed'], 'Source model/seed')
        for target_rule_id in TARGET_RULES.values():
            transform(raw, target_rule_id)


def make_plan(reference):
    validate_reference(reference)
    plan = {
        'contract': 'conditional-construction-v062-r1',
        'software_version': __version__, 'created_at': utc_now(),
        'reference': deepcopy(reference),
        'baseline': {'config': deepcopy(reference['config'])},
        'identities': deepcopy(reference['identities']),
        'model_keys': list(MODELS), 'modes': list(MODES), 'variants': list(VARIANTS),
        'target_rules': deepcopy(TARGET_RULES), 'schedule_seed': SCHEDULE_SEED,
        'rule_order': deepcopy(RULE_ORDER), 'boundary_cells': deepcopy(BOUNDARY_CELLS),
        'seeds': deepcopy(reference['seeds']), 'max_calls': MAX_CALLS,
        'policy': deepcopy(POLICY), 'slots': schedule(reference),
        'source_fingerprint': source_fingerprint(),
    }
    plan['actions'] = actions(plan['slots'])
    plan['request_hashes'] = {
        slot['id']: sha(request_bytes(plan, slot)) for slot in plan['slots']
    }
    plan['plan_sha256'] = digest(plan)
    validate_plan(plan)
    return plan


def validate_plan(plan, *, check_sources=True):
    fields = {
        'contract', 'software_version', 'created_at', 'reference', 'baseline',
        'identities', 'model_keys', 'modes', 'variants', 'target_rules',
        'schedule_seed', 'rule_order', 'boundary_cells', 'seeds', 'max_calls',
        'policy', 'slots', 'actions', 'source_fingerprint', 'request_hashes',
        'plan_sha256',
    }
    require(isinstance(plan, dict) and set(plan) == fields, 'Plan fields')
    require(plan['contract'] == 'conditional-construction-v062-r1'
            and plan['software_version'] == __version__, 'Plan contract/version')
    require(plan['plan_sha256'] == digest({key: value for key, value in plan.items()
                                            if key != 'plan_sha256'}), 'Plan hash')
    validate_reference(plan['reference'])
    reference = plan['reference']
    expected = {
        'baseline': {'config': reference['config']}, 'identities': reference['identities'],
        'model_keys': list(MODELS), 'modes': list(MODES), 'variants': list(VARIANTS),
        'target_rules': TARGET_RULES, 'schedule_seed': SCHEDULE_SEED,
        'rule_order': RULE_ORDER, 'boundary_cells': BOUNDARY_CELLS,
        'seeds': reference['seeds'], 'max_calls': MAX_CALLS, 'policy': POLICY,
        'slots': schedule(reference),
    }
    expected['actions'] = actions(expected['slots'])
    expected['request_hashes'] = {
        slot['id']: sha(request_bytes(plan, slot)) for slot in expected['slots']
    }
    for key, value in expected.items():
        require(canonical(plan[key]) == canonical(value), 'Frozen condition changed: ' + key)
    require(len(plan['slots']) == 40 and len(plan['actions']) == 60, 'Experiment size')
    if check_sources:
        require(plan['source_fingerprint'] == source_fingerprint(),
                'Source changed since plan freeze')


def prepare(bundle, out):
    from .evidence import import_v058

    require(not out.exists() and not out.with_suffix('.baseline.zip').exists(),
            'Existing plan/baseline preserved')
    reference = import_v058(bundle)
    plan = make_plan(reference)
    raw = bundle.read_bytes()
    require(sha(raw) == reference['bundle_sha256'], 'Baseline changed during preparation')
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.with_suffix('.baseline.zip').open('xb') as stream:
        stream.write(raw)
    write_json(out, plan, exclusive=True)
    require(canonical(read_plan_json(out)) == canonical(plan), 'Plan round-trip mismatch')
    return plan
