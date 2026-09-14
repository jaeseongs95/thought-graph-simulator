"""요청·일정·단계·집계를 독립 재구현한다. 생산 design/report/measure/stages는 사용하지 않는다."""
from copy import deepcopy
from collections import Counter
from audit_io import load,dump,digest,same,need
from audit_graph import _semantic as graph_audit, _schema_valid as graph_shape
FIELDS=('prompt_eval_count','eval_count','total_duration','prompt_eval_duration','eval_duration')


def reconstruct_schedule(s):
    ts=[];ss=[];aa=[]
    for block in range(6):
        pi,si=divmod(block,2);p=s['problems'][pi]
        combinations=[('reference',si,'shallow'),('reference',si,'deep'),('model',0,'shallow'),('model',0,'deep'),('model',1,'deep'),('model',1,'shallow')]
        combinations=combinations[::(-1 if si else 1)]
        aa.append({'kind':'metadata','id':f'b{block:02d}_before'})
        for arm,order,condition in combinations:
            tid='t'+str(len(ts)).zfill(3);kind=0 if condition=='shallow' else 1
            control=None
            if arm=='reference':control=s['candidate_ids'][s['candidate_orders'][order].index(kind)]
            ts.append({'id':tid,'block':block,'arm':arm,'problem_id':p['id'],'seed':s['seeds'][si],
                       'candidate_order_index':order,'condition':condition,'pair_id':f'p{pi}_s{si}_o{order}' if arm=='model' else None,'control_candidate_id':control})
            n=(max(len(r) for r in s['reference_plans'][p['id']].values()) if arm=='model'
               else len(s['reference_plans'][p['id']][s['reference_conditions'][kind]]))
            stages=(['select'] if arm=='model' else [])+['facts']+['rule']*n+['final'];rpos=0
            for phase in stages:
                pos=rpos if phase=='rule' else None
                suffix=f'rule_{pos:02d}' if phase=='rule' else phase
                sid=tid+'_'+suffix
                ss.append({'id':sid,'trial_id':tid,'stage':phase,'rule_position':pos});aa.append({'kind':'slot','id':sid})
                if phase=='rule':rpos+=1
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
        sid=t['id']+'_select';raw=raws.get(sid)
        src={'source_type':'model','source_id':sid,'response_sha256':None if raw is None else digest(raw),'content':None if raw is None else content(raw)}
    else:src={'source_type':'experimenter_reference','source_id':t['id']+'_reference','response_sha256':None,'content':dump({'candidate_id':t['control_candidate_id']}).decode()}
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
        history=[]
        for pre in plan['slots']:
            if pre['id']==slot['id']:break
            if pre['trial_id']==t['id'] and pre['stage']!='select' and pre['id'] in raws:
                history.append({'source_slot_id':pre['id'],'response_sha256':digest(raws[pre['id']]),'content':content(raws[pre['id']])})
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


def decode(rec,raw,spec,phase):
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
    if not stage_shape(phase,x):return 'invalid_schema',None,u
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
        st,x,u=decode(r,raws.get(sid,b''),spec,a['stage']);stat[sid]=st;objs[sid]=x
        if r is not None and r['kind']=='call':usages.append(u);outcomes[st]=outcomes.get(st,0)+1
        if r is not None and r['kind']=='skip':skips[r['reason']]=skips.get(r['reason'],0)+1
    for t in plan['trials']:
        p,cs,src,route=context(plan,t,raws)
        rd=[route_depth(p,spec['reference_plans'][p['id']][c]) for c in spec['reference_conditions']]
        target=min(rd) if t['condition']=='shallow' else max(rd)
        selected=None if route is None else route_depth(p,route['rule_ids'])
        selst=stat[t['id']+'_select'] if t['arm']=='model' else 'experimenter_reference_not_inference'
        selsuccess=(selected==target) if selst=='ok' else None
        sequence=[]
        if route is not None:
            for a in plan['slots']:
                if a['trial_id']!=t['id'] or a['stage']=='select':continue
                if a['stage']=='rule' and a['rule_position']>=len(route['rule_ids']):continue
                sequence.append({**a,'requested_rule_id':route['rule_ids'][a['rule_position']] if a['stage']=='rule' else None})
        checks=steps(p,sequence,objs,stat) if sequence else []
        complete=bool(sequence) and all(stat[a['id']]=='ok' for a in sequence)
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
        trace=None if selsuccess is None or genok is None else selsuccess and genok and targetok
        control=None if t['arm']!='reference' or genok is None else genok and targetok
        rows.append({'trial_id':t['id'],'arm':t['arm'],'problem_id':p['id'],'seed':t['seed'],'candidate_order_index':t['candidate_order_index'],
            'condition':t['condition'],'pair_id':t['pair_id'],'selector_status':selst,
            'selected_candidate_id':None if route is None else route['candidate_id'],'selected_rule_ids':None if route is None else route['rule_ids'],
            'selected_route_D':selected,'target_D':target,'selection_success':selsuccess,
            'generator_stage_statuses':[{'id':a['id'],'status':stat[a['id']]} for a in sequence],
            'step_checks':checks,'step_success':stepok,'graph':g,'graph_metric':gm,'route_fidelity':fidelity,
            'generator_success':genok,'target_structure_success':targetok,'trace_success':trace if t['arm']=='model' else None,'control_success':control})
    m=[r for r in rows if r['arm']=='model'];c=[r for r in rows if r['arm']=='reference'];ps=[]
    for pid in sorted(set(r['pair_id'] for r in m)):
        pair=sorted((r for r in m if r['pair_id']==pid),key=lambda x:x['condition'])
        vals=[r['trace_success'] for r in pair]
        ps.append({'pair_id':pid,'trial_ids':[r['trial_id'] for r in pair],
                   'success':None if None in vals else all(vals),
                   'actual_Ds':{r['condition']:r['graph_metric']['actual_D'] if r['graph_metric'] is not None else None for r in pair}})
    mc=tally([r['trace_success'] for r in m]);cc=tally([r['control_success'] for r in c]);pc=tally([r['success'] for r in ps])
    gate=None
    if state=='complete' and mc['unmeasured']==0 and cc['unmeasured']==0:gate=mc['successes']==24 and cc['successes']==12 and pc['successes']==12
    decision=('incomplete_or_unmeasured_no_retry' if gate is None else 'limited_end_to_end_baseline_ready_plan_P03' if gate else
              'close_batch_control_contract_not_ready' if cc['successes']!=12 else 'close_batch_no_model_trace_success' if mc['successes']==0 else 'close_batch_partial_model_trace_success')
    groups={k:{str(v):tally([r['trace_success'] for r in m if r[k]==v]) for v in sorted({r[k] for r in m},key=str)} for k in ('problem_id','candidate_order_index','condition')}
    u={}
    for k in FIELDS:
        values=[x.get(k) for x in usages];u[k]={'observed_sum':sum(x for x in values if x is not None),'missing_records':sum(x is None for x in values)}
    return {'contract':'v074-summary-r1','provenance':plan['provenance'],'state':state,'observed_inference_calls':len(usages),
            'skipped_action_slots':dict(sorted(skips.items())),'response_statuses':dict(sorted(outcomes.items())),
            'model_selection':tally([r['selection_success'] for r in m]),'model_generator_fidelity':tally([r['generator_success'] for r in m]),
            'model_target_structure':tally([r['target_structure_success'] for r in m]),'model_trace':mc,'model_pairs':pc,'reference_construction':cc,
            'end_to_end_baseline_ready':gate,'decision':decision,'model_trace_by':groups,'usage':u,'trials':rows,'pairs':ps}


def independent_report(s):
    text='# v074 후보 선택 → 증명 생성 종단 결과\n\n'
    text+=f"증거 구분: **{s['provenance']}** / 실행 상태: **{s['state']}**\n\n"
    text+=f"관측 추론: {s['observed_inference_calls']} / 최대 214. 조건부 생략: {s['skipped_action_slots']}\n\n"
    text+='|항목|성공|측정|배정|미측정|\n|---|---:|---:|---:|---:|\n'
    titles=['모델 경로 선택','선택 경로 구성 충실성','유효한 목표 D 구조','선택부터 종단까지','양방향 종단 쌍','별도 참조 구성 대조']
    keys=['model_selection','model_generator_fidelity','model_target_structure','model_trace','model_pairs','reference_construction']
    for title,key in zip(titles,keys):
        c=s[key];text+=f"|{title}|{c['successes']}|{c['measured']}|{c['assigned']}|{c['unmeasured']}|\n"
    text+=f"\n전체 공학적 기준: {s['end_to_end_baseline_ready']} / 결정: `{s['decision']}`\n\n"
    text+='참조 대조는 실험자가 경로를 지정했다. 모델의 경로 선택 성공에 합산하지 않는다.\n'
    text+='graph가 목표 D를 충족해도 선택 또는 앞 단계가 틀렸으면 종단 trace 성공이 아니다.\n'
    text+='정확한 깊이 숫자를 출력하는 과제는 없다. 출력 graph D만 재측정한다.\n'
    text+='현재 배치는 3개 개발 문제의 고정 후보 6개다. A/M, 내부 상태, 독립 holdout, 비용 우월성은 측정하지 않았다.\n'
    text+='한 배치로 종료한다. 미측정/실패를 자동 재시도하거나 문구·seed를 바꾸지 않는다.\n\n'
    text+='## 원문별 종단 판정\n\n|시행|군|문제|요구|선택|실제 D|종단/대조|\n|---|---|---|---|---|---:|---|\n'
    for r in s['trials']:
        d=r['graph_metric']['actual_D'] if r['graph_metric'] is not None else None
        val=r['control_success'] if r['arm']=='reference' else r['trace_success']
        text+=f"|{r['trial_id']}|{r['arm']}|{r['problem_id']}|{r['condition']}|{r['selected_candidate_id']}|{d}|{val}|\n"
    return text
