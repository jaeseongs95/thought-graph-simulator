"""v080 독립 검산. 생산 design080/report080/measure/stages를 import하지 않는다."""
from copy import deepcopy
import bootstrap
import audit_model as prior
from audit_graph import _semantic
from audit_io import load,dump,need


def reconstruct_schedule(s):
    ts,ss,aa=[],[],[]
    for block in range(len(s['problems'])*len(s['seeds'])):
        pi,si=divmod(block,len(s['seeds']));problem=s['problems'][pi]
        entries=[('reference',si%2,0,'D','shallow'),('reference',si%2,0,'D','deep')]
        for pos in (0,1):
            for lab in (0,1):
                ms=s['metrics_by_problem'][problem['id']][:]
                if (pi+si+pos+lab)&1:ms=ms[::-1]
                for m in ms:
                    ds=['shallow','deep']
                    if (pi+si+pos+lab+(m=='W'))&1:ds=ds[::-1]
                    for d in ds:entries.append(('model',pos,lab,m,d))
        if si&1:entries=entries[::-1]
        aa.append({'kind':'metadata','id':f'b{block:02d}_before'})
        for arm,order,labels,metric,c in entries:
            uid='t%03d'%len(ts);tid=uid+'_explicit_rule'
            selection=uid+'_select' if arm=='model' else None
            pair=f'p{pi}_s{si}_o{order}_l{labels}_{metric}' if arm=='model' else None
            physical=[s['candidate_ids'][x] for x in s['id_assignments'][labels]]
            target_position=s['candidate_orders'][order].index(int(c=='deep'))
            t={'id':tid,'unit_id':uid,'variant':'explicit_rule','selection_slot_id':selection,'block':block,'arm':arm,
               'problem_id':problem['id'],'seed':s['seeds'][si],'candidate_order_index':order,'id_assignment_index':labels,
               'metric':metric,'condition':c,'pair_id':pair,'base_pair_id':pair,
               'control_candidate_id':physical[target_position] if arm=='reference' else None}
            ts.append(t)
            if selection:
                ss.append({'id':selection,'trial_id':tid,'logical_id':selection,'stage':'select','rule_position':None})
                aa.append({'kind':'slot','id':selection})
            paths=s['reference_plans'][problem['id']]
            if arm=='reference':n=len(paths[s['reference_conditions'][int(c=='deep')]])
            else:n=max(len(x) for x in paths.values())
            for index in range(n+2):
                stage='facts' if index==0 else 'final' if index==n+1 else 'rule'
                pos=index-1 if stage=='rule' else None
                suffix='rule_%02d'%pos if stage=='rule' else stage
                sid=tid+'_'+suffix
                ss.append({'id':sid,'trial_id':tid,'logical_id':uid+'_'+suffix,'stage':stage,'rule_position':pos})
                aa.append({'kind':'slot','id':sid})
        aa.append({'kind':'metadata','id':f'b{block:02d}_after'})
    return ts,ss,aa


def projection(plan,t):
    s=deepcopy(plan['protocol'])
    label_indices=s['id_assignments'][t['id_assignment_index']]
    s['candidate_ids']=[plan['protocol']['candidate_ids'][label_indices[0]],plan['protocol']['candidate_ids'][label_indices[1]]]
    if t['metric']=='W':
        s['headers']['select']=s['count_select_header']
        for k in ('shallow','deep'):s['headers'][k]=s['count_conditions'][k]
    return dict(plan,protocol=s)


def expected_request(plan,slot,raws):
    t=next(x for x in plan['trials'] if x['id']==slot['trial_id'])
    skip,raw=prior.expected_request(projection(plan,t),slot,raws)
    if skip is None and slot['stage']=='select' and t['metric']=='W':
        req=load(raw);text=req['messages'][0]['content'];offset=text.index('\n\ninput: ')
        data=load(text[offset+9:]);value=data.pop('requested_depth');data['requested_rule_count']=value
        req['messages'][0]['content']=text[:offset+9]+dump(data).decode('utf-8');raw=dump(req)
    return skip,raw


def validate_protocol(s):
    need(s['contract']=='v080-depth-construct-metric-cross-r1','protocol version')
    need(s['candidate_ids']==['route_0','route_1'] and s['candidate_orders']==[[0,1],[1,0]],'candidate contract')
    need(s['id_assignments']==[[0,1],[1,0]],'independent label crossing')
    need(s['generator_variants']==['explicit_rule'] and s['seeds']==[64001001,64001002],'generator/seed frozen')
    need(s['metrics_by_problem']=={'H01':['D'],'H02':['D'],'H03':['D','W'],'H04':['D','W']},'metric assignment')
    need(not any(s[k] for k in ['holdout','automatic_retry','automatic_download','automatic_server_start','posthoc_repair']),'safety contract')
    expected={'H01':[(2,3),(3,3)],'H02':[(3,4),(4,4)],'H03':[(2,4),(3,3)],'H04':[(3,5),(4,4)]}
    for p in s['problems']:
        ids=[r['id'] for r in p['rules']]
        need(len(ids)==len(set(ids)) and len(p['facts'])==len(set(p['facts'])),'unique rules/facts')
        need(all(r['premises'] and len(r['premises'])==len(set(r['premises'])) for r in p['rules']),'nonempty unique premises')
        for i,key in enumerate(s['reference_conditions']):
            path=s['reference_plans'][p['id']][key]
            d=prior.route_depth(p,path)
            need((d,len(path))==expected[p['id']][i],'actual candidate D/W')
            # 각 후보의 모든 초기 사실과 규칙이 목표를 지지하는지 독립적으로 확인한다.
            rules={r['conclusion']:r for r in p['rules'] if r['id'] in path}
            seen=set();used=set()
            def visit(atom):
                seen.add(atom)
                if atom in p['facts']:return
                r=rules[atom];used.add(r['id'])
                for a in r['premises']:visit(a)
            visit(p['goal'])
            need(set(p['facts'])<=seen and used==set(path),'all supplied candidate nodes support goal')
    ts,ss,aa=reconstruct_schedule(s)
    need(len(ts)==112 and len(ss)==780 and len(aa)==796,'frozen counts')
    need(sum(t['arm']=='model' and t['metric']=='D' for t in ts)==64,'D denominator')
    need(sum(t['arm']=='model' and t['metric']=='W' for t in ts)==32,'W denominator')
    for t in ts:
        if t['metric']=='W':need(t['problem_id'] in ('H03','H04'),'no tie selection')


def independent_summary(plan,records,raws,state):
    s=plan['protocol'];statuses={};objects={};usage=[];rows=[]
    for op in plan['slots']:
        r=records.get(op['id'])
        st,obj,u=prior.decode(r,raws.get(op['id'],b''),s,op['stage'],'explicit_rule')
        statuses[op['id']]=st;objects[op['id']]=obj
        if r is not None and r['kind']=='call':usage.append(u)
    for t in plan['trials']:
        p,cs,src,route=prior.context(projection(plan,t),t,raws)
        cv={}
        for c in cs:
            rids=[r['id'] for r in c['rules']]
            cv[c['candidate_id']]={'D':prior.route_depth(p,rids),'W':len(rids)}
        extremes=sorted(v[t['metric']] for v in cv.values())
        target=extremes[int(t['condition']=='deep')]
        chosen=cv[route['candidate_id']] if route is not None else None
        st=statuses[t['selection_slot_id']] if t['arm']=='model' else 'experimenter_reference_not_inference'
        selected_ok=(chosen[t['metric']]==target) if st=='ok' else None
        seq=[]
        if route:
            for op in plan['slots']:
                if op['trial_id']==t['id'] and op['stage']!='select':
                    if op['stage']=='rule' and op['rule_position']>=len(route['rule_ids']):continue
                    seq.append(dict(op,requested_rule_id=route['rule_ids'][op['rule_position']] if op['stage']=='rule' else None))
        checks=prior.steps(p,seq,objects,statuses) if seq else []
        ready=bool(seq) and all(statuses[x['id']]=='ok' for x in seq)
        graph=None;gr=None;depth=None;work=None;gen=None
        if ready:
            ns=objects[seq[0]['id']]['nodes'][:]
            ns.extend(objects[o['id']]['node'] for o in seq[1:-1])
            graph={'nodes':ns,'final_node_id':objects[seq[-1]['id']]['final_node_id']}
            gr=_semantic(p,graph);depth=gr['actual_D']
            if gr['strict_valid'] is True:
                by={n['id']:n for n in ns};reachable={graph['final_node_id']}
                while True:
                    expanded=reachable|{pid for nid in reachable for pid in by[nid]['parents']}
                    if expanded==reachable:break
                    reachable=expanded
                work=len([nid for nid in reachable if by[nid]['rule'] is not None])
            fidelity=[n['rule'] for n in ns if n['rule'] is not None]==route['rule_ids']
            gen=bool(all(c['valid'] is True for c in checks) and gr['strict_valid'] is True and fidelity
                     and depth==chosen['D'] and work==chosen['W'])
        goal_ok=None if gen is None else bool(gen and (depth if t['metric']=='D' else work)==target)
        end=None if selected_ok is None or gen is None else bool(selected_ok and goal_ok)
        rows.append({'trial_id':t['id'],'arm':t['arm'],'problem_id':t['problem_id'],'seed':t['seed'],'metric':t['metric'],
                     'condition':t['condition'],'order':t['candidate_order_index'],'labels':t['id_assignment_index'],'pair_id':t['pair_id'],
                     'selector_status':st,'candidate_id':route['candidate_id'] if route else None,
                     'selected_position':next(i for i,c in enumerate(cs) if c['candidate_id']==route['candidate_id']) if route else None,
                     'selected_D':chosen['D'] if chosen else None,'selected_W':chosen['W'] if chosen else None,
                     'target_value':target,'selection_success':selected_ok,'generator_success':gen,'actual_D':depth,'actual_W':work,
                     'metric_end_to_end':end,'reference_success':goal_ok if t['arm']=='reference' else None,
                     'graph_result':gr,'step_checks':checks})
    return independent_aggregate(plan,rows,statuses,usage,state)


def tally(vs):
    yes=no=missing=0
    for v in vs:
        if v is True:yes+=1
        elif v is False:no+=1
        else:missing+=1
    return {'assigned':yes+no+missing,'measured':yes+no,'successes':yes,'failures':no,'unmeasured':missing}


def both(vs):
    if None in vs:return None
    return False not in vs


def sign(vs):
    if None in vs:return 'unmeasured'
    if vs[0]==vs[1]:return 'same'
    return 'forward' if vs[1]>vs[0] else 'reversed'


def independent_aggregate(plan,rows,statuses,usages,state):
    groups={}
    for row in rows:
        if row['pair_id'] is not None:groups.setdefault(row['pair_id'],{})[row['condition']]=row
    pairs=[]
    for key in sorted(groups):
        low,high=groups[key]['shallow'],groups[key]['deep'];rs=[low,high];metric=low['metric']
        pairs.append({'pair_id':key,'metric':metric,'problem_id':low['problem_id'],'seed':low['seed'],'order':low['order'],'labels':low['labels'],
                      'selection_success':both([r['selection_success'] for r in rs]),
                      'end_to_end_success':both([r['metric_end_to_end'] for r in rs]),
                      'selection_direction':sign([r['selected_'+metric] if r['selector_status']=='ok' else None for r in rs]),
                      'valid_graph_direction':sign([r['actual_'+metric] if r['generator_success'] is True else None for r in rs])})
    keyed={}
    for p in pairs:keyed.setdefault((p['metric'],p['problem_id'],p['seed']),[]).append(p)
    robust=[]
    for (metric,pid,seed),ps in sorted(keyed.items()):
        robust.append({'metric':metric,'problem_id':pid,'seed':seed,'presentation_pairs':len(ps),
                       'selection_success':both([p['selection_success'] for p in ps]),
                       'end_to_end_success':both([p['end_to_end_success'] for p in ps])})
    keys=sorted({(r['problem_id'],r['seed'],r['order'],r['labels']) for r in rows if r['arm']=='model' and r['metric']=='W'})
    contrasts=[]
    for pid,seed,order,labels in keys:
        chosen={(r['metric'],r['condition']):r for r in rows if r['arm']=='model' and (r['problem_id'],r['seed'],r['order'],r['labels'])==(pid,seed,order,labels)}
        flips=[]
        for c in ('shallow','deep'):
            a,b=chosen['D',c],chosen['W',c]
            flips.append(None if a['selector_status']!='ok' or b['selector_status']!='ok' else a['candidate_id']!=b['candidate_id'])
        contrasts.append({'problem_id':pid,'seed':seed,'order':order,'labels':labels,
                          'opposite_choices_for_both_directions':both(flips),
                          'all_four_selections_correct':both([r['selection_success'] for r in chosen.values()]),
                          'all_four_end_to_end_correct':both([r['metric_end_to_end'] for r in chosen.values()])})
    totals={}
    for metric in ('D','W'):
        rs=[r for r in rows if r['arm']=='model' and r['metric']==metric]
        ps=[p for p in pairs if p['metric']==metric];gs=[g for g in robust if g['metric']==metric]
        totals[metric]={k:tally([r[k] for r in rs]) for k in ('selection_success','generator_success','metric_end_to_end')}
        totals[metric]['selection_pairs']=tally([p['selection_success'] for p in ps])
        totals[metric]['end_to_end_pairs']=tally([p['end_to_end_success'] for p in ps])
        totals[metric]['presentation_robust_selection']=tally([g['selection_success'] for g in gs])
        totals[metric]['presentation_robust_end_to_end']=tally([g['end_to_end_success'] for g in gs])
    frequencies={}
    for st in statuses.values():frequencies[st]=frequencies.get(st,0)+1
    observed=[r for r in rows if r['arm']=='model' and r['selector_status']=='ok']
    usage={}
    for field in prior.FIELDS:
        xs=[u.get(field) for u in usages]
        usage[field]={'sum_observed':sum(x for x in xs if x is not None),'missing':len([x for x in xs if x is None])}
    return {'contract':'v080-summary-r1','provenance':plan['provenance'],'state':state,'totals':totals,
            'reference':tally([r['reference_success'] for r in rows if r['arm']=='reference']),
            'call_statuses':dict(sorted(frequencies.items())),'usage':usage,
            'position_id_diagnostic':{'observed_choices':len(observed),'first_position':len([r for r in observed if r['selected_position']==0]),'route_0_id':len([r for r in observed if r['candidate_id']=='route_0'])},
            'trials':rows,'pairs':pairs,'presentation_robust_groups':robust,'metric_discrimination':contrasts,
            'distinct_structural_problems':4,'new_independent_structures':0,
            'decision':'close_completed_diagnostic_no_automatic_followup' if state=='complete' else 'preserve_incomplete_no_retry'}
