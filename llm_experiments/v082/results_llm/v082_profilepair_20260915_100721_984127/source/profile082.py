"""후보 계산표의 사후 채점. 실행·선택·원응답 보정에는 사용하지 않는다."""
from collections import Counter
import bootstrap
import report as old_report
import core082 as core


def profile_shape(obj):
    def exact_keys(x, keys):
        return type(x) is dict and set(x) == set(keys)
    def integer(x):
        return type(x) is int and 0 <= x <= 1024
    def string(x):
        return type(x) is str and 1 <= len(x) <= 128
    def array(x):
        return type(x) is list and 1 <= len(x) <= 16
    def atom_value(x):
        return exact_keys(x, ('atom', 'depth')) and string(x['atom']) and integer(x['depth'])
    return (exact_keys(obj, ('facts', 'steps', 'goal_depth', 'rule_count'))
            and array(obj['facts']) and all(atom_value(x) for x in obj['facts'])
            and array(obj['steps']) and all(exact_keys(x, ('rule_id','conclusion','premises','depth'))
                and string(x['rule_id']) and string(x['conclusion']) and integer(x['depth'])
                and array(x['premises']) and all(atom_value(p) for p in x['premises']) for x in obj['steps'])
            and integer(obj['goal_depth']) and integer(obj['rule_count']))


def grade(problem, rules, status, value):
    depths = {a: 0 for a in problem['facts']}
    expected = []
    for r in rules:
        premises = [(a, depths[a]) for a in r['premises']]
        d = 1 + max(v for _,v in premises)
        depths[r['conclusion']] = d
        expected.append((r, premises, d))
    truth = {'D': depths[problem['goal']], 'W': len(rules)}
    failed = status in ('invalid_json','invalid_schema')
    out = {'status': status, 'trace_success': False if failed else None,
           'D_correct': False if failed else None, 'W_correct': False if failed else None,
           'reported_D': None, 'reported_W': None, 'facts_correct': None,
           'step_count_correct': None, 'steps': [], 'expected_D': truth['D'], 'expected_W': truth['W']}
    if status != 'ok':
        return out
    out.update(reported_D=value['goal_depth'], reported_W=value['rule_count'],
               D_correct=value['goal_depth']==truth['D'], W_correct=value['rule_count']==truth['W'],
               facts_correct=Counter((a['atom'],a['depth']) for a in value['facts'])==Counter((a,0) for a in problem['facts']),
               step_count_correct=len(value['steps'])==len(expected))
    for i,(r,prem,d) in enumerate(expected):
        got = value['steps'][i] if i < len(value['steps']) else None
        checks = {'rule_id_correct': got is not None and got['rule_id']==r['id'],
                  'conclusion_correct': got is not None and got['conclusion']==r['conclusion'],
                  'premises_correct': got is not None and Counter((x['atom'],x['depth']) for x in got['premises'])==Counter(prem),
                  'depth_correct': got is not None and got['depth']==d,
                  'arithmetic_correct': got is not None and got['depth']==1+max(x['depth'] for x in got['premises'])}
        out['steps'].append({'position':i, 'rule_id':r['id'], **checks, 'valid':all(checks.values())})
    out['trace_success'] = bool(out['facts_correct'] and out['step_count_correct'] and out['D_correct'] and out['W_correct']
                                and all(x['valid'] for x in out['steps']))
    return out


def _counts(xs):
    return {'assigned':len(xs),'measured':sum(x is not None for x in xs),'successes':sum(x is True for x in xs),
            'failures':sum(x is False for x in xs),'unmeasured':sum(x is None for x in xs)}


def _and(xs):
    return None if any(x is None for x in xs) else all(xs)


def attach_profiles(summary, plan, records, raws):
    spec=plan['protocol']; profiles=[]
    for op in plan['slots']:
        if op['stage']!='profile':
            continue
        t=next(t for t in plan['trials'] if t['id']==op['trial_id'])
        p=next(p for p in spec['problems'] if p['id']==t['problem_id'])
        ids=spec['reference_plans'][p['id']][spec['reference_conditions'][op['candidate_kind']]]
        rules=[next(r for r in p['rules'] if r['id']==rid) for rid in ids]
        st,obj,_=old_report.parse_response(records.get(op['id']),raws.get(op['id'],b''),spec['model'],'select',dict(spec,num_predict=spec['profile_num_predict']),'explicit_rule')
        if st in ('ok','invalid_schema'):
            st='ok' if profile_shape(obj) else 'invalid_schema'
        row={'profile_id':op['id'],'block':t['block'],'problem_id':p['id'],'seed':t['seed'],'candidate_kind':op['candidate_kind']}
        row.update(grade(p,rules,st,obj));profiles.append(row)
    by={r['profile_id']:r for r in profiles}
    for row in summary['trials']:
        row['profile_diagnostic']=None
        if row['selector_variant']!='profiled_id':
            continue
        t=next(t for t in plan['trials'] if t['id']==row['trial_id'])
        keys=[f"b{t['block']:02d}_profile_{kind}" for kind in spec['candidate_orders'][row['order']]]
        ps=[by[k] for k in keys]; values=[p['reported_'+row['metric']] for p in ps]
        trace=_and([p['trace_success'] for p in ps]); accurate=_and([p[row['metric']+'_correct'] for p in ps])
        compare='unavailable';follows=None
        if all(v is not None for v in values):
            if values[0]==values[1]:
                compare='reported_tie'
            elif row['selector_status']!='ok':
                compare='selection_unmeasured_or_invalid'
            else:
                compare='unique_reported_extreme'
                required=(min if row['condition']=='shallow' else max)(values)
                follows=values[row['selected_position']]==required
        row['profile_diagnostic']={'profile_ids':keys,'both_traces_success':trace,'both_requested_values_correct':accurate,
            'reported_comparison_status':compare,'follows_reported_extreme':follows,
            'full_pipeline_success':_and([trace,row['metric_end_to_end']])}
    diag={'unique_profile_calls':len(profiles),'shared_across_directions_metrics_presentations':True,'profiles':profiles,
          'trace':_counts([p['trace_success'] for p in profiles]),'D_values':_counts([p['D_correct'] for p in profiles]),
          'W_values':_counts([p['W_correct'] for p in profiles]), 'trial_diagnostics':{}, 'pipeline_pairs':{}}
    for m in ('D','W'):
        rs=[r for r in summary['trials'] if r['selector_variant']=='profiled_id' and r['metric']==m]
        fields=('both_traces_success','both_requested_values_correct','follows_reported_extreme','full_pipeline_success')
        diag['trial_diagnostics'][m]={k:_counts([r['profile_diagnostic'][k] for r in rs]) for k in fields}
        combos=Counter(('unmeasured' if r['profile_diagnostic']['both_requested_values_correct'] is None or r['selection_success'] is None
                         else ('values_correct' if r['profile_diagnostic']['both_requested_values_correct'] else 'values_wrong')
                              + ('__choice_correct' if r['selection_success'] else '__choice_wrong')) for r in rs)
        diag['trial_diagnostics'][m]['values_choice_cells']=dict(sorted(combos.items()))
        pairvals=[_and([r['profile_diagnostic']['full_pipeline_success'] for r in rs if r['pair_id']==key]) for key in sorted({r['pair_id'] for r in rs})]
        diag['pipeline_pairs'][m]=_counts(pairvals)
    summary['profile_analysis']=diag
    return summary
