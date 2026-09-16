"""v087 사전 배정 및 무보정 요청. 생산 점수는 요청 생성에 사용하지 않는다."""
from __future__ import annotations
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
import bridge087
import core087 as core
import design086 as frozen


@lru_cache(maxsize=1)
def anchors():
    return core.load((core.ROOT/'data/anchors.json').read_bytes())


def schedule(s):
    trials, slots, actions = [], [], []
    names=list(s['factors'])
    def op(t,stage,pos=None,oid=None,logical=None):
        tail=f'rule_{pos:02d}' if stage=='rule' else stage
        item={'id':oid or t['id']+'_'+tail,'trial_id':t['id'],
              'logical_id':logical or t['unit_id']+'_'+tail,'stage':stage,'rule_position':pos}
        slots.append(item);actions.append({'kind':'slot','id':item['id']})
    for block in range(len(s['problems'])*len(s['seeds'])):
        pi,si=divmod(block,len(s['seeds']));problem=s['problems'][pi]
        actions.append({'kind':'metadata','id':f'b{block:02d}_before'})
        # 규칙 진단: 한 경로의 동일한 관측 유효 이력을 네 군/두 seed에 제공한다.
        these=[a for a in anchors() if a['problem_id']==problem['id']]
        if si%2:these=list(reversed(these))
        for j,a in enumerate(these):
            order=names[(pi+si+j)%4:]+names[:(pi+si+j)%4]
            for arm in order:
                uid=f"d{pi:02d}s{si}_{a['route_kind']}_r{a['rule_position']:02d}"
                t={'id':uid+'_'+arm,'unit_id':uid,'phase':'rule_probe','generator_arm':arm,
                   'anchor_id':a['id'],'problem_id':problem['id'],'seed':s['seeds'][si],
                   'block':block,'selector_variant':'two_stage_values','variant':'explicit_rule',
                   'metric':'D','condition':a['route_kind'],'selection_slot_id':None,'comparison_slot_id':None}
                trials.append(t);op(t,'rule',a['rule_position'])
        # D 선택 두 호출을 한 번만 실행한 후, 원응답을 공통 입력으로 네 생성군에 전달한다.
        for unit in [u for u in s['units'] if u['block']==block]:
            uid=unit['unit_id'];group=[]
            for arm in names:
                t=dict(unit,id=uid+'_'+arm,phase='end_to_end',generator_arm=arm,
                       selector_variant='two_stage_values',variant='explicit_rule',metric='D',arm='model',generate=True,
                       selection_slot_id=uid+'_two_stage_values_select',comparison_slot_id=uid+'_two_stage_values_compare',
                       pair_id=unit['base_pair_id']+'_'+arm,control_candidate_id=None)
                group.append(t);trials.append(t)
            for stage in ('compare','select'):
                op(group[0],stage,oid=group[0]['comparison_slot_id' if stage=='compare' else 'selection_slot_id'],logical=uid+'_'+stage)
            shift=(pi+si+2*unit['candidate_order_index']+unit['id_assignment_index']+int(unit['condition']=='deep'))%4
            group=group[shift:]+group[:shift]
            n=max(map(len,s['reference_plans'][problem['id']].values()))
            for t in group:
                op(t,'facts')
                for pos in range(n):op(t,'rule',pos)
                op(t,'final')
        actions.append({'kind':'metadata','id':f'b{block:02d}_after'})
    if (len(trials),len(slots),len(actions))!=(1072,s['max_inference_calls'],s['max_action_slots']):
        raise ValueError('v087 frozen schedule count '+str((len(trials),len(slots),len(actions))))
    return trials, slots, actions


def trial_for(plan,slot):
    return next(t for t in plan['trials'] if t['id']==slot['trial_id'])


def history_inventory(history):
    """사실 여부를 판단하지 않는 손실 없는 투영. 중복/오답 행도 보존한다."""
    rows=[];unreadable=[]
    for h in history:
        try:x=core.load(h['content'])
        except (ValueError,TypeError,UnicodeError):
            unreadable.append(h['source_slot_id']);continue
        if isinstance(x,dict) and set(x)=={'nodes'} and isinstance(x['nodes'],list):ns=x['nodes']
        elif isinstance(x,dict) and set(x)=={'node'}:ns=[x['node']]
        else:unreadable.append(h['source_slot_id']);continue
        for i,n in enumerate(ns):
            if not isinstance(n,dict) or not isinstance(n.get('id'),str) or not isinstance(n.get('atom'),str):
                unreadable.append(h['source_slot_id']);continue
            rows.append({'source_slot_id':h['source_slot_id'],'node_index':i,'id':n['id'],'atom':n['atom']})
    return {'rows':rows,'unreadable_source_slots':unreadable}


def allocate_id(history,prefix):
    # 손상/비표준 JSON에서도 해석 가능한 id와 원문에 보이는 후보 문자열은 재사용하지 않는다.
    used=set()
    def visit(x):
        if isinstance(x,dict):
            if isinstance(x.get('id'),str):used.add(x['id'])
            for v in x.values():visit(v)
        elif isinstance(x,list):
            for v in x:visit(v)
    raw_text=[]
    for h in history:
        text=h.get('content')
        if isinstance(text,str):
            raw_text.append(text)
            try:visit(core.load(text))
            except (ValueError,TypeError,UnicodeError):pass
    i=1
    while f'{prefix}{i:04d}' in used or any(f'{prefix}{i:04d}' in text for text in raw_text):i+=1
    return f'{prefix}{i:04d}'


def extend_request(body,arm,s):
    inv,newid=s['factors'][arm]
    if not inv and not newid:return body  # 기준선 바이트를 다시 직렬화하지 않는다.
    body=deepcopy(body);text=body['messages'][0]['content']
    header,rest=text.split('\nJSON 객체 하나만 출력한다. 출력 형식(JSON Schema):\n',1)
    _,input_text=rest.split('\n\ninput: ',1);data=core.load(input_text)
    if data.get('operation',{}).get('stage')!='rule':return body
    schema=deepcopy(body['format'])
    if inv:
        data['observed_node_inventory']=history_inventory(data['history'])
        header+='\n'+s['inventory_header']
    if newid:
        allocated=allocate_id(data['history'],s['allocated_id_prefix'])
        data['allocated_node_id']=allocated
        # 새 식별자만 사전 제약한다. 부모·원자·규칙 정답은 제약하지 않는다.
        schema['properties']['node']['properties']['id']={'type':'string','enum':[allocated]}
        header+='\n'+s['allocated_id_header']
    text=header+'\nJSON 객체 하나만 출력한다. 출력 형식(JSON Schema):\n'+core.wire(schema).decode()+'\n\ninput: '+core.wire(data).decode()
    body['messages']=[{'role':'user','content':text}];body['format']=schema
    if len(core.wire(body))>s['request_utf8_byte_limit']:raise ValueError('request budget; no truncation')
    return body


def disposition(plan,slot,responses):
    if trial_for(plan,slot)['phase']=='rule_probe':return None
    return frozen.disposition(plan,slot,responses)


def request_for(plan,slot,responses):
    t=trial_for(plan,slot)
    if t['phase']=='rule_probe':
        a=next(a for a in anchors() if a['id']==t['anchor_id'])
        body=deepcopy(a['request_body']);body['options']['seed']=t['seed']
    else:body=frozen.request_for(plan,slot,responses)
    if slot['stage']=='rule':body=extend_request(body,t['generator_arm'],plan['protocol'])
    return body


def make_plan(baseline_path,run_name,provenance='live',audit_previous=True):
    if provenance not in ('live','synthetic'):raise ValueError('provenance')
    from baseline087 import validate_inputs
    validate_inputs(baseline_path,run_verifier=audit_previous)
    spec=core.spec();ts,ss,aa=schedule(spec)
    p={'contract':'v087-plan-r1','run_name':core.check_run_name(run_name),'provenance':provenance,
       'protocol':spec,'protocol_sha256':core.sha((core.ROOT/'data/protocol.json').read_bytes()),
       'baseline_sha256':spec['baseline_sha256'],'source_hashes':core.source_hashes(),
       'trials':ts,'slots':ss,'actions':aa}
    p['plan_sha256']=core.sha(core.wire(p));return p
