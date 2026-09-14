"""실행 후에만 채점한다. 원문/선택/그래프를 수정하지 않는다."""
from __future__ import annotations
from collections import Counter
import common, design, measure, stages
USAGE=('prompt_eval_count','eval_count','total_duration','prompt_eval_duration','eval_duration')


def parse_response(record, raw, model, stage, spec, variant=None):
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
    return ('ok',obj,usage) if valid else ('invalid_schema',obj,usage)


def counts(values):
    return {'assigned':len(values),'measured':sum(v is not None for v in values),
            'successes':sum(v is True for v in values),'failures':sum(v is False for v in values),
            'unmeasured':sum(v is None for v in values)}


def summarize(plan, records, responses, state):
    spec=plan['protocol'];rows=[];usage=[];call_statuses=Counter();skip_counts=Counter()
    parsed={};statuses={}
    for s in plan['slots']:
        rec=records.get(s['id']);status,obj,u=parse_response(rec,responses.get(s['id'],b''),spec['model'],s['stage'],spec, next(t['variant'] for t in plan['trials'] if t['id']==s['trial_id']))
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
        projected=dict(parsed)
        node_statuses=dict(statuses)
        ready={s['id'] for s in ordered if node_statuses[s['id']]=='ok'}
        checks=stages.audit_steps(problem,ordered,projected,ready) if ordered else []
        parent_checks=[]
        for op in ordered:
            if op['stage']!='rule':continue
            expected=len(next(r for r in problem['rules'] if r['id']==op['requested_rule_id'])['premises'])
            observed=len(parsed[op['id']]['node']['parents']) if op['id'] in ready else None
            step=next(c for c in checks if c['id']==op['id'])
            parent_checks.append({'id':op['id'],'requested_rule_id':op['requested_rule_id'],
                'expected_count':expected,'observed_count':observed,
                'count_valid':None if observed is None else observed==expected,
                'step_valid':step['valid'],'error_codes':step['error_codes']})
        all_ready=bool(ordered) and len(ready)==len(ordered)
        graph=stages.assemble(ordered,projected) if all_ready else None
        metric=measure.assess(problem,graph) if graph is not None else None
        step_success=all(c['valid'] is True for c in checks) if all_ready else None
        strict=None if metric is None or metric['strict_valid'] is None else metric['strict_valid']
        actual_D=None if metric is None else metric['actual_D']
        route_fidelity=None if graph is None else [n['rule'] for n in graph['nodes'] if n['rule'] is not None]==route['rule_ids']
        generator_success=None if not all_ready or strict is None else (step_success and strict and route_fidelity and actual_D==selected_D)
        graph_only_generator_success=generator_success
        target_structure_success=None if strict is None else strict and actual_D==target_D
        trace=(selection_success and generator_success and target_structure_success) if selection_success is not None and generator_success is not None else None
        graph_only_trace=(selection_success and graph_only_generator_success and target_structure_success) if selection_success is not None and graph_only_generator_success is not None else None
        control=(generator_success and target_structure_success) if t['arm']=='reference' and generator_success is not None else None
        rows.append({'trial_id':t['id'],'unit_id':t['unit_id'],'variant':t['variant'],'base_pair_id':t['base_pair_id'],'initial_fact_success':checks[0]['valid'] if checks else None,'arm':t['arm'],'problem_id':t['problem_id'],'seed':t['seed'],
                     'candidate_order_index':t['candidate_order_index'],'condition':t['condition'],'pair_id':t['pair_id'],
                     'family':spec['problem_metadata'][problem['id']]['family'],
                     'selected_route_rule_count':None if route is None else len(route['rule_ids']),
                     'actual_goal_support_rule_count':sum(n['rule'] is not None for n in graph['nodes']) if strict is True else None,
                     'selector_status':selector_status,'selected_candidate_id':None if route is None else route['candidate_id'],
                     'selected_rule_ids':None if route is None else route['rule_ids'],'selected_route_D':selected_D,'target_D':target_D,
                     'selection_success':selection_success,'generator_stage_statuses':[{'id':s['id'],'status':statuses[s['id']]} for s in ordered],
                     'node_stage_statuses':[{'id':s['id'],'status':node_statuses[s['id']]} for s in ordered],'graph_only_generator_success':graph_only_generator_success,'graph_only_trace_success':graph_only_trace if t['arm']=='model' else None,'step_checks':checks,'parent_count_checks':parent_checks,'step_success':step_success,'graph':graph,'graph_metric':metric,
                     'route_fidelity':route_fidelity,'generator_success':generator_success,'target_structure_success':target_structure_success,
                     'trace_success':trace if t['arm']=='model' else None,'control_success':control})
    result = aggregate(rows, state, spec)
    result.update(contract='v078-summary-r1',provenance=plan['provenance'],state=state,
        observed_inference_calls=len(usage),skipped_action_slots=dict(sorted(skip_counts.items())),
        response_statuses=dict(sorted(call_statuses.items())),
        usage={k:{'observed_sum':sum(u.get(k) for u in usage if u.get(k) is not None),
                  'missing_records':sum(u.get(k) is None for u in usage)} for k in USAGE})
    return result



def aggregate(rows, state, spec):
    """새 구조의 성과만 집계한다. v077 이력 점수/참조는 본실험 분자에 합산하지 않는다."""
    model=[r for r in rows if r['arm']=='model']; controls=[r for r in rows if r['arm']=='reference']
    pairs=[]
    for pid in sorted({r['pair_id'] for r in model}):
        rr=sorted([r for r in model if r['pair_id']==pid],key=lambda r:r['condition'])
        if len(rr)!=2 or {r['condition'] for r in rr}!={'shallow','deep'}:raise ValueError('양방향 pair 계약')
        ds={r['condition']:None if r['graph_metric'] is None else r['graph_metric']['actual_D'] for r in rr}
        vals=[r['trace_success'] for r in rr];sv=[r['selection_success'] for r in rr]
        pairs.append({'pair_id':pid,'variant':'base','problem_id':rr[0]['problem_id'],'family':rr[0]['family'],
                      'trial_ids':[r['trial_id'] for r in rr],
                      'success':None if any(x is None for x in vals) else all(vals),
                      'selection_success':None if any(x is None for x in sv) else all(sv),
                      'same_selected_candidate':None if any(x is None for x in sv) else rr[0]['selected_candidate_id']==rr[1]['selected_candidate_id'],
                      'actual_Ds':ds,'actual_rule_counts':{r['condition']:r['actual_goal_support_rule_count'] for r in rr},
                      'observed_D_increase':None if any(v is None for v in ds.values()) else ds['deep']>ds['shallow']})
    mc=counts([r['trace_success'] for r in model]);gc=counts([r['generator_success'] for r in model]);cc=counts([r['control_success'] for r in controls]);pc=counts([p['success'] for p in pairs])
    fully=state=='complete' and mc['measured']==spec['assigned_model_trials'] and cc['measured']==spec['assigned_control_trials']
    gate=(mc['successes']==32 and cc['successes']==16 and pc['successes']==16) if fully else None
    generator_gate=(gc['successes']==32 and cc['successes']==16) if state=='complete' and gc['measured']==32 and cc['measured']==16 else None
    by={key:{str(v):counts([r['trace_success'] for r in model if r[key]==v]) for v in sorted({r[key] for r in model},key=str)}
        for key in ('problem_id','candidate_order_index','condition','family')}
    arm={'initial_fact_stage':counts([r['initial_fact_success'] for r in rows]),
         'rule_parent_counts':counts([c['count_valid'] for r in rows for c in r['parent_count_checks']]),
         'rule_semantic_steps':counts([c['step_valid'] for r in rows for c in r['parent_count_checks']]),
         'count_correct_but_step_wrong':sum(c['count_valid'] is True and c['step_valid'] is False for r in rows for c in r['parent_count_checks']),
         'model_generator_fidelity':gc,'model_target_structure':counts([r['target_structure_success'] for r in model]),
         'model_trace':mc,'model_pairs':pc,'reference_construction':cc,
         'generator_baseline_ready':generator_gate,'end_to_end_baseline_ready':gate,'model_trace_by':by}
    def group_result(m,c,ps):
        return {'model_selection':counts([r['selection_success'] for r in m]),
                'selection_pairs':counts([p['selection_success'] for p in ps]),
                'model_generator_fidelity':counts([r['generator_success'] for r in m]),
                'model_trace':counts([r['trace_success'] for r in m]),
                'model_pairs':counts([p['success'] for p in ps]),
                'reference_construction':counts([r['control_success'] for r in c])}
    strata={f:{'distinct_structural_problems':len({r['problem_id'] for r in model if r['family']==f}),
               **group_result([r for r in model if r['family']==f],[r for r in controls if r['family']==f],[p for p in pairs if p['family']==f])}
            for f in ('equal_rule_count','inverted_rule_count')}
    problems={p['id']:{'design':spec['problem_metadata'][p['id']],
                      **group_result([r for r in model if r['problem_id']==p['id']],[r for r in controls if r['problem_id']==p['id']],[x for x in pairs if x['problem_id']==p['id']])}
              for p in spec['problems']}
    return {'shared_model_selection':counts([r['selection_success'] for r in model]),
            'shared_selection_pairs':counts([p['selection_success'] for p in pairs]),
            'arms':{'base':arm},'strata':strata,'problem_results':problems,
            'end_to_end_baseline_ready':gate,
            'decision':'close_frozen_structural_batch' if state=='complete' else 'preserve_incomplete_batch_no_retry',
            'scientific_scope':{'distinct_structural_problems':4,'model_trials':32,'reference_trials':16,
                                'name_order_effect_isolated':False,'independent_population_generalization':False,
                                'internal_control_measured':False,'A_measured':False,'M_measured':False},
            'pairs':pairs,'trials':rows}


def render(s):
    def cell(d):return f"{d['successes']}/{d['assigned']} (실패 {d['failures']}, 미측정 {d['unmeasured']})"
    a=s['arms']['base']
    lines=['# v078 P03 — 규칙 수와 D를 분리한 새 구조 확인', '',
           f"실행 상태: `{s['state']}` / 출처: `{s['provenance']}` / 관측 추론 응답: {s['observed_inference_calls']}",
           f"배치 결정: `{s['decision']}` / 전수 공학 기준: `{s['end_to_end_baseline_ready']}`", '',
           '**모든 종단·pair는 초기 사실, 각 단계, 실제 전체 graph, 선택 경로 충실성, 요구 D를 포함한 동일 기준이다. 대응표 계약은 없다.**', '',
           '|지표|base|','|---|---:|',
           '|모델 경로 선택|'+cell(s['shared_model_selection'])+'|',
           '|양방향 선택 쌍|'+cell(s['shared_selection_pairs'])+'|',
           '|선택 경로 생성 충실성|'+cell(a['model_generator_fidelity'])+'|',
           '|D 종단 성공|'+cell(a['model_trace'])+'|',
           '|양방향 D 종단 쌍|'+cell(a['model_pairs'])+'|',
           '|실험자 지정 참조 구성|'+cell(a['reference_construction'])+'|','',
           '## 규칙 수-D 관계별 결과','',
           '|설계층|실제 구조 수|선택|종단|양방향 종단|참조|','|---|---:|---:|---:|---:|---:|']
    for f,title in [('equal_rule_count','규칙 수 동일'),('inverted_rule_count','규칙 수-D 역전')]:
        r=s['strata'][f];lines.append('|'+title+'|'+str(r['distinct_structural_problems'])+'|'+cell(r['model_selection'])+'|'+cell(r['model_trace'])+'|'+cell(r['model_pairs'])+'|'+cell(r['reference_construction'])+'|')
    lines += ['', '## 문제별 결과','', '|문제|작은 D / 규칙 수|큰 D / 규칙 수|종단|양방향 종단|참조|','|---|---:|---:|---:|---:|---:|']
    for pid,r in s['problem_results'].items():
        m=r['design'];lines.append(f"|{pid}|{m['shallow_D']} / {m['shallow_rule_count']}|{m['deep_D']} / {m['deep_rule_count']}|"+cell(r['model_trace'])+'|'+cell(r['model_pairs'])+'|'+cell(r['reference_construction'])+'|')
    lines += ['', '## 판독 경계','',
              '새 구조는 4개다. seed·후보 순서 반복 32건을 독립 문제 32개로 세지 않는다. 이름/규칙 순서는 새 고정 표현이며 그 효과를 별도로 추정하지 않는다.',
              '잘못 고른 경로도 그대로 생성했다. 선택 실패와 생성 실패는 trials에서 분리한다. 참조는 실험자 지정 경로이므로 자율 선택 성공에 합산하지 않는다.',
              '미실행·HTTP·identity·length·파싱/스키마 실패는 response_statuses 및 단계 상태에 보존한다. D가 측정되지 않으면 null이며 0으로 대체하지 않는다.',
              '전수 공학 기준은 모델 종단32/32·양방향16/16·참조16/16이다. 이 기준의 실패가 관찰된 부분 효과의 부재를 뜻하지 않는다.',
              'synthetic은 합성 HTTP/단위시험이며 실제 모델 성과가 아니다. 이 보고서는 v077 과거 점수와 새 성과를 합산하지 않는다.',
              '원문을 보정하거나 자동 재시도·추가 버전 실행을 하지 않는다. 내부 사고 깊이, A/M, 큰 모델 대비 동등성 및 비용 우월성은 이 실험의 평가 대상이 아니다.', '']
    return '\n'.join(lines)
