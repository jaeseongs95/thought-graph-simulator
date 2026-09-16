"""실행 후 채점 전용. 계산표·선택·graph를 보정하거나 모델을 호출하지 않는다."""
from collections import Counter
import bootstrap
import report as legacy_report
import stages, measure
import core086 as core
import design086 as design
from render086 import render

MODEL_OUTPUT_FAILURES = {'invalid_json','invalid_schema','unmappable_selection','lookup_null','skipped_invalid_comparison_output'}


def parse_response(record, raw, spec, phase, selector):
    if phase=='compare' or phase=='select' and selector in ('two_stage_values','oracle_lookup'):
        from numeric086 import decode
        return decode(record,raw,spec,phase)
    return legacy_report.parse_response(record, raw, spec['model'], phase, spec, 'explicit_rule')


def summarize(plan, records, responses, state):
    spec = plan['protocol']
    objects, statuses, format_statuses, usages = {}, {}, {}, {}
    trial_by_id = {t['id']: t for t in plan['trials']}
    for op in plan['slots']:
        t = trial_by_id[op['trial_id']]
        st, obj, usage = parse_response(records.get(op['id']), responses.get(op['id'], b''), spec, op['stage'], t['selector_variant'])
        format_statuses[op['id']] = st
        if op['stage'] == 'select' and st == 'ok' and design.selected_route(plan, t, responses) is None:
            st = 'lookup_null' if t['selector_variant'] in ('two_stage_values','oracle_lookup') and obj.get('candidate_id') is None else 'unmappable_selection'
        objects[op['id']], statuses[op['id']] = obj, st
        if records.get(op['id'], {}).get('kind') == 'call':
            usages[op['id']] = usage
    rows = []
    for t in plan['trials']:
        problem = design.problem_for(plan, t)
        route = design.selected_route(plan, t, responses)
        cs = design.cards(plan, t)
        values = {c['candidate_id']: route_values(problem, [r['id'] for r in c['rules']]) for c in cs}
        target = (min if t['condition'] == 'shallow' else max)(v[t['metric']] for v in values.values())
        chosen = None if route is None else values[route['candidate_id']]
        sid = t['selection_slot_id']
        ss = statuses[sid] if sid else 'experimenter_reference_not_inference'
        fs = format_statuses[sid] if sid else ss
        mapped = True if ss == 'ok' else False if ss in MODEL_OUTPUT_FAILURES else None
        choice = chosen[t['metric']] == target if ss == 'ok' else None
        selection = choice if ss == 'ok' else False if ss in MODEL_OUTPUT_FAILURES else None
        sequence = []
        if route is not None:
            for op in plan['slots']:
                if op['trial_id'] != t['id'] or op['stage'] not in ('facts','rule','final'):
                    continue
                if op['stage'] == 'rule' and op['rule_position'] >= len(route['rule_ids']):
                    continue
                sequence.append(dict(op, requested_rule_id=route['rule_ids'][op['rule_position']] if op['stage'] == 'rule' else None))
        ready = {op['id'] for op in sequence if statuses[op['id']] == 'ok'}
        checks = stages.audit_steps(problem, sequence, objects, ready) if sequence else []
        complete = bool(sequence) and len(ready) == len(sequence)
        graph = stages.assemble(sequence, objects) if complete else None
        result = measure.assess(problem, graph) if graph is not None else None
        actual_D = result['actual_D'] if result is not None else None
        actual_W = sum(n['rule'] is not None for n in graph['nodes']) if result is not None and result['strict_valid'] is True else None
        generated = None
        generator_status = 'not_dispatched_unmappable_selection' if route is None else 'incomplete_or_nonsemantic'
        if complete:
            fidelity = [n['rule'] for n in graph['nodes'] if n['rule'] is not None] == route['rule_ids']
            generated = bool(all(c['valid'] is True for c in checks) and result['strict_valid'] is True and fidelity
                             and actual_D == chosen['D'] and actual_W == chosen['W'])
            generator_status = 'valid_graph' if generated else 'semantic_failure'
        elif sequence and any(statuses[op['id']] in {'invalid_json', 'invalid_schema'} for op in sequence):
            generated, generator_status = False, 'model_output_format_failure'
        goal = None if generated is None else bool(generated and (actual_D if t['metric'] == 'D' else actual_W) == target)
        if ss in MODEL_OUTPUT_FAILURES and route is None:
            end = False  # 관측된 선택 출력 계약 실패다. 미실행 graph를 실패로 채우지는 않는다.
        else:
            end = None if selection is None or generated is None else bool(selection and goal)
        if not t['generate']:
            generated = end = actual_D = actual_W = goal = None
            generator_status = 'not_scheduled_by_design'
        rows.append({'generation_scheduled':t['generate'], 'trial_id': t['id'], 'unit_id': t['unit_id'], 'selector_variant': t['selector_variant'],
                     'arm': t['arm'], 'problem_id': t['problem_id'], 'seed': t['seed'],
                     'metric': t['metric'], 'condition': t['condition'], 'order': t['candidate_order_index'],
                     'labels': t['id_assignment_index'], 'pair_id': t['pair_id'],
                     'selector_format_status': fs, 'selector_status': ss, 'mapping_success': mapped,
                     'structural_choice_correct': choice,
                     'candidate_id': None if route is None else route['candidate_id'],
                     'selected_rule_ids': None if route is None else route['rule_ids'],
                     'selected_position': None if route is None else [c['candidate_id'] for c in cs].index(route['candidate_id']),
                     'selected_D': None if chosen is None else chosen['D'], 'selected_W': None if chosen is None else chosen['W'],
                     'target_value': target, 'selection_success': selection,
                     'generator_success': generated, 'generator_status': generator_status,
                     'actual_D': actual_D, 'actual_W': actual_W, 'metric_end_to_end': end,
                     'reference_success': goal if t['arm'] == 'reference' else None,
                     'graph_result': result, 'step_checks': checks})
    for row in rows:
        add_pipeline_fields(plan,row,objects,statuses,format_statuses)
    result = aggregate(plan, rows, statuses, usages, state)
    return result



def route_values(problem,rule_ids):
    depths={a:0 for a in problem['facts']}
    rules={r['id']:r for r in problem['rules']}
    for rid in rule_ids:
        r=rules[rid]
        depths[r['conclusion']]=1+max(depths[a] for a in r['premises'])
    return {'D':depths[problem['goal']],'W':len(rule_ids)}

def counts(values):
    return {'assigned':len(values),'measured':sum(v is not None for v in values),
            'successes':sum(v is True for v in values),'failures':sum(v is False for v in values),
            'unmeasured':sum(v is None for v in values)}

def conjunction(values):return None if any(v is None for v in values) else all(values)

def _usage(us):
    return {k:{'sum_observed':sum(u[k] for u in us if u.get(k) is not None),
               'missing':sum(u.get(k) is None for u in us)} for k in legacy_report.USAGE}


def paired_counts(pairs, key):
    result = dict(assigned=len(pairs), both_success=0, left_only=0, right_only=0, both_failure=0, not_comparable=0)
    for a,b in pairs:
        x,y=a[key],b[key]
        tag = 'not_comparable' if x is None or y is None else 'both_success' if x and y else 'left_only' if x else 'right_only' if y else 'both_failure'
        result[tag]+=1
    return result


def _pair_rows(rows):
    result=[]
    for key in sorted({r['pair_id'] for r in rows if r['pair_id']}):
        lo,hi=sorted([r for r in rows if r['pair_id']==key], key=lambda r:r['condition']!='shallow')
        k=lo['metric']; scheduled=lo['generation_scheduled'] and hi['generation_scheduled']
        select=conjunction([lo['selection_success'],hi['selection_success']])
        selected=[lo['selected_'+k],hi['selected_'+k]]
        actual=[lo['actual_'+k],hi['actual_'+k]]
        def sign(v):
            return 'unmeasured' if any(x is None for x in v) else 'forward' if v[0]<v[1] else 'reversed' if v[0]>v[1] else 'same'
        result.append({'pair_id':key,'problem_id':lo['problem_id'],'seed':lo['seed'],'order':lo['order'],'labels':lo['labels'],'metric':k,
                       'generation_scheduled':scheduled,'selection_success':select,
                       'end_to_end_success':conjunction([lo['metric_end_to_end'],hi['metric_end_to_end']]) if scheduled else None,
                       'selection_direction':sign(selected),
                       'valid_graph_direction':sign(actual) if scheduled else 'not_scheduled'})
    return result


def aggregate(plan, rows, statuses, usages, state):
    variants=plan['protocol']['selector_variants'];groups={}
    for row in rows:
        row['support_diagnostic']=None
        if row['arm']=='model' and row['selector_variant']!='candidate_id':
            t=next(t for t in plan['trials'] if t['id']==row['trial_id'])
            ms=design.measurements_for(plan,t);field='goal_depth' if row['metric']=='D' else 'rule_count'
            values=[core.load(m['content'])[field] for m in ms]
            value=(min if row['condition']=='shallow' else max)(values)
            target=ms[values.index(value)]['candidate_id']
            row['support_diagnostic']={'origin':'experimenter_frozen_control_not_model_output',
                'supplied_requested_values':values,'supplied_extreme_candidate_id':target,
                'follows_supplied_extreme':row['candidate_id']==target if row['selector_status']=='ok' else None}
    for variant in variants:
        rs=[r for r in rows if r['selector_variant']==variant];pairs=_pair_rows(rs);robust=[];contrasts=[]
        for metric,pid,seed in sorted({(p['metric'],p['problem_id'],p['seed']) for p in pairs}):
            ps=[p for p in pairs if (p['metric'],p['problem_id'],p['seed'])==(metric,pid,seed)]
            scheduled=all(p['generation_scheduled'] for p in ps)
            robust.append({'metric':metric,'problem_id':pid,'seed':seed,'generation_scheduled':scheduled,
               'selection_success':conjunction([p['selection_success'] for p in ps]),
               'end_to_end_success':conjunction([p['end_to_end_success'] for p in ps]) if scheduled else None})
        for pid,seed,order,labels in sorted({(r['problem_id'],r['seed'],r['order'],r['labels']) for r in rs if r['metric']=='W'}):
            subset=[r for r in rs if (r['problem_id'],r['seed'],r['order'],r['labels'])==(pid,seed,order,labels)]
            contrasts.append({'problem_id':pid,'seed':seed,'order':order,'labels':labels,
                'all_four_selections_correct':conjunction([r['selection_success'] for r in subset]),
                'end_to_end_scheduled':False})
        totals={}
        for metric in ['D','W']:
            subset=[r for r in rs if r['metric']==metric];generated=[r for r in subset if r['generation_scheduled']]
            ps=[p for p in pairs if p['metric']==metric];rb=[p for p in robust if p['metric']==metric]
            totals[metric]={'mapping_success':counts([r['mapping_success'] for r in subset]),
                'selection_success':counts([r['selection_success'] for r in subset]),
                'conditional_choice':counts([r['structural_choice_correct'] for r in subset if r['mapping_success'] is True]),
                'generator_success':counts([r['generator_success'] for r in generated]),
                'metric_end_to_end':counts([r['metric_end_to_end'] for r in generated]),
                'selection_pairs':counts([p['selection_success'] for p in ps]),
                'end_to_end_pairs':counts([p['end_to_end_success'] for p in ps if p['generation_scheduled']]),
                'presentation_robust_selection':counts([p['selection_success'] for p in rb]),
                'presentation_robust_end_to_end':counts([p['end_to_end_success'] for p in rb if p['generation_scheduled']]),
                'follows_supplied_extreme':counts([r['support_diagnostic']['follows_supplied_extreme'] for r in subset if r['support_diagnostic']])}
        tids={r['trial_id'] for r in rs};ops=[o for o in plan['slots'] if o['trial_id'] in tids]
        stage_usage={}
        for stage in ['compare','select','generation']:
            us=[usages[o['id']] for o in ops if o['id'] in usages and (o['stage']==stage if stage!='generation' else o['stage'] in ('facts','rule','final'))]
            stage_usage[stage]={'calls':len(us),'fields':_usage(us)}
        observed=[r for r in rs if r['selector_status']=='ok']
        groups[variant]={'totals':totals,'pairs':pairs,'presentation_robust_groups':robust,'metric_discrimination':contrasts,
            'position_id_diagnostic':{m:{'observed_choices':sum(r['metric']==m for r in observed),
                'first_position':sum(r['metric']==m and r['selected_position']==0 for r in observed),
                'route_0_id':sum(r['metric']==m and r['candidate_id']=='route_0' for r in observed)} for m in ['D','W']},
            'usage_by_stage':stage_usage,'selection_statuses':dict(sorted(Counter(r['selector_status'] for r in rs).items()))}
    comparisons={}
    for name,left,right in [('C0_anchor_support','candidate_id','correct_values'),('C1_two_stage_vs_supported','correct_values','two_stage_values'),('C2_oracle_lookup_vs_supported','correct_values','oracle_lookup')]:
        matched=[]
        for uid in sorted({r['unit_id'] for r in rows if r['arm']=='model'}):
            matched.append(tuple(next(r for r in rows if r['unit_id']==uid and r['selector_variant']==v) for v in (left,right)))
        by_metric={}
        for metric in ['D','W']:
            selected=[(a,b) for a,b in matched if a['metric']==metric]
            generated=[(a,b) for a,b in selected if a['generation_scheduled'] and b['generation_scheduled']]
            lp=[p for p in groups[left]['pairs'] if p['metric']==metric]
            rp=groups[right]['pairs'];key=lambda p:(p['metric'],p['problem_id'],p['seed'],p['order'],p['labels'])
            pairsets=[(a,next(b for b in rp if key(b)==key(a))) for a in lp]
            by_metric[metric]={'selection':paired_counts(selected,'selection_success'),
                'generator':paired_counts(generated,'generator_success'),'end_to_end':paired_counts(generated,'metric_end_to_end'),
                'selection_pairs':paired_counts(pairsets,'selection_success'),
                'end_to_end_pairs':paired_counts([(a,b) for a,b in pairsets if a['generation_scheduled'] and b['generation_scheduled']],'end_to_end_success'),
                'changed_path':counts([a['selected_rule_ids']!=b['selected_rule_ids'] if a['selector_status']==b['selector_status']=='ok' else None for a,b in selected]),
                'both_follow_supplied_extreme':counts([conjunction([a['support_diagnostic']['follows_supplied_extreme'],b['support_diagnostic']['follows_supplied_extreme']]) for a,b in selected if a['support_diagnostic'] and b['support_diagnostic']])}
        comparisons[name]={'left':left,'right':right,'by_metric':by_metric}
    return {'stage_diagnostics':stage_diagnostics(plan,rows),'structural_comparison':structural_analysis(plan,groups,rows),'contract':'v086-summary-r1','provenance':plan['provenance'],'state':state,'groups':groups,'hypothesis_comparisons':comparisons,
        'reference':counts([r['reference_success'] for r in rows if r['arm']=='reference']),
        'reference_shared_not_duplicated':True,'trials':rows,'call_statuses':dict(sorted(Counter(statuses.values()).items())),
        'usage':_usage(list(usages.values())), 'distinct_structural_problems':8,'new_heldout_structural_cases':8,'iid_structure_sampling':False,
        'frozen_control_origin':'experimenter_not_model_generated', 'model_profile_calls':0,
        'diagnostic_only':'W all arms and oracle_lookup: selection/lookup only; not D end-to-end evidence',
        'decision':'close_frozen_holdout_batch_no_automatic_followup' if state=='complete' else 'preserve_incomplete_no_retry'}


def structural_analysis(plan, groups, rows):
    """주평가는 구조별 두 단계 선택−기존 수치 지원의 양방향 D 종단 차이다."""
    left,right=plan['protocol']['primary_comparison'];cases=[]
    for problem in plan['protocol']['problems']:
        pid=problem['id'];arms={};by_arm={}
        for variant in plan['protocol']['generation_selector_variants']:
            ps=sorted([p for p in groups[variant]['pairs'] if p['problem_id']==pid and p['metric']=='D'],key=lambda p:(p['seed'],p['order'],p['labels']))
            by_arm[variant]=ps
            subset=[r for r in rows if r['problem_id']==pid and r['selector_variant']==variant and r['metric']=='D']
            arms[variant]={'selection':counts([r['selection_success'] for r in subset]),'end_to_end':counts([r['metric_end_to_end'] for r in subset]),
                          'pairs':counts([p['end_to_end_success'] for p in ps]),'all_seeds_all_presentations':conjunction([p['end_to_end_success'] for p in ps])}
        matched=list(zip(by_arm[left],by_arm[right]))
        if len(matched)!=8:raise ValueError('구조별 사전 배정 8쌍 불일치')
        tally=paired_counts(matched,'end_to_end_success')
        delta=None if tally['not_comparable'] else (tally['right_only']-tally['left_only'])/8
        refs=[r for r in rows if r['arm']=='reference' and r['problem_id']==pid]
        cases.append({'problem_id':pid,'family':plan['protocol']['problem_metadata'][pid]['family'],'numeric_profile_regime':plan['protocol']['problem_metadata'][pid]['numeric_profile_regime'],'arms':arms,
                      'paired_end_to_end':tally,'pair_rate_difference':delta,
                      'reference_by_direction':{d:counts([r['reference_success'] for r in refs if r['condition']==d]) for d in ('shallow','deep')}})
    deltas=[c['pair_rate_difference'] for c in cases];families={}
    for family in ('equal_rule_count','inverted_rule_count'):
        vs=[c['pair_rate_difference'] for c in cases if c['family']==family]
        families[family]={'assigned_structures':len(vs),'complete_structures':sum(v is not None for v in vs),
                          'mean_pair_rate_difference':sum(vs)/len(vs) if all(v is not None for v in vs) else None}
    return {'unit':'prespecified_new_structural_case','left':left,'right':right,'assigned_structures':len(cases),
            'complete_structures':sum(v is not None for v in deltas),'improved_structures':sum(v is not None and v>0 for v in deltas),
            'worsened_structures':sum(v is not None and v<0 for v in deltas),'unchanged_structures':sum(v==0 for v in deltas),
            'unmeasured_structures':sum(v is None for v in deltas),'mean_pair_rate_difference':sum(deltas)/len(deltas) if all(v is not None for v in deltas) else None,
            'families':families,'numeric_profile_strata':{kind:{'assigned_structures':sum(c['numeric_profile_regime']==kind for c in cases),'mean_pair_rate_difference':(sum(c['pair_rate_difference'] for c in cases if c['numeric_profile_regime']==kind)/sum(c['numeric_profile_regime']==kind for c in cases)) if all(c['pair_rate_difference'] is not None for c in cases if c['numeric_profile_regime']==kind) else None} for kind in ('previous_depth_profile','new_depth_profile')},'cases':cases,'inferential_p_value':None,
            'interpretation':'v085 절차를 동결한 신규 구조쌍 8개의 재현이다. 기존 12쌍과 비동형이며 seed/표시/숫자 요청 반복은 독립 구조가 아니다. IID 표본 추론이 아니다.'}


def add_pipeline_fields(plan,row,objects,statuses,formats):
    t=next(t for t in plan['trials'] if t['id']==row['trial_id']);v=t['selector_variant']
    row.update(diagnostic_only=v=='oracle_lookup',final_choice_success=row['selection_success'],
               comparison_status='not_scheduled',comparison_value=None,comparison_success=None,
               lookup_value_source=None,lookup_input_value=None,lookup_adherence=None)
    gen=row['generator_success'];actual=row['actual_'+row['metric']]
    row['target_graph_success_without_selection_trace']=None if gen is None else bool(gen and actual==row['target_value'])
    if v not in ('two_stage_values','oracle_lookup'):return
    if v=='two_stage_values':
        sid=t['comparison_slot_id'];st=statuses[sid];obj=objects[sid]
        value=obj['target_value'] if st=='ok' else None
        success=value==row['target_value'] if st=='ok' else False if st in ('invalid_json','invalid_schema') else None
        row.update(comparison_status=st,comparison_value=value,comparison_success=success,lookup_value_source='model_comparison',lookup_input_value=value)
    else:
        row.update(lookup_value_source='experimenter_target_diagnostic_only',lookup_input_value=row['target_value'])
    value=row['lookup_input_value'];sid=t['selection_slot_id'];fmt=formats[sid]
    if value is not None:
        if fmt=='ok':
            field='goal_depth' if row['metric']=='D' else 'rule_count'
            ms=design.measurements_for(plan,t)
            matches=[m['candidate_id'] for m in ms if core.load(m['content'])[field]==value]
            expected=matches[0] if len(matches)==1 else None
            row['lookup_adherence']=objects[sid]['candidate_id']==expected
        elif fmt in ('invalid_json','invalid_schema'):
            row['lookup_adherence']=False
    if v=='two_stage_values':
        comp=row['comparison_success']
        if comp is False:success=False
        elif comp is None:success=None
        else:success=conjunction([comp,row['lookup_adherence'],row['final_choice_success']])
        row['selection_success']=success
        if t['generate']:
            if row['candidate_id'] is None and success is False:row['metric_end_to_end']=False
            else:row['metric_end_to_end']=None if success is None or gen is None else bool(success and row['target_graph_success_without_selection_trace'])


def stage_diagnostics(plan,rows):
    out={}
    for variant in plan['protocol']['selector_variants']:
        rs=[r for r in rows if r['selector_variant']==variant];by_metric={}
        for metric in ('D','W'):
            sub=[r for r in rs if r['metric']==metric];cells={}
            for position in (0,1):
                for cid in plan['protocol']['candidate_ids']:
                    selected=[]
                    for r in sub:
                        t=next(t for t in plan['trials'] if t['id']==r['trial_id']);cs=design.cards(plan,t);p=design.problem_for(plan,t)
                        values=[route_values(p,[x['id'] for x in c['rules']])[metric] for c in cs]
                        idx=values.index(r['target_value'])
                        if idx==position and cs[idx]['candidate_id']==cid:selected.append(r)
                    cells[f'position_{position+1}_{cid}']={'final_choice':counts([r['final_choice_success'] for r in selected]),
                                                       'full_selection':counts([r['selection_success'] for r in selected])}
            by_metric[metric]={'comparison':counts([r['comparison_success'] for r in sub if variant=='two_stage_values']),
                               'lookup_adherence':counts([r['lookup_adherence'] for r in sub if variant in ('two_stage_values','oracle_lookup')]),
                               'lookup_given_correct_comparison':counts([r['lookup_adherence'] for r in sub if r['comparison_success'] is True]),
                               'final_choice_without_trace':counts([r['final_choice_success'] for r in sub]),
                               'target_graph_without_trace':counts([r['target_graph_success_without_selection_trace'] for r in sub if r['generation_scheduled']]),
                               'accidental_target_graph_after_wrong_comparison':counts([r['target_graph_success_without_selection_trace'] for r in sub if r['comparison_success'] is False and r['generation_scheduled']]),
                               'target_position_id_cells':cells}
        out[variant]=by_metric
    return out
