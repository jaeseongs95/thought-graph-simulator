"""요청 작성에 정답 계산기를 사용하지 않는다. 기준선 요청에서 지정 문단만 바꾼다."""
from adm_diagnostic_v052.requests import request_bytes as old_request, GRAPH_COMMON, encode
from adm_pilot_v051.requests import D
from .contracts import strict_json, unb64, require

DEPTH_DEFINITION = '''\n깊이의 계산 정의:
초기 사실 노드 n의 깊이 d(n)는 0이다.
규칙을 적용한 노드 n의 깊이 d(n)는 1 + max(d(p): p는 n의 부모 노드)이다.
증명 전체의 깊이는 선택한 최종 노드의 d(final_node_id)이다.
여러 전제의 깊이를 더하지 않는다. 노드의 출력 순번, 전체 노드 수, 문장 수는 깊이가 아니다.
'''

def request_bytes(plan, slot, parents=None):
    reference = strict_json(unb64(plan['reference']['plan_b64']))
    direction = slot['direction']
    old_slot = {'problem_id': slot['problem_id'], 'seed': slot['seed'], 'arm': 'explicit',
                'task': 'graph_only', 'role_id': 'instance_' + ('shallow' if direction == 'neutral' else direction) + '_M0'}
    raw = old_request(reference, old_slot)
    if slot['arm'] == 'original' and direction != 'neutral':
        return raw
    request = strict_json(raw)
    system = request['messages'][0]['content']
    if direction == 'neutral':
        removal = '\n경로 지시:\n' + D['shallow']
        require(system.count(removal) == 1, '중립 지시 제거 위치 오류')
        system = system.replace(removal, '', 1)
    if slot['arm'] == 'defined':
        require(system.startswith(GRAPH_COMMON), '기준선 공통 지시 변경')
        system = GRAPH_COMMON + DEPTH_DEFINITION + system[len(GRAPH_COMMON):]
    request['messages'][0]['content'] = system
    return encode(request)
