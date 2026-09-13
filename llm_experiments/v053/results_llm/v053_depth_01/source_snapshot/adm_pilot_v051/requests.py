"""입력 문제와 역할 지시만 전송. 정답표·생성기·채점기 import 없음."""
from __future__ import annotations
from .contracts import OUTPUT_SCHEMA, strict_json, unb64, wire
from .design import role_for

COMMON = '''고정 문제의 facts와 rules만 사용하여 goal의 지지 증명 DAG를 작성한다.
외부 지식, 없는 규칙, 새로운 초기 사실을 추가하지 않는다. 도출 가능하다는 것과 초기 facts에 있다는 것은 다르다.
nodes는 위상 순서이며 id, atom, rule, parents를 가진다. 초기 사실 노드는 rule=null, parents=[]이다.
규칙 노드는 실제 rule id와 모든 전제 노드 id를 parents에 쓴다. final은 실제 목표 노드의 id다.
모든 노드는 final의 지지 조상이어야 한다. 불필요한 노드나 순환을 추가하지 않는다.
views는 모든 node id를 키로 갖는다. instance 표현은 kind와 실제 atom을 쓴다.
universal_schema 표현은 quantifier=forall_boolean_valuations, binding, assumptions, conclusion을 쓴다.
binding은 해당 노드의 지지 조상에 사용된 원자 전체에 대한 변수→원자의 일대일 치환이다.
assumptions는 실제 사용된 초기 사실(if=[], then=변수)과 규칙(if=전제 변수 목록, then=결론 변수)만이다.
가정 전체가 참이면 결론이 참이라는 함의가 모든 bool 배정에 대해 성립해야 한다. 목표를 임의의 가정으로 넣지 않는다.
reviews의 argument 검토는 target=final, check=support_replay, evidence=해당 지지 노드 id 목록이며,
finding에 grounded, used_rules, conclusion을 실제로 검토해 적는다.
acceptance_criterion 검토는 target=valid_proof_and_goal, check=counterexample_probe이다.
probe는 goal을 atom으로 가진 rule=null, parents=[]의 단독 주장이다. 이는 위에서 만든 증명과 별개인 시험 주장이다.
finding.answer_only_accepts는 이 시험 주장의 atom이 goal과 같은지,
proof_and_goal_accepts는 그 일치와 이 단독 주장이 실제 초기 facts에 속하는지를 모두 만족하는지,
gap_detected는 앞 기준은 수락하지만 뒤 기준은 거부하는지를 나타낸다.
모든 값은 직접 작성한다. 요청 역할명을 결과에 붙이거나 A/D/M 자기평가 숫자를 출력하지 않는다.
JSON 객체 하나만 출력한다. 아래 schema는 형식이며 실제 정답과 원하는 경로를 미리 지정하지 않는다.
'''
A = {
    'instance': '각 노드의 views는 구체 instance 표현으로 작성한다.',
    'schema': '각 노드의 views는 보편 universal_schema 표현으로 작성한다.',
}
D = {
    'shallow': '허용된 유효한 증명 중 최종 지지 깊이가 가장 작은 경로를 선택한다.',
    'deep': '허용된 비순환 유효한 증명 중 최종 지지 깊이가 가장 큰 경로를 선택한다.',
}
M = {
    0: '증명만 작성하고 reviews는 빈 배열로 둔다.',
    1: '최종 증명을 대상으로 argument/support_replay 검토 하나만 작성한다.',
    2: '평가 기준을 대상으로 acceptance_criterion/counterexample_probe 검토 하나만 작성한다.',
}


def request_bytes(plan, slot, parents=None):
    role = role_for(slot)
    base = strict_json(unb64(plan['baseline']['templates']['00']['request_b64']))
    base['options']['seed'] = slot['seed']
    base['format'] = OUTPUT_SCHEMA
    system = COMMON + '이번 역할 지시:\n' + A[role['A']] + '\n' + D[role['D']] + '\n' + M[role['M']]
    system += '\n공통 출력 JSON Schema:\n' + wire(OUTPUT_SCHEMA).decode('utf-8')
    base['messages'] = [{'role': 'system', 'content': system},
                        {'role': 'user', 'content': 'problem: ' + wire(plan['problem']).decode('utf-8')}]
    return wire(base)
