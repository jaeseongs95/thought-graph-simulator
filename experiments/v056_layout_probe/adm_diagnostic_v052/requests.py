"""고정 입력과 지시만 전달한다. 생성 정답·경로를 생산 채점기에서 가져오지 않는다."""
import json
from .contracts import strict_json,unb64
from .design import problem_for,role_for
from .schema import schema_for
from adm_pilot_v051.requests import A,D,M,request_bytes as legacy_request

GRAPH_COMMON='''facts와 rules만 사용하여 goal을 지지하는 증명 DAG 하나를 작성한다.
한 증명만 선택한다. 서로 대안인 두 경로를 모두 나열하면 안 된다. 모든 노드는 선택한 목표 노드의 조상이어야 한다.
nodes는 위상 순서의 id, atom, rule, parents 배열이다. 초기 사실의 rule은 null이고 parents는 []다.
규칙 적용의 rule은 실제 규칙 id이며 parents에는 모든 전제 노드 id를 쓴다.
final_node_id는 선택한 목표 노드의 id이다. 원자 이름(goal 문자열)을 쓰는 필드가 아니다.
최종 노드는 nodes 안에 있어야 한다. 목표 문자열이 같아도 근거 없는 단독 주장은 유효한 증명이 아니다.
'''
FULL_COMMON=GRAPH_COMMON+'''node_views는 각 node_id에 대응하는 representation의 배열이다. 모든 실제 노드를 한 번씩만 표현한다.
instance 표현은 kind=instance와 해당 atom이다.
universal_schema 표현은 quantifier=forall_boolean_valuations, bindings, assumptions, conclusion이다.
bindings는 {variable,atom}의 배열이며 해당 노드의 실제 지지 조상 전체의 원자에 대한 일대일 대응이다.
assumptions의 {if,then}은 실제 사용한 초기 사실(if=[])과 규칙만 변수로 표현한다. 목표를 가정에 추가하지 않는다.
모든 Boolean 변수 배정에서 가정들이 참이면 conclusion이 참이어야 한다.
reviews의 argument 검토는 target에 최종 노드 id, check=support_replay, evidence에 모든 지지 node id를 쓴다.
finding의 grounded, used_rules, conclusion은 실제 제출 증명을 재검토한 판정이다.
acceptance_criterion 검토는 target=valid_proof_and_goal, check=counterexample_probe이다.
probe는 goal을 atom으로 쓰는 rule=null, parents=[]의 단독 주장이고 위에서 만든 증명과 별개의 시험 대상이다.
answer_only_accepts는 probe.atom과 goal의 문자열 일치이다.
proof_and_goal_accepts는 문자열 일치와 이 단독 주장이 실제 초기 facts의 원소임을 모두 요구한다.
gap_detected는 앞 기준은 수락하지만 뒤 기준은 거부하는지이다.
도출 가능성은 초기 facts의 원소 여부와 다르다. 검토 대상 수준과 판정의 진위는 모두 검사된다.
모든 내용을 직접 작성하고 역할명이나 A/D/M 자기평가 점수를 붙이지 않는다.
'''

def encode(value):
    # 속성 삽입 순서: nodes를 선언하고 참조 final_node_id를 뒤에 둔다.
    return json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf-8')

def request_bytes(plan,slot,parents=None):
    if slot['arm']=='legacy':
        old=strict_json(unb64(plan['reference']['plan_b64']))
        return legacy_request(old,slot)
    base=strict_json(unb64(plan['baseline']['templates']['00']['request_b64']))
    base['options']['seed']=slot['seed'];base['format']=schema_for(slot)
    role=role_for(slot);task=slot['task'];problem=problem_for(slot)
    if task=='copy_control':
        system='이 요청은 추론 성능 평가가 아니라 정답을 제공한 JSON 복사 진단이다. reference_record를 값 변경 없이 지정 형식 그대로 복사한다. 새 증명·판정을 만들지 않는다.'
        user='problem: '+encode(problem).decode()+'\nreference_record: '+encode(plan['copy_records'][slot['problem_id']]).decode()
    else:
        system=GRAPH_COMMON if task=='graph_only' else FULL_COMMON
        if task=='graph_only':system+='\n경로 지시:\n'+D[role['D']]
        elif task=='factorial':
            axis_a=('각 노드의 node_views는 구체 instance 표현으로 작성한다.' if role['A']=='instance' else '각 노드의 node_views는 보편 universal_schema 표현으로 작성한다.')
            system+='\n이번 역할 지시:\n'+axis_a+'\n'+D[role['D']]+'\n'+M[role['M']]
        # 중립군에는 특정 A/D/M를 지정하는 문장이 전혀 없다.
        user='problem: '+encode(problem).decode()
    system+='\nJSON 객체 하나만 출력한다. 출력 형식(JSON Schema):\n'+encode(schema_for(slot)).decode()
    base['messages']=[{'role':'system','content':system},{'role':'user','content':user}]
    return encode(base)
