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
            variants=['base']
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
    result.update(contract='v078-summary-r1',provenance=plan['provenance'],state=state,
        observed_inference_calls=len(usages),skipped_action_slots=dict(sorted(skips.items())),
        response_statuses=dict(sorted(outcomes.items())),usage=u)
    return result



def independent_aggregate(rows, state, spec):
    """행 판정을 독립적으로 재집계한다. 생산 집계 함수/결과는 참조하지 않는다."""
    main=[]; ref=[]; pairmap={}
    for r in rows:
        if r['arm']=='reference':ref.append(r)
        else:
            main.append(r)
            pairmap.setdefault(r['pair_id'],{})[r['condition']]=r
    pairs=[]
    for key in sorted(pairmap):
        pair=pairmap[key];need(set(pair)=={'shallow','deep'},'paired directions')
        ordered=[pair['deep'],pair['shallow']]
        end_values=[x['trace_success'] for x in ordered]
        select_values=[x['selection_success'] for x in ordered]
        d={};k={}
        for x in ordered:
            d[x['condition']]=x['graph_metric']['actual_D'] if x['graph_metric'] is not None else None
            k[x['condition']]=x['actual_goal_support_rule_count']
        both=lambda vals: None if None in vals else False not in vals
        pair_select=both(select_values)
        pairs.append(dict(pair_id=key,variant='base',problem_id=ordered[0]['problem_id'],family=ordered[0]['family'],
            trial_ids=[r['trial_id'] for r in ordered],success=both(end_values),selection_success=pair_select,
            same_selected_candidate=None if pair_select is None else pair['deep']['selected_candidate_id']==pair['shallow']['selected_candidate_id'],
            actual_Ds=d,actual_rule_counts=k,
            observed_D_increase=None if d['deep'] is None or d['shallow'] is None else d['deep']-d['shallow']>0))
    def metric(rs,key):return tally([r[key] for r in rs])
    def grouped(m,c,p):
        return dict(model_selection=metric(m,'selection_success'),selection_pairs=metric(p,'selection_success'),
            model_generator_fidelity=metric(m,'generator_success'),model_trace=metric(m,'trace_success'),
            model_pairs=metric(p,'success'),reference_construction=metric(c,'control_success'))
    scores=grouped(main,ref,pairs)
    mc=scores['model_trace'];cc=scores['reference_construction'];gc=scores['model_generator_fidelity'];pc=scores['model_pairs']
    gate=None;generator_gate=None
    if state=='complete' and mc['unmeasured']==0 and cc['unmeasured']==0 and len(main)==32 and len(ref)==16:
        gate=(mc['successes'],cc['successes'],pc['successes'])==(32,16,16)
    if state=='complete' and gc['measured']==32 and cc['measured']==16:
        generator_gate=gc['successes']==32 and cc['successes']==16
    by={}
    for field in ['problem_id','candidate_order_index','condition','family']:
        bins={}
        for r in main:bins.setdefault(str(r[field]),[]).append(r['trace_success'])
        by[field]={key:tally(bins[key]) for key in sorted(bins)}
    local=[c for r in rows for c in r['parent_count_checks']]
    arm=dict(initial_fact_stage=metric(rows,'initial_fact_success'),rule_parent_counts=metric(local,'count_valid'),
        rule_semantic_steps=metric(local,'step_valid'),
        count_correct_but_step_wrong=len([c for c in local if c['count_valid'] is True and c['step_valid'] is False]),
        model_generator_fidelity=gc,model_target_structure=metric(main,'target_structure_success'),
        model_trace=mc,model_pairs=pc,reference_construction=cc,generator_baseline_ready=generator_gate,
        end_to_end_baseline_ready=gate,model_trace_by=by)
    strata={}
    for family in ['equal_rule_count','inverted_rule_count']:
        m=[r for r in main if r['family']==family];c=[r for r in ref if r['family']==family];ps=[p for p in pairs if p['family']==family]
        strata[family]={'distinct_structural_problems':len(set(r['problem_id'] for r in m)),**grouped(m,c,ps)}
    problems={}
    for problem in spec['problems']:
        pid=problem['id'];problems[pid]={'design':spec['problem_metadata'][pid],
            **grouped([r for r in main if r['problem_id']==pid],[r for r in ref if r['problem_id']==pid],[p for p in pairs if p['problem_id']==pid])}
    return dict(shared_model_selection=scores['model_selection'],shared_selection_pairs=scores['selection_pairs'],
        arms={'base':arm},strata=strata,problem_results=problems,end_to_end_baseline_ready=gate,
        decision='close_frozen_structural_batch' if state=='complete' else 'preserve_incomplete_batch_no_retry',
        scientific_scope=dict(distinct_structural_problems=4,model_trials=32,reference_trials=16,
            name_order_effect_isolated=False,independent_population_generalization=False,internal_control_measured=False,A_measured=False,M_measured=False),
        pairs=pairs,trials=rows)


def independent_report(s):
    """고정 보고 서식을 독립 집계에 적용한다. 생산 render는 호출하지 않는다."""
    def cell(c):return str(c['successes'])+'/'+str(c['assigned'])+' (실패 '+str(c['failures'])+', 미측정 '+str(c['unmeasured'])+')'
    text='# v078 P03 — 규칙 수와 D를 분리한 새 구조 확인\n\n'
    text+=f"실행 상태: `{s['state']}` / 출처: `{s['provenance']}` / 관측 추론 응답: {s['observed_inference_calls']}\n"
    text+=f"배치 결정: `{s['decision']}` / 전수 공학 기준: `{s['end_to_end_baseline_ready']}`\n\n"
    text+='**모든 종단·pair는 초기 사실, 각 단계, 실제 전체 graph, 선택 경로 충실성, 요구 D를 포함한 동일 기준이다. 대응표 계약은 없다.**\n\n'
    text+='|지표|base|\n|---|---:|\n'
    a=s['arms']['base']
    items=[('모델 경로 선택',s['shared_model_selection']),('양방향 선택 쌍',s['shared_selection_pairs']),
        ('선택 경로 생성 충실성',a['model_generator_fidelity']),('D 종단 성공',a['model_trace']),
        ('양방향 D 종단 쌍',a['model_pairs']),('실험자 지정 참조 구성',a['reference_construction'])]
    for name,c in items:text+='|'+name+'|'+cell(c)+'|\n'
    text+='\n## 규칙 수-D 관계별 결과\n\n|설계층|실제 구조 수|선택|종단|양방향 종단|참조|\n|---|---:|---:|---:|---:|---:|\n'
    for f,title in [('equal_rule_count','규칙 수 동일'),('inverted_rule_count','규칙 수-D 역전')]:
        r=s['strata'][f]
        text+='|'+title+'|'+str(r['distinct_structural_problems'])+'|'
        text+='|'.join(cell(r[k]) for k in ['model_selection','model_trace','model_pairs','reference_construction'])+'|\n'
    text+='\n## 문제별 결과\n\n|문제|작은 D / 규칙 수|큰 D / 규칙 수|종단|양방향 종단|참조|\n|---|---:|---:|---:|---:|---:|\n'
    for pid in s['problem_results']:
        r=s['problem_results'][pid];m=r['design']
        text+=f"|{pid}|{m['shallow_D']} / {m['shallow_rule_count']}|{m['deep_D']} / {m['deep_rule_count']}|"
        text+='|'.join(cell(r[k]) for k in ['model_trace','model_pairs','reference_construction'])+'|\n'
    text+='\n## 판독 경계\n\n'
    text+='새 구조는 4개다. seed·후보 순서 반복 32건을 독립 문제 32개로 세지 않는다. 이름/규칙 순서는 새 고정 표현이며 그 효과를 별도로 추정하지 않는다.\n'
    text+='잘못 고른 경로도 그대로 생성했다. 선택 실패와 생성 실패는 trials에서 분리한다. 참조는 실험자 지정 경로이므로 자율 선택 성공에 합산하지 않는다.\n'
    text+='미실행·HTTP·identity·length·파싱/스키마 실패는 response_statuses 및 단계 상태에 보존한다. D가 측정되지 않으면 null이며 0으로 대체하지 않는다.\n'
    text+='전수 공학 기준은 모델 종단32/32·양방향16/16·참조16/16이다. 이 기준의 실패가 관찰된 부분 효과의 부재를 뜻하지 않는다.\n'
    text+='synthetic은 합성 HTTP/단위시험이며 실제 모델 성과가 아니다. 이 보고서는 v077 과거 점수와 새 성과를 합산하지 않는다.\n'
    text+='원문을 보정하거나 자동 재시도·추가 버전 실행을 하지 않는다. 내부 사고 깊이, A/M, 큰 모델 대비 동등성 및 비용 우월성은 이 실험의 평가 대상이 아니다.\n'
    return text
