"""Reproducible read-only analysis of the supplied v058 raw evidence."""
from pathlib import Path
import argparse
import collections
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import rule_order_v059
sys.path.insert(0, str(rule_order_v059.DEPENDENCY_ROOT / 'tools'))
from verify_v058 import verify, unpack
from independent_graph_forensic import load, extract_payload, inspect, sha
from independent_verify_v057 import choice


def analyze(bundle):
    receipt = verify(bundle)
    data, _ = unpack(bundle.read_bytes())
    p = load(data['external_plan/v058.plan.json'])
    s = load(data['run/summary.json'])
    groups = {}
    raw_rows = []
    for slot in p['slots']:
        path = 'run/calls/' + slot['id']
        q = load(data[path + '/request.wire.json'])
        problem = load(q['messages'][0]['content'].split('\n\nproblem: ')[1].encode('utf-8'))
        response = data[path + '/response.raw.json']
        payload = extract_payload(response, q['model'])
        m = inspect(problem, payload) if slot['mode'] == 'graph' else choice(problem, payload)
        raw_rows.append({'slot_id': slot['id'], 'seed': slot['seed'], 'model_key': slot['model_key'],
            'mode': slot['mode'], 'sequence': slot['sequence'], 'position': slot['position'],
            'request_sha256': sha(data[path + '/request.wire.json']), 'response_sha256': sha(response),
            'format_valid': m['format_valid'], 'strict_valid': m['strict_valid'],
            'choice_valid': m.get('choice_valid'), 'D': m['D'],
            'selected_rule_id': m.get('selected_rule_id'), 'implied_depth': m.get('implied_depth')})
    for model in ('reference', 'candidate'):
        groups[model] = {}
        for mode in ('graph', 'choice'):
            rows = [r for r in raw_rows if r['model_key'] == model and r['mode'] == mode]
            field = 'strict_valid' if mode == 'graph' else 'choice_valid'
            errors = collections.Counter(e for t in s['trials'] if t['model_key'] == model and t['mode'] == mode
                                         for e in t['measurement']['errors'])
            groups[model][mode] = {'calls': len(rows), 'format_valid': sum(r['format_valid'] for r in rows),
                'task_valid': sum(r[field] is True for r in rows),
                'selected_rule_ids': dict(collections.Counter(r['selected_rule_id'] for r in rows)) if mode == 'choice' else None,
                'actual_D': dict(collections.Counter(str(r['D']) if r['D'] is not None else 'unmeasured' for r in rows)) if mode == 'graph' else None,
                'producer_first_reported_error_counts': dict(errors)}
    return {'contract': 'v058-multiperspective-reanalysis-r1', 'independent_receipt': receipt,
            'groups': groups, 'discordant_pairs': [x for x in s['pairs'] if x['outcome'] in ('first_only', 'second_only')],
            'rows': raw_rows,
            'limits': ['Stored artifact consistency is not external execution attestation.',
                       'Same-seed repetitions are not independent problems.',
                       'Error counts are the producer first-reported violations, not exhaustive fault counts.',
                       'Order changes include period and history; cache causality is not identified.',
                       'Choice implied_depth is not generated graph D.'],
            'new_model_inference': False}


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('bundle', type=Path)
    ap.add_argument('--out', required=True, type=Path)
    a = ap.parse_args()
    result = analyze(a.bundle)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with a.out.open('x', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'output': str(a.out.resolve()), 'groups': result['groups'],
                      'compared_fields': result['independent_receipt']['compared_fields']}, ensure_ascii=False, indent=2))
