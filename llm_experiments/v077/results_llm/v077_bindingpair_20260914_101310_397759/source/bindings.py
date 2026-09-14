"""모델이 직접 작성한 대응표의 오프라인 감사. 실행기/요청 생성에서는 사용하지 않는다."""
from collections import Counter
import stages


def shape(obj):
    if not isinstance(obj, dict) or set(obj) != {'bindings', 'node'}:
        return False
    if not stages.node_valid(obj['node']):
        return False
    entries = obj['bindings']
    return (isinstance(entries, list) and len(entries) <= 16
            and all(isinstance(e, dict) and set(e) == {'premise', 'parent_id'}
                    and stages.text(e['premise']) and stages.text(e['parent_id']) for e in entries))


def node_payload(obj):
    """node 필드의 고정 투영. 대응표로 부모를 생성·수정·정렬하지 않는다."""
    return {'node': obj['node']}


def audit(problem, slots, payloads, ready_ids, table_ready_ids=None):
    if table_ready_ids is None:
        table_ready_ids = ready_ids
    emitted = []
    available = True
    checks = []
    rules = {r['id']: r for r in problem['rules']}
    for slot in slots:
        sid, stage = slot['id'], slot['stage']
        if sid not in ready_ids:
            available = False
        if stage == 'rule':
            if not available or sid not in table_ready_ids:
                checks.append({'id': sid, 'valid': None, 'error_codes': None})
                if available:
                    emitted.append(payloads[sid]['node'])
                continue
            obj = payloads[sid]
            entries = obj['bindings']
            rule = rules[slot['requested_rule_id']]
            errors = []
            if Counter(e['premise'] for e in entries) != Counter(rule['premises']):
                errors.append('binding_premise_multiset')
            if Counter(e['parent_id'] for e in entries) != Counter(obj['node']['parents']):
                errors.append('binding_node_parents_disagree')
            for entry in entries:
                candidates = [n for n in emitted if n['id'] == entry['parent_id']]
                if not candidates:
                    errors.append('binding_missing_parent')
                elif len(candidates) != 1:
                    errors.append('binding_ambiguous_parent')
                elif candidates[0]['atom'] != entry['premise']:
                    errors.append('binding_atom_mismatch')
            checks.append({'id': sid, 'valid': not errors, 'error_codes': sorted(set(errors))})
        if available and stage == 'facts':
            emitted.extend(payloads[sid]['nodes'])
        elif available and stage == 'rule':
            emitted.append(payloads[sid]['node'])
    return checks
