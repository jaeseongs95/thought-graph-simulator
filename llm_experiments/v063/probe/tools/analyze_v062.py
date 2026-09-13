"""v062 원자료의 실패 위치를 분석한다. 재채점·풀이 보정·새 모델 호출은 하지 않는다."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parents[1] / 'v062' / 'probe' / 'tools'))
from verify_v062 import verify, unpack, independent_measure, schema_valid, call_status
from independent_graph_forensic import load, canonical, sha


def node_diagnostics(problem, payload, target):
    """Locate errors without deleting nodes or assigning a repaired proof score."""
    empty = {'final_rule_label_matches_target': None, 'final_atom_matches_goal': None,
             'node_diagnostics': None, 'final_ancestor_ids': None,
             'outside_final_ancestry_ids': None, 'has_nodes_outside_final_ancestry': None, 'error_nodes_inside': None,
             'error_nodes_outside': None, 'errors_only_outside_final_ancestry': None}
    if not schema_valid(payload):
        return empty
    counts = Counter(node['id'] for node in payload['nodes'])
    nodes = {node['id']: node for node in payload['nodes']}
    rules = {rule['id']: rule for rule in problem['rules']}
    unique = all(count == 1 for count in counts.values())
    final = nodes.get(payload['final_node_id']) if unique else None
    ancestors = set()
    if final is not None:
        todo = [payload['final_node_id']]
        while todo:
            key = todo.pop()
            if key in ancestors or key not in nodes:
                continue
            ancestors.add(key)
            todo.extend(nodes[key]['parents'])
    details = []
    for index, node in enumerate(payload['nodes']):
        errors = []
        parents = node['parents']
        if counts[node['id']] != 1:
            errors.append('duplicate_id')
        if final is not None and node['id'] == payload['final_node_id'] and node['atom'] != problem['goal']:
            errors.append('final_goal_mismatch')
        if len(parents) != len(set(parents)):
            errors.append('duplicate_parent')
        if any(parent not in nodes for parent in parents):
            errors.append('missing_parent')
        if node['rule_id'] is None:
            if parents:
                errors.append('fact_with_parents')
            if node['atom'] not in problem['facts']:
                errors.append('unreachable_fact')
        elif node['rule_id'] not in rules:
            errors.append('unregistered_rule')
        else:
            rule = rules[node['rule_id']]
            if node['atom'] != rule['conclusion']:
                errors.append('wrong_atom')
            if unique and all(parent in nodes for parent in parents):
                if Counter(nodes[parent]['atom'] for parent in parents) != Counter(rule['premises']):
                    errors.append('premise_counter_mismatch')
        if unique:
            visited, todo = set(), list(parents)
            while todo:
                key = todo.pop()
                if key == node['id']:
                    errors.append('cycle_member')
                    break
                if key not in nodes or key in visited:
                    continue
                visited.add(key)
                todo.extend(nodes[key]['parents'])
        details.append({'index': index, 'id': node['id'], 'atom': node['atom'],
                        'rule_id': node['rule_id'], 'parents': list(parents),
                        'errors': sorted(set(errors)),
                        'in_final_ancestry': node['id'] in ancestors if final else None})
    inside = sum(bool(node['errors']) for node in details if node['in_final_ancestry'] is True)
    outside = sum(bool(node['errors']) for node in details if node['in_final_ancestry'] is False)
    return {
        'final_rule_label_matches_target': final['rule_id'] == target if final else None,
        'final_atom_matches_goal': final['atom'] == problem['goal'] if final else None,
        'node_diagnostics': details,
        'final_ancestor_ids': sorted(ancestors) if final else None,
        'outside_final_ancestry_ids': sorted(set(nodes) - ancestors) if final else None,
        'has_nodes_outside_final_ancestry': bool(set(nodes) - ancestors) if final else None,
        'error_nodes_inside': inside if final else None,
        'error_nodes_outside': outside if final else None,
        'errors_only_outside_final_ancestry': inside == 0 and outside > 0 if final else None,
    }


def summarize(rows, seeds, complete):
    lookup = {(row['seed'], row['variant'], row['repeat']): row for row in rows}
    if len(lookup) != len(rows):
        raise ValueError('Duplicate seed/variant/repeat')
    variants = ('target_k03', 'target_k17')
    def group(cells):
        seen = [row for row in cells if row['observed']]
        measured = [row for row in seen if row['official_measurement']['proof_valid'] is not None]
        def count(key):
            return sum(row['official_measurement'][key] is True for row in seen)
        return {'assigned': len(cells), 'observed': len(seen),
                'semantic_measured': len(measured), 'format_valid': count('format_valid'),
                'proof_valid': count('proof_valid'), 'strict_valid': count('strict_valid'),
                'instruction_fulfilled': count('instruction_fulfilled'),
                'instruction_rate': count('instruction_fulfilled') / len(cells)
                    if complete and cells and len(measured) == len(cells) else None,
                'final_rule_label_matches_target': sum(
                    row['diagnostics']['final_rule_label_matches_target'] is True for row in seen),
                'final_atom_matches_goal': sum(
                    row['diagnostics']['final_atom_matches_goal'] is True for row in seen),
                'has_nodes_outside_final_ancestry': sum(
                    row['diagnostics']['has_nodes_outside_final_ancestry'] is True for row in seen),
                'errors_only_outside_final_ancestry': sum(
                    row['diagnostics']['errors_only_outside_final_ancestry'] is True for row in seen),
                'selected_rule_ids': dict(Counter(row['official_measurement']['selected_rule_id']
                                                  or 'unmeasured' for row in seen)),
                'call_error_counts': dict(Counter(error for row in seen
                                                   for error in row['official_measurement']['errors'])),
                'actual_depths': dict(Counter(str(row['official_measurement']['actual_D'])
                    if row['official_measurement']['actual_D'] is not None else 'unmeasured'
                    for row in seen))}
    seed_rows = []
    for seed in seeds:
        cells = [lookup.get((seed, variant, repeat)) for variant in variants for repeat in (0, 1)]
        ids = [row['official_measurement']['selected_rule_id']
               if row and row['observed'] else None for row in cells]
        seed_rows.append({'seed': seed, 'ids_A0_A1_B0_B1': ids,
                         'label_repeat_stable': ids[0] == ids[1] and ids[2] == ids[3]
                             if all(key is not None for key in ids) else None})
    strata = {}
    for axis in ('sequence', 'period', 'previous_variant', 'repeat_distance', 'prompt_eval_cached_count'):
        strata[axis] = {}
        for value in sorted({str(row.get(axis)) for row in rows}):
            strata[axis][value] = {variant: group([row for row in rows
                if str(row.get(axis)) == value and row['variant'] == variant]) for variant in variants
                if any(str(row.get(axis)) == value and row['variant'] == variant for row in rows)}
    return {'groups': {variant: group([row for row in rows if row['variant'] == variant])
                       for variant in variants}, 'seed_rows': seed_rows, 'strata': strata}


def analyze(bundle):
    if bundle.stat().st_size > 100 * 1024**2:
        raise ValueError('Evidence archive too large')
    raw = bundle.read_bytes()
    receipt = verify(bundle)
    if sha(bundle.read_bytes()) != sha(raw):
        raise ValueError('Evidence changed during verification')
    data, _ = unpack(raw)
    plan = load(data['external_plan/v062.plan.json'])
    stored = load(data['run/summary.json'])
    events = [load(line) for line in data['run/events.jsonl'].splitlines()]
    call_events = {event['action']['id']: event for event in events if event['action']['kind'] == 'call'}
    rows = []
    for slot in plan['slots']:
        row = {key: slot[key] for key in ('id', 'seed', 'variant', 'repeat', 'sequence', 'period',
                                          'previous_variant', 'repeat_distance', 'target_rule_id')}
        event = call_events.get(slot['id'])
        if event is None:
            rows.append({**row, 'observed': False, 'official_measurement': None, 'diagnostics': None})
            continue
        prefix = 'run/calls/' + slot['id'] + '/'
        request = load(data[prefix + 'request.wire.json'])
        response = data[prefix + 'response.raw.json']
        problem = load(request['messages'][0]['content'].rsplit('\n\nproblem: ', 1)[1].encode('utf-8'))
        _, category, payload = call_status(response, request['model'], event['http_status'], event['transport_error'])
        measured = independent_measure(problem, payload, slot)
        try:
            envelope = load(response)
            cached = envelope.get('prompt_eval_cached_count') if isinstance(envelope, dict) else None
        except (ValueError, UnicodeError):
            cached = None
        if type(cached) is not int or cached < 0:
            cached = None
        rows.append({**row, 'observed': True, 'official_measurement': measured,
                     'diagnostics': node_diagnostics(problem, payload, slot['target_rule_id']),
                     'raw_parse_category': category, 'payload': payload,
                     'request_sha256': sha(data[prefix + 'request.wire.json']),
                     'response_sha256': sha(response), 'prompt_eval_cached_count': cached})
    return {'contract': 'v062-failure-forensics-r1', 'bundle_sha256': sha(raw),
            'independent_receipt': receipt, 'plan_sha256': plan['plan_sha256'],
            'source_evidence_kind': stored['evidence_kind'],
            'source_recorded_new_model_inference': stored['new_model_inference'],
            'event_tip': stored['event_tip'], 'model': plan['identities']['candidate']['model'],
            'model_digest': plan['identities']['candidate']['digest'],
            'official_admission_gate_passed': stored['admission_gate_passed'],
            'official_admission_gate': stored['admission_gate'],
            **summarize(rows, plan['seeds'], receipt['complete']), 'rows': rows,
            'independent_problem_count': 1, 'new_model_inference': False,
            'posthoc_diagnostics': True, 'repaired_scores_generated': False,
            'legacy_parse_error_text_is_not_trusted': True,
            'limits': ['Node error locations are post-hoc diagnostics, not repaired proof scores.',
                       'A matching final-rule label does not imply a valid target proof.',
                       'Raw-derived parse category replaces unverified legacy diagnostic text in this report.',
                       'One problem and repeated seeds do not support model-wide or internal causal claims.']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    result = analyze(args.bundle)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({key: result[key] for key in ('independent_receipt', 'groups',
                     'official_admission_gate_passed')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
