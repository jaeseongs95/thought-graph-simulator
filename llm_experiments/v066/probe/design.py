"""36-call bounded system comparison. Request creation never calls plan/graph scorers."""
from copy import deepcopy
from pathlib import Path
import common,previous,measure
CONTRACT='v066-plan-r1'
DIRECTIONS={'shallow':'허용된 유효한 증명 중 최종 지지 깊이가 가장 작은 경로를 선택한다.','deep':'허용된 유효한 증명 중 최종 지지 깊이가 가장 큰 경로를 선택한다.'}
PLAN_SCHEMA={'type':'object','properties':{'rule_ids':{'type':'array','items':{'type':'string','minLength':1,'maxLength':128},'minItems':1,'maxItems':16}},'required':['rule_ids'],'additionalProperties':False}
PLAN_HEADER='facts와 rules만 사용하여 goal을 지지하는 증명 경로 하나를 계획한다.\n전체 노드와 부모 ID를 쓰지 말고, 사용할 규칙 ID를 적용 순서대로 rule_ids에 한 번씩 나열한다.\n각 규칙의 전제는 초기 facts 또는 그 앞에서 선택한 규칙의 결론으로 얻어져야 한다.\n마지막 규칙이 goal을 도출해야 한다. 최종 goal에 필요 없는 다른 경로의 규칙은 포함하지 않는다.\n입력에 등록된 실제 규칙 ID를 사용하고 새 규칙을 만들지 않는다.'
CONSTRUCT_HEADER='아래 route_plan_response는 앞선 모델 호출의 원응답이다. 그 응답의 rule_ids와 규칙 적용 순서를 그대로 사용하여 전체 증명 DAG를 작성한다.\n규칙 계획을 추가·삭제·치환·재정렬하거나 다른 경로로 다시 선택하지 않는다. 계획이 틀려도 정답 경로로 고쳐 쓰지 않는다.\n각 노드 ID, 초기 사실 노드 및 부모 연결은 직접 작성하되 원래 증명 규칙과 출력 계약을 지킨다.'

def _slots(spec):
    slots=[];last=None;last_condition=None
    for pi,p in enumerate(spec['problems']):
        for si,seed in enumerate(spec['seeds']):
            block=pi*len(spec['seeds'])+si
            ds=['shallow','deep'] if si==0 else ['deep','shallow']
            for di,d in enumerate(ds):
                arms=['direct','staged'] if (block+di)%2==0 else ['staged','direct']
                for arm in arms:
                    parent=None
                    for stage in (['direct'] if arm=='direct' else ['plan','construct']):
                        sid=f'b{block:02d}_p{pi}_{d}_{stage}'
                        slots.append({'id':sid,'problem_id':p['id'],'seed':seed,'seed_index':si,'block':block,'period':len([s for s in slots if s['block']==block]),'direction':d,'arm':arm,'stage':stage,'parent_plan_id':parent if stage=='construct' else None,'previous_call_id':last,'previous_condition':last_condition})
                        if stage=='plan':parent=sid
                        last=sid;last_condition=d
    if len(slots)!=36:raise ValueError('36 slots required')
    return slots

def _actions(slots,blocks):
    actions=[]
    for b in range(blocks):
        ss=[s for s in slots if s['block']==b]
        if len(ss)!=6:raise ValueError('six calls in block')
        actions.append({'kind':'metadata','id':f'b{b:02d}_before'});actions += [{'kind':'call','id':s['id']} for s in ss];actions.append({'kind':'metadata','id':f'b{b:02d}_after'})
    return actions

def build_plan(baseline_path,run_name,provenance='live'):
    if provenance not in ('live','synthetic'):raise ValueError('provenance')
    spec=common.spec()
    if spec['contract']!='v066-direct-vs-staged-D-r1':raise ValueError('protocol')
    raw=Path(baseline_path).read_bytes();_,old,req,_=previous.inspect_prior(raw)
    for problem in spec['problems']:
        if measure.depth_ranges(problem)!=spec['depth_ranges'][problem['id']]:raise ValueError('problem depths')
    slots=_slots(spec)
    p={'contract':CONTRACT,'run_name':common.check_run_name(run_name),'provenance':provenance,'protocol':deepcopy(spec),'protocol_sha256':common.sha((common.ROOT/'data/protocol.json').read_bytes()),'source_hashes':common.source_hashes(),'baseline_sha256':common.sha(raw),'baseline_request':req,'identity':deepcopy(old['identity']),'slots':slots,'actions':_actions(slots,6)}
    p['plan_sha256']=common.sha(common.wire(p));return p

def transfer(raw,parent_id):
    # 단지 응답 문자열을 운반한다. rule_ids는 여기서 파싱하거나 정답 검사하지 않는다.
    try:
        env=common.load(raw);msg=env.get('message');content=msg.get('content') if isinstance(msg,dict) else None
        if not isinstance(content,str):content=None
    except (ValueError,UnicodeError,AttributeError):content=None
    return {'source_slot_id':parent_id,'response_sha256':common.sha(raw),'content':content}

def request_for(plan,slot,parent_raw=None):
    body=deepcopy(plan['baseline_request']);text=body['messages'][0]['content'];marker='\n\nproblem: '
    if len(body['messages'])!=1 or body['messages'][0]['role']!='user' or text.count(marker)!=1:raise ValueError('baseline message')
    prefix,_=text.rsplit(marker,1)
    if prefix.count(DIRECTIONS['shallow'])!=1:raise ValueError('direction anchor')
    prefix=prefix.replace(DIRECTIONS['shallow'],DIRECTIONS[slot['direction']]);problem=next(p for p in plan['protocol']['problems'] if p['id']==slot['problem_id'])
    if slot['stage']=='plan':
        body['format']=deepcopy(PLAN_SCHEMA)
        prefix=PLAN_HEADER+'\n경로 지시:\n'+DIRECTIONS[slot['direction']]+'\nJSON 객체 하나만 출력한다. 출력 형식(JSON Schema):\n'+common.wire(PLAN_SCHEMA).decode('utf-8')
    elif slot['stage'] not in ('direct','construct'):raise ValueError('stage')
    body['messages'][0]['content']=prefix+marker+common.wire(problem).decode('utf-8')
    if slot['stage']=='construct':
        if not isinstance(parent_raw,bytes) or not slot['parent_plan_id']:raise ValueError('actual planner raw required')
        body['messages'][0]['content']+='\n\n'+CONSTRUCT_HEADER+'\nroute_plan_response: '+common.wire(transfer(parent_raw,slot['parent_plan_id'])).decode('utf-8')
    elif parent_raw is not None:raise ValueError('unexpected parent')
    body['options']['seed']=slot['seed']
    if len(common.wire(body))>plan['protocol']['request_utf8_byte_limit']:raise ValueError('request byte limit')
    return body
