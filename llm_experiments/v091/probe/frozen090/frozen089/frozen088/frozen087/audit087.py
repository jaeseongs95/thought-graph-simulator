"""독립 배정·요청 재구성. design087/rows087/measure/stages를 import하지 않는다."""
from pathlib import Path
from copy import deepcopy
from functools import lru_cache
from collections import Counter
import bridge087
from audit_bytes087 import dump,load,need,same,digest
import audit086 as old
ROOT=Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def anchor_list():return load((ROOT/'data/anchors.json').read_bytes())


def reconstruct_schedule(s):
    ts=[];ss=[];actions=[];arms=['baseline','node_inventory','allocated_id','inventory_allocated']
    templates=anchor_list()
    for block in range(16):
        pi,si=divmod(block,2);p=s['problems'][pi];actions.append({'kind':'metadata','id':'b%02d_before'%block})
        local=sorted([a for a in templates if a['problem_id']==p['id']],key=lambda a:s['anchor_ids'].index(a['id']),reverse=bool(si))
        for j,a in enumerate(local):
            off=(pi+si+j)%4
            for k in range(4):
                arm=arms[(k+off)%4];uid='d%02ds%d_%s_r%02d'%(pi,si,a['route_kind'],a['rule_position'])
                t=dict(id=uid+'_'+arm,unit_id=uid,phase='rule_probe',generator_arm=arm,anchor_id=a['id'],problem_id=p['id'],seed=s['seeds'][si],block=block,
                       selector_variant='two_stage_values',variant='explicit_rule',metric='D',condition=a['route_kind'],selection_slot_id=None,comparison_slot_id=None)
                ts.append(t);sid=t['id']+'_rule_%02d'%a['rule_position']
                ss.append(dict(id=sid,trial_id=t['id'],logical_id=uid+'_rule_%02d'%a['rule_position'],stage='rule',rule_position=a['rule_position']))
                actions.append({'kind':'slot','id':sid})
        for u in s['units']:
            if u['block']!=block:continue
            uid=u['unit_id'];g={}
            for arm in arms:
                t=deepcopy(u);t.update(id=uid+'_'+arm,phase='end_to_end',generator_arm=arm,selector_variant='two_stage_values',variant='explicit_rule',metric='D',arm='model',generate=True,
                    selection_slot_id=uid+'_two_stage_values_select',comparison_slot_id=uid+'_two_stage_values_compare',pair_id=u['base_pair_id']+'_'+arm,control_candidate_id=None)
                ts.append(t);g[arm]=t
            for stage in ('compare','select'):
                sid=uid+'_two_stage_values_'+stage;ss.append(dict(id=sid,trial_id=g['baseline']['id'],logical_id=uid+'_'+stage,stage=stage,rule_position=None));actions.append({'kind':'slot','id':sid})
            off=(pi+si+2*u['candidate_order_index']+u['id_assignment_index']+(u['condition']=='deep'))%4
            n=max(len(v)for v in s['reference_plans'][p['id']].values())
            for k in range(4):
                t=g[arms[(k+off)%4]]
                for q in range(n+2):
                    stage='facts'if q==0 else'final'if q==n+1 else'rule';pos=q-1 if stage=='rule'else None
                    tail='rule_%02d'%pos if stage=='rule'else stage;sid=t['id']+'_'+tail
                    ss.append(dict(id=sid,trial_id=t['id'],logical_id=uid+'_'+tail,stage=stage,rule_position=pos));actions.append({'kind':'slot','id':sid})
        actions.append({'kind':'metadata','id':'b%02d_after'%block})
    return ts,ss,actions


def independent_inventory(history):
    out=[];bad=[]
    for record in history:
        try:value=load(record['content'])
        except (ValueError,TypeError,UnicodeError):bad.append(record['source_slot_id']);continue
        nodes=None
        if type(value)is dict:
            if set(value)=={'nodes'}and type(value['nodes'])is list:nodes=value['nodes']
            elif set(value)=={'node'}:nodes=[value['node']]
        if nodes is None:bad.append(record['source_slot_id']);continue
        for ix,node in enumerate(nodes):
            if type(node)is not dict or type(node.get('id'))is not str or type(node.get('atom'))is not str:bad.append(record['source_slot_id']);continue
            out.append(dict(source_slot_id=record['source_slot_id'],node_index=ix,id=node['id'],atom=node['atom']))
    return dict(rows=out,unreadable_source_slots=bad)


def expected_request(plan,slot,raws):
    s=plan['protocol'];t=next(t for t in plan['trials']if t['id']==slot['trial_id'])
    if t['phase']=='rule_probe':
        a=next(a for a in anchor_list()if a['id']==t['anchor_id']);body=deepcopy(a['request_body']);body['options']['seed']=t['seed']
    else:
        skip,raw=old.expected_request(plan,slot,raws)
        if skip:return skip,None
        body=load(raw)
    if slot['stage']=='rule' and t['generator_arm']!='baseline':
        content=body['messages'][0]['content'];head=content.split('\nJSON 객체 하나만 출력한다. 출력 형식(JSON Schema):\n',1)[0]
        d=load(content.split('\n\ninput: ',1)[1]);sc=deepcopy(body['format'])
        uses_table=t['generator_arm']in ('node_inventory','inventory_allocated');uses_id=t['generator_arm']in ('allocated_id','inventory_allocated')
        inv=independent_inventory(d['history'])
        if uses_table:d['observed_node_inventory']=inv;head+='\n'+s['inventory_header']
        if uses_id:
            occupied=set();strings=[]
            for item in d['history']:
                txt=item.get('content')
                if type(txt)is not str:continue
                strings.append(txt)
                try:stack=[load(txt)]
                except (ValueError,TypeError,UnicodeError):stack=[]
                while stack:
                    node=stack.pop()
                    if type(node)is dict:
                        if type(node.get('id'))is str:occupied.add(node['id'])
                        stack.extend(node.values())
                    elif type(node)is list:stack.extend(node)
            count=1
            while s['allocated_id_prefix']+('%04d'%count)in occupied or any(s['allocated_id_prefix']+('%04d'%count)in x for x in strings):count+=1
            new=s['allocated_id_prefix']+('%04d'%count);d['allocated_node_id']=new
            sc['properties']['node']['properties']['id']={'type':'string','enum':[new]};head+='\n'+s['allocated_id_header']
        body['messages']=[{'role':'user','content':head+'\nJSON 객체 하나만 출력한다. 출력 형식(JSON Schema):\n'+dump(sc).decode()+'\n\ninput: '+dump(d).decode()}];body['format']=sc
    raw=dump(body);need(len(raw)<=s['request_utf8_byte_limit'],'request overflow')
    return None,raw


def validate_protocol(s):
    base=load((ROOT/'frozen086/data/protocol.json').read_bytes())
    for k in ('identity','model','problems','reference_plans','depth_ranges','seeds','conditions','reference_conditions','candidate_orders','candidate_ids','headers','selector_schema','api_defaults','generation_schema','num_predict','request_utf8_byte_limit','timeout_seconds','id_assignments','frozen_profiles','numeric_compare_schema','lookup_schema','numeric_compare_header','lookup_header'):
        need(same(s[k],base[k]),'frozen v086 input contract '+k)
    need(s['contract']=='v087-generator-factorial-r1'and s['holdout']is False and s['new_independent_structures']==0 and s['diagnostic_case_reuse']is True,'diagnostic case reuse')
    need(s['factors']=={'baseline':[False,False],'node_inventory':[True,False],'allocated_id':[False,True],'inventory_allocated':[True,True]},'2x2 factors')
    need(list(s['factors'])==['baseline','node_inventory','allocated_id','inventory_allocated'],'fixed arm order')
    need(s['primary_comparison']==['baseline','inventory_allocated'],'primary contrast')
    need(not any(s[k]for k in ('automatic_retry','automatic_download','automatic_server_start','posthoc_repair')),'no repair/retry')
    need(s['max_inference_calls']==4208 and s['max_action_slots']==4240 and s['expected_inference_calls_if_all_target_routes_selected']==4080,'budget')
    aa=anchor_list();need(digest((ROOT/'data/anchors.json').read_bytes())==s['anchors_sha256'],'anchors hash')
    need([a['id']for a in aa]==s['anchor_ids']and len(aa)==70,'all rule anchors')
    for a in aa:
        body=a['request_body'];d=load(body['messages'][0]['content'].split('\n\ninput: ',1)[1]);p=next(p for p in s['problems']if p['id']==a['problem_id'])
        need(same(d['problem'],p),'anchor problem');need(d['operation']['requested_rule_id']==a['rule_id'],'anchor operation')
        need(digest(dump(body))==a['source_request_sha256'],'anchor request hash')
        path=s['reference_plans'][p['id']][s['reference_conditions'][int(a['route_kind']=='deep')]]
        need(d['provided_route_plan']['rule_ids']==path and path[a['rule_position']]==a['rule_id'],'anchor route')
    old_trials,_,_=old.reconstruct_schedule(base)
    expected=[{k:t[k]for k in ('unit_id','block','problem_id','seed','candidate_order_index','id_assignment_index','condition','base_pair_id')}for t in old_trials if t['selector_variant']=='two_stage_values'and t['metric']=='D']
    need(same(s['units'],expected),'same logical D conditions')


def independent_summary(plan,records,raws,state):
    from audit_rows087 import independent_rows
    from tables087 import aggregate
    rows,status,usage=independent_rows(plan,records,raws)
    return aggregate(plan,rows,status,usage,state)
