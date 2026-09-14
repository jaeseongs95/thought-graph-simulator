"""기존 graph/단계 판정과 D/W 목표 달성을 분리하는 생산 집계. 실행 뒤에만 사용한다."""
from collections import Counter
import bootstrap
import report as legacy_report
import stages,measure
import design080 as design
from render080 import render


def route_values(problem,rule_ids):
    depths={a:0 for a in problem['facts']}
    rules={r['id']:r for r in problem['rules']}
    for rid in rule_ids:
        r=rules[rid]
        depths[r['conclusion']]=1+max(depths[a] for a in r['premises'])
    return {'D':depths[problem['goal']],'W':len(rule_ids)}


def summarize(plan,records,responses,state):
    spec=plan['protocol'];parsed={};statuses={};usages=[]
    for slot in plan['slots']:
        rec=records.get(slot['id'])
        st,obj,usage=legacy_report.parse_response(rec,responses.get(slot['id'],b''),spec['model'],slot['stage'],spec,'explicit_rule')
        parsed[slot['id']]=obj;statuses[slot['id']]=st
        if rec and rec['kind']=='call':usages.append(usage)
    rows=[]
    for t in plan['trials']:
        problem=design.problem_for(plan,t);route=design.selected_route(plan,t,responses)
        cs=design.cards(plan,t)
        candidates={c['candidate_id']:route_values(problem,[r['id'] for r in c['rules']]) for c in cs}
        vals=[x[t['metric']] for x in candidates.values()]
        target=(min if t['condition']=='shallow' else max)(vals)
        selected=None if route is None else candidates[route['candidate_id']]
        ss=statuses[t['selection_slot_id']] if t['arm']=='model' else 'experimenter_reference_not_inference'
        selection_success=None if ss!='ok' else selected[t['metric']]==target
        sequence=[]
        if route is not None:
            for op in plan['slots']:
                if op['trial_id']!=t['id'] or op['stage']=='select':continue
                if op['stage']=='rule' and op['rule_position']>=len(route['rule_ids']):continue
                sequence.append({**op,'requested_rule_id':route['rule_ids'][op['rule_position']] if op['stage']=='rule' else None})
        ready={op['id'] for op in sequence if statuses[op['id']]=='ok'}
        checks=stages.audit_steps(problem,sequence,parsed,ready) if sequence else []
        all_ready=bool(sequence) and len(ready)==len(sequence)
        graph=stages.assemble(sequence,parsed) if all_ready else None
        result=measure.assess(problem,graph) if graph is not None else None
        actual_D=None if result is None else result['actual_D']
        actual_W=(sum(n['rule'] is not None for n in graph['nodes'])
                  if result is not None and result['strict_valid'] is True else None)
        fidelity=None if graph is None else [n['rule'] for n in graph['nodes'] if n['rule'] is not None]==route['rule_ids']
        generated=(all(c['valid'] is True for c in checks) and result['strict_valid'] is True
                   and fidelity and actual_D==selected['D'] and actual_W==selected['W']) if all_ready else None
        actual=actual_D if t['metric']=='D' else actual_W
        goal_success=(generated and actual==target) if generated is not None else None
        end=(selection_success and goal_success) if selection_success is not None and generated is not None else None
        rows.append({'trial_id':t['id'],'arm':t['arm'],'problem_id':t['problem_id'],'seed':t['seed'],
                     'metric':t['metric'],'condition':t['condition'],'order':t['candidate_order_index'],
                     'labels':t['id_assignment_index'],'pair_id':t['pair_id'],
                     'selector_status':ss,'candidate_id':None if route is None else route['candidate_id'],
                     'selected_position':None if route is None else [c['candidate_id'] for c in cs].index(route['candidate_id']),
                     'selected_D':None if selected is None else selected['D'],'selected_W':None if selected is None else selected['W'],
                     'target_value':target,'selection_success':selection_success,'generator_success':generated,
                     'actual_D':actual_D,'actual_W':actual_W,'metric_end_to_end':end,
                     'reference_success':goal_success if t['arm']=='reference' else None,
                     'graph_result':result,'step_checks':checks})
    return aggregate(plan,rows,statuses,usages,state)


def counts(values):
    return {'assigned':len(values),'measured':sum(v is not None for v in values),
            'successes':sum(v is True for v in values),'failures':sum(v is False for v in values),
            'unmeasured':sum(v is None for v in values)}


def conjunction(values):return None if any(v is None for v in values) else all(values)


def aggregate(plan,rows,statuses,usages,state):
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
    return {'contract':'v080-summary-r1','provenance':plan['provenance'],'state':state,'totals':totals,'reference':refs,
            'call_statuses':dict(sorted(Counter(statuses.values()).items())),
            'usage':{k:{'sum_observed':sum(u[k] for u in usages if u.get(k) is not None),'missing':sum(u.get(k) is None for u in usages)} for k in legacy_report.USAGE},
            'position_id_diagnostic':bias,'trials':rows,'pairs':pairs,'presentation_robust_groups':robust,
            'metric_discrimination':contrasts,'distinct_structural_problems':4,'new_independent_structures':0,
            'decision':'close_completed_diagnostic_no_automatic_followup' if state=='complete' else 'preserve_incomplete_no_retry'}
