"""지정 참조 규칙의 append-only 실행 계획. 호스트는 내용 채점으로 요청을 고치지 않는다."""
from copy import deepcopy
from pathlib import Path
import common, previous, reference, measure
CONTRACT='v069-plan-r1'

def _slots(spec):
    slots=[]; last=None; lastcond=None
    for pi,problem in enumerate(spec['problems']):
        for si,seed in enumerate(spec['seeds']):
            block=pi*len(spec['seeds'])+si; period=0
            for condition in spec['orders'][block]:
                trial=f'b{block:02d}_p{pi}_{condition}'; route=spec['reference_plans'][problem['id']][condition]
                history=[]
                operations=[('facts',None)]+[('rule',i) for i in range(len(route))]+[('final',None)]
                for oi,(stage,position) in enumerate(operations):
                    sid=trial+'_'+(f'rule_{position:02d}' if stage=='rule' else stage)
                    slots.append({'id':sid,'trial_id':trial,'block':block,'period':period,
                        'problem_id':problem['id'],'seed':seed,'seed_index':si,'condition':condition,
                        'arm':'append_only','stage':stage,'operation_index':oi,'rule_position':position,
                        'requested_rule_id':route[position] if position is not None else None,
                        'history_ids':history[:],'reference_rule_ids':route[:],
                        'reference_origin':'experimenter_verified_reference',
                        'previous_call_id':last,'previous_condition':lastcond})
                    history.append(sid); last=sid; lastcond=condition; period+=1
    if len(slots)!=54 or len({s['id'] for s in slots})!=54:raise ValueError('54 unique calls required')
    return slots

def _actions(slots,blocks):
    actions=[]
    for b in range(blocks):
        group=[s for s in slots if s['block']==b]
        if len(group) not in (8,9,10):raise ValueError('unexpected block size')
        actions += [{'kind':'metadata','id':f'b{b:02d}_before'}]
        actions += [{'kind':'call','id':s['id']} for s in group]
        actions += [{'kind':'metadata','id':f'b{b:02d}_after'}]
    return actions

def build_plan(baseline_path,run_name,provenance='live'):
    if provenance not in ('live','synthetic'):raise ValueError('provenance')
    spec=common.spec()
    if spec['contract']!='v069-guided-append-positive-control-r1':raise ValueError('protocol')
    raw=Path(baseline_path).read_bytes(); _,old,request,_=previous.inspect_prior(raw)
    for problem in spec['problems']:
        if measure.depth_ranges(problem)!=spec['depth_ranges'][problem['id']]:raise ValueError('depth ranges')
        for i,c in enumerate(spec['conditions']):
            if reference.validate(problem,spec['reference_plans'][problem['id']][c])!=spec['depth_ranges'][problem['id']][i]:raise ValueError('reference invalid')
    slots=_slots(spec)
    plan={'contract':CONTRACT,'run_name':common.check_run_name(run_name),'provenance':provenance,
          'protocol':deepcopy(spec),'protocol_sha256':common.sha((common.ROOT/'data/protocol.json').read_bytes()),
          'source_hashes':common.source_hashes(),'baseline_sha256':common.sha(raw),
          'baseline_request':request,'identity':deepcopy(old['identity']),'slots':slots,'actions':_actions(slots,6)}
    plan['plan_sha256']=common.sha(common.wire(plan));return plan

def transfer(raw,source_id):
    # 모델 JSON 내부는 해석하지 않는다. 외부 message.content만 원문으로 운반한다.
    content=None
    try:
        outer=common.load(raw)
        if isinstance(outer,dict) and isinstance(outer.get('message'),dict):
            value=outer['message'].get('content')
            if isinstance(value,str):content=value
    except (ValueError,UnicodeError):pass
    return {'source_slot_id':source_id,'response_sha256':common.sha(raw),'content':content}

def request_for(plan,slot,history_raw=None):
    history_raw={} if history_raw is None else history_raw
    if set(history_raw)!=set(slot['history_ids']):raise ValueError('actual full preceding history required')
    body=deepcopy(plan['baseline_request'])
    if len(body['messages'])!=1 or body['messages'][0]['role']!='user':raise ValueError('baseline message')
    properties=body['format']['properties']; stage=slot['stage']
    if stage=='facts':selected={'nodes':deepcopy(properties['nodes'])}
    elif stage=='rule':selected={'node':deepcopy(properties['nodes']['items'])}
    elif stage=='final':selected={'final_node_id':deepcopy(properties['final_node_id'])}
    else:raise ValueError('stage')
    body['format']={'type':'object','properties':selected,'required':list(selected),'additionalProperties':False}
    problem=next(p for p in plan['protocol']['problems'] if p['id']==slot['problem_id'])
    route=plan['protocol']['reference_plans'][problem['id']][slot['condition']]
    if route!=slot['reference_rule_ids'] or slot['reference_origin']!='experimenter_verified_reference':raise ValueError('reference drift')
    headers=plan['protocol']['headers']
    text=headers['common']+'\n\n'+headers[stage]+'\nJSON 객체 하나만 출력한다. 출력 형식(JSON Schema):\n'+common.wire(body['format']).decode()
    text+='\n\nproblem: '+common.wire(problem).decode()
    text+='\n\nprovided_route_plan: '+common.wire({'origin':slot['reference_origin'],'rule_ids':route}).decode()
    text+='\n\noperation: '+common.wire({'stage':stage,'index':slot['operation_index'],'requested_rule_id':slot['requested_rule_id']}).decode()
    text+='\n\nhistory: '+common.wire([transfer(history_raw[sid],sid) for sid in slot['history_ids']]).decode()
    body['messages'][0]['content']=text;body['options']['seed']=slot['seed']
    if len(common.wire(body))>plan['protocol']['request_utf8_byte_limit']:raise ValueError('request byte limit; no truncation or repair')
    return body
