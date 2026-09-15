"""실행 후 채점 전용. 규칙 목록의 보정·실행 재개·모델 호출을 하지 않는다."""
from collections import Counter
import bootstrap
import report as legacy_report
import stages, measure
import core081 as core
import design081 as design
from render081 import render

MODEL_OUTPUT_FAILURES = {'invalid_json', 'invalid_schema', 'unmappable_selection'}


def parse_response(record, raw, spec, phase, selector):
    status, obj, usage = legacy_report.parse_response(record, raw, spec['model'], phase, spec, 'explicit_rule')
    if phase == 'select' and selector == 'rule_ids' and status in ('ok', 'invalid_schema'):
        status = 'ok' if design.route_list_shape(obj) else 'invalid_schema'
    return status, obj, usage


def copy_diagnostic(plan, trial, obj):
    if trial['selector_variant'] != 'rule_ids':
        return None
    if not design.route_list_shape(obj):
        return {'kind': 'invalid_shape', 'same_multiset_candidate_id': None}
    ids = obj['rule_ids']
    cards = design.cards(plan, trial)
    exact = [c['candidate_id'] for c in cards if [r['id'] for r in c['rules']] == ids]
    unordered = [c['candidate_id'] for c in cards if sorted(r['id'] for r in c['rules']) == sorted(ids)]
    if exact:
        kind = 'exact_candidate'
    elif unordered:
        kind = 'order_mismatch'
    elif len(ids) != len(set(ids)):
        kind = 'duplicate_rule'
    elif any(rid not in {r['id'] for r in design.problem_for(plan, trial)['rules']} for rid in ids):
        kind = 'unknown_rule'
    else:
        kind = 'not_a_complete_candidate'
    # 이 값은 보고용이다. 실행기 매핑은 항상 정확한 순서 일치만 사용한다.
    return {'kind': kind, 'same_multiset_candidate_id': unordered[0] if len(unordered) == 1 else None}


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
        rows.append({'trial_id': t['id'], 'unit_id': t['unit_id'], 'selector_variant': t['selector_variant'],
                     'arm': t['arm'], 'problem_id': t['problem_id'], 'seed': t['seed'],
                     'metric': t['metric'], 'condition': t['condition'], 'order': t['candidate_order_index'],
                     'labels': t['id_assignment_index'], 'pair_id': t['pair_id'],
                     'selector_format_status': fs, 'selector_status': ss, 'mapping_success': mapped,
                     'structural_choice_correct': choice, 'copy_diagnostic': copy_diagnostic(plan, t, objects.get(sid)) if sid and fs in ('ok', 'invalid_schema') else ({'kind': 'invalid_json', 'same_multiset_candidate_id': None} if t['selector_variant'] == 'rule_ids' and fs == 'invalid_json' else None),
                     'candidate_id': None if route is None else route['candidate_id'],
                     'selected_rule_ids': None if route is None else route['rule_ids'],
                     'selected_position': None if route is None else [c['candidate_id'] for c in cs].index(route['candidate_id']),
                     'selected_D': None if chosen is None else chosen['D'], 'selected_W': None if chosen is None else chosen['W'],
                     'target_value': target, 'selection_success': selection,
                     'generator_success': generated, 'generator_status': generator_status,
                     'actual_D': actual_D, 'actual_W': actual_W, 'metric_end_to_end': end,
                     'reference_success': goal if t['arm'] == 'reference' else None,
                     'graph_result': result, 'step_checks': checks})
    return aggregate(plan, rows, statuses, usages, state)



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

def group_aggregate(plan,rows,statuses,usages,state):
    pairs=[]
    for key in sorted({r['pair_id'] for r in rows if r['pair_id'] is not None}):
        group=sorted([r for r in rows if r['pair_id']==key],key=lambda r:r['condition']!='shallow')
        lo,hi=group
        selected_key='selected_'+lo['metric'];actual_key='actual_'+lo['metric']
        def direction(values):
            if any(v is None for v in values):return 'unmeasured'
            return 'forward' if values[0]<values[1] else 'reversed' if values[0]>values[1] else 'same'
        sel_values=[r[selected_key] if r['selector_status']=='ok' else None for r in group]
        gen_values=[r[actual_key] if r['generator_success'] is True else None for r in group]
        pairs.append({'pair_id':key,'metric':lo['metric'],'problem_id':lo['problem_id'],'seed':lo['seed'],
                      'order':lo['order'],'labels':lo['labels'],
                      'selection_success':conjunction([r['selection_success'] for r in group]),
                      'end_to_end_success':conjunction([r['metric_end_to_end'] for r in group]),
                      'selection_direction':direction(sel_values),'valid_graph_direction':direction(gen_values)})
    robust=[]
    for metric,pid,seed in sorted({(p['metric'],p['problem_id'],p['seed']) for p in pairs}):
        ps=[p for p in pairs if (p['metric'],p['problem_id'],p['seed'])==(metric,pid,seed)]
        robust.append({'metric':metric,'problem_id':pid,'seed':seed,'presentation_pairs':len(ps),
                       'selection_success':conjunction([p['selection_success'] for p in ps]),
                       'end_to_end_success':conjunction([p['end_to_end_success'] for p in ps])})
    contrasts=[]
    for pid,seed,order,labels in sorted({(r['problem_id'],r['seed'],r['order'],r['labels']) for r in rows if r['arm']=='model' and r['metric']=='W'}):
        rs=[r for r in rows if r['arm']=='model' and (r['problem_id'],r['seed'],r['order'],r['labels'])==(pid,seed,order,labels)]
        by={(r['metric'],r['condition']):r for r in rs}
        flips=[]
        for c in ['shallow','deep']:
            a,b=by['D',c],by['W',c]
            flips.append(a['candidate_id']!=b['candidate_id'] if a['selector_status']==b['selector_status']=='ok' else None)
        contrasts.append({'problem_id':pid,'seed':seed,'order':order,'labels':labels,
                          'opposite_choices_for_both_directions':conjunction(flips),
                          'all_four_selections_correct':conjunction([r['selection_success'] for r in rs]),
                          'all_four_end_to_end_correct':conjunction([r['metric_end_to_end'] for r in rs])})
    totals={}
    for metric in ['D','W']:
        rs=[r for r in rows if r['arm']=='model' and r['metric']==metric]
        ps=[p for p in pairs if p['metric']==metric];rob=[r for r in robust if r['metric']==metric]
        totals[metric]={k:counts([r[k] for r in rs]) for k in ['selection_success','generator_success','metric_end_to_end']}
        totals[metric].update(selection_pairs=counts([p['selection_success'] for p in ps]),end_to_end_pairs=counts([p['end_to_end_success'] for p in ps]),
                             presentation_robust_selection=counts([r['selection_success'] for r in rob]),presentation_robust_end_to_end=counts([r['end_to_end_success'] for r in rob]))
    refs=counts([r['reference_success'] for r in rows if r['arm']=='reference'])
    observed=[r for r in rows if r['arm']=='model' and r['selector_status']=='ok']
    bias={'observed_choices':len(observed),'first_position':sum(r['selected_position']==0 for r in observed),'route_0_id':sum(r['candidate_id']=='route_0' for r in observed)}
    return {'contract':'v081-summary-r1','provenance':plan['provenance'],'state':state,'totals':totals,'reference':refs,
            'call_statuses':dict(sorted(Counter(statuses.values()).items())),
            'usage':{k:{'sum_observed':sum(u[k] for u in usages if u.get(k) is not None),'missing':sum(u.get(k) is None for u in usages)} for k in legacy_report.USAGE},
            'position_id_diagnostic':bias,'trials':rows,'pairs':pairs,'presentation_robust_groups':robust,
            'metric_discrimination':contrasts,'distinct_structural_problems':4,'new_independent_structures':0,
            'decision':'close_completed_diagnostic_no_automatic_followup' if state=='complete' else 'preserve_incomplete_no_retry'}


def paired_counts(pairs, key):
    out = {'assigned': len(pairs), 'both_success': 0, 'candidate_id_only': 0,
           'rule_ids_only': 0, 'both_failure': 0, 'not_comparable': 0}
    for a, b in pairs:
        x, y = a[key], b[key]
        tag = ('not_comparable' if x is None or y is None else 'both_success' if x and y
               else 'candidate_id_only' if x else 'rule_ids_only' if y else 'both_failure')
        out[tag] += 1
    return out


def aggregate(plan, rows, statuses, usages, state):
    groups = {}
    fields = ['totals', 'pairs', 'presentation_robust_groups', 'metric_discrimination',
              'position_id_diagnostic', 'usage', 'call_statuses']
    for variant in plan['protocol']['selector_variants']:
        rs = [r for r in rows if r['selector_variant'] == variant]
        tids = {r['trial_id'] for r in rs}
        ops = [op for op in plan['slots'] if op['trial_id'] in tids]
        group = group_aggregate(plan, rs, {o['id']: statuses[o['id']] for o in ops},
                                [usages[o['id']] for o in ops if o['id'] in usages], state)
        groups[variant] = {k: group[k] for k in fields}
        groups[variant]['mapping'] = {m: counts([r['mapping_success'] for r in rs if r['metric'] == m]) for m in ['D', 'W']}
        groups[variant]['conditional_choice'] = {m: counts([r['structural_choice_correct'] for r in rs if r['metric'] == m]) for m in ['D', 'W']}
        groups[variant]['selection_statuses'] = dict(sorted(Counter(r['selector_status'] for r in rs).items()))
        groups[variant]['usage_by_stage'] = {}
        for stage in ['select', 'generation']:
            us = [usages[o['id']] for o in ops if o['id'] in usages and ((o['stage'] == 'select') == (stage == 'select'))]
            groups[variant]['usage_by_stage'][stage] = {'calls': len(us), 'fields': {
                k: {'sum_observed': sum(u[k] for u in us if u.get(k) is not None), 'missing': sum(u.get(k) is None for u in us)}
                for k in legacy_report.USAGE}}
    matched = []
    for uid in sorted({r['unit_id'] for r in rows if r['arm'] == 'model'}):
        a = next(r for r in rows if r['unit_id'] == uid and r['selector_variant'] == 'candidate_id')
        b = next(r for r in rows if r['unit_id'] == uid and r['selector_variant'] == 'rule_ids')
        matched.append((a, b))
    paired = {m: {k: paired_counts([(a, b) for a, b in matched if a['metric'] == m], k)
                      for k in ['mapping_success', 'selection_success', 'generator_success', 'metric_end_to_end']}
              for m in ['D', 'W']}
    # 양방향 성공도 같은 문제·seed·표시 안에서 군간 직접 대조한다.
    paired_pairs = {}
    for metric in ['D', 'W']:
        left = [p for p in groups['candidate_id']['pairs'] if p['metric'] == metric]
        right = groups['rule_ids']['pairs']
        pairs = [(p, next(q for q in right if (q['metric'], q['problem_id'], q['seed'], q['order'], q['labels']) ==
                          (p['metric'], p['problem_id'], p['seed'], p['order'], p['labels']))) for p in left]
        paired_pairs[metric] = {k: paired_counts(pairs, k) for k in ['selection_success', 'end_to_end_success']}
    return {'contract': 'v081-summary-r1', 'provenance': plan['provenance'], 'state': state,
            'groups': groups, 'paired_trials': paired, 'paired_pairs': paired_pairs,
            'reference': counts([r['reference_success'] for r in rows if r['arm'] == 'reference']),
            'reference_shared_not_duplicated': True, 'trials': rows,
            'call_statuses': dict(sorted(Counter(statuses.values()).items())),
            'usage': {k: {'sum_observed': sum(u[k] for u in usages.values() if u.get(k) is not None),
                          'missing': sum(u.get(k) is None for u in usages.values())} for k in legacy_report.USAGE},
            'copy_diagnostic_counts': dict(sorted(Counter(r['copy_diagnostic']['kind'] for r in rows if r['copy_diagnostic']).items())),
            'distinct_structural_problems': 4, 'new_independent_structures': 0,
            'decision': 'close_completed_paired_selector_batch_no_automatic_followup' if state == 'complete' else 'preserve_incomplete_no_retry'}
