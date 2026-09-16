"""ID 표현만 바꾸는 국소 대조, 연속 참조 대조, 기존 D 종단 모니터."""
from __future__ import annotations
from copy import deepcopy
from functools import lru_cache
import core088 as core
import bridge088
import design086 as frozen
import design087 as previous

SEPARATOR='\nJSON 객체 하나만 출력한다. 출력 형식(JSON Schema):\n'

@lru_cache(maxsize=1)
def anchors():return core.load((core.ROOT/'data/anchors.json').read_bytes())

def anchor_for(t):return next(a for a in anchors() if a['id']==t['anchor_id'])
def trial_for(plan,slot):return next(t for t in plan['trials'] if t['id']==slot['trial_id'])
def data_from(body):return core.load(body['messages'][0]['content'].split('\n\ninput: ',1)[1])

def schedule(s):
    trials=[];slots=[];actions=[]
    def add(t,stage,pos=None,oid=None,logical=None):
        tail=f'rule_{pos:02d}' if stage=='rule' else stage
        item=dict(id=oid or t['id']+'_'+tail,trial_id=t['id'],logical_id=logical or t['unit_id']+'_'+tail,stage=stage,rule_position=pos)
        slots.append(item);actions.append(dict(kind='slot',id=item['id']))
    for block in range(len(s['problems'])*len(s['seeds'])):
        pi,si=divmod(block,len(s['seeds']));p=s['problems'][pi]
        actions.append(dict(kind='metadata',id=f'b{block:02d}_before'))
        local=[a for a in anchors() if a['problem_id']==p['id']]
        if si%2:local.reverse()
        for j,a in enumerate(local):
            arms=s['probe_arms'];shift=(pi+si+j)%len(arms)
            for arm in arms[shift:]+arms[:shift]:
                uid=f'p{pi:02d}s{si}_{a["route_kind"]}_r{a["rule_position"]:02d}'
                t=dict(id=uid+'_'+arm,unit_id=uid,phase='rename_probe',generator_arm=arm,anchor_id=a['id'],
                    problem_id=p['id'],seed=s['seeds'][si],block=block,condition=a['route_kind'],metric='D',
                    selector_variant='two_stage_values',variant='explicit_rule',selection_slot_id=None,comparison_slot_id=None)
                trials.append(t);add(t,'rule',a['rule_position'])
        for kind in ('shallow','deep'):
            arms=s['continuation_arms'];shift=(pi+si+int(kind=='deep'))%len(arms)
            path=s['reference_plans'][p['id']][s['reference_conditions'][int(kind=='deep')]]
            for arm in arms[shift:]+arms[:shift]:
                uid=f'c{pi:02d}s{si}_{kind}'
                t=dict(id=uid+'_'+arm,unit_id=uid,phase='continuation',generator_arm=arm,anchor_id=p['id']+'_'+kind+'_r00',
                    problem_id=p['id'],seed=s['seeds'][si],block=block,condition=kind,metric='D',
                    selector_variant='two_stage_values',variant='explicit_rule',selection_slot_id=None,comparison_slot_id=None,
                    pair_id=f'c{pi:02d}s{si}_'+arm,base_pair_id=f'c{pi:02d}s{si}',route_rule_ids=path)
                trials.append(t)
                for pos in range(len(path)):add(t,'rule',pos)
                add(t,'final')
        for u in [u for u in s['units'] if u['block']==block]:
            group=[]
            for arm in s['monitor_arms']:
                t=dict(u,id=u['unit_id']+'_'+arm,phase='end_to_end',generator_arm=arm,selector_variant='two_stage_values',
                    variant='explicit_rule',metric='D',arm='model',generate=True,
                    selection_slot_id=u['unit_id']+'_two_stage_values_select',comparison_slot_id=u['unit_id']+'_two_stage_values_compare',
                    pair_id=u['base_pair_id']+'_'+arm,control_candidate_id=None)
                group.append(t);trials.append(t)
            for stage in ('compare','select'):add(group[0],stage,oid=group[0]['comparison_slot_id' if stage=='compare' else 'selection_slot_id'],logical=u['unit_id']+'_'+stage)
            if (pi+si+2*u['candidate_order_index']+u['id_assignment_index']+int(u['condition']=='deep'))%2:group.reverse()
            n=max(map(len,s['reference_plans'][p['id']].values()))
            for t in group:
                add(t,'facts')
                for pos in range(n):add(t,'rule',pos)
                add(t,'final')
        actions.append(dict(kind='metadata',id=f'b{block:02d}_after'))
    if (len(trials),len(slots),len(actions))!=(944,s['max_inference_calls'],s['max_action_slots']):raise ValueError('frozen schedule count '+str((len(trials),len(slots),len(actions))))
    return trials,slots,actions

def history_nodes(history):
    nodes=[]
    for record in history:
        x=core.load(record['content'])
        nodes.extend(x['nodes'] if 'nodes' in x else [x['node']])
    return nodes

def rename_history(history,style):
    """고정된 유효 진단 입력의 ID와 내부 부모 참조만 전단사 치환한다.

    model의 새 출력은 이 함수에 통과시키지 않는다. 모든 군(관측형 포함)에
    동일한 JSON 재직렬화를 적용해 공백 정규화와 ID 변화가 혼합되지 않게 한다.
    """
    nodes=history_nodes(history);old=[n['id'] for n in nodes]
    if len(set(old))!=len(old):raise ValueError('invalid prefix duplicate ID')
    if style=='observed':new=old[:]
    elif style=='atom_alias':new=[n['atom'] for n in nodes]
    elif style in ('short','legacy_long'):
        prefix='n' if style=='short' else 'v087_node_'
        new=[prefix+f'{i:04d}' for i in range(1,len(nodes)+1)]
    else:raise ValueError('unknown rename style')
    if len(set(new))!=len(new):raise ValueError('nonbijective rename')
    mapping=dict(zip(old,new));out=[]
    for h in history:
        x=core.load(h['content']);ns=x['nodes'] if 'nodes' in x else [x['node']]
        for n in ns:
            n['id']=mapping[n['id']]
            n['parents']=[mapping[k] for k in n['parents']]
        out.append(dict(h,content=core.wire(x).decode()))
    return out,mapping

def render_body(template,data,header=None,schema=None,seed=None):
    body=deepcopy(template);schema=deepcopy(body['format'] if schema is None else schema)
    if header is None:header=body['messages'][0]['content'].split(SEPARATOR,1)[0]
    if seed is not None:body['options']['seed']=seed
    body['format']=schema;body['messages']=[dict(role='user',content=header+SEPARATOR+core.wire(schema).decode()+'\n\ninput: '+core.wire(data).decode())]
    return body

def continuation_seed(t):
    """두 scope에서 동일 출력 ID를 쓰도록 최초의 사실 이력 합집합으로만 예약한다."""
    a=anchor_for(t);d=data_from(a['request_body']);original=d['history'];family=t['generator_arm'].split('_')[0]
    style='short' if family=='short' else 'legacy_long'
    uniform,mapping=rename_history(original,style);observed,_=rename_history(original,'observed')
    before=history_nodes(original);blocked={n['id'] for n in before}|set(mapping.values())
    prefix='n' if family=='short' else 'v087_node_'
    allocated=[];counter=len(before)+1
    for unused in t['route_rule_ids']:
        candidate=prefix+f'{counter:04d}'
        while candidate in blocked:
            counter+=1;candidate=prefix+f'{counter:04d}'
        allocated.append(candidate);blocked.add(candidate);counter+=1
    return (uniform if t['generator_arm'].endswith('_uniform') else observed),allocated,mapping

def disposition(plan,slot,responses):
    if trial_for(plan,slot)['phase']=='end_to_end':return frozen.disposition(plan,slot,responses)
    return None

def request_for(plan,slot,responses):
    t=trial_for(plan,slot);s=plan['protocol'];stage=slot['stage']
    if t['phase']=='end_to_end':
        body=frozen.request_for(plan,slot,responses)
        if stage=='rule' and t['generator_arm']=='allocated_id':
            # v087 실패 처치의 동시 대조. 기본 생성기 승격이 아니다.
            old_s=dict(s,factors={'allocated_id':[False,True]})
            body=previous.extend_request(body,'allocated_id',old_s)
    elif t['phase']=='rename_probe':
        a=anchor_for(t);body=a['request_body'];d=data_from(body)
        d['history'],_=rename_history(d['history'],t['generator_arm'])
        body=render_body(body,d,seed=t['seed'])
    else:
        a=anchor_for(t);d=data_from(a['request_body']);history,ids,_=continuation_seed(t)
        for op in plan['slots']:
            if op['id']==slot['id']:break
            if op['trial_id']==t['id'] and op['id'] in responses:
                history.append(dict(source_slot_id=op['logical_id'],content=frozen.legacy.raw_content(responses[op['id']])))
        d['history']=history;path=t['route_rule_ids']
        if stage=='rule':
            pos=slot['rule_position'];rid=path[pos]
            d['operation']=dict(stage='rule',index=pos+1,requested_rule_id=rid,
                requested_rule=deepcopy(next(r for r in d['problem']['rules'] if r['id']==rid)))
            d['allocated_node_id']=ids[pos];schema=deepcopy(a['request_body']['format'])
            schema['properties']['node']['properties']['id']={'type':'string','enum':[ids[pos]]}
            header=s['headers']['generator']+'\n\n'+s['headers']['rule']+'\n'+s['allocated_id_header']
        else:
            d['operation']=dict(stage='final',index=len(path)+1,requested_rule_id=None)
            prop=s['generation_schema']['properties']['final_node_id']
            schema={'type':'object','properties':{'final_node_id':deepcopy(prop)},'required':['final_node_id'],'additionalProperties':False}
            header=s['headers']['generator']+'\n\n'+s['headers']['final']
        body=render_body(a['request_body'],d,header,schema,t['seed'])
    if len(core.wire(body))>s['request_utf8_byte_limit']:raise ValueError('request budget; no truncation')
    return body

def make_plan(baseline_path,run_name,provenance='live',audit_previous=True):
    if provenance not in ('live','synthetic'):raise ValueError('provenance')
    from baseline088 import validate_inputs
    validate_inputs(baseline_path,run_verifier=audit_previous)
    from audit088 import validate_protocol
    s=core.spec();validate_protocol(s);ts,ss,aa=schedule(s)
    p=dict(contract='v088-plan-r2',run_name=core.check_run_name(run_name),provenance=provenance,
        protocol=s,protocol_sha256=core.sha((core.ROOT/'data/protocol.json').read_bytes()),baseline_sha256=s['baseline_sha256'],
        source_hashes=core.source_hashes(),trials=ts,slots=ss,actions=aa)
    p['plan_sha256']=core.sha(core.wire(p));return p
