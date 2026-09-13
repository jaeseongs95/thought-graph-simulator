"""Recompute v061 ID-only observations; keep historical runs separate."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parents[1] / 'v061' / 'probe' / 'tools'))
from verify_v061 import verify, unpack, independent_measure
from independent_graph_forensic import load, extract_payload, sha


def summarize(rows, seeds, complete):
    variants = ('shallow', 'deep')
    groups = {}
    for variant in variants:
        assigned = [r for r in rows if r['variant'] == variant]
        seen = [r for r in assigned if r['observed']]
        measured = [r for r in seen if r['measurement']['instruction_fulfilled'] is not None]
        success = sum(r['measurement']['instruction_fulfilled'] is True for r in measured)
        groups[variant] = {
            'assigned': len(assigned), 'observed': len(seen), 'measured': len(measured),
            'format_valid': sum(r['measurement']['format_valid'] for r in seen),
            'goal_reachable_choice': sum(r['measurement']['goal_reachable_choice'] is True for r in seen),
            'instruction_fulfilled': success,
            'instruction_rate': success / len(assigned)
                if assigned and complete and len(measured) == len(assigned) else None,
            'selected_ids': dict(Counter(r['measurement']['selected_rule_id'] or 'unmeasured' for r in seen))}
    lookup = {(r['seed'], r['variant'], r['repeat']): r for r in rows}
    if len(lookup) != len(rows):
        raise ValueError('Duplicate trial keys')
    profiles = {('k03', 'k17'): 'directive_sensitive', ('k03', 'k03'): 'fixed_shallow_or_first_terminal',
                ('k17', 'k17'): 'fixed_deep', ('k17', 'k03'): 'reverse_direction'}
    seed_rows, pairs, repeats = [], [], []
    for seed in seeds:
        cells = [lookup.get((seed, v, repeat)) for v in variants for repeat in (0, 1)]
        ids = [r['measurement']['selected_rule_id'] if r and r['observed'] and r['measurement'] else None
               for r in cells]
        stable = (ids[0] == ids[1] and ids[2] == ids[3]) if all(x is not None for x in ids) else None
        profile = ('unmeasured' if stable is None else 'unstable' if not stable
                   else profiles.get((ids[0], ids[2]), 'other'))
        seed_rows.append({'seed': seed, 'ids_A0_A1_B0_B1': ids,
                          'stable_within_both': stable, 'profile': profile})
        for i, v in enumerate(variants):
            a, b = ids[i * 2:i * 2 + 2]
            repeats.append({'seed': seed, 'variant': v,
                            'changed': a != b if a is not None and b is not None else None})
        for repeat in (0, 1):
            a, b = cells[repeat], cells[repeat + 2]
            ia, ib = ids[repeat], ids[repeat + 2]
            ma = a['measurement']['instruction_fulfilled'] if a and a['measurement'] else None
            mb = b['measurement']['instruction_fulfilled'] if b and b['measurement'] else None
            pairs.append({'seed': seed, 'repeat': repeat,
                          'changed': ia != ib if ia is not None and ib is not None else None,
                          'both_instructions': bool(ma and mb) if ma is not None and mb is not None else None})
    strata = {}
    for axis in ('sequence', 'period', 'previous_variant', 'repeat_distance', 'prompt_eval_cached_count'):
        strata[axis] = {}
        for value in sorted({str(r.get(axis)) for r in rows}):
            strata[axis][value] = {}
            for v in variants:
                cells = [r for r in rows if str(r.get(axis)) == value and r['variant'] == v]
                if cells:
                    seen = [r for r in cells if r['observed']]
                    strata[axis][value][v] = {
                        'assigned': len(cells), 'observed': len(seen),
                        'selected_ids': dict(Counter(r['measurement']['selected_rule_id'] or 'unmeasured' for r in seen))}
    return {'groups': groups, 'seed_rows': seed_rows, 'pairs': pairs, 'repeats': repeats,
            'profile_counts': dict(Counter(r['profile'] for r in seed_rows)), 'strata': strata}


def analyze(bundle, historical_v060=None, historical_v059=None):
    raw = bundle.read_bytes()
    receipt = verify(bundle)
    if sha(bundle.read_bytes()) != sha(raw):
        raise ValueError('Evidence changed while being verified')
    data, _ = unpack(raw)
    plan = load(data['external_plan/v061.plan.json'])
    rows = []
    for slot in plan['slots']:
        row = {key: slot[key] for key in ('id', 'seed', 'variant', 'repeat', 'sequence', 'period',
                                          'previous_variant', 'repeat_distance')}
        prefix = 'run/calls/' + slot['id'] + '/'
        if prefix + 'response.raw.json' not in data:
            rows.append({**row, 'observed': False, 'measurement': None})
            continue
        qraw, rraw = data[prefix + 'request.wire.json'], data[prefix + 'response.raw.json']
        q = load(qraw)
        problem = load(q['messages'][0]['content'].rsplit('\n\nproblem: ', 1)[1].encode('utf-8'))
        if problem['id'] != 'K01':
            raise ValueError('K01-only reanalysis')
        measured = independent_measure(problem, extract_payload(rraw, q['model']), slot['direction'])
        try:
            response = load(rraw)
            cached = response.get('prompt_eval_cached_count') if isinstance(response, dict) else None
        except (ValueError, TypeError):
            cached = None
        if type(cached) is not int or cached < 0:
            cached = None
        rows.append({**row, 'observed': True, 'measurement': measured,
                     'model': q['model'], 'rule_order': [r['id'] for r in problem['rules']],
                     'prompt_eval_cached_count': cached, 'request_sha256': sha(qraw),
                     'response_sha256': sha(rraw)})
    history = None
    if historical_v060 is not None:
        from analyze_v060 import analyze as historical_analysis
        history = historical_analysis(historical_v060, historical_v059)
    elif historical_v059 is not None:
        raise ValueError('v059 history requires the separate v060 history input')
    return {'contract': 'v061-reanalysis-r1', 'bundle_sha256': sha(raw),
            'independent_receipt': receipt, 'model': plan['identities']['candidate']['model'],
            'model_digest': plan['identities']['candidate']['digest'], 'rows': rows,
            **summarize(rows, plan['seeds'], receipt['complete']),
            'historical_runs': history, 'independent_problem_count': 1,
            'seed_blocks': len(plan['seeds']), 'actual_D': None, 'pooled_effect_estimate': None,
            'new_model_inference': False,
            'limits': ['Direction insensitivity is scoped to one wording, layout, model and problem.',
                       'Rule ID selection does not measure a generated proof DAG.',
                       'Repeated seeds and historical runs are not independent new problems.',
                       'Hashes prove internal consistency, not external execution authenticity.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('--historical-v060', type=Path)
    parser.add_argument('--historical-v059', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.bundle, args.historical_v060, args.historical_v059)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({k: result[k] for k in ('independent_receipt', 'groups', 'profile_counts')},
                     ensure_ascii=False))
