"""Recompute v060 raw observations and optionally compare separate v059 records."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parents[1] / 'v060' / 'probe' / 'tools'))
from verify_v060 import verify, unpack, independent_measure
from independent_graph_forensic import load, extract_payload, sha


def predictions(order):
    terminals = [rid for rid in order if rid in ('k17', 'k03')]
    if len(order) != 3 or set(order) != {'k10', 'k17', 'k03'}:
        raise ValueError('K01 three-rule permutations required')
    return {'first_terminal': terminals[0], 'first_item': order[0],
            'absolute_second': order[1], 'last_terminal': terminals[-1],
            'fixed_shallow': 'k03', 'fixed_deep': 'k17'}


def summarize(rows, variants, seeds, complete):
    groups = {}
    for variant in variants:
        assigned = [r for r in rows if r['variant'] == variant]
        seen = [r for r in assigned if r['observed']]
        measured = [r for r in seen if r['measurement']['format_valid']]
        groups[variant] = {
            'assigned': len(assigned), 'observed': len(seen), 'measured': len(measured),
            'format_valid': len(measured),
            'goal_reachable_choice': sum(r['measurement']['choice_valid'] is True for r in seen),
            'shallow_success': sum(r['measurement']['shallow_success'] is True for r in seen),
            'selected_ids': dict(Counter(r['measurement']['selected_rule_id'] or 'unmeasured' for r in seen)),
            'selected_positions': dict(Counter(str(r['measurement']['selected_rule_position'])
                                               if r['measurement']['selected_rule_position'] is not None
                                               else 'unmeasured' for r in seen)),
            'terminal_ranks': dict(Counter(str(r['measurement']['terminal_rank'])
                                          if r['measurement']['terminal_rank'] is not None
                                          else 'unmeasured' for r in seen)),
        }
    fits = {}
    for name in predictions(['k10', 'k17', 'k03']):
        comparable = [r for r in rows if r['observed'] and r['measurement']['format_valid']]
        matches = sum(r['measurement']['selected_rule_id'] == predictions(r['rule_order'])[name]
                      for r in comparable)
        fits[name] = {'assigned': len(rows), 'measured': len(comparable), 'matching': matches,
                      'full_match': (matches == len(rows)) if complete and len(comparable) == len(rows) else None}
    repeats, seed_rows = [], []
    for seed in seeds:
        changes = []
        joint = {}
        for variant in variants:
            cells = sorted((r for r in rows if r['seed'] == seed and r['variant'] == variant),
                           key=lambda r: r['repeat'])
            ids = [r['measurement']['selected_rule_id'] if r['measurement'] else None for r in cells]
            changed = ids[0] != ids[1] if len(ids) == 2 and all(x is not None for x in ids) else None
            repeats.append({'seed': seed, 'variant': variant, 'changed': changed})
            joint[variant] = ids
            changes.append(changed)
        stable = (all(value is False for value in changes)
                  if all(value is not None for value in changes) else None)
        seed_rows.append({'seed': seed, 'selected_ids_by_variant': joint, 'both_repeats_stable': stable})
    strata = {}
    for axis in ('sequence', 'period', 'previous_variant', 'repeat_distance',
                 'prompt_eval_cached_count'):
        values = sorted({str(r.get(axis)) for r in rows})
        strata[axis] = {}
        for value in values:
            strata[axis][value] = {}
            for variant in variants:
                cells = [r for r in rows if str(r.get(axis)) == value and r['variant'] == variant]
                if not cells:
                    continue
                seen = [r for r in cells if r['observed']]
                strata[axis][value][variant] = {
                    'assigned': len(cells), 'observed': len(seen),
                    'selected_ids': dict(Counter(r['measurement']['selected_rule_id'] or 'unmeasured'
                                                 for r in seen)),
                    'shallow_success': sum(r['measurement']['shallow_success'] is True for r in seen)}
    return {'groups': groups, 'prediction_fits': fits, 'repeats': repeats,
            'seed_rows': seed_rows, 'strata': strata}


def read_run(bundle, version):
    if version == 'v059':
        sys.path.insert(0, str(ROOT.parents[1] / 'v059' / 'probe' / 'tools'))
        from verify_v059 import verify as verifier, unpack as unpacker
    else:
        verifier, unpacker = verify, unpack
    raw = bundle.read_bytes()
    digest = sha(raw)
    receipt = verifier(bundle)
    if sha(bundle.read_bytes()) != digest:
        raise ValueError('Evidence changed during verification')
    data, _ = unpacker(raw)
    plan = load(data[f'external_plan/{version}.plan.json'])
    rows = []
    for slot in plan['slots']:
        prefix = 'run/calls/' + slot['id']
        request_name, response_name = prefix + '/request.wire.json', prefix + '/response.raw.json'
        row = {k: slot[k] for k in ('id', 'seed', 'variant', 'repeat', 'period', 'sequence',
                                   'position', 'previous_variant', 'repeat_distance')}
        if response_name not in data:
            rows.append({**row, 'observed': False, 'measurement': None})
            continue
        q = load(data[request_name])
        problem = load(q['messages'][0]['content'].rsplit('\n\nproblem: ', 1)[1].encode('utf-8'))
        if problem['id'] != 'K01':
            raise ValueError('Only frozen K01 analysis is supported')
        m = independent_measure(problem, extract_payload(data[response_name], q['model']))
        try:
            response = load(data[response_name])
            cache_count = response.get('prompt_eval_cached_count') if isinstance(response, dict) else None
        except (ValueError, TypeError):
            cache_count = None
        if type(cache_count) is not int or cache_count < 0:
            cache_count = None
        rows.append({**row, 'observed': True, 'rule_order': [r['id'] for r in problem['rules']],
                     'prompt_eval_cached_count': cache_count,
                     'measurement': m, 'request_sha256': sha(data[request_name]),
                     'response_sha256': sha(data[response_name])})
    return {'version': version, 'bundle_sha256': digest, 'independent_receipt': receipt,
            'rows': rows, **summarize(rows, plan['variants'], plan['seeds'], receipt['complete']),
            'independent_problem_count': 1, 'unique_seed_blocks': len(plan['seeds'])}


def analyze(bundle, historical_bundle=None):
    current = read_run(bundle, 'v060')
    history = read_run(historical_bundle, 'v059') if historical_bundle else None
    common = None
    if history is not None:
        common = [name for name, fit in current['prediction_fits'].items()
                  if fit['full_match'] is True and history['prediction_fits'][name]['full_match'] is True]
    return {'contract': 'v060-multiperspective-reanalysis-r1', 'current': current,
            'historical': history, 'compatible_in_each_separate_run': common,
            'pooled_effect_estimate': None, 'new_model_inference': False, 'actual_D': None,
            'limits': ['Matching a rule-selection prediction does not establish an internal mechanism.',
                       'Historical runs are separate evidence, not randomized layout contrasts.',
                       'Repeated seeds do not create independent problem samples.',
                       'Integrity verification is not external execution attestation.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('--historical-bundle', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.bundle, args.historical_bundle)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'groups': result['current']['groups'],
                      'prediction_fits': result['current']['prediction_fits'],
                      'compatible_in_each_separate_run': result['compatible_in_each_separate_run'],
                      'receipt': result['current']['independent_receipt']}, ensure_ascii=False))
