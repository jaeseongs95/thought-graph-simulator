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
    result.update(contract='v079-summary-r1',provenance=plan['provenance'],state=state,
        observed_inference_calls=len(usage),skipped_action_slots=dict(sorted(skip_counts.items())),
        response_statuses=dict(sorted(call_statuses.items())),
        usage={k:{'observed_sum':sum(u.get(k) for u in usage if u.get(k) is not None),
                  'missing_records':sum(u.get(k) is None for u in usage)} for k in USAGE})
    grouped_usage={g:[] for g in ['shared_selection',*spec['generator_variants']]}
    for slot in plan['slots']:
        rec=records.get(slot['id'])
        if rec is None or rec.get('kind')!='call':continue
        variant=next(t['variant'] for t in plan['trials'] if t['id']==slot['trial_id'])
        _,_,u=parse_response(rec,responses.get(slot['id'],b''),spec['model'],slot['stage'],spec,variant)
        grouped_usage['shared_selection' if slot['stage']=='select' else variant].append(u)
    result['usage_by_group']={g:{'observed_calls':len(items),'fields':{k:{'observed_sum':sum(u[k] for u in items if u.get(k) is not None),'missing_records':sum(u.get(k) is None for u in items)} for k in USAGE}} for g,items in grouped_usage.items()}
    return result



def paired_counts(left, right, key, metric):
    """동일 단위에서 두 군의 성패를 짝짓는다. 미관측은 discordant 실패로 만들지 않는다."""
    lm={r[key]:r[metric] for r in left};rm={r[key]:r[metric] for r in right}
    if set(lm)!=set(rm) or len(lm)!=len(left) or len(rm)!=len(right):raise ValueError('paired units mismatch')
    out=dict(assigned=len(lm),measured=0,both_success=0,base_only=0,explicit_rule_only=0,both_failure=0,unmeasured=0)
    for k in lm:
        a,b=lm[k],rm[k]
        if a is None or b is None:out['unmeasured']+=1;continue
        out['measured']+=1
        out['both_success' if a and b else 'base_only' if a else 'explicit_rule_only' if b else 'both_failure']+=1
    out['net_success_change']=out['explicit_rule_only']-out['base_only']
    return out


def aggregate(rows, state, spec):
    model=[r for r in rows if r['arm']=='model']; controls=[r for r in rows if r['arm']=='reference']
    pairs=[]
    for pid in sorted({r['pair_id'] for r in model}):
        rr=sorted([r for r in model if r['pair_id']==pid],key=lambda r:r['condition'])
        if len(rr)!=2 or {r['condition'] for r in rr}!={'shallow','deep'}:raise ValueError('양방향 pair 계약')
        ds={r['condition']:None if r['graph_metric'] is None else r['graph_metric']['actual_D'] for r in rr}
        vals=[r['trace_success'] for r in rr];sv=[r['selection_success'] for r in rr];gv=[r['generator_success'] for r in rr]
        selected_pattern=('unmeasured' if any(x is None for x in sv) else 'forward' if all(sv)
            else 'same' if rr[0]['selected_candidate_id']==rr[1]['selected_candidate_id'] else 'reversed')
        direction=('unmeasured' if any(x is None for x in gv) else 'invalid' if not all(gv)
            else 'forward' if ds['deep']>ds['shallow'] else 'reversed' if ds['deep']<ds['shallow'] else 'same')
        pairs.append({'pair_id':pid,'base_pair_id':rr[0]['base_pair_id'],'variant':rr[0]['variant'],
                      'problem_id':rr[0]['problem_id'],'family':rr[0]['family'],'trial_ids':[r['trial_id'] for r in rr],
                      'success':None if any(x is None for x in vals) else all(vals),
                      'selection_success':None if any(x is None for x in sv) else all(sv),
                      'same_selected_candidate':None if any(x is None for x in sv) else rr[0]['selected_candidate_id']==rr[1]['selected_candidate_id'],
                      'selection_pattern':selected_pattern,'valid_graph_direction':direction,
                      'actual_Ds':ds,'actual_rule_counts':{r['condition']:r['actual_goal_support_rule_count'] for r in rr},
                      'observed_D_increase':None if any(v is None for v in ds.values()) else ds['deep']>ds['shallow']})
    def group_result(m,c,ps):
        return {'model_generator_fidelity':counts([r['generator_success'] for r in m]),
                'model_trace':counts([r['trace_success'] for r in m]),
                'model_pairs':counts([p['success'] for p in ps]),
                'reference_construction':counts([r['control_success'] for r in c])}
    arms={}
    for variant in spec['generator_variants']:
        m=[r for r in model if r['variant']==variant];c=[r for r in controls if r['variant']==variant]
        ps=[p for p in pairs if p['variant']==variant];allrows=m+c
        arm=group_result(m,c,ps);mc=arm['model_trace'];gc=arm['model_generator_fidelity'];cc=arm['reference_construction'];pc=arm['model_pairs']
        full=state=='complete' and mc['measured']==32 and cc['measured']==16
        gate=(mc['successes']==32 and cc['successes']==16 and pc['successes']==16) if full else None
        gen_gate=(gc['successes']==32 and cc['successes']==16) if state=='complete' and gc['measured']==32 and cc['measured']==16 else None
        by={key:{str(v):counts([r['trace_success'] for r in m if r[key]==v]) for v in sorted({r[key] for r in m},key=str)}
            for key in ('problem_id','candidate_order_index','condition','family')}
        pcs=[x for r in allrows for x in r['parent_count_checks']]
        cross=dict(selection_right_generator_right=0,selection_right_generator_wrong=0,
                   selection_wrong_generator_right=0,selection_wrong_generator_wrong=0,unmeasured=0)
        for r in m:
            a,b=r['selection_success'],r['generator_success']
            key='unmeasured' if a is None or b is None else 'selection_'+('right' if a else 'wrong')+'_generator_'+('right' if b else 'wrong')
            cross[key]+=1
        arm.update(initial_fact_stage=counts([r['initial_fact_success'] for r in allrows]),
            rule_parent_counts=counts([x['count_valid'] for x in pcs]),rule_semantic_steps=counts([x['step_valid'] for x in pcs]),
            count_correct_but_step_wrong=sum(x['count_valid'] is True and x['step_valid'] is False for x in pcs),
            model_target_structure=counts([r['target_structure_success'] for r in m]),
            generator_baseline_ready=gen_gate,end_to_end_baseline_ready=gate,model_trace_by=by,
            selection_generation_cross=cross,valid_graph_pair_directions=dict(sorted(Counter(p['valid_graph_direction'] for p in ps).items())))
        arms[variant]=arm
    # 선택은 생성군별 반복으로 가산하지 않는다. 공유 원응답의 두 row도 같은 판정을 가져야 한다.
    selected=[r for r in model if r['variant']=='base'];selected_pairs=[p for p in pairs if p['variant']=='base']
    for row in selected:
        other=next(r for r in model if r['unit_id']==row['unit_id'] and r['variant']=='explicit_rule')
        for key in ('selector_status','selected_candidate_id','selected_rule_ids','selected_route_D','selection_success'):
            if not common.exact(row[key],other[key]):raise ValueError('shared selection mismatch')
    strata={};problems={}
    for f in ('equal_rule_count','inverted_rule_count'):
        strata[f]={'distinct_structural_problems':len({r['problem_id'] for r in selected if r['family']==f}),
            'model_selection':counts([r['selection_success'] for r in selected if r['family']==f]),
            'selection_pairs':counts([p['selection_success'] for p in selected_pairs if p['family']==f]),
            'arms':{v:group_result([r for r in model if r['variant']==v and r['family']==f],
                                  [r for r in controls if r['variant']==v and r['family']==f],
                                  [p for p in pairs if p['variant']==v and p['family']==f]) for v in spec['generator_variants']}}
    for problem in spec['problems']:
        pid=problem['id'];problems[pid]={'design':spec['problem_metadata'][pid],
            'model_selection':counts([r['selection_success'] for r in selected if r['problem_id']==pid]),
            'selection_pairs':counts([p['selection_success'] for p in selected_pairs if p['problem_id']==pid]),
            'arms':{v:group_result([r for r in model if r['variant']==v and r['problem_id']==pid],
                                  [r for r in controls if r['variant']==v and r['problem_id']==pid],
                                  [p for p in pairs if p['variant']==v and p['problem_id']==pid]) for v in spec['generator_variants']}}
    comparisons={}
    for name,data,key,metric in [('model_generator_fidelity',model,'unit_id','generator_success'),('model_trace',model,'unit_id','trace_success'),
        ('reference_construction',controls,'unit_id','control_success'),('model_pairs',pairs,'base_pair_id','success')]:
        comparisons[name]=paired_counts([r for r in data if r['variant']=='base'],[r for r in data if r['variant']=='explicit_rule'],key,metric)
    gates=[a['end_to_end_baseline_ready'] for a in arms.values()]
    return {'shared_model_selection':counts([r['selection_success'] for r in selected]),
            'shared_selection_pairs':counts([p['selection_success'] for p in selected_pairs]),
            'shared_selection_patterns':dict(sorted(Counter(p['selection_pattern'] for p in selected_pairs).items())),
            'arms':arms,'strata':strata,'problem_results':problems,'paired_comparisons':comparisons,
            'end_to_end_baseline_ready':None if any(x is None for x in gates) else all(gates),
            'decision':'close_frozen_generator_diagnostic' if state=='complete' else 'preserve_incomplete_batch_no_retry',
            'scientific_scope':{'distinct_structural_problems':4,'new_independent_structural_problems':0,'exposed_diagnostic_set':True,
                               'shared_model_selections':32,'model_trials_per_variant':32,'reference_trials_per_variant':16,
                               'selector_changed':False,'parent_answers_supplied':False,'independent_population_generalization':False,
                               'internal_control_measured':False,'A_measured':False,'M_measured':False},
            'pairs':pairs,'trials':rows}


def render(s):
    def cell(d):return f"{d['successes']}/{d['assigned']} (실패 {d['failures']}, 미측정 {d['unmeasured']})"
    vs=['base','explicit_rule']
    lines=['# v079 — 현재 규칙 명시의 짝대조', '',
           f"실행 상태: `{s['state']}` / 출처: `{s['provenance']}` / 관측 추론 응답: {s['observed_inference_calls']}",
           f"배치 결정: `{s['decision']}`",'',
           '**H01-H04는 v078에서 결과를 본 진단 문제다. 새 holdout 성과가 아니다. 선택기는 동일하며, rule 단계의 입력에 현재 규칙 객체만 추가한다.**','',
           '공유 경로 선택: '+cell(s['shared_model_selection'])+' / 공유 양방향 선택: '+cell(s['shared_selection_pairs']),
           '공유 선택 패턴: '+common.wire(s['shared_selection_patterns']).decode('utf-8'),'',
           '|지표|base|explicit_rule|','|---|---:|---:|']
    for title,key in [('선택 경로 전체 생성 충실성','model_generator_fidelity'),('요구 D 종단','model_trace'),('양방향 D 종단 쌍','model_pairs'),('실험자 지정 참조 구성','reference_construction'),('초기 사실','initial_fact_stage'),('개별 규칙 단계','rule_semantic_steps')]:
        lines.append('|'+title+'|'+'|'.join(cell(s['arms'][v][key]) for v in vs)+'|')
    for v in vs:
        a=s['arms'][v];lines += ['',f"{v}: 생성 전수 기준 `{a['generator_baseline_ready']}` / D 종단 전수 기준 `{a['end_to_end_baseline_ready']}`",
            '유효 graph 쌍 방향: '+common.wire(a['valid_graph_pair_directions']).decode('utf-8')]
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
