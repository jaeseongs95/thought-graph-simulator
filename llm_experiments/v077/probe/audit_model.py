"""요청·일정·단계·집계를 독립 재구현한다. 생산 design/report/measure/stages는 사용하지 않는다."""
from copy import deepcopy
import audit_bindings
from collections import Counter
from audit_io import load,dump,digest,same,need
from audit_graph import _semantic as graph_audit, _schema_valid as graph_shape
FIELDS=('prompt_eval_count','eval_count','total_duration','prompt_eval_duration','eval_duration')


def reconstruct_schedule(s):
    ts=[]; ss=[]; aa=[]; unit=0
    for block in range(6):
        pi,si=divmod(block,2); problem=s['problems'][pi]
        entries=[('reference',si,'shallow'),('reference',si,'deep'),('model',0,'shallow'),('model',0,'deep'),('model',1,'deep'),('model',1,'shallow')]
        if si: entries=entries[::-1]
        aa.append({'kind':'metadata','id':f'b{block:02d}_before'})
        for arm,order,direction in entries:
            uid='t'+str(unit).zfill(3);unit+=1
            variants=['premise_binding','base'] if (pi+si+order+(direction=='deep'))%2 else ['base','premise_binding']
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

        if phase=='rule' and t['variant']=='premise_binding':
            existing=schema['properties']['node']
            schema['properties']={'bindings':deepcopy(s['binding_schema']), 'node':existing}
            schema['required']=['bindings','node']

        history=[]
        for pre in plan['slots']:
            if pre['id']==slot['id']:break
            if pre['trial_id']==t['id'] and pre['stage']!='select' and pre['id'] in raws:
                history.append({'source_slot_id':pre['logical_id'],'content':content(raws[pre['id']])})
        index={'facts':0,'final':len(route['rule_ids'])+1}.get(phase)
        if phase=='rule':index=slot['rule_position']+1
        data={'problem':p,'selection_original':src,'provided_route_plan':route,
              'operation':{'stage':phase,'index':index,'requested_rule_id':route['rule_ids'][slot['rule_position']] if phase=='rule' else None},'history':history}
        header=s['headers']['generator']+'\n\n'+s['headers'][phase]
        if phase=='rule' and t['variant']=='premise_binding':
            header += '\n\n'+s['headers']['binding_rule']
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
    valid=audit_bindings.shape(x) if phase=='rule' and variant=='premise_binding' else stage_shape(phase,x)
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
        if t['variant']=='premise_binding':
            for action in sequence:
                sid=action['id'];x=objs[sid]
                if action['stage']=='rule' and stat[sid] in ('ok','invalid_schema'):
                    okay=type(x) is dict and 'node' in x and graph_shape({'nodes':[x['node']],'final_node_id':'check'})
                    node_stat[sid]='ok' if okay else 'invalid_schema'
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
        binding_checks=audit_bindings.inspect(p,sequence,objs,node_stat,stat) if t['variant']=='premise_binding' else []
        binding_success=(all(x['valid'] is True for x in binding_checks) if binding_checks and not any(x['valid'] is None for x in binding_checks) else None)
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
        if t['variant']=='premise_binding':genok=None if genok is None or binding_success is None else genok and binding_success
        graph_only_trace=None if selsuccess is None or graph_only_gen is None else selsuccess and graph_only_gen and targetok
        trace=None if selsuccess is None or genok is None else selsuccess and genok and targetok
        control=None if t['arm']!='reference' or genok is None else genok and targetok
        rows.append({'trial_id':t['id'],'unit_id':t['unit_id'],'variant':t['variant'],'base_pair_id':t['base_pair_id'],'initial_fact_success':checks[0]['valid'] if checks else None,'arm':t['arm'],'problem_id':p['id'],'seed':t['seed'],'candidate_order_index':t['candidate_order_index'],
            'condition':t['condition'],'pair_id':t['pair_id'],'selector_status':selst,
            'selected_candidate_id':None if route is None else route['candidate_id'],'selected_rule_ids':None if route is None else route['rule_ids'],
            'selected_route_D':selected,'target_D':target,'selection_success':selsuccess,
            'generator_stage_statuses':[{'id':a['id'],'status':stat[a['id']]} for a in sequence],
            'node_stage_statuses':[{'id':a['id'],'status':node_stat[a['id']]} for a in sequence],'binding_checks':binding_checks,'binding_success':binding_success,'graph_only_generator_success':graph_only_gen,'graph_only_trace_success':graph_only_trace if t['arm']=='model' else None,'step_checks':checks,'parent_count_checks':pc,'step_success':stepok,'graph':g,'graph_metric':gm,'route_fidelity':fidelity,
            'generator_success':genok,'target_structure_success':targetok,'trace_success':trace if t['arm']=='model' else None,'control_success':control})
    result=independent_aggregate(rows,state)
    u={}
    for k in FIELDS:
        values=[x.get(k) for x in usages];u[k]={'observed_sum':sum(x for x in values if x is not None),'missing_records':sum(x is None for x in values)}
    result.update(contract='v077-summary-r1',provenance=plan['provenance'],state=state,
        observed_inference_calls=len(usages),skipped_action_slots=dict(sorted(skips.items())),
        response_statuses=dict(sorted(outcomes.items())),usage=u)
    return result


def cross_tab(xs):
    a=b=c=d=n=0
    for left,right in xs:
        if left is None or right is None:n+=1
        elif left is True and right is True:a+=1
        elif left is True:b+=1
        elif right is True:c+=1
        else:d+=1
    return dict(assigned=a+b+c+d+n,measured=a+b+c+d,both_success=a,base_only=b,premise_binding_only=c,both_fail=d,unmeasured=n)


def independent_aggregate(rows,state):
    buckets={'base':[],'premise_binding':[]};units={}
    for row in rows:
        buckets[row['variant']].append(row);units.setdefault(row['unit_id'],{})[row['variant']]=row
    arms={};allpairs=[]
    for variant,rs in buckets.items():
        m=list(filter(lambda r:r['arm']=='model',rs));c=list(filter(lambda r:r['arm']=='reference',rs));groups={}
        for r in m:groups.setdefault(r['pair_id'],[]).append(r)
        ps=[]
        for pid in sorted(groups):
            rr=sorted(groups[pid],key=lambda r:r['condition']);vals=[r['trace_success'] for r in rr]
            success=None if any(v is None for v in vals) else all(vals)
            ps.append(dict(pair_id=pid,variant=variant,trial_ids=[r['trial_id'] for r in rr],success=success,
                actual_Ds={r['condition']:None if r['graph_metric'] is None else r['graph_metric']['actual_D'] for r in rr}))
        allpairs.extend(ps)
        mc=tally([r['trace_success'] for r in m]);gc=tally([r['generator_success'] for r in m]);cc=tally([r['control_success'] for r in c]);pc=tally([r['success'] for r in ps])
        measured=state=='complete' and mc['measured']==24 and cc['measured']==12
        by={}
        for key in ('problem_id','candidate_order_index','condition'):
            by[key]={}
            for value in sorted(set(r[key] for r in m),key=str):by[key][str(value)]=tally([r['trace_success'] for r in m if r[key]==value])
        arms[variant]=dict(initial_fact_stage=tally([r['initial_fact_success'] for r in rs]),
            rule_parent_counts=tally([d['count_valid'] for r in rs for d in r['parent_count_checks']]),
            rule_semantic_steps=tally([d['step_valid'] for r in rs for d in r['parent_count_checks']]),
            count_correct_but_step_wrong=len([d for r in rs for d in r['parent_count_checks'] if d['count_valid'] is True and d['step_valid'] is False]),
            binding_steps=tally([d['valid'] for r in rs for d in r['binding_checks']]),
            graph_valid_binding_failed=len([r for r in rs if r['graph_only_generator_success'] is True and r['binding_success'] is False]),
            model_graph_only_generator=tally([r['graph_only_generator_success'] for r in m]),
            model_graph_only_trace=tally([r['graph_only_trace_success'] for r in m]),
            model_generator_fidelity=gc,
            model_target_structure=tally([r['target_structure_success'] for r in m]),model_trace=mc,model_pairs=pc,reference_construction=cc,
            generator_baseline_ready=(gc['successes']==24 and cc['successes']==12) if state=='complete' and gc['measured']==24 and cc['measured']==12 else None,
            end_to_end_baseline_ready=(mc['successes']==24 and cc['successes']==12 and pc['successes']==12) if measured else None,model_trace_by=by)
    unique=[u['base'] for u in units.values() if u['base']['arm']=='model'];chosen=tally([r['selection_success'] for r in unique])
    sp={}
    for r in unique:sp.setdefault(r['base_pair_id'],[]).append(r['selection_success'])
    selpairs=[None if any(v is None for v in vs) else all(vs) for key,vs in sorted(sp.items())]
    comparisons=[]
    for uid in sorted(units):
        a=units[uid]['base'];b=units[uid]['premise_binding']
        comparisons.append(dict(unit_id=uid,arm=a['arm'],problem_id=a['problem_id'],base_trial_id=a['trial_id'],premise_binding_trial_id=b['trial_id'],
            initial_fact=[a['initial_fact_success'],b['initial_fact_success']],generator=[a['generator_success'],b['generator_success']],
            trace=[a['trace_success'],b['trace_success']],control=[a['control_success'],b['control_success']]))
    effects={}
    for name,metric,arm in [('initial_fact_all','initial_fact',None),('model_generator','generator','model'),('model_trace','trace','model'),('reference_construction','control','reference')]:
        effects[name]=cross_tab([r[metric] for r in comparisons if arm is None or r['arm']==arm])
    ga=arms['base']['end_to_end_baseline_ready'];gb=arms['premise_binding']['end_to_end_baseline_ready']
    gate=None if ga is None or gb is None else ga or gb
    preferred=('base' if ga else 'premise_binding') if gate is True else None
    if gate is None:decision='incomplete_or_unmeasured_no_retry'
    elif gate:decision='close_batch_limited_end_to_end_baseline_plan_P03'
    else:decision='close_batch_partial_no_automatic_followup'
    return dict(shared_model_selection=chosen,shared_selection_pairs=tally(selpairs),
        selection_trace_ceiling=dict(successful_trials=chosen['successes'],successful_pairs=sum(v is True for v in selpairs),
            note='이번 실제 선택의 측정된 범위에서 두 생성기 공통 종단 상한. 미측정 선택을 오답으로 채운 상한 아님.'),
        arms=arms,paired_effects=effects,end_to_end_baseline_ready=gate,preferred_generator_for_future_contract=preferred,
        decision=decision,trials=rows,pairs=allpairs,within_unit_comparisons=comparisons)


def independent_report(s):
    text='# v077 동일 선택 공유 · 전제 대응표 종단 대조\n\n'
    text+=f"증거 구분: **{s['provenance']}** / 실행 상태: **{s['state']}**\n\n"
    text+=f"관측 추론: {s['observed_inference_calls']} / 최대 404. 조건부 생략: {s['skipped_action_slots']}\n\n"
    text+=f"공유 선택: {s['shared_model_selection']['successes']}/{s['shared_model_selection']['assigned']}. 두 생성기 결과를 48개 독립 선택으로 세지 않는다.\n\n"
    text+='|항목|base 성공/배정|premise_binding 성공/배정|\n|---|---:|---:|\n'
    titles=['초기 사실 단계','선택 경로 구성 충실성','노드·단계 기준 종단(대응표 별도)','유효한 목표 D 구조','선택부터 종단까지','양방향 종단 쌍','별도 참조 구성']
    keys=['initial_fact_stage','model_generator_fidelity','model_graph_only_trace','model_target_structure','model_trace','model_pairs','reference_construction']
    for title,key in zip(titles,keys):
        a=s['arms']['base'][key];b=s['arms']['premise_binding'][key]
        text+=f"|{title}|{a['successes']}/{a['assigned']}|{b['successes']}/{b['assigned']}|\n"
    for v in ['base','premise_binding']:
        a=s['arms'][v];p=a['rule_parent_counts'];q=a['rule_semantic_steps']
        text+=f"{v} 규칙 진단: 부모 수 {p['successes']}/{p['assigned']}, 규칙 단계 {q['successes']}/{q['assigned']}, 수는 맞지만 단계 실패 {a['count_correct_but_step_wrong']}건. 단계 수는 독립 문제 수가 아니다.\n"
    for v in ['base','premise_binding']:
        a=s['arms'][v];b=a['binding_steps']
        text+=f"{v} 대응표 검사: {b['successes']}/{b['assigned']}, node·단계는 맞고 대응표가 틀린 증명 {a['graph_valid_binding_failed']}건. base에는 대응표 의무가 없다.\n"
    text+=f"\n전체 공학적 기준: {s['end_to_end_baseline_ready']} / 결정: `{s['decision']}`\n\n"
    for variant in ['base','premise_binding']:
        a=s['arms'][variant]
        text+=f"{variant}: 생성 기준 {a['generator_baseline_ready']}, 종단 기준 {a['end_to_end_baseline_ready']}, 본실험 미측정 {a['model_trace']['unmeasured']}, 참조 미측정 {a['reference_construction']['unmeasured']}\n"
    text+='\n## 같은 선택에 대한 종단 짝비교\n\n|둘 다 성공|base만 성공|premise_binding만 성공|둘 다 실패|미측정|\n|---:|---:|---:|---:|---:|\n'
    e=s['paired_effects']['model_trace'];text+='|'+ '|'.join(str(e[k]) for k in ['both_success','base_only','premise_binding_only','both_fail','unmeasured'])+'|\n\n'
    text+='두 군 모두 사실 전용 스키마와 content-only 이력을 사용한다. 새 군만 모델 작성 전제 대응표를 추가한다. 부모 수·정답 부모 ID는 고정하지 않는다.\n'
    text+='참조 대조는 실험자가 경로를 지정했다. 선택 성공에 합산하지 않는다.\n'
    text+='선택 오류 뒤 생성만 맞아도 종단 성공이 아니다. 실제 graph의 D와 단계 계약을 함께 확인한다.\n'
    text+='공유 선택과 두 생성 경로는 독립 표본이 아니다. 3개 개발 문제이며 새 구조 일반화·A/M·비용 우월성은 미측정이다.\n'
    text+='한 배치 후 종료한다. 결과에 따라 자동 재시도·문구/공백/seed 진단을 추가하지 않는다.\n\n'
    text+='## 원문별 판정\n\n|시행|군|문제|요구|선택|초기 사실|실제 D|종단/대조|\n|---|---|---|---|---|---|---:|---|\n'
    for r in s['trials']:
        d=None if r['graph_metric'] is None else r['graph_metric']['actual_D'];val=r['control_success'] if r['arm']=='reference' else r['trace_success']
        text+=f"|{r['trial_id']}|{r['arm']}|{r['problem_id']}|{r['condition']}|{r['selected_candidate_id']}|{r['initial_fact_success']}|{d}|{val}|\n"
    return text
