"""Recompute observed choices and competing rule-order predictions offline."""
from pathlib import Path
import argparse
import collections
import itertools
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parents[1] / 'v059' / 'probe' / 'tools'))
from verify_v059 import verify, unpack
from independent_graph_forensic import load, extract_payload, sha
from independent_verify_v057 import choice


def predictions(order):
    return {'first_terminal': next(r for r in order if r in ('k17', 'k03')),
            'absolute_second': order[1], 'fixed_deep': 'k17',
            'shortest_reachable': 'k03'}


def analyze(bundle):
    before = sha(bundle.read_bytes())
    receipt = verify(bundle)
    raw = bundle.read_bytes()
    if sha(raw) != before:
        raise ValueError('Evidence changed during verification')
    data, _ = unpack(raw)
    plan = load(data['external_plan/v059.plan.json'])
    rows = []
    for slot in plan['slots']:
        prefix = 'run/calls/' + slot['id']
        request_name, response_name = prefix + '/request.wire.json', prefix + '/response.raw.json'
        if response_name not in data:
            rows.append({**{k: slot[k] for k in ('id', 'seed', 'variant', 'repeat', 'period', 'sequence')},
                         'observed': False, 'measurement': None, 'prediction_matches': None})
            continue
        request = load(data[request_name])
        problem = load(request['messages'][0]['content'].rsplit('\n\nproblem: ', 1)[1].encode('utf-8'))
        payload = extract_payload(data[response_name], request['model'])
        measurement = choice(problem, payload)
        selected = measurement.get('selected_rule_id')
        order = [r['id'] for r in problem['rules']]
        rows.append({**{k: slot[k] for k in ('id', 'seed', 'variant', 'repeat', 'period', 'sequence')},
                     'observed': True, 'measurement': measurement, 'rule_order': order,
                     'selected_position_zero_based': order.index(selected) if selected in order else None,
                     'prediction_matches': {k: (selected == v if measurement['format_valid'] else None)
                                            for k, v in predictions(order).items()},
                     'request_sha256': sha(data[request_name]), 'response_sha256': sha(data[response_name])})
    groups = {}
    for variant in plan['variants']:
        assigned = [r for r in rows if r['variant'] == variant]
        observed = [r for r in assigned if r['observed']]
        groups[variant] = {'assigned': len(assigned), 'observed': len(observed),
            'selected_ids': dict(collections.Counter(r['measurement'].get('selected_rule_id') for r in observed)),
            'format_valid': sum(r['measurement']['format_valid'] is True for r in observed),
            'choice_valid': sum(r['measurement']['choice_valid'] is True for r in observed),
            'shallow_success': sum(r['measurement'].get('choice_valid') is True and
                                   r['measurement'].get('implied_depth') == 1 for r in observed)}
    signatures = {name: [predictions(r['rule_order'])[name] for r in rows if r['observed']]
                  for name in predictions(['k10', 'k17', 'k03'])}
    equivalent = [[a, b] for a, b in itertools.combinations(signatures, 2) if signatures[a] == signatures[b]]
    repeats = []
    for seed in plan['seeds']:
        for variant in plan['variants']:
            pair = [r for r in rows if r['seed'] == seed and r['variant'] == variant]
            ids = [r['measurement'].get('selected_rule_id') if r['measurement'] else None for r in pair]
            repeats.append({'seed': seed, 'variant': variant,
                            'changed': ids[0] != ids[1] if len(ids) == 2 and all(i is not None for i in ids) else None})
    return {'contract': 'v059-multiperspective-reanalysis-r1', 'bundle_sha256': before,
            'independent_receipt': receipt, 'groups': groups, 'rows': rows,
            'repeats': repeats, 'observationally_equivalent_predictions': equivalent,
            'hypothetical_permutation_predictions': [{'order': list(order), **predictions(order)}
                                                     for order in itertools.permutations(('k10', 'k17', 'k03'))],
            'independent_problem_count': 1, 'unique_seed_blocks': len(plan['seeds']),
            'new_model_inference': False, 'actual_D': None,
            'limits': ['Predictions describe observable patterns, not verified internal mechanisms.',
                       'Historical and repeated calls are not new independent problem samples.',
                       'Artifact consistency is not external execution attestation.',
                       'Unmeasured and unobserved values remain distinct from task failure.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.bundle)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'groups': result['groups'], 'equivalent': result['observationally_equivalent_predictions'],
                      'receipt': result['independent_receipt']}, ensure_ascii=False))
