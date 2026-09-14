"""대응표 검산의 별도 구현. 생산 bindings/stages/measure/report를 가져오지 않는다."""
from audit_graph import _schema_valid


def shape(value):
    if type(value) is not dict or set(value) != {'node', 'bindings'}:
        return False
    if not _schema_valid({'nodes': [value['node']], 'final_node_id': 'check'}):
        return False
    bs = value['bindings']
    if type(bs) is not list or len(bs) > 16:
        return False
    for item in bs:
        if type(item) is not dict or set(item) != {'parent_id', 'premise'}:
            return False
        if any(type(item[k]) is not str or not 1 <= len(item[k]) <= 128 for k in item):
            return False
    return True


def inspect(problem, sequence, objects, statuses, table_statuses=None):
    if table_statuses is None:
        table_statuses = statuses
    result = []
    for position, action in enumerate(sequence):
        if action['stage'] != 'rule':
            continue
        sid = action['id']
        if table_statuses[sid] != 'ok' or any(statuses[a['id']] != 'ok' for a in sequence[:position+1]):
            result.append(dict(id=sid, valid=None, error_codes=None))
            continue
        prefix = []
        for previous in sequence[:position]:
            obj = objects[previous['id']]
            prefix += obj['nodes'] if previous['stage'] == 'facts' else [obj['node']]
        obj = objects[sid]
        bs = obj['bindings']
        wanted = next(r['premises'] for r in problem['rules'] if r['id'] == action['requested_rule_id'])
        failures = set()
        if sorted(b['premise'] for b in bs) != sorted(wanted):
            failures.add('binding_premise_multiset')
        if sorted(b['parent_id'] for b in bs) != sorted(obj['node']['parents']):
            failures.add('binding_node_parents_disagree')
        for b in bs:
            found = tuple(n['atom'] for n in prefix if n['id'] == b['parent_id'])
            if len(found) == 0:
                failures.add('binding_missing_parent')
            elif len(found) > 1:
                failures.add('binding_ambiguous_parent')
            elif found[0] != b['premise']:
                failures.add('binding_atom_mismatch')
        result.append(dict(id=sid, valid=len(failures) == 0, error_codes=sorted(failures)))
    return result
