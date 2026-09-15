"""독립 계산표 검산: 그래프의 원자별 재귀 깊이로 기대값을 계산한다.
생산 profile082/design082/report082를 import하지 않는다.
"""
from collections import Counter
import bootstrap
import audit_model as prior
from audit_io import need


def profile_shape(x):
    def schema(v,k): return type(v) is dict and sorted(v)==sorted(k)
    def natural(v): return type(v) is int and v in range(1025)
    def token(v): return type(v) is str and 0<len(v)<129
    def sequence(v): return type(v) is list and 0<len(v)<17
    def atom(v): return schema(v,['atom','depth']) and token(v['atom']) and natural(v['depth'])
    if not schema(x,['facts','steps','goal_depth','rule_count']):return False
    if not (natural(x['goal_depth']) and natural(x['rule_count']) and sequence(x['facts']) and sequence(x['steps'])):return False
    if not all(atom(v) for v in x['facts']):return False
    for row in x['steps']:
        if not schema(row,['rule_id','conclusion','premises','depth']):return False
        if not token(row['rule_id']) or not token(row['conclusion']) or not natural(row['depth']):return False
        if not sequence(row['premises']) or not all(atom(v) for v in row['premises']):return False
    return True


def validate_profile_schema(s):
    text={'type':'string','minLength':1,'maxLength':128};num={'type':'integer','minimum':0,'maximum':1024}
    def rec(properties):return dict(type='object',properties=properties,required=list(properties),additionalProperties=False)
    def seq(item):return dict(type='array',items=item,minItems=1,maxItems=16)
    av=rec({'atom':text,'depth':num})
    expected=rec({'facts':seq(av),'steps':seq(rec({'rule_id':text,'conclusion':text,'premises':seq(av),'depth':num})),
                  'goal_depth':num,'rule_count':num})
    need(s==expected,'profile schema has no answer-valued enum or fixed rule-count lengths')


def grade(p, rules, status, obj):
    lookup={r['conclusion']:r for r in rules}
    def depth(atom):
        if atom in p['facts']:return 0
        return 1+max(map(depth,lookup[atom]['premises']))
    result={'status':status,'trace_success':None,'D_correct':None,'W_correct':None,'reported_D':None,'reported_W':None,
            'facts_correct':None,'step_count_correct':None,'steps':[],'expected_D':depth(p['goal']),'expected_W':len(rules)}
    if status in ('invalid_schema','invalid_json'):
        result.update(trace_success=False,D_correct=False,W_correct=False)
    if status!='ok':return result
    result['reported_D'],result['reported_W']=obj['goal_depth'],obj['rule_count']
    result['D_correct']=obj['goal_depth']==depth(p['goal']);result['W_correct']=obj['rule_count']==len(rules)
    result['facts_correct']=sorted((x['atom'],x['depth']) for x in obj['facts'])==sorted((a,0) for a in p['facts'])
    result['step_count_correct']=len(obj['steps'])==len(rules)
    for index,r in enumerate(rules):
        x=obj['steps'][index] if index<len(obj['steps']) else None
        rid=x is not None and x['rule_id']==r['id'];con=x is not None and x['conclusion']==r['conclusion']
        prem=x is not None and sorted((z['atom'],z['depth']) for z in x['premises'])==sorted((a,depth(a)) for a in r['premises'])
        correct=x is not None and x['depth']==depth(r['conclusion'])
        arithmetic=x is not None and (x['depth']-1)==max(z['depth'] for z in x['premises'])
        result['steps'].append(dict(position=index,rule_id=r['id'],rule_id_correct=rid,conclusion_correct=con,
                                    premises_correct=prem,depth_correct=correct,arithmetic_correct=arithmetic,valid=rid and con and prem and correct and arithmetic))
    result['trace_success']=all([result[k] for k in ('D_correct','W_correct','facts_correct','step_count_correct')]+[r['valid'] for r in result['steps']])
    return result


def tally(values):
    successes=sum(v is True for v in values);failures=sum(v is False for v in values)
    return dict(assigned=len(values),measured=successes+failures,successes=successes,failures=failures,unmeasured=len(values)-successes-failures)


def tri(values):
    return None if None in values else False not in values


def attach_profiles(summary,plan,records,raws):
    s=plan['protocol']; profiles=[];trials={t['id']:t for t in plan['trials']}
    for op in plan['slots']:
        if op['stage']!='profile':continue
        t=trials[op['trial_id']];p=next(p for p in s['problems'] if p['id']==t['problem_id'])
        ids=s['reference_plans'][p['id']][s['reference_conditions'][op['candidate_kind']]]
        rulemap={r['id']:r for r in p['rules']}
        status,x,_=prior.decode(records.get(op['id']),raws.get(op['id'],b''),dict(s,num_predict=s['profile_num_predict']),'select','explicit_rule')
        if status=='ok' or status=='invalid_schema':status='ok' if profile_shape(x) else 'invalid_schema'
        assessed=grade(p,[rulemap[r] for r in ids],status,x)
        row=dict(profile_id=op['id'],block=t['block'],problem_id=p['id'],seed=t['seed'],candidate_kind=op['candidate_kind'])
        row.update(assessed);profiles.append(row)
    for r in summary['trials']:
        r['profile_diagnostic']=None
        if r['selector_variant']!='profiled_id':continue
        t=trials[r['trial_id']];kinds=s['candidate_orders'][r['order']]
        pp=[next(x for x in profiles if x['block']==t['block'] and x['candidate_kind']==k) for k in kinds]
        computed=[x['reported_'+r['metric']] for x in pp]
        both=tri([x['trace_success'] for x in pp]);values=tri([x[r['metric']+'_correct'] for x in pp])
        follows=None;comparison='unavailable'
        if None not in computed:
            if computed[0]==computed[1]:comparison='reported_tie'
            elif r['selector_status']!='ok':comparison='selection_unmeasured_or_invalid'
            else:
                comparison='unique_reported_extreme'
                position=0 if ((computed[0]<computed[1])==(r['condition']=='shallow')) else 1
                follows=r['selected_position']==position
        r['profile_diagnostic']=dict(profile_ids=[x['profile_id'] for x in pp],both_traces_success=both,
            both_requested_values_correct=values,reported_comparison_status=comparison,follows_reported_extreme=follows,
            full_pipeline_success=tri([both,r['metric_end_to_end']]))
    diag={'unique_profile_calls':len(profiles),'shared_across_directions_metrics_presentations':True,'profiles':profiles,
          'trace':tally([p['trace_success'] for p in profiles]),'D_values':tally([p['D_correct'] for p in profiles]),
          'W_values':tally([p['W_correct'] for p in profiles]),'trial_diagnostics':{},'pipeline_pairs':{}}
    for metric in ('D','W'):
        rr=[r for r in summary['trials'] if (r['selector_variant'],r['metric'])==('profiled_id',metric)]
        fields=('both_traces_success','both_requested_values_correct','follows_reported_extreme','full_pipeline_success')
        d={key:tally([r['profile_diagnostic'][key] for r in rr]) for key in fields}
        cells={}
        for r in rr:
            v=r['profile_diagnostic']['both_requested_values_correct'];c=r['selection_success']
            if v is None or c is None:label='unmeasured'
            else:label=('values_correct' if v else 'values_wrong')+'__'+('choice_correct' if c else 'choice_wrong')
            cells[label]=cells.get(label,0)+1
        d['values_choice_cells']=dict(sorted(cells.items()));diag['trial_diagnostics'][metric]=d
        pairs={}
        for r in rr:pairs.setdefault(r['pair_id'],[]).append(r['profile_diagnostic']['full_pipeline_success'])
        diag['pipeline_pairs'][metric]=tally([tri(vals) for _,vals in sorted(pairs.items())])
    summary['profile_analysis']=diag
    return summary
