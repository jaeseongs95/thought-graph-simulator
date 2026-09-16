"""생산 설계/재명명 함수를 사용하지 않는 배정·입력·변환 검산."""
from pathlib import Path
from copy import deepcopy
from functools import lru_cache
import bridge088
from audit_bytes088 import load,dump,digest,need,same
import audit086 as frozen
import audit087 as legacy
ROOT=Path(__file__).resolve().parent
SEP='\nJSON 객체 하나만 출력한다. 출력 형식(JSON Schema):\n'

@lru_cache(maxsize=1)
def anchor_list():return load((ROOT/'data/anchors.json').read_bytes())
def get_anchor(t):return next(a for a in anchor_list() if a['id']==t['anchor_id'])
def data(body):return load(body['messages'][0]['content'].split('\n\ninput: ',1)[1])

def reconstruct_schedule(s):
    ts=[];ops=[];actions=[]
    def emit(t,stage,pos=None,physical=None):
        end=('rule_%02d'%pos) if stage=='rule' else stage
        sid=physical or t['id']+'_'+end
        ops.append(dict(id=sid,trial_id=t['id'],logical_id=t['unit_id']+'_'+end,stage=stage,rule_position=pos))
        actions.append(dict(kind='slot',id=sid))
    for b in range(16):
        ix,seedix=divmod(b,2);p=s['problems'][ix];seed=s['seeds'][seedix]
        actions.append(dict(kind='metadata',id='b%02d_before'%b))
        aa=[a for a in anchor_list() if a['problem_id']==p['id']]
        if seedix:aa=aa[::-1]
        for j,a in enumerate(aa):
            shift=(ix+seedix+j)%4
            for k in range(4):
                arm=('observed','atom_alias','short','legacy_long')[(shift+k)%4]
                uid='p%02ds%d_%s_r%02d'%(ix,seedix,a['route_kind'],a['rule_position'])
                t=dict(id=uid+'_'+arm,unit_id=uid,phase='rename_probe',generator_arm=arm,anchor_id=a['id'],problem_id=p['id'],seed=seed,
                    block=b,condition=a['route_kind'],metric='D',selector_variant='two_stage_values',variant='explicit_rule',selection_slot_id=None,comparison_slot_id=None)
                ts.append(t);emit(t,'rule',a['rule_position'])
        for kind in ('shallow','deep'):
            path=s['reference_plans'][p['id']][s['reference_conditions'][int(kind=='deep')]]
            for k in range(4):
                arm=('short_mixed','short_uniform','long_mixed','long_uniform')[(ix+seedix+int(kind=='deep')+k)%4]
                uid='c%02ds%d_%s'%(ix,seedix,kind)
                t=dict(id=uid+'_'+arm,unit_id=uid,phase='continuation',generator_arm=arm,anchor_id=p['id']+'_'+kind+'_r00',
                    problem_id=p['id'],seed=seed,block=b,condition=kind,metric='D',selector_variant='two_stage_values',variant='explicit_rule',
                    selection_slot_id=None,comparison_slot_id=None,pair_id='c%02ds%d_%s'%(ix,seedix,arm),base_pair_id='c%02ds%d'%(ix,seedix),route_rule_ids=path)
                ts.append(t)
                for pos in range(len(path)):emit(t,'rule',pos)
                emit(t,'final')
        for u in s['units']:
            if u['block']!=b:continue
            g=[]
            for arm in ('baseline','allocated_id'):
                t=deepcopy(u);t.update(id=u['unit_id']+'_'+arm,phase='end_to_end',generator_arm=arm,selector_variant='two_stage_values',variant='explicit_rule',metric='D',
                    arm='model',generate=True,selection_slot_id=u['unit_id']+'_two_stage_values_select',comparison_slot_id=u['unit_id']+'_two_stage_values_compare',
                    pair_id=u['base_pair_id']+'_'+arm,control_candidate_id=None)
                ts.append(t);g.append(t)
            emit(g[0],'compare',physical=g[0]['comparison_slot_id']);emit(g[0],'select',physical=g[0]['selection_slot_id'])
            shift=(ix+seedix+2*u['candidate_order_index']+u['id_assignment_index']+int(u['condition']=='deep'))%2
            for k in range(2):
                t=g[(k+shift)%2];emit(t,'facts')
                for pos in range(max(len(x) for x in s['reference_plans'][p['id']].values())):emit(t,'rule',pos)
                emit(t,'final')
        actions.append(dict(kind='metadata',id='b%02d_after'%b))
    return ts,ops,actions

def renamed(history,style):
    values=[load(h['content']) for h in history]
    ns=[]
    for item in values:ns.extend(item['nodes'] if 'nodes' in item else [item['node']])
    identifiers=[n['id'] for n in ns];need(len(set(identifiers))==len(identifiers),'duplicate prefix')
    table={}
    for ix,n in enumerate(ns,1):
        if style=='observed':new=n['id']
        elif style=='atom_alias':new=n['atom']
        elif style=='short':new='n%04d'%ix
        elif style=='legacy_long':new='v087_node_%04d'%ix
        else:raise ValueError('rename style')
        table[n['id']]=new
    need(len(set(table.values()))==len(table),'rename not injective')
    for n in ns:
        n['id']=table[n['id']]
        n['parents']=[table[v] for v in n['parents']]
    return [dict(h,content=dump(v).decode()) for h,v in zip(history,values)],table

def continuing(t):
    d=data(get_anchor(t)['request_body']);h=d['history'];family=t['generator_arm'].split('_')[0]
    uniform,table=renamed(h,'short' if family=='short' else 'legacy_long')
    observed,_=renamed(h,'observed');ns=load(h[0]['content'])['nodes']
    used={n['id'] for n in ns}|set(table.values());prefix='n' if family=='short' else 'v087_node_'
    next_number=len(ns);ids=[]
    for _ in t['route_rule_ids']:
        while True:
            next_number+=1;name=prefix+('%04d'%next_number)
            if name not in used:break
        used.add(name);ids.append(name)
    return (uniform if t['generator_arm'].endswith('_uniform') else observed),ids,table

def build(template,d,seed,head=None,sc=None):
    out=deepcopy(template);out['options']['seed']=seed
    if sc is None:sc=deepcopy(template['format'])
    if head is None:head=template['messages'][0]['content'].split(SEP,1)[0]
    out['format']=sc;out['messages']=[dict(role='user',content=head+SEP+dump(sc).decode()+'\n\ninput: '+dump(d).decode())]
    return out

def expected_request(p,o,raws):
    s=p['protocol'];t=next(t for t in p['trials'] if t['id']==o['trial_id'])
    if t['phase']=='end_to_end':return legacy.expected_request(p,o,raws)
    a=get_anchor(t);d=data(a['request_body'])
    if t['phase']=='rename_probe':
        d['history'],_=renamed(d['history'],t['generator_arm']);body=build(a['request_body'],d,t['seed'])
    else:
        history,allocated,_=continuing(t)
        for prior in p['slots']:
            if prior['id']==o['id']:break
            if prior['trial_id']==t['id'] and prior['id'] in raws:
                history.append(dict(source_slot_id=prior['logical_id'],content=frozen.prior.content(raws[prior['id']])))
        d['history']=history;path=t['route_rule_ids']
        if o['stage']=='rule':
            pos=o['rule_position'];rid=path[pos];r=next(r for r in d['problem']['rules'] if r['id']==rid)
            d['operation']=dict(stage='rule',index=pos+1,requested_rule_id=rid,requested_rule=deepcopy(r))
            d['allocated_node_id']=allocated[pos];sc=deepcopy(a['request_body']['format']);sc['properties']['node']['properties']['id']={'type':'string','enum':[allocated[pos]]}
            head=s['headers']['generator']+'\n\n'+s['headers']['rule']+'\n'+s['allocated_id_header']
        else:
            d['operation']=dict(stage='final',index=len(path)+1,requested_rule_id=None)
            sc=dict(type='object',properties={'final_node_id':deepcopy(s['generation_schema']['properties']['final_node_id'])},required=['final_node_id'],additionalProperties=False)
            head=s['headers']['generator']+'\n\n'+s['headers']['final']
        body=build(a['request_body'],d,t['seed'],head,sc)
    raw=dump(body);need(len(raw)<=s['request_utf8_byte_limit'],'request budget')
    return None,raw

def validate_protocol(s):
    base=load((ROOT/'frozen087/data/protocol.json').read_bytes())
    r1=load((ROOT/'data/protocol_r1_snapshot.json').read_bytes())
    need(r1['contract']=='v088-id-continuity-r1','r1 protocol snapshot contract')
    need(s.keys()==r1.keys(),'r2 protocol top-level key drift')
    for k in r1:
        if k not in ('contract','identity'):need(same(s[k],r1[k]),'r2 research protocol drift: '+k)
    keys=('model','problems','reference_plans','depth_ranges','seeds','conditions','reference_conditions','candidate_orders','candidate_ids','headers','selector_schema',
          'api_defaults','generation_schema','num_predict','request_utf8_byte_limit','timeout_seconds','id_assignments','frozen_profiles','numeric_compare_schema','lookup_schema','numeric_compare_header','lookup_header','allocated_id_header','allocated_id_prefix','units')
    for k in keys:need(same(r1[k],base[k]),'r1/v087 contract drift: '+k)
    # runtime refreeze만 허용한다. 모델 digest/template/parameters 및 기타 model_info는 그대로여야 한다.
    oldi,newi=r1['identity'],s['identity']
    need(newi['model']==oldi['model'] and newi['digest']==oldi['digest'],'r2 model identity drift')
    need(same(newi['tag_details'],oldi['tag_details']),'r2 tag details drift')
    need(same(newi['server'],{'version':'0.34.1'}),'r2 Ollama server')
    need(oldi['server']=={'version':'0.34.0'},'r1 Ollama server provenance')
    for k in ('template','system','parameters','details','capabilities','projector_info'):
        need(same(newi['native'][k],oldi['native'][k]),'r2 native drift: '+k)
    oldmi,newmi=oldi['native']['model_info'],newi['native']['model_info']
    changed={
        'general.tags':(['text-generation'],None),
        'tokenizer.ggml.merges':([],None),
        'tokenizer.ggml.tokens':([],None),
        'tokenizer.ggml.token_type':([],None),
    }
    need(oldmi.keys()==newmi.keys(),'r2 model_info key drift')
    for k in oldmi:
        if k in changed:
            expected_new,expected_old=changed[k];need(same(newmi[k],expected_new) and same(oldmi[k],expected_old),'r2 metadata transition: '+k)
        else:need(same(newmi[k],oldmi[k]),'r2 model_info drift: '+k)
    rp=load((ROOT/'data/runtime_provenance_r2.json').read_bytes())
    need(rp['contract']=='v088-runtime-refreeze-r2' and rp['research_design_changed'] is False,'r2 provenance contract')
    need(rp['r1_protocol_sha256']==digest((ROOT/'data/protocol_r1_snapshot.json').read_bytes()),'r1 protocol provenance hash')
    need(rp['r2_protocol_sha256']==digest((ROOT/'data/protocol.json').read_bytes()),'r2 protocol provenance hash')
    need(rp['r1_failure']['run_name']=='v088_idcontinuity_20260916_081431_746223' and rp['r1_failure']['inference_calls']==0 and rp['r1_failure']['observed_calls']==0 and rp['r1_failure']['research_samples_generated']==0,'r1 zero-inference provenance')
    need(rp['r2_refreeze']['ollama_server']=='0.34.1' and rp['r2_refreeze']['model_digest']==newi['digest'] and rp['r2_refreeze']['runtime_identity_only'] is True,'r2 runtime provenance')
    need(s['contract']=='v088-id-continuity-r2-runtime-refreeze' and s['holdout'] is False and s['new_independent_structures']==0,'v088 scope')
    need(s['probe_arms']==['observed','atom_alias','short','legacy_long'],'probe arms')
    need(s['continuation_arms']==['short_mixed','short_uniform','long_mixed','long_uniform'],'continuation 2x2')
    need(s['monitor_arms']==['baseline','allocated_id'],'baseline monitor')
    need(s['primary_comparison']==['long_mixed','long_uniform'],'primary')
    need(not any(s[k] for k in ('automatic_retry','automatic_download','automatic_server_start','posthoc_repair')),'no repair or retry')
    need((s['max_inference_calls'],s['max_action_slots'],s['expected_inference_calls_if_all_target_routes_selected'])==(3200,3232,3136),'budget')
    aa=anchor_list();need(len(aa)==70 and [a['id']for a in aa]==s['anchor_ids'],'anchors schedule')
    need(digest((ROOT/'data/anchors.json').read_bytes())==s['anchors_sha256'],'anchors digest')
    # 접두 이력 유효성은 독립 규칙 검사로 재계산한다.
    from audit_model import stage_shape
    from audit_rows087 import step_check
    for a in aa:
        d=data(a['request_body']);p=next(p for p in s['problems'] if p['id']==a['problem_id']);path=s['reference_plans'][p['id']][s['reference_conditions'][int(a['route_kind']=='deep')]]
        need(same(d['problem'],p) and d['provided_route_plan']['rule_ids']==path,'anchor task')
        need(d['operation']['index']==a['rule_position']+1 and d['operation']['requested_rule_id']==a['rule_id']==path[a['rule_position']],'anchor operation')
        need(digest(dump(a['request_body']))==a['source_request_sha256'],'anchor request bytes')
        need(len(d['history'])==a['rule_position']+1,'prefix length')
        for style in s['probe_arms']:
            hs,table=renamed(d['history'],style);ns=[]
            for j,h in enumerate(hs):
                x=load(h['content']);need(stage_shape('facts' if j==0 else 'rule',x),'prefix schema')
                if j==0:
                    ns=x['nodes'];need(sorted(n['atom']for n in ns)==sorted(p['facts']) and len(set(n['id']for n in ns))==len(ns),'prefix facts')
                    need(all(n['rule'] is None and not n['parents'] for n in ns),'prefix fact shape')
                else:
                    need(step_check(p,ns,x['node'],path[j-1])['valid'],'renamed prefix invalid');ns.append(x['node'])

def independent_summary(plan,records,raws,state):
    from audit_rows088 import independent_rows
    from tables088 import aggregate
    rows,statuses,usage=independent_rows(plan,records,raws)
    return aggregate(plan,rows,statuses,usage,state)
