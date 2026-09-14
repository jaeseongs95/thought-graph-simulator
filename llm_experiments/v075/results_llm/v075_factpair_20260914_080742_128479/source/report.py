"""실행 후에만 채점한다. 원문/선택/그래프를 수정하지 않는다."""
from __future__ import annotations
from collections import Counter
import common, design, measure, stages
USAGE=('prompt_eval_count','eval_count','total_duration','prompt_eval_duration','eval_duration')


def parse_response(record, raw, model, stage, spec):
    if record is None:return 'not_executed',None,{}
    if record.get('kind')=='skip':return 'skipped_'+record['reason'],None,{}
    if record.get('error') is not None:return 'transport_error',None,{}
    if record.get('http_status')!=200:return 'http_error',None,{}
    try:outer=common.load(raw)
    except (ValueError,UnicodeError):return 'invalid_outer_json',None,{}
    if not isinstance(outer,dict):return 'invalid_outer_schema',None,{}
    usage={k:outer.get(k) if type(outer.get(k)) is int and outer[k]>=0 else None for k in USAGE}
    if outer.get('model')!=model:return 'identity_error',None,usage
    if type(outer.get('eval_count')) is int and outer['eval_count']>spec['num_predict']:return 'generation_budget_exceeded',None,usage
    if outer.get('done_reason')=='length':return 'length_termination',None,usage
    if outer.get('done') is not True or outer.get('done_reason')!='stop':return 'incomplete_response',None,usage
    msg=outer.get('message')
    if not isinstance(msg,dict) or msg.get('role')!='assistant' or msg.get('tool_calls') or not isinstance(msg.get('content'),str):return 'invalid_outer_schema',None,usage
    try:obj=common.load(msg['content'])
    except (ValueError,UnicodeError):return 'invalid_json',None,usage
    valid=(isinstance(obj,dict) and set(obj)=={'candidate_id'} and obj['candidate_id'] in spec['candidate_ids']) if stage=='select' else stages.format_valid(stage,obj)
    return ('ok',obj,usage) if valid else ('invalid_schema',None,usage)


def counts(values):
    return {'assigned':len(values),'measured':sum(v is not None for v in values),
            'successes':sum(v is True for v in values),'failures':sum(v is False for v in values),
            'unmeasured':sum(v is None for v in values)}


def summarize(plan, records, responses, state):
    spec=plan['protocol'];rows=[];usage=[];call_statuses=Counter();skip_counts=Counter()
    parsed={};statuses={}
    for s in plan['slots']:
        rec=records.get(s['id']);status,obj,u=parse_response(rec,responses.get(s['id'],b''),spec['model'],s['stage'],spec)
        statuses[s['id']]=status;parsed[s['id']]=obj
        if rec is not None and rec.get('kind')=='call':call_statuses[status]+=1;usage.append(u)
        if rec is not None and rec.get('kind')=='skip':skip_counts[rec['reason']]+=1
    for t in plan['trials']:
        problem=design.problem_for(plan,t);route=design.selected_route(plan,t,responses)
        target_D=measure.depth_ranges(problem)[0 if t['condition']=='shallow' else 1]
        selected_D=None
        if route is not None:
            # 독립적인 경로 깊이 계산은 최종 출력 채점에만 사용한다.
            available={a:0 for a in problem['facts']};rules={r['id']:r for r in problem['rules']}
            for rid in route['rule_ids']:
                r=rules[rid];available[r['conclusion']]=1+max(available[a] for a in r['premises'])
            selected_D=available[problem['goal']]
        selector_status=statuses.get(t['selection_slot_id']) if t['arm']=='model' else 'experimenter_reference_not_inference'
        selection_success=(selected_D==target_D) if selector_status=='ok' else None
        ordered=[]
        if route is not None:
            for s in plan['slots']:
                if s['trial_id']==t['id'] and s['stage']!='select' and not (s['stage']=='rule' and s['rule_position']>=len(route['rule_ids'])):
                    ordered.append(dict(s,requested_rule_id=route['rule_ids'][s['rule_position']] if s['stage']=='rule' else None))
        ready={s['id'] for s in ordered if statuses[s['id']]=='ok'}
        checks=stages.audit_steps(problem,ordered,parsed,ready) if ordered else []
        all_ready=bool(ordered) and len(ready)==len(ordered)
        graph=stages.assemble(ordered,parsed) if all_ready else None
        metric=measure.assess(problem,graph) if graph is not None else None
        step_success=all(c['valid'] is True for c in checks) if all_ready else None
        strict=None if metric is None or metric['strict_valid'] is None else metric['strict_valid']
        actual_D=None if metric is None else metric['actual_D']
        route_fidelity=None if graph is None else [n['rule'] for n in graph['nodes'] if n['rule'] is not None]==route['rule_ids']
        generator_success=None if not all_ready or strict is None else (step_success and strict and route_fidelity and actual_D==selected_D)
        target_structure_success=None if strict is None else strict and actual_D==target_D
        trace=(selection_success and generator_success and target_structure_success) if selection_success is not None and generator_success is not None else None
        control=(generator_success and target_structure_success) if t['arm']=='reference' and generator_success is not None else None
        rows.append({'trial_id':t['id'],'unit_id':t['unit_id'],'variant':t['variant'],'base_pair_id':t['base_pair_id'],'initial_fact_success':checks[0]['valid'] if checks else None,'arm':t['arm'],'problem_id':t['problem_id'],'seed':t['seed'],
                     'candidate_order_index':t['candidate_order_index'],'condition':t['condition'],'pair_id':t['pair_id'],
                     'selector_status':selector_status,'selected_candidate_id':None if route is None else route['candidate_id'],
                     'selected_rule_ids':None if route is None else route['rule_ids'],'selected_route_D':selected_D,'target_D':target_D,
                     'selection_success':selection_success,'generator_stage_statuses':[{'id':s['id'],'status':statuses[s['id']]} for s in ordered],
                     'step_checks':checks,'step_success':step_success,'graph':graph,'graph_metric':metric,
                     'route_fidelity':route_fidelity,'generator_success':generator_success,'target_structure_success':target_structure_success,
                     'trace_success':trace if t['arm']=='model' else None,'control_success':control})
    result = aggregate(rows, state)
    result.update(contract='v075-summary-r1',provenance=plan['provenance'],state=state,
        observed_inference_calls=len(usage),skipped_action_slots=dict(sorted(skip_counts.items())),
        response_statuses=dict(sorted(call_statuses.items())),
        usage={k:{'observed_sum':sum(u.get(k) for u in usage if u.get(k) is not None),
                  'missing_records':sum(u.get(k) is None for u in usage)} for k in USAGE})
    return result


def paired_counts(pairs):
    out={'assigned':len(pairs),'measured':0,'both_success':0,'legacy_only':0,'fact_only_only':0,'both_fail':0,'unmeasured':0}
    for a,b in pairs:
        if a is None or b is None:out['unmeasured']+=1
        else:
            out['measured']+=1
            out['both_success' if a and b else 'legacy_only' if a else 'fact_only_only' if b else 'both_fail']+=1
    return out


def aggregate(rows, state):
    arms={};pairs=[]
    for variant in ('legacy','fact_only'):
        rs=[r for r in rows if r['variant']==variant];m=[r for r in rs if r['arm']=='model'];c=[r for r in rs if r['arm']=='reference'];vp=[]
        for pid in sorted({r['pair_id'] for r in m}):
            rr=sorted([r for r in m if r['pair_id']==pid],key=lambda r:r['condition'])
            values=[r['trace_success'] for r in rr]
            vp.append({'pair_id':pid,'variant':variant,'trial_ids':[r['trial_id'] for r in rr],
                       'success':None if None in values else all(values),
                       'actual_Ds':{r['condition']:r['graph_metric']['actual_D'] if r['graph_metric'] is not None else None for r in rr}})
        mc=counts([r['trace_success'] for r in m]);cc=counts([r['control_success'] for r in c]);pc=counts([x['success'] for x in vp]);gc=counts([r['generator_success'] for r in m])
        measured=state=='complete' and not mc['unmeasured'] and not cc['unmeasured']
        arms[variant]={'initial_fact_stage':counts([r['initial_fact_success'] for r in rs]),
            'model_generator_fidelity':gc,'model_target_structure':counts([r['target_structure_success'] for r in m]),
            'model_trace':mc,'model_pairs':pc,'reference_construction':cc,
            'generator_baseline_ready':(gc['successes']==24 and cc['successes']==12) if state=='complete' and gc['unmeasured']==0 and cc['unmeasured']==0 else None,
            'end_to_end_baseline_ready':(mc['successes']==24 and pc['successes']==12 and cc['successes']==12) if measured else None,
            'model_trace_by':{k:{str(v):counts([r['trace_success'] for r in m if r[k]==v]) for v in sorted({r[k] for r in m},key=str)} for k in ('problem_id','candidate_order_index','condition')}}
        pairs.extend(vp)
    uniques=[r for r in rows if r['variant']=='legacy' and r['arm']=='model'];selection=counts([r['selection_success'] for r in uniques])
    selection_ps=[]
    for pid in sorted({r['base_pair_id'] for r in uniques}):
        values=[r['selection_success'] for r in uniques if r['base_pair_id']==pid]
        selection_ps.append(None if None in values else all(values))
    comparisons=[]
    for uid in sorted({r['unit_id'] for r in rows}):
        a=next(r for r in rows if r['unit_id']==uid and r['variant']=='legacy');b=next(r for r in rows if r['unit_id']==uid and r['variant']=='fact_only')
        comparisons.append({'unit_id':uid,'arm':a['arm'],'problem_id':a['problem_id'],
            'legacy_trial_id':a['trial_id'],'fact_only_trial_id':b['trial_id'],
            'initial_fact':[a['initial_fact_success'],b['initial_fact_success']],
            'generator':[a['generator_success'],b['generator_success']],
            'trace':[a['trace_success'],b['trace_success']],
            'control':[a['control_success'],b['control_success']]})
    effects={'initial_fact_all':paired_counts([r['initial_fact'] for r in comparisons]),
        'model_generator':paired_counts([r['generator'] for r in comparisons if r['arm']=='model']),
        'model_trace':paired_counts([r['trace'] for r in comparisons if r['arm']=='model']),
        'reference_construction':paired_counts([r['control'] for r in comparisons if r['arm']=='reference'])}
    gates=[arms[v]['end_to_end_baseline_ready'] for v in ('legacy','fact_only')]
    overall=None if None in gates else any(gates)
    preferred=None if overall is not True else ('legacy' if gates[0] else 'fact_only')
    decision=('incomplete_or_unmeasured_no_retry' if overall is None else
        'close_batch_limited_end_to_end_baseline_plan_P03' if overall else
        'close_batch_partial_no_automatic_followup')
    return {'shared_model_selection':selection,'shared_selection_pairs':counts(selection_ps),
        'selection_trace_ceiling':{'successful_trials':selection['successes'],'successful_pairs':sum(x is True for x in selection_ps),
             'note':'이번 실제 선택의 측정된 범위에서 두 생성기 공통 종단 상한. 미측정 선택을 오답으로 채운 상한 아님.'},
        'arms':arms,'paired_effects':effects,'end_to_end_baseline_ready':overall,'preferred_generator_for_future_contract':preferred,
        'decision':decision,'trials':rows,'pairs':pairs,'within_unit_comparisons':comparisons}


def render(s):
    lines=['# v075 동일 선택 공유 · 초기 사실 스키마 종단 대조','',
        f"증거 구분: **{s['provenance']}** / 실행 상태: **{s['state']}**",'',
        f"관측 추론: {s['observed_inference_calls']} / 최대 404. 조건부 생략: {s['skipped_action_slots']}",'',
        f"공유 선택: {s['shared_model_selection']['successes']}/{s['shared_model_selection']['assigned']}. 두 생성기 결과를 48개 독립 선택으로 세지 않는다.",'',
        '|항목|legacy 성공/배정|fact_only 성공/배정|','|---|---:|---:|']
    for title,key in [('초기 사실 단계','initial_fact_stage'),('선택 경로 구성 충실성','model_generator_fidelity'),('유효한 목표 D 구조','model_target_structure'),('선택부터 종단까지','model_trace'),('양방향 종단 쌍','model_pairs'),('별도 참조 구성','reference_construction')]:
        a=s['arms']['legacy'][key];b=s['arms']['fact_only'][key]
        lines.append(f"|{title}|{a['successes']}/{a['assigned']}|{b['successes']}/{b['assigned']}|")
    lines += ['',f"전체 공학적 기준: {s['end_to_end_baseline_ready']} / 결정: `{s['decision']}`",'']
    for v in ('legacy','fact_only'):
        a=s['arms'][v];lines.append(f"{v}: 생성 기준 {a['generator_baseline_ready']}, 종단 기준 {a['end_to_end_baseline_ready']}, 본실험 미측정 {a['model_trace']['unmeasured']}, 참조 미측정 {a['reference_construction']['unmeasured']}")
    lines += ['', '## 같은 선택에 대한 종단 짝비교','', '|둘 다 성공|legacy만 성공|fact_only만 성공|둘 다 실패|미측정|','|---:|---:|---:|---:|---:|']
    e=s['paired_effects']['model_trace'];lines.append('|'+ '|'.join(str(e[k]) for k in ('both_success','legacy_only','fact_only_only','both_fail','unmeasured'))+'|')
    lines += ['', '첫 사실 스키마만 실험 처치다. atom·id·부모 정답을 호스트가 작성하거나 원응답을 보정하지 않는다.',
        '참조 대조는 실험자가 경로를 지정했다. 선택 성공에 합산하지 않는다.',
        '선택 오류 뒤 생성만 맞아도 종단 성공이 아니다. 실제 graph의 D와 단계 계약을 함께 확인한다.',
        '공유 선택과 두 생성 경로는 독립 표본이 아니다. 3개 개발 문제이며 새 구조 일반화·A/M·비용 우월성은 미측정이다.',
        '한 배치 후 종료한다. 결과에 따라 자동 재시도·문구/공백/seed 진단을 추가하지 않는다.','',
        '## 원문별 판정','', '|시행|군|문제|요구|선택|초기 사실|실제 D|종단/대조|','|---|---|---|---|---|---|---:|---|']
    for r in s['trials']:
        d=r['graph_metric']['actual_D'] if r['graph_metric'] is not None else None
        val=r['trace_success'] if r['arm']=='model' else r['control_success']
        lines.append(f"|{r['trial_id']}|{r['arm']}|{r['problem_id']}|{r['condition']}|{r['selected_candidate_id']}|{r['initial_fact_success']}|{d}|{val}|")
    return '\n'.join(lines)+'\n'
