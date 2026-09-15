"""실행 후 채점 전용. 계산표·선택·graph를 보정하거나 모델을 호출하지 않는다."""
from collections import Counter
import bootstrap
import report as legacy_report
import stages, measure
import core083 as core
import design083 as design
from render083 import render

MODEL_OUTPUT_FAILURES = {'invalid_json', 'invalid_schema', 'unmappable_selection'}


def parse_response(record, raw, spec, phase, selector):
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
            st = 'unmappable_selection'
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
                if op['trial_id'] != t['id'] or op['stage'] == 'select':
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
        for stage in ['select','generation']:
            us=[usages[o['id']] for o in ops if o['id'] in usages and ((o['stage']=='select')==(stage=='select'))]
            stage_usage[stage]={'calls':len(us),'fields':_usage(us)}
        observed=[r for r in rs if r['selector_status']=='ok']
        groups[variant]={'totals':totals,'pairs':pairs,'presentation_robust_groups':robust,'metric_discrimination':contrasts,
            'position_id_diagnostic':{m:{'observed_choices':sum(r['metric']==m for r in observed),
                'first_position':sum(r['metric']==m and r['selected_position']==0 for r in observed),
                'route_0_id':sum(r['metric']==m and r['candidate_id']=='route_0' for r in observed)} for m in ['D','W']},
            'usage_by_stage':stage_usage,'selection_statuses':dict(sorted(Counter(r['selector_status'] for r in rs).items()))}
    comparisons={}
    for name,left,right in [('H1_accuracy_support','candidate_id','correct_full'),
                            ('H2_representation','correct_full','correct_values'),
                            ('H3_value_swap','correct_values','swapped_values')]:
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
    return {'contract':'v083-summary-r1','provenance':plan['provenance'],'state':state,'groups':groups,'hypothesis_comparisons':comparisons,
        'reference':counts([r['reference_success'] for r in rows if r['arm']=='reference']),
        'reference_shared_not_duplicated':True,'trials':rows,'call_statuses':dict(sorted(Counter(statuses.values()).items())),
        'usage':_usage(list(usages.values())), 'distinct_structural_problems':4,'new_independent_structures':0,
        'frozen_control_origin':'experimenter_not_model_generated', 'model_profile_calls':0,
        'diagnostic_only':'W all arms and swapped_values D: no graph scheduled; not zero successes or unobserved execution',
        'decision':'close_frozen_three_hypothesis_batch_no_automatic_followup' if state=='complete' else 'preserve_incomplete_no_retry'}
