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
        selector_status=statuses.get(t['id']+'_select') if t['arm']=='model' else 'experimenter_reference_not_inference'
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
        rows.append({'trial_id':t['id'],'arm':t['arm'],'problem_id':t['problem_id'],'seed':t['seed'],
                     'candidate_order_index':t['candidate_order_index'],'condition':t['condition'],'pair_id':t['pair_id'],
                     'selector_status':selector_status,'selected_candidate_id':None if route is None else route['candidate_id'],
                     'selected_rule_ids':None if route is None else route['rule_ids'],'selected_route_D':selected_D,'target_D':target_D,
                     'selection_success':selection_success,'generator_stage_statuses':[{'id':s['id'],'status':statuses[s['id']]} for s in ordered],
                     'step_checks':checks,'step_success':step_success,'graph':graph,'graph_metric':metric,
                     'route_fidelity':route_fidelity,'generator_success':generator_success,'target_structure_success':target_structure_success,
                     'trace_success':trace if t['arm']=='model' else None,'control_success':control})
    model=[r for r in rows if r['arm']=='model'];control=[r for r in rows if r['arm']=='reference'];pairs=[]
    for pid in sorted({r['pair_id'] for r in model}):
        rs=sorted([r for r in model if r['pair_id']==pid],key=lambda r:r['condition'])
        vals=[r['trace_success'] for r in rs]
        pairs.append({'pair_id':pid,'trial_ids':[r['trial_id'] for r in rs],
                      'success':all(v is True for v in vals) if all(v is not None for v in vals) else None,
                      'actual_Ds':{r['condition']:None if r['graph_metric'] is None else r['graph_metric']['actual_D'] for r in rs}})
    mc=counts([r['trace_success'] for r in model]);cc=counts([r['control_success'] for r in control]);pc=counts([p['success'] for p in pairs])
    gate=None if state!='complete' or mc['unmeasured'] or cc['unmeasured'] else (mc['successes']==24 and cc['successes']==12 and pc['successes']==12)
    if gate is None:decision='incomplete_or_unmeasured_no_retry'
    elif gate:decision='limited_end_to_end_baseline_ready_plan_P03'
    elif cc['successes']!=12:decision='close_batch_control_contract_not_ready'
    elif mc['successes']==0:decision='close_batch_no_model_trace_success'
    else:decision='close_batch_partial_model_trace_success'
    groups={}
    for key in ('problem_id','candidate_order_index','condition'):
        groups[key]={str(v):counts([r['trace_success'] for r in model if r[key]==v]) for v in sorted({r[key] for r in model},key=str)}
    return {'contract':'v074-summary-r1','provenance':plan['provenance'],'state':state,
            'observed_inference_calls':len(usage),'skipped_action_slots':dict(sorted(skip_counts.items())),
            'response_statuses':dict(sorted(call_statuses.items())),
            'model_selection':counts([r['selection_success'] for r in model]),
            'model_generator_fidelity':counts([r['generator_success'] for r in model]),
            'model_target_structure':counts([r['target_structure_success'] for r in model]),
            'model_trace':mc,'model_pairs':pc,'reference_construction':cc,
            'end_to_end_baseline_ready':gate,'decision':decision,'model_trace_by':groups,
            'usage':{k:{'observed_sum':sum(u.get(k) for u in usage if u.get(k) is not None),
                        'missing_records':sum(u.get(k) is None for u in usage)} for k in USAGE},
            'trials':rows,'pairs':pairs}


def render(s):
    lines=['# v074 후보 선택 → 증명 생성 종단 결과', '',
           f"증거 구분: **{s['provenance']}** / 실행 상태: **{s['state']}**",'',
           f"관측 추론: {s['observed_inference_calls']} / 최대 214. 조건부 생략: {s['skipped_action_slots']}", '',
           '|항목|성공|측정|배정|미측정|','|---|---:|---:|---:|---:|']
    for name,key in [('모델 경로 선택','model_selection'),('선택 경로 구성 충실성','model_generator_fidelity'),
                     ('유효한 목표 D 구조','model_target_structure'),('선택부터 종단까지','model_trace'),
                     ('양방향 종단 쌍','model_pairs'),('별도 참조 구성 대조','reference_construction')]:
        c=s[key];lines.append(f"|{name}|{c['successes']}|{c['measured']}|{c['assigned']}|{c['unmeasured']}|")
    lines += ['',f"전체 공학적 기준: {s['end_to_end_baseline_ready']} / 결정: `{s['decision']}`",'',
              '참조 대조는 실험자가 경로를 지정했다. 모델의 경로 선택 성공에 합산하지 않는다.',
              'graph가 목표 D를 충족해도 선택 또는 앞 단계가 틀렸으면 종단 trace 성공이 아니다.',
              '정확한 깊이 숫자를 출력하는 과제는 없다. 출력 graph D만 재측정한다.',
              '현재 배치는 3개 개발 문제의 고정 후보 6개다. A/M, 내부 상태, 독립 holdout, 비용 우월성은 측정하지 않았다.',
              '한 배치로 종료한다. 미측정/실패를 자동 재시도하거나 문구·seed를 바꾸지 않는다.', '',
              '## 원문별 종단 판정','', '|시행|군|문제|요구|선택|실제 D|종단/대조|','|---|---|---|---|---|---:|---|']
    for r in s['trials']:
        d=None if r['graph_metric'] is None else r['graph_metric']['actual_D']
        val=r['trace_success'] if r['arm']=='model' else r['control_success']
        lines.append(f"|{r['trial_id']}|{r['arm']}|{r['problem_id']}|{r['condition']}|{r['selected_candidate_id']}|{d}|{val}|")
    return '\n'.join(lines)+'\n'
