"""요청·일정·단계·집계를 독립 재구현한다. 생산 design/report/measure/stages는 사용하지 않는다."""
from copy import deepcopy
from collections import Counter
from audit_io import load,dump,digest,same,need
from audit_graph import _semantic as graph_audit, _schema_valid as graph_shape
FIELDS=('prompt_eval_count','eval_count','total_duration','prompt_eval_duration','eval_duration')


def reconstruct_schedule(s):
    ts=[]; ss=[]; aa=[]; unit=0
    for block in range(len(s['problems']) * len(s['seeds'])):
        pi,si=divmod(block,len(s['seeds'])); problem=s['problems'][pi]
        entries=[('reference',si,'shallow'),('reference',si,'deep'),('model',0,'shallow'),('model',0,'deep'),('model',1,'deep'),('model',1,'shallow')]
        if si: entries=entries[::-1]
        aa.append({'kind':'metadata','id':f'b{block:02d}_before'})
        for arm,order,direction in entries:
            uid='t'+str(unit).zfill(3);unit+=1
            variants=list(s['generator_variants'])
            if (pi+si+order+int(direction=='deep'))%2:variants=variants[::-1]
            sel=uid+'_select' if arm=='model' else None
            if sel:
                ss.append({'id':sel,'trial_id':uid+'_'+variants[0],'logical_id':sel,'stage':'select','rule_position':None})
                aa.append({'kind':'slot','id':sel})
            for variant in variants:
                tid=uid+'_'+variant;kind=['shallow','deep'].index(direction)
                base=f'p{pi}_s{si}_o{order}' if arm=='model' else None
                control=s['candidate_ids'][s['candidate_orders'][order].index(kind)] if arm=='reference' else None
                ts.append({'id':tid,'unit_id':uid,'variant':variant,'selection_slot_id':sel,'block':block,
                    'arm':arm,'problem_id':problem['id'],'seed':s['seeds'][si],'candidate_order_index':order,
                    'condition':direction,'pair_id':base+'_'+variant if base else None,'base_pair_id':base,'control_candidate_id':control})
                lengths=[len(x) for x in s['reference_plans'][problem['id']].values()]
                n=max(lengths) if arm=='model' else len(s['reference_plans'][problem['id']][s['reference_conditions'][kind]])
                phases=['facts']+['rule']*n+['final']
                for index,phase in enumerate(phases):
                    pos=index-1 if phase=='rule' else None
                    suffix='rule_'+str(pos).zfill(2) if phase=='rule' else phase
                    sid=tid+'_'+suffix
                    ss.append({'id':sid,'trial_id':tid,'logical_id':uid+'_'+suffix,'stage':phase,'rule_position':pos})
                    aa.append({'kind':'slot','id':sid})
        aa.append({'kind':'metadata','id':f'b{block:02d}_after'})
    return ts,ss,aa


def content(raw):
    try:
        x=load(raw)
        if isinstance(x,dict) and isinstance(x.get('message'),dict) and isinstance(x['message'].get('content'),str):return x['message']['content']
    except (ValueError,UnicodeError):pass
    return None


def context(plan,t,raws):
    s=plan['protocol'];p=next(p for p in s['problems'] if p['id']==t['problem_id'])
    cs=[]
    for i,ridx in enumerate(s['candidate_orders'][t['candidate_order_index']]):
        ids=s['reference_plans'][p['id']][s['reference_conditions'][ridx]]
        cs.append({'candidate_id':s['candidate_ids'][i],'rules':[deepcopy(next(r for r in p['rules'] if r['id']==rid)) for rid in ids]})
    if t['arm']=='model':
        sid=t['selection_slot_id'];raw=raws.get(sid)
        src={'source_type':'model','source_id':sid,'content':None if raw is None else content(raw)}
    else:src={'source_type':'experimenter_reference','source_id':t['unit_id']+'_reference','content':dump({'candidate_id':t['control_candidate_id']}).decode()}
    route=None
    try:
        value=load(src['content']) if src['content'] is not None else None
        if type(value) is dict and set(value)=={'candidate_id'}:
            matches=[c for c in cs if c['candidate_id']==value['candidate_id']]
            if len(matches)==1:route={'candidate_id':matches[0]['candidate_id'],'rule_ids':[r['id'] for r in matches[0]['rules']]}
    except (ValueError,UnicodeError):pass
    return p,cs,src,route


def expected_request(plan,slot,raws):
    t=next(t for t in plan['trials'] if t['id']==slot['trial_id']);s=plan['protocol'];phase=slot['stage']
    p,cs,src,route=context(plan,t,raws)
    if phase!='select':
        if route is None:return 'unmappable_selection',None
        if phase=='rule' and slot['rule_position']>=len(route['rule_ids']):return 'outside_selected_route',None
    body=deepcopy(s['api_defaults']);body['options']['seed']=t['seed']
    if phase=='select':
        schema=deepcopy(s['selector_schema']);data={'problem':{k:p[k] for k in ('facts','rules','goal')},'candidates':cs,'requested_depth':s['headers'][t['condition']]};header=s['headers']['select']
    else:
        if phase=='facts':key='nodes';prop=s['generation_schema']['properties']['nodes']
        elif phase=='rule':key='node';prop=s['generation_schema']['properties']['nodes']['items']
        else:key='final_node_id';prop=s['generation_schema']['properties']['final_node_id']
        schema={'type':'object','properties':{key:deepcopy(prop)},'required':[key],'additionalProperties':False}
        if phase=='facts':
            item=schema['properties']['nodes']['items']['properties']
            item['rule']={'type':'null'}
            item['parents']['maxItems']=0
            schema['properties']['nodes'].update(minItems=len(p['facts']),maxItems=len(p['facts']))

        history=[]
        for pre in plan['slots']:
            if pre['id']==slot['id']:break
            if pre['trial_id']==t['id'] and pre['stage']!='select' and pre['id'] in raws:
                history.append({'source_slot_id':pre['logical_id'],'content':content(raws[pre['id']])})
        index={'facts':0,'final':len(route['rule_ids'])+1}.get(phase)
        if phase=='rule':index=slot['rule_position']+1
        data={'problem':p,'selection_original':src,'provided_route_plan':route,
              'operation':{'stage':phase,'index':index,'requested_rule_id':route['rule_ids'][slot['rule_position']] if phase=='rule' else None},'history':history}
        if phase == 'rule' and t['variant'] == 'explicit_rule':
            current = data['operation']['requested_rule_id']
            matches = [dict(r) for r in p['rules'] if r['id'] == current]
            need(len(matches) == 1, 'current rule uniquely identified')
            data['operation']['requested_rule'] = deepcopy(matches[0])
        header=s['headers']['generator']+'\n\n'+s['headers'][phase]
    text=header+'\nJSON 객체 하나만 출력한다. 출력 형식(JSON Schema):\n'+dump(schema).decode()+'\n\ninput: '+dump(data).decode()
    body['messages']=[{'role':'user','content':text}];body['format']=schema
    return None,dump(body)


def stage_shape(phase,x):
    if not isinstance(x,dict):return False
    if phase=='select':return set(x)=={'candidate_id'} and x['candidate_id'] in ('route_0','route_1')
    if phase=='facts':return set(x)=={'nodes'} and graph_shape({'nodes':x['nodes'],'final_node_id':'check'})
    if phase=='rule':return set(x)=={'node'} and graph_shape({'nodes':[x['node']],'final_node_id':'check'})
    if phase=='final':return set(x)=={'final_node_id'} and isinstance(x['final_node_id'],str) and 1<=len(x['final_node_id'])<=128
    return False


def decode(rec,raw,spec,phase,variant=None):
    if rec is None:return 'not_executed',None,{}
    if rec['kind']=='skip':return 'skipped_'+rec['reason'],None,{}
    if rec['error'] is not None:return 'transport_error',None,{}
    if rec['http_status']!=200:return 'http_error',None,{}
    try:o=load(raw)
    except (ValueError,UnicodeError):return 'invalid_outer_json',None,{}
    if type(o) is not dict:return 'invalid_outer_schema',None,{}
    u={k:o[k] if type(o.get(k)) is int and o[k]>=0 else None for k in FIELDS}
    if o.get('model')!=spec['model']:return 'identity_error',None,u
    if type(o.get('eval_count')) is int and o['eval_count']>spec['num_predict']:return 'generation_budget_exceeded',None,u
    if o.get('done_reason')=='length':return 'length_termination',None,u
    if o.get('done') is not True or o.get('done_reason')!='stop':return 'incomplete_response',None,u
    m=o.get('message')
    if type(m) is not dict or m.get('role')!='assistant' or m.get('tool_calls') or type(m.get('content')) is not str:return 'invalid_outer_schema',None,u
    try:x=load(m['content'])
    except (ValueError,UnicodeError):return 'invalid_json',None,u
    valid=stage_shape(phase,x)
    if not valid:return 'invalid_schema',x,u
    return 'ok',x,u


def route_depth(p,ids):
    by={r['id']:r for r in p['rules'] if r['id'] in ids}
    need(len(by)==len(ids),'reference unique rules')
    def depth(atom,stack):
        if atom in p['facts']:return 0
        candidates=[r for r in by.values() if r['conclusion']==atom]
        need(len(candidates)==1 and atom not in stack,'unambiguous acyclic path')
        return 1+max(depth(a,stack|{atom}) for a in candidates[0]['premises'])
    return depth(p['goal'],set())


def steps(p,ordered,objects,status):
    out=[]
    for i,o in enumerate(ordered):
        phase=o['stage'];sid=o['id'];errs=[]
        if any(status[a['id']]!='ok' for a in ordered[:i+1]):
            out.append({'id':sid,'stage':phase,'valid':None,'error_codes':None});continue
        x=objects[sid]
        if phase=='facts':
            nodes=x['nodes']
            if sorted(n['atom'] for n in nodes)!=sorted(p['facts']):errs.append('initial_fact_multiset')
            if any(n['rule'] is not None or n['parents']!=[] for n in nodes):errs.append('initial_fact_shape')
            if len({n['id'] for n in nodes})!=len(nodes):errs.append('duplicate_node_id')
        else:
            nodes=objects[ordered[0]['id']]['nodes']+[objects[a['id']]['node'] for a in ordered[1:i]]
            byid={n['id']:n for n in nodes}
            if phase=='final':
                target=byid.get(x['final_node_id'])
                if target is None:errs.append('missing_final_node')
                elif target['atom']!=p['goal']:errs.append('wrong_goal')
            else:
                n=x['node'];r=next((r for r in p['rules'] if r['id']==n['rule']),None)
                if n['id'] in byid:errs.append('duplicate_node_id')
                if n['rule']!=o['requested_rule_id']:errs.append('requested_rule_mismatch')
                if r is None:errs.append('unregistered_rule')
                else:
                    if n['atom']!=r['conclusion']:errs.append('wrong_atom')
                    if any(a not in byid for a in n['parents']):errs.append('missing_parent')
                    elif sorted(byid[a]['atom'] for a in n['parents'])!=sorted(r['premises']):errs.append('premise_counter_mismatch')
        out.append({'id':sid,'stage':phase,'valid':not errs,'error_codes':sorted(set(errs))})
    return out


def tally(vs):
    yes=no=missing=0
    for v in vs:
        if v is True:yes+=1
        elif v is False:no+=1
        else:missing+=1
    return {'assigned':yes+no+missing,'measured':yes+no,'successes':yes,'failures':no,'unmeasured':missing}


def independent_summary(plan,records,raws,state):
    spec=plan['protocol'];stat={};objs={};usages=[];outcomes={};skips={};rows=[]
    for a in plan['slots']:
        sid=a['id'];r=records.get(sid)
        st,x,u=decode(r,raws.get(sid,b''),spec,a['stage'],next(t['variant'] for t in plan['trials'] if t['id']==a['trial_id']));stat[sid]=st;objs[sid]=x
        if r is not None and r['kind']=='call':usages.append(u);outcomes[st]=outcomes.get(st,0)+1
        if r is not None and r['kind']=='skip':skips[r['reason']]=skips.get(r['reason'],0)+1
    for t in plan['trials']:
        p,cs,src,route=context(plan,t,raws)
        rd=[route_depth(p,spec['reference_plans'][p['id']][c]) for c in spec['reference_conditions']]
        target=min(rd) if t['condition']=='shallow' else max(rd)
        selected=None if route is None else route_depth(p,route['rule_ids'])
        selst=stat[t['selection_slot_id']] if t['arm']=='model' else 'experimenter_reference_not_inference'
        selsuccess=(selected==target) if selst=='ok' else None
        sequence=[]
        if route is not None:
            for a in plan['slots']:
                if a['trial_id']!=t['id'] or a['stage']=='select':continue
                if a['stage']=='rule' and a['rule_position']>=len(route['rule_ids']):continue
                sequence.append({**a,'requested_rule_id':route['rule_ids'][a['rule_position']] if a['stage']=='rule' else None})
        node_stat=dict(stat)
        checks=steps(p,sequence,objs,node_stat) if sequence else []
        pc=[]
        for op in sequence:
            if op['stage']=='rule':
                rule=next(r for r in p['rules'] if r['id']==op['requested_rule_id'])
                n=sum(1 for _ in rule['premises'])
                have=sum(1 for _ in objs[op['id']]['node']['parents']) if node_stat[op['id']]=='ok' else None
                verdict=next(c for c in checks if c['id']==op['id'])
                pc.append(dict(id=op['id'],requested_rule_id=op['requested_rule_id'],expected_count=n,
                    observed_count=have,count_valid=None if have is None else have==n,
                    step_valid=verdict['valid'],error_codes=verdict['error_codes']))
        complete=bool(sequence) and all(node_stat[a['id']]=='ok' for a in sequence)
        g=None;gm=None;stepok=None;fidelity=None;genok=None;targetok=None
        if complete:
            nodes=list(objs[sequence[0]['id']]['nodes'])
            nodes.extend(objs[a['id']]['node'] for a in sequence[1:-1])
            g={'nodes':nodes,'final_node_id':objs[sequence[-1]['id']]['final_node_id']};gm=graph_audit(p,g)
            stepok=all(c['valid'] is True for c in checks)
            fidelity=[n['rule'] for n in nodes if n['rule'] is not None]==route['rule_ids']
            if gm['strict_valid'] is not None:
                genok=stepok and gm['strict_valid'] and fidelity and gm['actual_D']==selected
                targetok=gm['strict_valid'] and gm['actual_D']==target
        graph_only_gen=genok
        graph_only_trace=None if selsuccess is None or graph_only_gen is None else selsuccess and graph_only_gen and targetok
        trace=None if selsuccess is None or genok is None else selsuccess and genok and targetok
        control=None if t['arm']!='reference' or genok is None else genok and targetok
        rows.append({'trial_id':t['id'],'unit_id':t['unit_id'],'variant':t['variant'],'base_pair_id':t['base_pair_id'],'initial_fact_success':checks[0]['valid'] if checks else None,'arm':t['arm'],'problem_id':p['id'],'seed':t['seed'],'candidate_order_index':t['candidate_order_index'],
            'condition':t['condition'],'pair_id':t['pair_id'],
            'family':spec['problem_metadata'][p['id']]['family'],
            'selected_route_rule_count':None if route is None else len(route['rule_ids']),
            'actual_goal_support_rule_count':len([n for n in g['nodes'] if n['rule'] is not None]) if gm is not None and gm['strict_valid'] is True else None,
            'selector_status':selst,
            'selected_candidate_id':None if route is None else route['candidate_id'],'selected_rule_ids':None if route is None else route['rule_ids'],
            'selected_route_D':selected,'target_D':target,'selection_success':selsuccess,
            'generator_stage_statuses':[{'id':a['id'],'status':stat[a['id']]} for a in sequence],
            'node_stage_statuses':[{'id':a['id'],'status':node_stat[a['id']]} for a in sequence],'graph_only_generator_success':graph_only_gen,'graph_only_trace_success':graph_only_trace if t['arm']=='model' else None,'step_checks':checks,'parent_count_checks':pc,'step_success':stepok,'graph':g,'graph_metric':gm,'route_fidelity':fidelity,
            'generator_success':genok,'target_structure_success':targetok,'trace_success':trace if t['arm']=='model' else None,'control_success':control})
    result=independent_aggregate(rows,state,spec)
    u={}
    for k in FIELDS:
        values=[x.get(k) for x in usages];u[k]={'observed_sum':sum(x for x in values if x is not None),'missing_records':sum(x is None for x in values)}
    result.update(contract='v079-summary-r1',provenance=plan['provenance'],state=state,
        observed_inference_calls=len(usages),skipped_action_slots=dict(sorted(skips.items())),
        response_statuses=dict(sorted(outcomes.items())),usage=u)
    accounting={g:[] for g in ['shared_selection',*spec['generator_variants']]}
    for slot in plan['slots']:
        rec=records.get(slot['id'])
        if rec is not None and rec['kind']=='call':
            variant=next(t['variant'] for t in plan['trials'] if t['id']==slot['trial_id'])
            _,_,values=decode(rec,raws.get(slot['id'],b''),spec,slot['stage'],variant)
            label='shared_selection' if slot['stage']=='select' else variant
            accounting[label].append(values)
    detail={}
    for label,items in accounting.items():
        fields={}
        for field in FIELDS:
            present=[item[field] for item in items if item.get(field) is not None]
            fields[field]={'observed_sum':sum(present),'missing_records':len(items)-len(present)}
        detail[label]={'observed_calls':len(items),'fields':fields}
    result['usage_by_group']=detail
    return result



def independent_aggregate(rows, state, spec):
    """생산 집계를 호출하지 않고 단위·군·조건으로 재구성한 뒤 비교한다."""
    units={};pairmap={}
    for r in rows:
        key=(r['arm'],r['unit_id']);units.setdefault(key,{})[r['variant']]=r
        if r['arm']=='model':pairmap.setdefault(r['pair_id'],{})[r['condition']]=r
    need(all(set(v)=={'base','explicit_rule'} for v in units.values()),'two variants per unit')
    pairs=[]
    for key in sorted(pairmap):
        d=pairmap[key];need(set(d)=={'shallow','deep'},'paired directions')
        deep,shallow=d['deep'],d['shallow'];ordered=[deep,shallow]
        both=lambda vs: None if any(v is None for v in vs) else all(v is True for v in vs)
        depths={r['condition']:None if r['graph_metric'] is None else r['graph_metric']['actual_D'] for r in ordered}
        ss=[r['selection_success'] for r in ordered];gs=[r['generator_success'] for r in ordered]
        sm=None if any(v is None for v in ss) else deep['selected_candidate_id']==shallow['selected_candidate_id']
        if both(ss) is None:pattern='unmeasured'
        elif both(ss):pattern='forward'
        elif sm:pattern='same'
        else:pattern='reversed'
        if both(gs) is None:direction='unmeasured'
        elif not both(gs):direction='invalid'
        elif depths['shallow']==depths['deep']:direction='same'
        elif depths['shallow']<depths['deep']:direction='forward'
        else:direction='reversed'
        pairs.append(dict(pair_id=key,base_pair_id=deep['base_pair_id'],variant=deep['variant'],problem_id=deep['problem_id'],family=deep['family'],
            trial_ids=[r['trial_id'] for r in ordered],success=both([r['trace_success'] for r in ordered]),selection_success=both(ss),
            same_selected_candidate=sm,selection_pattern=pattern,valid_graph_direction=direction,actual_Ds=depths,
            actual_rule_counts={r['condition']:r['actual_goal_support_rule_count'] for r in ordered},
            observed_D_increase=None if any(x is None for x in depths.values()) else depths['deep']-depths['shallow']>0))
    def score(rs,field):return tally([r[field] for r in rs])
    def hist(values):
        answer={}
        for v in values:answer[v]=answer.get(v,0)+1
        return dict(sorted(answer.items()))
    def sample(variant,arm=None,field=None,value=None):
        return [r for r in rows if r['variant']==variant and (arm is None or r['arm']==arm) and (field is None or r[field]==value)]
    def psample(variant,field=None,value=None):return [p for p in pairs if p['variant']==variant and (field is None or p[field]==value)]
    def four(variant,field=None,value=None):
        m=sample(variant,'model',field,value);c=sample(variant,'reference',field,value);p=psample(variant,field,value)
        return dict(model_generator_fidelity=score(m,'generator_success'),model_trace=score(m,'trace_success'),
                    model_pairs=score(p,'success'),reference_construction=score(c,'control_success'))
    arms={}
    for variant in ['base','explicit_rule']:
        m=sample(variant,'model');c=sample(variant,'reference');rr=m+c;pp=psample(variant)
        a=four(variant);gen=a['model_generator_fidelity'];trace=a['model_trace'];ref=a['reference_construction'];pair=a['model_pairs']
        gate=gg=None
        if state=='complete' and trace['unmeasured']==0 and ref['unmeasured']==0 and len(m)==32 and len(c)==16:
            gate=(trace['successes'],pair['successes'],ref['successes'])==(32,16,16)
        if state=='complete' and gen['measured']==32 and ref['measured']==16:
            gg=gen['successes']==32 and ref['successes']==16
        by={}
        for field in ('problem_id','candidate_order_index','condition','family'):
            bins={}
            for r in m:bins.setdefault(str(r[field]),[]).append(r['trace_success'])
            by[field]={k:tally(bins[k]) for k in sorted(bins)}
        checks=[item for r in rr for item in r['parent_count_checks']]
        cross={key:0 for key in ('selection_right_generator_right','selection_right_generator_wrong','selection_wrong_generator_right','selection_wrong_generator_wrong','unmeasured')}
        for r in m:
            k=(r['selection_success'],r['generator_success'])
            names={(True,True):'selection_right_generator_right',(True,False):'selection_right_generator_wrong',
                   (False,True):'selection_wrong_generator_right',(False,False):'selection_wrong_generator_wrong'}
            cross[names.get(k,'unmeasured')]+=1
        a.update(initial_fact_stage=score(rr,'initial_fact_success'),rule_parent_counts=score(checks,'count_valid'),rule_semantic_steps=score(checks,'step_valid'),
            count_correct_but_step_wrong=len([x for x in checks if x['count_valid'] is True and x['step_valid'] is False]),
            model_target_structure=score(m,'target_structure_success'),generator_baseline_ready=gg,end_to_end_baseline_ready=gate,
            model_trace_by=by,selection_generation_cross=cross,valid_graph_pair_directions=hist(p['valid_graph_direction'] for p in pp))
        arms[variant]=a
    selected=sample('base','model');selection_pairs=psample('base')
    for (arm,uid),rr in units.items():
        if arm=='model':
            a,b=rr['base'],rr['explicit_rule']
            for field in ('selector_status','selected_candidate_id','selected_rule_ids','selected_route_D','selection_success'):
                need(same(a[field],b[field]),'shared selector fields')
    strata={}
    for f in ['equal_rule_count','inverted_rule_count']:
        m=sample('base','model','family',f);ps=psample('base','family',f)
        strata[f]={'distinct_structural_problems':len(set(r['problem_id'] for r in m)),
                   'model_selection':score(m,'selection_success'),'selection_pairs':score(ps,'selection_success'),
                   'arms':{v:four(v,'family',f) for v in ['base','explicit_rule']}}
    problems={}
    for p in spec['problems']:
        pid=p['id'];m=sample('base','model','problem_id',pid);ps=psample('base','problem_id',pid)
        problems[pid]={'design':spec['problem_metadata'][pid],'model_selection':score(m,'selection_success'),
                       'selection_pairs':score(ps,'selection_success'),'arms':{v:four(v,'problem_id',pid) for v in ['base','explicit_rule']}}
    comparisons={}
    def matched(entries,metric):
        a=dict(assigned=len(entries),measured=0,both_success=0,base_only=0,explicit_rule_only=0,both_failure=0,unmeasured=0)
        for rr in entries:
            left,right=rr['base'][metric],rr['explicit_rule'][metric]
            if left is None or right is None:a['unmeasured']+=1
            else:
                a['measured']+=1
                key={(True,True):'both_success',(True,False):'base_only',(False,True):'explicit_rule_only',(False,False):'both_failure'}[(left,right)]
                a[key]+=1
        a['net_success_change']=a['explicit_rule_only']-a['base_only']
        return a
    for name,arm,metric in [('model_generator_fidelity','model','generator_success'),('model_trace','model','trace_success'),('reference_construction','reference','control_success')]:
        comparisons[name]=matched([rr for (kind,uid),rr in units.items() if kind==arm],metric)
    pg={}
    for p in pairs:pg.setdefault(p['base_pair_id'],{})[p['variant']]=p
    comparisons['model_pairs']=matched(list(pg.values()),'success')
    gates=[arms[v]['end_to_end_baseline_ready'] for v in ['base','explicit_rule']]
    return dict(shared_model_selection=score(selected,'selection_success'),shared_selection_pairs=score(selection_pairs,'selection_success'),
        shared_selection_patterns=hist(p['selection_pattern'] for p in selection_pairs),
        arms=arms,strata=strata,problem_results=problems,paired_comparisons=comparisons,
        end_to_end_baseline_ready=None if None in gates else all(gates),
        decision='close_frozen_generator_diagnostic' if state=='complete' else 'preserve_incomplete_batch_no_retry',
        scientific_scope=dict(distinct_structural_problems=4,new_independent_structural_problems=0,exposed_diagnostic_set=True,
            shared_model_selections=32,model_trials_per_variant=32,reference_trials_per_variant=16,selector_changed=False,parent_answers_supplied=False,
            independent_population_generalization=False,internal_control_measured=False,A_measured=False,M_measured=False),pairs=pairs,trials=rows)


def independent_report(s):
    def cell(d):return f"{d['successes']}/{d['assigned']} (실패 {d['failures']}, 미측정 {d['unmeasured']})"
    vs=['base','explicit_rule']
    lines=['# v079 — 현재 규칙 명시의 짝대조', '',
           f"실행 상태: `{s['state']}` / 출처: `{s['provenance']}` / 관측 추론 응답: {s['observed_inference_calls']}",
           f"배치 결정: `{s['decision']}`",'',
           '**H01-H04는 v078에서 결과를 본 진단 문제다. 새 holdout 성과가 아니다. 선택기는 동일하며, rule 단계의 입력에 현재 규칙 객체만 추가한다.**','',
           '공유 경로 선택: '+cell(s['shared_model_selection'])+' / 공유 양방향 선택: '+cell(s['shared_selection_pairs']),
           '공유 선택 패턴: '+dump(s['shared_selection_patterns']).decode('utf-8'),'',
           '|지표|base|explicit_rule|','|---|---:|---:|']
    for title,key in [('선택 경로 전체 생성 충실성','model_generator_fidelity'),('요구 D 종단','model_trace'),('양방향 D 종단 쌍','model_pairs'),('실험자 지정 참조 구성','reference_construction'),('초기 사실','initial_fact_stage'),('개별 규칙 단계','rule_semantic_steps')]:
        lines.append('|'+title+'|'+'|'.join(cell(s['arms'][v][key]) for v in vs)+'|')
    for v in vs:
        a=s['arms'][v];lines += ['',f"{v}: 생성 전수 기준 `{a['generator_baseline_ready']}` / D 종단 전수 기준 `{a['end_to_end_baseline_ready']}`",
            '유효 graph 쌍 방향: '+dump(a['valid_graph_pair_directions']).decode('utf-8')]
    lines += ['', '## 같은 단위의 짝비교','', '|지표|배정|관측 짝|둘 다 성공|base만|명시군만|둘 다 실패|미측정|순증|','|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for k in ['model_generator_fidelity','model_trace','reference_construction','model_pairs']:
        c=s['paired_comparisons'][k];lines.append('|'+k+'|'+'|'.join(str(c[f]) for f in ['assigned','measured','both_success','base_only','explicit_rule_only','both_failure','unmeasured','net_success_change'])+'|')
    lines += ['', '## 문제별 결과','', '|문제|생성군|선택 경로 생성|D 종단|양방향|참조|','|---|---|---:|---:|---:|---:|']
    for pid,r in s['problem_results'].items():
        for v in vs:lines.append('|'+pid+'|'+v+'|'+'|'.join(cell(r['arms'][v][k]) for k in ['model_generator_fidelity','model_trace','model_pairs','reference_construction'])+'|')
    lines += ['', '## 규칙 수-D 관계별 결과','', '|관계|군|실제 구조 수|생성|종단|양방향|참조|','|---|---|---:|---:|---:|---:|---:|']
    for f,r in s['strata'].items():
        for v in vs:lines.append('|'+f+'|'+v+'|'+str(r['distinct_structural_problems'])+'|'+'|'.join(cell(r['arms'][v][k]) for k in ['model_generator_fidelity','model_trace','model_pairs','reference_construction'])+'|')
    lines += ['', '## 판독 경계','',
        '생성 충실성은 초기 사실·모든 단계·전체 graph·선택 경로·실제 D를 검사한다. D 종단은 여기에 요구 방향 일치를 추가한다. 마지막 정답만 맞으면 성공으로 세지 않는다.',
        'forward/reversed/same은 두 선택 경로 증명 모두 유효할 때의 실제 D 방향이다. invalid는 증명 실패, unmeasured는 미관측이다. 역방향 쌍을 성공에 합산하지 않는다.',
        '같은 선택을 두 군에 전달했으므로 선택 분모는32다. 참조는 군당16건이며 모델의 자율 선택 성공에 합산하지 않는다. 새 독립 구조는0개다.',
        '명시군은 이미 문제에 있는 현재 규칙을 다시 보여준다. 호스트는 정답 부모 ID·binding·깊이를 주지 않고 원응답을 수정하지 않는다. 이 대조는 입력 중복/가시성 효과이며 내부 원인 판별이 아니다.',
        '미실행·HTTP·identity·length·파싱/스키마 상태를 따로 보존한다. 측정되지 않은 D는 null이다. 순증은 관측된 짝에서만 계산하며 미측정이0일 때만 전체 배치 순증과 같다.',
        '전수 기준은 각 군에서 모델 종단32/32·양방향16/16·참조16/16이다. 실패해도 실제 부분 성공은 보존한다. 생성 개선만으로 선택 제어/종단 제어가 회복됐다고 선언하지 않는다.',
        '계측 usage_by_group은 공유 선택과 두 생성군을 분리한다. 누락 수를 함께 읽는다. 서버 duration 합은 wall-clock 또는 일반적인 비용 비율이 아니다.',
        '이 배치가 끝나면 진단 분기를 닫는다. 성과에 관계없이 자동 재시도·추가 제약·새 버전·모델 다운로드/갱신/서버 시작은 없다.',
        'synthetic은 합성 실행/소프트웨어 시험이며 실제 모델 연구 성과가 아니다. v078의 원 evidence와 과거 점수는 변경하거나 합산하지 않는다.', '']
    return '\n'.join(lines)
