"""실행용 요청 변환. 정답 계산, 답 후보 나열, 실패 응답 보정 없음."""
from copy import deepcopy
from .contracts import strict_json,unb64,require
from adm_diagnostic_v052.requests import encode
from order_probe_v054.schema import schema_for as graph_schema
CHOICE_SCHEMA={'type':'object','properties':{'final_rule_id':{'type':'string','minLength':1,'maxLength':128}},'required':['final_rule_id'],'additionalProperties':False}
CHOICE_INSTRUCTION=(
 'facts와 rules만 사용하여 goal을 지지하는 비순환 증명 경로 하나를 선택한다.\n'
 '이번에는 전체 증명 DAG를 작성하지 않는다. 선택한 경로에서 goal을 직접 도출하는 마지막 규칙의 id 하나만 출력한다.\n'
 'final_rule_id에는 입력 rules에 등록된 실제 규칙 id를 쓴다. 원자 이름이나 새 노드 id를 쓰지 않는다.\n'
 '선택한 마지막 규칙의 모든 전제는 facts에서 rules를 통해 도출 가능해야 한다.\n'
 '후보 목록, 증명 노드, 설명, 깊이 숫자는 출력하지 않는다.'
)

def schema_for(slot):
    require(slot['mode'] in ('graph','choice'),'미등록 출력 과제')
    return deepcopy(CHOICE_SCHEMA) if slot['mode']=='choice' else graph_schema(slot)

def request_bytes(plan,slot):
    raw=unb64(plan['reference']['request_bank'][slot['reference_slot_id']]);q=strict_json(raw)
    require(q['model']==plan['identities'][slot['model_key']]['model'],'요청 모델 불일치')
    require(q['options']['seed']==slot['seed'],'요청 seed 불일치')
    require(slot['mode'] in ('graph','choice'),'미등록 출력 과제')
    messages=q['messages'];require(len(messages)==1 and set(messages[0])=={'role','content'} and messages[0]['role']=='user','기준선 merged 사용자 메시지 하나 필요')
    if slot['mode']=='graph':return raw
    text=messages[0]['content'];require(isinstance(text,str) and text.count('\n\nproblem: ')==1,'기준선 문제 경계')
    old_system,user=text.rsplit('\n\nproblem: ',1)
    # 기존 경로 지시를 토씨 그대로 옮긴다. 중립에는 방향 지시를 새로 넣지 않는다.
    marker='\nJSON 객체 하나만 출력한다. 출력 형식(JSON Schema):\n'
    require(old_system.count(marker)==1,'원래 출력 계약 경계')
    prefix=old_system.split(marker,1)[0]
    direction=''
    if slot['direction']!='neutral':
        require(prefix.count('\n경로 지시:\n')==1,'경로 지시 누락/중복')
        direction='\n경로 지시:\n'+prefix.split('\n경로 지시:\n',1)[1]
    else:require('\n경로 지시:\n' not in prefix,'중립에 방향 지시')
    q['messages']=[{'role':'user','content':CHOICE_INSTRUCTION+direction+marker+encode(CHOICE_SCHEMA).decode()+'\n\nproblem: '+user}]
    q['format']=deepcopy(CHOICE_SCHEMA)
    return encode(q)
