"""Build a common minimal-DAG request without importing scoring code."""
from copy import deepcopy
import json

from .contracts import require, strict_json, unb64, wire
from .design import RULE_ORDER, SOURCE_RULE_ORDER, TARGET_RULES

NODE_SCHEMA = {
    'type': 'object',
    'properties': {
        'id': {'type': 'string', 'minLength': 1, 'maxLength': 128},
        'atom': {'type': 'string', 'minLength': 1, 'maxLength': 128},
        'rule_id': {'anyOf': [
            {'type': 'string', 'minLength': 1, 'maxLength': 128},
            {'type': 'null'},
        ]},
        'parents': {
            'type': 'array', 'minItems': 0, 'maxItems': 8,
            'items': {'type': 'string', 'minLength': 1, 'maxLength': 128},
        },
    },
    'required': ['id', 'atom', 'rule_id', 'parents'],
    'additionalProperties': False,
}
GRAPH_SCHEMA = {
    'type': 'object',
    'properties': {
        'nodes': {'type': 'array', 'minItems': 1, 'maxItems': 16, 'items': NODE_SCHEMA},
        'final_node_id': {'type': 'string', 'minLength': 1, 'maxLength': 128},
    },
    'required': ['nodes', 'final_node_id'],
    'additionalProperties': False,
}


def _compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def schema_for(slot):
    require(slot['mode'] == 'graph' and slot['task'] == 'conditional_construction',
            'Conditional graph task required')
    return deepcopy(GRAPH_SCHEMA)


def prompt_for(target_rule_id):
    require(target_rule_id in TARGET_RULES.values(), 'Unknown target rule')
    return (
        'facts와 rules만 사용하여 goal을 지지하는 비순환 증명 DAG 하나를 작성한다.\n'
        f'final_node_id가 가리키는 goal 노드에는 지정된 마지막 규칙 id {target_rule_id}를 사용한다.\n'
        '각 node는 id, atom, rule_id, parents를 모두 쓴다. 초기 사실 node는 rule_id=null, parents=[]이다.\n'
        '규칙 적용 node는 입력 rules에 등록된 rule_id와 그 규칙의 모든 전제 node id를 parents에 쓴다.\n'
        '모든 node는 최종 node 자신이거나 그 조상이어야 한다. 설명, 후보 목록, 깊이 숫자는 출력하지 않는다.\n'
        'JSON 객체 하나만 출력한다. 출력 형식(JSON Schema):\n'
        + _compact(GRAPH_SCHEMA)
    )


def transform(raw, target_rule_id):
    """Replace merged prompt/schema and reorder the embedded K01 rules."""
    q = strict_json(raw)
    messages = q.get('messages')
    require(isinstance(messages, list) and len(messages) == 1
            and set(messages[0]) == {'role', 'content'} and messages[0]['role'] == 'user',
            'One merged user message required')
    content = messages[0]['content']
    require(isinstance(content, str) and content.count('\n\nproblem: ') == 1,
            'Problem boundary')
    problem = strict_json(content.rsplit('\n\nproblem: ', 1)[1].encode('utf-8'))
    require(problem.get('id') == 'K01'
            and [rule.get('id') for rule in problem.get('rules', [])] == SOURCE_RULE_ORDER,
            'Expected v058 K01 original rule order')
    by_id = {rule['id']: rule for rule in problem['rules']}
    require(set(by_id) == set(RULE_ORDER), 'K01 rule IDs changed')
    problem['rules'] = [by_id[rule_id] for rule_id in RULE_ORDER]
    q['messages'] = [{'role': 'user', 'content': prompt_for(target_rule_id)
                      + '\n\nproblem: ' + _compact(problem)}]
    q['format'] = deepcopy(GRAPH_SCHEMA)
    return wire(q)


def request_bytes(plan, slot):
    require(slot['variant'] in TARGET_RULES
            and slot['target_rule_id'] == TARGET_RULES[slot['variant']],
            'Frozen target rule mismatch')
    raw = unb64(plan['reference']['request_bank'][slot['reference_slot_id']])
    q = strict_json(raw)
    require(q['model'] == plan['identities']['candidate']['model']
            and q['options']['seed'] == slot['seed'], 'Model/seed mismatch')
    return transform(raw, slot['target_rule_id'])
