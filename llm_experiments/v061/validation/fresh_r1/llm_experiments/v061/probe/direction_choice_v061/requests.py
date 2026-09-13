"""Fix one rule array and change only the frozen depth directive."""
import json
from copy import deepcopy
from .contracts import require, strict_json, unb64
from .design import RULE_ORDERS, SOURCE_RULE_ORDER
from selection_probe_v057.requests import CHOICE_SCHEMA


def schema_for(slot):
    require(slot['mode'] == 'choice', 'Choice-only experiment')
    return deepcopy(CHOICE_SCHEMA)


SHALLOW_DIRECTIVE = '허용된 유효한 증명 중 최종 지지 깊이가 가장 작은 경로를 선택한다.'
DEEP_DIRECTIVE = '허용된 유효한 증명 중 최종 지지 깊이가 가장 큰 경로를 선택한다.'


def transform(raw, variant):
    require(variant in RULE_ORDERS, 'Unknown direction')
    q = strict_json(raw)
    messages = q['messages']
    require(len(messages) == 1 and set(messages[0]) == {'role', 'content'}
            and messages[0]['role'] == 'user', 'One merged user message required')
    text = messages[0]['content']
    require(text.count('\n\nproblem: ') == 1, 'Problem boundary')
    prefix, problem_text = text.rsplit('\n\nproblem: ', 1)
    problem = strict_json(problem_text.encode('utf-8'))
    require(problem['id'] == 'K01' and [r['id'] for r in problem['rules']] == SOURCE_RULE_ORDER, 'Source rule order')
    require(text.count(SHALLOW_DIRECTIVE) == 1
            and DEEP_DIRECTIVE not in text,
            'Unique shallow directive required')
    # Historical request is compact JSON. Verify both exact byte spans before
    # replacement, so instructions/options are never reserialized.
    encode = lambda obj: json.dumps(obj, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    old_rules = encode(problem['rules'])
    by_id = {r['id']: r for r in problem['rules']}
    new_rules = encode([by_id[rid] for rid in RULE_ORDERS[variant]])
    old_span = encode(old_rules)[1:-1].encode('utf-8')
    new_span = encode(new_rules)[1:-1].encode('utf-8')
    require(raw.count(old_span) == 1, 'Unique compact rules byte span required')
    output = raw.replace(old_span, new_span, 1)
    shallow_span = SHALLOW_DIRECTIVE.encode('utf-8')
    deep_span = DEEP_DIRECTIVE.encode('utf-8')
    require(output.count(shallow_span) == 1
            and output.count(deep_span) == 0,
            'Unique directive byte span required')
    if variant == 'deep':
        output = output.replace(shallow_span, deep_span, 1)
    got = strict_json(output)
    expected = deepcopy(q)
    require(problem_text.count(old_rules) == 1, 'Unique problem rule span')
    expected_text = prefix + '\n\nproblem: ' + problem_text.replace(
        old_rules, new_rules, 1)
    if variant == 'deep':
        expected_text = expected_text.replace(
            SHALLOW_DIRECTIVE, DEEP_DIRECTIVE, 1)
    expected['messages'][0]['content'] = expected_text
    require(got == expected, 'Unintended request change')
    return output


def request_bytes(plan, slot):
    raw = unb64(plan['reference']['request_bank'][slot['reference_slot_id']])
    q = strict_json(raw)
    require(q['model'] == plan['identities']['candidate']['model'] and q['options']['seed'] == slot['seed'], 'Model/seed mismatch')
    return transform(raw, slot['variant'])
