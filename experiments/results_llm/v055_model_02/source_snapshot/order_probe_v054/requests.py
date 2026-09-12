"""생성 전에 경로를 선택하지 않는다. 사용자 입력의 rules 배열 순서만 바꾼다."""
from depth_probe_v053.requests import request_bytes as old_request
from adm_diagnostic_v052.requests import encode
from .contracts import strict_json, unb64, require
from .design import problem_for

def request_bytes(plan, slot, parents=None):
    previous = strict_json(unb64(plan['reference']['plan_b64']))
    old_slot = {**slot, 'arm': 'original'}
    raw = old_request(previous, old_slot)
    if slot['arm'] == 'original':
        return raw
    require(slot['arm'] == 'swapped', '알 수 없는 규칙 순서 조건')
    request = strict_json(raw)
    require(len(request['messages']) == 2 and request['messages'][1]['role'] == 'user', '기준선 메시지 형식')
    original = request['messages'][1]['content']
    require(original.startswith('problem: '), '기준선 문제 접두사 변경')
    before = strict_json(original[len('problem: '):]); after = problem_for(slot)
    require({k:v for k,v in before.items() if k != 'rules'} == {k:v for k,v in after.items() if k != 'rules'}, '규칙 밖 입력 변경')
    require(sorted(before['rules'], key=lambda r:r['id']) == sorted(after['rules'], key=lambda r:r['id']), '규칙 내용 변경')
    request['messages'][1]['content'] = 'problem: ' + encode(after).decode('utf-8')
    return encode(request)
