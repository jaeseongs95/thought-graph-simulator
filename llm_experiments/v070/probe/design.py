"""D 지시 × 후보 순서의 동결된 선택 전용 계획. 정답은 채점에서만 사용한다."""
from copy import deepcopy
from pathlib import Path
import common, previous, reference, measure
CONTRACT = 'v070-plan-r1'

def _slots(spec):
    out=[];last=None;lastcond=None
    for pi,problem in enumerate(spec['problems']):
        for si,seed in enumerate(spec['seeds']):
            block=pi*2+si
            # 각 문제/seed 안에 후보 순서 2개와 D 방향 2개를 모두 교차한다.
            combinations=[(0,'shallow'),(0,'deep'),(1,'deep'),(1,'shallow')]
            if si==1:combinations=list(reversed(combinations))
            for period,(order,condition) in enumerate(combinations):
                sid=f'b{block:02d}_o{order}_{condition}'
                out.append({'id':sid,'pair_id':f'b{block:02d}_o{order}','block':block,'period':period,
                    'problem_id':problem['id'],'seed':seed,'seed_index':si,'condition':condition,
                    'candidate_order_index':order,'stage':'select','history_ids':[],
                    'problem_role':'seen_constructor_task' if pi<3 else 'authored_discriminating_control',
                    'previous_call_id':last,'previous_condition':lastcond})
                last=sid;lastcond=condition
    if len(out)!=spec['max_inference_calls'] or len({s['id'] for s in out})!=40:raise ValueError('40 unique slots required')
    return out

def _actions(slots,blocks):
    actions=[]
    for block in range(blocks):
        group=[s for s in slots if s['block']==block]
        if len(group)!=4:raise ValueError('four calls per block required')
        actions.append({'kind':'metadata','id':f'b{block:02d}_before'})
        actions.extend({'kind':'call','id':s['id']} for s in group)
        actions.append({'kind':'metadata','id':f'b{block:02d}_after'})
    return actions

def build_plan(baseline_path,run_name,provenance='live'):
    if provenance not in ('live','synthetic'):raise ValueError('provenance')
    spec=common.spec()
    if spec['contract']!='v070-depth-route-selection-r1':raise ValueError('protocol')
    raw=Path(baseline_path).read_bytes();_,old,request,_=previous.inspect_prior(raw)
    for p in spec['problems']:
        if measure.depth_ranges(p)!=spec['depth_ranges'][p['id']]:raise ValueError('global depth ranges')
        for i,c in enumerate(spec['reference_conditions']):
            if reference.validate(p,spec['reference_plans'][p['id']][c])!=spec['depth_ranges'][p['id']][i]:raise ValueError('invalid candidate')
    slots=_slots(spec)
    plan={'contract':CONTRACT,'run_name':common.check_run_name(run_name),'provenance':provenance,
          'protocol':deepcopy(spec),'protocol_sha256':common.sha((common.ROOT/'data/protocol.json').read_bytes()),
          'source_hashes':common.source_hashes(),'baseline_sha256':common.sha(raw),
          'baseline_request':request,'identity':deepcopy(old['identity']),'slots':slots,'actions':_actions(slots,10)}
    plan['plan_sha256']=common.sha(common.wire(plan));return plan

def request_for(plan,slot,history_raw=None):
    if history_raw or slot['history_ids']:raise ValueError('selector has no cross-call history')
    p=next(p for p in plan['protocol']['problems'] if p['id']==slot['problem_id'])
    spec=plan['protocol'];routes=spec['reference_plans'][p['id']]
    candidates=[routes[spec['reference_conditions'][i]] for i in spec['candidate_orders'][slot['candidate_order_index']]]
    body=deepcopy(plan['baseline_request'])
    if len(body['messages'])!=1 or body['messages'][0]['role']!='user':raise ValueError('baseline messages')
    body['format']={'type':'object','properties':{'rule_ids':{'type':'array','minItems':1,'maxItems':16,'items':{'type':'string','minLength':1,'maxLength':128}}},'required':['rule_ids'],'additionalProperties':False}
    # 역할 이름, 기대 D, 정답 경로 라벨, 블록/seed 정보는 메시지에 넣지 않는다.
    data={'problem':{'facts':p['facts'],'rules':p['rules'],'goal':p['goal']},
          'candidate_rule_ids':candidates,'requested_depth':spec['headers'][slot['condition']]}
    text=spec['headers']['common']+'\nJSON 객체 하나만 출력한다. 출력 형식(JSON Schema):\n'+common.wire(body['format']).decode()
    text+='\n\ninput: '+common.wire(data).decode()
    body['messages'][0]['content']=text;body['options']['seed']=slot['seed']
    if len(common.wire(body))>spec['request_utf8_byte_limit']:raise ValueError('request byte limit')
    return body
