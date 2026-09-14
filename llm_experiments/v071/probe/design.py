"""깊이 계산 원문→수치 선택과 정답 깊이 대조의 동결 계획. 호스트 의미 보정 없음."""
from copy import deepcopy
from pathlib import Path
import common, previous, reference, measure
CONTRACT='v071-plan-r1'

def _slots(spec):
    slots=[]
    for pi,p in enumerate(spec['problems']):
        for si,seed in enumerate(spec['seeds']):
            for oi in range(2):
                block=(pi*len(spec['seeds'])+si)*2+oi
                unit=f'b{block:02d}'
                # 원응답 의존성을 지키면서 oracle/model 선택의 선후를 교차한다.
                if (si+oi)%2==0:
                    seq=[('oracle_depth','shallow'),('oracle_depth','deep'),('estimate',None),('model_depth','deep'),('model_depth','shallow')]
                else:
                    seq=[('estimate',None),('model_depth','shallow'),('model_depth','deep'),('oracle_depth','deep'),('oracle_depth','shallow')]
                for period,(arm,condition) in enumerate(seq):
                    stage='estimate' if arm=='estimate' else 'select'
                    sid=unit+'_estimate' if stage=='estimate' else unit+'_'+arm+'_'+condition
                    slots.append({'id':sid,'unit_id':unit,'pair_id':None if stage=='estimate' else unit+'_'+arm,
                        'block':block,'period':period,'problem_id':p['id'],'seed':seed,'seed_index':si,
                        'candidate_order_index':oi,'stage':stage,'arm':arm,'condition':condition,
                        'history_ids':[unit+'_estimate'] if arm=='model_depth' else [],
                        'problem_role':'seen_constructor_task' if pi<3 else 'seen_authored_diagnostic'})
    if len(slots)!=spec['max_inference_calls'] or len({s['id'] for s in slots})!=100:
        raise ValueError('100 unique calls required')
    return slots

def _actions(slots,blocks):
    actions=[]
    for b in range(blocks):
        group=[s for s in slots if s['block']==b]
        if len(group)!=5:raise ValueError('five calls per block')
        actions.append({'kind':'metadata','id':f'b{b:02d}_before'})
        actions.extend({'kind':'call','id':s['id']} for s in group)
        actions.append({'kind':'metadata','id':f'b{b:02d}_after'})
    return actions

def build_plan(baseline_path,run_name,provenance='live'):
    if provenance not in ('live','synthetic'):raise ValueError('provenance')
    spec=common.spec()
    if spec['contract']!='v071-depth-estimate-compare-r1':raise ValueError('protocol')
    raw=Path(baseline_path).read_bytes()
    _,old,request,_=previous.inspect_prior(raw)
    for p in spec['problems']:
        if measure.depth_ranges(p)!=spec['depth_ranges'][p['id']]:raise ValueError('global depth ranges')
        for i,c in enumerate(spec['reference_conditions']):
            if reference.validate(p,spec['reference_plans'][p['id']][c])!=spec['depth_ranges'][p['id']][i]:
                raise ValueError('invalid candidate')
    slots=_slots(spec)
    plan={'contract':CONTRACT,'run_name':common.check_run_name(run_name),'provenance':provenance,
        'protocol':deepcopy(spec),'protocol_sha256':common.sha((common.ROOT/'data/protocol.json').read_bytes()),
        'source_hashes':common.source_hashes(),'baseline_sha256':common.sha(raw),
        'baseline_request':request,'identity':deepcopy(old['identity']),'slots':slots,
        'actions':_actions(slots,spec['assigned_blocks'])}
    plan['plan_sha256']=common.sha(common.wire(plan))
    return plan

def content_or_null(raw):
    """전송 envelope에서 content 문자열만 그대로 취한다. payload 파싱/수정은 하지 않는다."""
    try:
        envelope=common.load(raw)
        message=envelope.get('message') if isinstance(envelope,dict) else None
        value=message.get('content') if isinstance(message,dict) else None
        return value if isinstance(value,str) else None
    except (UnicodeError,ValueError):
        return None

def request_for(plan,slot,history_raw=None):
    history_raw={} if history_raw is None else history_raw
    if set(history_raw)!=set(slot['history_ids']):raise ValueError('exact history IDs required')
    spec=plan['protocol']
    body=deepcopy(plan['baseline_request'])
    if len(body['messages'])!=1 or body['messages'][0]['role']!='user':raise ValueError('baseline messages')
    if slot['stage']=='estimate':
        p=next(p for p in spec['problems'] if p['id']==slot['problem_id'])
        order=spec['candidate_orders'][slot['candidate_order_index']]
        candidates=[spec['reference_plans'][p['id']][spec['reference_conditions'][i]] for i in order]
        body['format']={'type':'object','properties':{'depths':{'type':'array','minItems':2,'maxItems':2,
            'items':{'type':'integer','minimum':0,'maximum':64}}},'required':['depths'],'additionalProperties':False}
        data={'problem':{k:p[k] for k in ('facts','rules','goal')},'candidate_rule_ids':candidates}
        header=spec['headers']['depth']
    else:
        body['format']={'type':'object','properties':{'candidate_index':{'type':'integer','enum':[0,1]}},
            'required':['candidate_index'],'additionalProperties':False}
        if slot['arm']=='model_depth':
            depth_report=content_or_null(history_raw[slot['history_ids'][0]])
        elif slot['arm']=='oracle_depth':
            # 명시적인 정답입력 양성 대조에만 참값을 공급한다. model arm에서는 이 분기를 실행하지 않는다.
            order=spec['candidate_orders'][slot['candidate_order_index']]
            depth_report=common.wire({'depths':[spec['depth_ranges'][slot['problem_id']][i] for i in order]}).decode('utf-8')
        else:raise ValueError('choice arm')
        data={'depth_report':depth_report,'requested_depth':spec['headers'][slot['condition']]}
        header=spec['headers']['compare']
    body['messages'][0]['content']=header+'\nJSON 객체 하나만 출력한다. 출력 형식(JSON Schema):\n'+common.wire(body['format']).decode('utf-8')+'\n\ninput: '+common.wire(data).decode('utf-8')
    body['options']['seed']=slot['seed']
    if len(common.wire(body))>spec['request_utf8_byte_limit']:raise ValueError('request byte limit; no truncation')
    return body
