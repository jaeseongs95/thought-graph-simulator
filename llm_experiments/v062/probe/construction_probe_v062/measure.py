"""Measure an emitted minimal proof DAG from its actual parent edges."""
from collections import Counter

from .contracts import ContractError, validate_payload
from .requests import GRAPH_SCHEMA


def _empty():
    return {
        'kind': 'conditional_proof_dag', 'format_valid': False,
        'proof_valid': None, 'strict_valid': None, 'D': None, 'actual_D': None,
        'selected_rule_id': None, 'selected_rule_position': None, 'terminal_rank': None,
        'goal_reached': None, 'target_rule_match': None,
        'instruction_fulfilled': None, 'node_count': None, 'errors': [],
    }


def _append(errors, code):
    if code not in errors:
        errors.append(code)


def _cycle_nodes(nodes):
    colors, cyclic = {}, set()

    def visit(node_id, trail):
        state = colors.get(node_id, 0)
        if state == 1:
            cyclic.update(trail[trail.index(node_id):])
            return
        if state == 2:
            return
        colors[node_id] = 1
        for parent in nodes[node_id]['parents']:
            if parent in nodes:
                visit(parent, trail + [node_id])
        colors[node_id] = 2

    for node_id in nodes:
        visit(node_id, [])
    return cyclic


def _final_ancestors(nodes, final_node_id):
    seen, todo = set(), [final_node_id]
    while todo:
        node_id = todo.pop()
        if node_id in seen or node_id not in nodes:
            continue
        seen.add(node_id)
        todo.extend(nodes[node_id]['parents'])
    return seen


def _depth(nodes, final_node_id):
    memo = {}

    def visit(node_id):
        if node_id not in memo:
            node = nodes[node_id]
            memo[node_id] = (0 if node['rule_id'] is None else 1 + max(
                (visit(parent) for parent in node['parents']), default=0))
        return memo[node_id]

    return visit(final_node_id)


def measure(problem, payload, slot):
    out = _empty()
    if payload is None:
        return out
    try:
        validate_payload(payload, GRAPH_SCHEMA)
    except ContractError as exc:
        out['errors'] = ['schema_invalid']
        return out
    out['format_valid'] = True
    out['node_count'] = len(payload['nodes'])
    errors = out['errors']
    nodes = {}
    for node in payload['nodes']:
        if node['id'] in nodes:
            _append(errors, 'duplicate_id')
        else:
            nodes[node['id']] = node
    rules = {rule['id']: rule for rule in problem['rules']}
    rule_ids = [rule['id'] for rule in problem['rules']]
    terminal_ids = [rule['id'] for rule in problem['rules']
                    if rule['conclusion'] == problem['goal']]
    final_node = nodes.get(payload['final_node_id'])
    if final_node is None:
        _append(errors, 'missing_final_node')
    else:
        out['selected_rule_id'] = final_node['rule_id']
        if final_node['rule_id'] in rule_ids:
            out['selected_rule_position'] = rule_ids.index(final_node['rule_id'])
        if final_node['rule_id'] in terminal_ids:
            out['terminal_rank'] = terminal_ids.index(final_node['rule_id'])
        if final_node['atom'] != problem['goal']:
            _append(errors, 'final_goal_mismatch')
    for node in nodes.values():
        parents, rule_id = node['parents'], node['rule_id']
        if len(parents) != len(set(parents)):
            _append(errors, 'duplicate_parent')
        if any(parent not in nodes for parent in parents):
            _append(errors, 'missing_parent')
        if rule_id is None:
            if parents:
                _append(errors, 'fact_with_parents')
            if node['atom'] not in problem['facts']:
                _append(errors, 'unreachable_fact')
        else:
            rule = rules.get(rule_id)
            if rule is None:
                _append(errors, 'unregistered_rule')
            else:
                if node['atom'] != rule['conclusion']:
                    _append(errors, 'wrong_atom')
                if all(parent in nodes for parent in parents):
                    if Counter(nodes[parent]['atom'] for parent in parents) != Counter(rule['premises']):
                        _append(errors, 'premise_counter_mismatch')
    if _cycle_nodes(nodes):
        _append(errors, 'cycle')
    out['proof_valid'] = not errors
    out['goal_reached'] = out['proof_valid']
    if out['proof_valid']:
        out['D'] = out['actual_D'] = _depth(nodes, payload['final_node_id'])
        out['strict_valid'] = _final_ancestors(nodes, payload['final_node_id']) == set(nodes)
        if not out['strict_valid']:
            _append(errors, 'extra_unused_node')
    else:
        out['strict_valid'] = False
    out['target_rule_match'] = bool(
        out['proof_valid'] and final_node['rule_id'] == slot['target_rule_id'])
    out['instruction_fulfilled'] = bool(out['strict_valid'] and out['target_rule_match'])
    out['errors'] = sorted(set(out['errors']))
    return out


def match(problem, measurement, slot):
    return measurement['instruction_fulfilled']
