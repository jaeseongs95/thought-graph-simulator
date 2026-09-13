"""공통 JSON/출력 형식. 올바른 증명이나 정답 bool은 형식에 넣지 않는다."""
from __future__ import annotations
from pathlib import Path
from criterion_probe_v050.contracts import (
    ContractError, require, strict_json, wire, canonical, sha, digest, b64, unb64,
    read_json, write_json, utc_now, usage, require_external_plan,
)


def obj(properties):
    return {'type': 'object', 'properties': properties,
            'required': list(properties), 'additionalProperties': False}


def arr(item, maximum=16, minimum=0):
    return {'type': 'array', 'items': item, 'minItems': minimum, 'maxItems': maximum}


STR = {'type': 'string', 'minLength': 1, 'maxLength': 128}
BOOL = {'type': 'boolean'}
NULL = {'type': 'null'}
NODE = obj({'id': STR, 'atom': STR, 'rule': {'anyOf': [STR, NULL]}, 'parents': arr(STR)})
CLAUSE = obj({'if': arr(STR), 'then': STR})
INSTANCE = obj({'kind': {'const': 'instance', 'type': 'string'}, 'atom': STR})
SCHEMA = obj({'kind': {'const': 'universal_schema', 'type': 'string'},
              'quantifier': {'const': 'forall_boolean_valuations', 'type': 'string'},
              'binding': {'type': 'object', 'additionalProperties': STR,
                          'minProperties': 1, 'maxProperties': 10},
              'assumptions': arr(CLAUSE, maximum=32, minimum=1), 'conclusion': STR})
VIEW = {'anyOf': [INSTANCE, SCHEMA]}
M1 = obj({'id': STR, 'target_kind': {'const': 'argument', 'type': 'string'},
          'target': STR, 'check': {'const': 'support_replay', 'type': 'string'},
          'evidence': arr(STR, minimum=1),
          'finding': obj({'grounded': BOOL, 'used_rules': arr(STR), 'conclusion': STR})})
M2 = obj({'id': STR, 'target_kind': {'const': 'acceptance_criterion', 'type': 'string'},
          'target': STR, 'check': {'const': 'counterexample_probe', 'type': 'string'},
          'probe': obj({'atom': STR, 'rule': {'anyOf': [STR, NULL]}, 'parents': arr(STR)}),
          'finding': obj({'answer_only_accepts': BOOL, 'proof_and_goal_accepts': BOOL,
                          'gap_detected': BOOL})})
# 모든 역할에 완전히 같은 형식. 원하는 역할이나 경로를 schema enum으로 강제하지 않는다.
OUTPUT_SCHEMA = obj({'nodes': arr(NODE, maximum=16, minimum=1), 'final': STR,
                     'views': {'type': 'object', 'additionalProperties': VIEW,
                               'minProperties': 1, 'maxProperties': 16},
                     'reviews': arr({'anyOf': [M1, M2]}, maximum=4)})


def validate_payload(value, schema=OUTPUT_SCHEMA, path='$'):
    """이 모듈이 쓰는 JSON Schema 부분집합의 독립 strict 검사."""
    if 'anyOf' in schema:
        errors = []
        for sub in schema['anyOf']:
            try:
                validate_payload(value, sub, path)
                return
            except ContractError as exc:
                errors.append(str(exc))
        raise ContractError(path + ': 허용한 형식 중 어느 것에도 맞지 않음')
    kind = schema['type']
    if kind == 'object':
        require(isinstance(value, dict), path + ': 객체 필요')
        if 'properties' in schema:
            require(set(value) == set(schema['properties']), path + ': 누락/추가 필드')
            for key, spec in schema['properties'].items():
                validate_payload(value[key], spec, path + '.' + key)
        else:
            require(schema['minProperties'] <= len(value) <= schema['maxProperties'], path + ': 속성 수')
            for key, entry in value.items():
                require(isinstance(key, str) and 1 <= len(key) <= 128, path + ': 잘못된 속성 이름')
                validate_payload(entry, schema['additionalProperties'], path + '.' + key)
    elif kind == 'array':
        require(isinstance(value, list) and schema['minItems'] <= len(value) <= schema['maxItems'], path + ': 배열 크기')
        for i, entry in enumerate(value):
            validate_payload(entry, schema['items'], path + f'[{i}]')
    elif kind == 'string':
        require(isinstance(value, str) and schema.get('minLength', 0) <= len(value) <= schema.get('maxLength', 128), path + ': 문자열')
    elif kind == 'boolean':
        require(type(value) is bool, path + ': bool만 허용')
    elif kind == 'null':
        require(value is None, path + ': null만 허용')
    else:
        raise ContractError('지원하지 않는 내부 schema')
    if 'const' in schema:
        require(type(value) is type(schema['const']) and value == schema['const'], path + ': 종류/양화자 오류')


def decode_response(raw, model, stage=None):
    env = strict_json(raw)
    require(isinstance(env, dict) and env.get('model') == model, '응답 모델 불일치')
    require(env.get('done') is True and env.get('done_reason') == 'stop', '정상 stop 종료 아님')
    msg = env.get('message')
    require(isinstance(msg, dict) and msg.get('role') == 'assistant', 'assistant 응답 아님')
    require(not msg.get('images') and not msg.get('tool_calls'), '도구/이미지 응답 금지')
    thinking = msg.get('thinking')
    require(thinking is None or (isinstance(thinking, str) and not thinking.strip()), 'non-thinking 계약 위반')
    content = msg.get('content')
    require(isinstance(content, str) and '<think>' not in content and '</think>' not in content, 'content 계약 위반')
    value = strict_json(content)
    require(isinstance(value, dict), '출력은 JSON 객체여야 함')
    # 전체 schema 실패가 정상인 앞 필드를 지우지 않도록 의미 검사기에서 층별 채점한다.
    return value


def source_fingerprint():
    root = Path(__file__).resolve().parent.parent
    result = {}
    for mod in ('paired_probe_v047', 'paired_probe_v048', 'paired_probe_v049',
                'criterion_probe_v050', 'adm_pilot_v051'):
        for file in sorted((root / mod).glob('*.py')):
            result[mod + '/' + file.name] = sha(file.read_text(encoding='utf-8-sig').replace('\r\n', '\n').replace('\r', '\n').encode())
    return result
