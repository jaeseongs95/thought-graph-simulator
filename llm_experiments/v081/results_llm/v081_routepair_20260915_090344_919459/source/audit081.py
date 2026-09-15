"""독립 선택·요청·증명 검산. 생산 design081/report081/measure/stages를 import하지 않는다."""
from copy import deepcopy
from collections import Counter
import bootstrap
import audit_model as prior
from audit_graph import _semantic
from audit_io import load, dump, need


def reconstruct_schedule(s):
    trials, ops, actions = [], [], []
    number = 0
    for block in range(8):
        pi, si = divmod(block, 2)
        problem = s['problems'][pi]
        entries = [('reference', si, 0, 'D', 'shallow'), ('reference', si, 0, 'D', 'deep')]
        for pos in (0, 1):
            for lab in (0, 1):
                ms = s['metrics_by_problem'][problem['id']][:]
                if (pi + si + pos + lab) & 1:
                    ms = ms[::-1]
                for metric in ms:
                    ds = ['shallow', 'deep']
                    if (pi + si + pos + lab + (metric == 'W')) & 1:
                        ds = ds[::-1]
                    entries.extend(('model', pos, lab, metric, d) for d in ds)
        if si:
            entries = entries[::-1]
        actions.append({'kind': 'metadata', 'id': 'b%02d_before' % block})
        for arm, pos, lab, metric, direction in entries:
            unit = 't%03d' % number
            number += 1
            strategies = ['candidate_id', 'rule_ids'] if arm == 'model' else ['reference']
            if (pi + si + pos + lab + (metric == 'W') + (direction == 'deep')) & 1:
                strategies = strategies[::-1]
            group = []
            for strategy in strategies:
                tid = unit + ('_rule_ids' if strategy == 'rule_ids' else '_explicit_rule')
                sid = None if arm == 'reference' else unit + ('_rule_ids_select' if strategy == 'rule_ids' else '_select')
                pair = f'p{pi}_s{si}_o{pos}_l{lab}_{metric}' if arm == 'model' else None
                control = None
                if arm == 'reference':
                    location = s['candidate_orders'][pos].index(int(direction == 'deep'))
                    control = s['candidate_ids'][s['id_assignments'][lab][location]]
                t = dict(id=tid, unit_id=unit, variant='explicit_rule', selector_variant=strategy,
                         selection_slot_id=sid, block=block, arm=arm, problem_id=problem['id'],
                         seed=s['seeds'][si], candidate_order_index=pos, id_assignment_index=lab,
                         metric=metric, condition=direction, pair_id=pair + '_' + strategy if pair else None,
                         base_pair_id=pair, control_candidate_id=control)
                trials.append(t)
                group.append(t)
                if sid:
                    ops.append(dict(id=sid, trial_id=tid, logical_id=unit + '_select', stage='select', rule_position=None))
                    actions.append({'kind': 'slot', 'id': sid})
            for t in group:
                routes = s['reference_plans'][problem['id']]
                length = max(len(p) for p in routes.values()) if arm == 'model' else len(routes[s['reference_conditions'][int(direction == 'deep')]])
                for j in range(length + 2):
                    phase = 'facts' if j == 0 else 'final' if j == length + 1 else 'rule'
                    idx = j - 1 if phase == 'rule' else None
                    tail = ('rule_%02d' % idx) if phase == 'rule' else phase
                    oid = t['id'] + '_' + tail
                    ops.append(dict(id=oid, trial_id=t['id'], logical_id=unit + '_' + tail, stage=phase, rule_position=idx))
                    actions.append({'kind': 'slot', 'id': oid})
        actions.append({'kind': 'metadata', 'id': 'b%02d_after' % block})
    return trials, ops, actions


def context(plan, t, raws):
    s = plan['protocol']
    p = next(x for x in s['problems'] if x['id'] == t['problem_id'])
    cs = []
    for index, kind in enumerate(s['candidate_orders'][t['candidate_order_index']]):
        label = s['candidate_ids'][s['id_assignments'][t['id_assignment_index']][index]]
        ids = s['reference_plans'][p['id']][s['reference_conditions'][kind]]
        cs.append({'candidate_id': label, 'rules': [deepcopy(next(r for r in p['rules'] if r['id'] == rid)) for rid in ids]})
    if t['arm'] == 'model':
        raw = raws.get(t['selection_slot_id'])
        src = {'source_type': 'model', 'source_id': t['unit_id'] + '_select',
               'content': None if raw is None else prior.content(raw)}
    else:
        src = {'source_type': 'experimenter_reference', 'source_id': t['unit_id'] + '_reference',
               'content': dump({'candidate_id': t['control_candidate_id']}).decode()}
    route = None
    try:
        value = load(src['content']) if src['content'] is not None else None
        matches = []
        if t['selector_variant'] == 'rule_ids' and list_shape(value):
            for c in cs:
                ids = [r['id'] for r in c['rules']]
                if len(value['rule_ids']) == len(ids) and all(type(a) is str and a == b for a, b in zip(value['rule_ids'], ids)):
                    matches.append(c)
        elif t['selector_variant'] != 'rule_ids' and type(value) is dict and set(value) == {'candidate_id'}:
            matches = [c for c in cs if c['candidate_id'] == value['candidate_id']]
        if len(matches) == 1:
            route = {'candidate_id': matches[0]['candidate_id'], 'rule_ids': [r['id'] for r in matches[0]['rules']]}
    except (ValueError, UnicodeError):
        pass
    return p, cs, src, route


def list_shape(value):
    if type(value) is not dict or set(value) != {'rule_ids'}:
        return False
    ids = value['rule_ids']
    return type(ids) is list and 0 < len(ids) < 17 and all(type(i) is str and 0 < len(i) < 129 for i in ids)


def decode(record, raw, spec, phase, strategy):
    st, value, usage = prior.decode(record, raw, spec, phase, 'explicit_rule')
    if phase == 'select' and strategy == 'rule_ids' and st in ('ok', 'invalid_schema'):
        st = 'ok' if list_shape(value) else 'invalid_schema'
    return st, value, usage


def copy_check(plan, t, obj, p, cards):
    if t['selector_variant'] != 'rule_ids':
        return None
    if not list_shape(obj):
        return {'kind': 'invalid_shape', 'same_multiset_candidate_id': None}
    ids = obj['rule_ids']
    sequence = {c['candidate_id']: [r['id'] for r in c['rules']] for c in cards}
    multisets = [cid for cid, seq in sequence.items() if Counter(seq) == Counter(ids)]
    if any(seq == ids for seq in sequence.values()):
        kind = 'exact_candidate'
    elif multisets:
        kind = 'order_mismatch'
    elif len(set(ids)) < len(ids):
        kind = 'duplicate_rule'
    elif set(ids) - {r['id'] for r in p['rules']}:
        kind = 'unknown_rule'
    else:
        kind = 'not_a_complete_candidate'
    return {'kind': kind, 'same_multiset_candidate_id': multisets[0] if len(multisets) == 1 else None}


def expected_request(plan,slot,raws):
    t=next(t for t in plan['trials'] if t['id']==slot['trial_id']);s=plan['protocol'];phase=slot['stage']
    p,cs,src,route=context(plan,t,raws)
    if phase!='select':
        if route is None:return 'unmappable_selection',None
        if phase=='rule' and slot['rule_position']>=len(route['rule_ids']):return 'outside_selected_route',None
    body=deepcopy(s['api_defaults']);body['options']['seed']=t['seed']
    if phase=='select':
        rules_mode = t['selector_variant'] == 'rule_ids'
        schema = deepcopy(s['route_selector_schema'] if rules_mode else s['selector_schema'])
        if t['metric'] == 'D':
            field = 'requested_depth'
            demand = s['headers'][t['condition']]
            header = s['route_select_header'] if rules_mode else s['headers']['select']
        else:
            field = 'requested_rule_count'
            demand = s['count_conditions'][t['condition']]
            header = s['route_count_select_header'] if rules_mode else s['count_select_header']
        data = {'problem': {k:p[k] for k in ('facts','rules','goal')}, 'candidates': cs, field: demand}
    else:
        if phase=='facts':key='nodes';prop=s['generation_schema']['properties']['nodes']
        elif phase=='rule':key='node';prop=s['generation_schema']['properties']['nodes']['items']
        else:key='final_node_id';prop=s['generation_schema']['properties']['final_node_id']
        schema={'type':'object','properties':{key:deepcopy(prop)},'required':[key],'additionalProperties':False}
        if phase=='facts':
            item=schema['properties']['nodes']['items']['properties']
            item['rule']={'type':'null'}
            item['parents']['maxItems']=0
            schema['properties']['nodes'].update(minItems=len(p['facts']),maxItems=len(p['facts']))

        history=[]
        for pre in plan['slots']:
            if pre['id']==slot['id']:break
            if pre['trial_id']==t['id'] and pre['stage']!='select' and pre['id'] in raws:
                history.append({'source_slot_id':pre['logical_id'],'content':prior.content(raws[pre['id']])})
        index={'facts':0,'final':len(route['rule_ids'])+1}.get(phase)
        if phase=='rule':index=slot['rule_position']+1
        data={'problem':p,'selection_original':src,'provided_route_plan':route,
              'operation':{'stage':phase,'index':index,'requested_rule_id':route['rule_ids'][slot['rule_position']] if phase=='rule' else None},'history':history}
        if phase == 'rule' and t['variant'] == 'explicit_rule':
            current = data['operation']['requested_rule_id']
            matches = [dict(r) for r in p['rules'] if r['id'] == current]
            need(len(matches) == 1, 'current rule uniquely identified')
            data['operation']['requested_rule'] = deepcopy(matches[0])
        header=s['headers']['generator']+'\n\n'+s['headers'][phase]
    text=header+'\nJSON 객체 하나만 출력한다. 출력 형식(JSON Schema):\n'+dump(schema).decode()+'\n\ninput: '+dump(data).decode()
    body['messages']=[{'role':'user','content':text}];body['format']=schema
    return None,dump(body)


def validate_protocol(s):
    need(s['contract']=='v081-id-versus-route-content-r1','protocol version')
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
    need(len(ts)==208 and len(ss)==1468 and len(aa)==1484,'frozen counts')
    need(sum(t['arm']=='model' and t['metric']=='D' for t in ts)==128,'D denominator')
    need(sum(t['arm']=='model' and t['metric']=='W' for t in ts)==64,'W denominator')
    for t in ts:
        if t['metric']=='W':need(t['problem_id'] in ('H03','H04'),'no tie selection')
    need(s['selector_variants'] == ['candidate_id','rule_ids'], 'two frozen selector variants')
    need(s['assigned_control_trials']==16 and s['selector_calls']==192, 'reference not duplicated')
    need(s['exact_rule_sequence_mapping'] is True and s['shared_reference_controls'] is True, 'mapping/control contract')
    for pi,problem in enumerate(s['problems']):
        paths=list(s['reference_plans'][problem['id']].values())
        need(len(paths)==2 and paths[0]!=paths[1], 'unique candidate sequence')
    need(s['route_selector_schema']=={'type':'object','properties':{'rule_ids':{'type':'array','items':{'type':'string','minLength':1,'maxLength':128},'minItems':1,'maxItems':16}},'required':['rule_ids'],'additionalProperties':False},'unrestricted candidate list schema')
    need(sum(op['stage']=='select' for op in ss)==192, 'independent selections per arm')
    maxima=sum(1 for op in ss)
    need(maxima==s['max_inference_calls'] and len(aa)==s['max_action_slots'], 'budget exact')
    expected=minimum=0
    for t in ts:
        p=next(x for x in s['problems'] if x['id']==t['problem_id'])
        paths=list(s['reference_plans'][p['id']].values())
        if t['arm']=='reference':
            n=len(paths[int(t['condition']=='deep')]); expected+=n+2; minimum+=n+2
        else:
            values=[prior.route_depth(p,r) if t['metric']=='D' else len(r) for r in paths]
            best=(min if t['condition']=='shallow' else max)(values)
            need(values[0]!=values[1], 'no ties')
            expected+=3+len(paths[values.index(best)])
            minimum+=3+min(map(len,paths))
    need(expected==s['expected_inference_calls_if_all_target_routes_selected']==1404,'oracle call budget')
    need(minimum==s['minimum_inference_calls_if_all_selections_mappable']==1340,'minimum mapped call budget')



def independent_summary(plan, records, raws, state):
    s = plan['protocol']; statuses={}; formats={}; objects={}; usages={}; rows=[]
    for op in plan['slots']:
        t=next(x for x in plan['trials'] if x['id']==op['trial_id'])
        rec=records.get(op['id'])
        status,obj,u=decode(rec,raws.get(op['id'],b''),s,op['stage'],t['selector_variant'])
        formats[op['id']]=status
        if op['stage']=='select' and status=='ok' and context(plan,t,raws)[3] is None:
            status='unmappable_selection'
        statuses[op['id']]=status;objects[op['id']]=obj
        if rec is not None and rec['kind']=='call':usages[op['id']]=u
    model_failures=('invalid_schema','invalid_json','unmappable_selection')
    for t in plan['trials']:
        p,cs,src,route=context(plan,t,raws)
        cv={c['candidate_id']:{'D':prior.route_depth(p,[r['id'] for r in c['rules']]),'W':len(c['rules'])} for c in cs}
        extremes=sorted(v[t['metric']] for v in cv.values());target=extremes[int(t['condition']=='deep')]
        chosen=cv[route['candidate_id']] if route else None
        sid=t['selection_slot_id'];status=statuses[sid] if sid else 'experimenter_reference_not_inference'
        formatted=formats[sid] if sid else status
        mapping=True if status=='ok' else False if status in model_failures else None
        choice=chosen[t['metric']]==target if status=='ok' else None
        selected=choice if status=='ok' else False if status in model_failures else None
        seq=[]
        if route:
            for op in plan['slots']:
                if op['trial_id']==t['id'] and op['stage']!='select':
                    if op['stage']=='rule' and op['rule_position']>=len(route['rule_ids']):continue
                    seq.append(dict(op,requested_rule_id=route['rule_ids'][op['rule_position']] if op['stage']=='rule' else None))
        checks=prior.steps(p,seq,objects,statuses) if seq else []
        ready=bool(seq) and all(statuses[o['id']]=='ok' for o in seq)
        gr=depth=work=gen=None
        genstatus='not_dispatched_unmappable_selection' if route is None else 'incomplete_or_nonsemantic'
        if ready:
            ns=list(objects[seq[0]['id']]['nodes'])
            ns.extend(objects[o['id']]['node'] for o in seq[1:-1])
            graph={'nodes':ns,'final_node_id':objects[seq[-1]['id']]['final_node_id']}
            gr=_semantic(p,graph);depth=gr['actual_D']
            if gr['strict_valid'] is True:
                by={n['id']:n for n in ns};reachable={graph['final_node_id']}
                while True:
                    expanded=reachable|{parent for nid in reachable for parent in by[nid]['parents']}
                    if expanded==reachable:break
                    reachable=expanded
                work=sum(by[nid]['rule'] is not None for nid in reachable)
            gen=bool(gr['strict_valid'] is True and all(c['valid'] is True for c in checks)
                     and [n['rule'] for n in ns if n['rule'] is not None]==route['rule_ids']
                     and depth==chosen['D'] and work==chosen['W'])
            genstatus='valid_graph' if gen else 'semantic_failure'
        elif seq and any(statuses[o['id']] in ('invalid_schema','invalid_json') for o in seq):
            gen=False;genstatus='model_output_format_failure'
        goal=None if gen is None else bool(gen and (depth if t['metric']=='D' else work)==target)
        end=False if status in model_failures and route is None else (None if selected is None or gen is None else bool(selected and goal))
        rows.append({'trial_id':t['id'],'unit_id':t['unit_id'],'selector_variant':t['selector_variant'],'arm':t['arm'],
                     'problem_id':t['problem_id'],'seed':t['seed'],'metric':t['metric'],'condition':t['condition'],
                     'order':t['candidate_order_index'],'labels':t['id_assignment_index'],'pair_id':t['pair_id'],
                     'selector_format_status':formatted,'selector_status':status,'mapping_success':mapping,
                     'structural_choice_correct':choice,'copy_diagnostic':copy_check(plan,t,objects.get(sid),p,cs) if sid and formatted in ('ok','invalid_schema') else ({'kind':'invalid_json','same_multiset_candidate_id':None} if t['selector_variant']=='rule_ids' and formatted=='invalid_json' else None),
                     'candidate_id':route['candidate_id'] if route else None,'selected_rule_ids':route['rule_ids'] if route else None,
                     'selected_position':next(i for i,c in enumerate(cs) if c['candidate_id']==route['candidate_id']) if route else None,
                     'selected_D':chosen['D'] if chosen else None,'selected_W':chosen['W'] if chosen else None,
                     'target_value':target,'selection_success':selected,'generator_success':gen,'generator_status':genstatus,
                     'actual_D':depth,'actual_W':work,'metric_end_to_end':end,'reference_success':goal if t['arm']=='reference' else None,
                     'graph_result':gr,'step_checks':checks})
    return paired_aggregate(plan,rows,statuses,usages,state)



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


def group_aggregate(plan,rows,statuses,usages,state):
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
    return {'contract':'v081-summary-r1','provenance':plan['provenance'],'state':state,'totals':totals,
            'reference':tally([r['reference_success'] for r in rows if r['arm']=='reference']),
            'call_statuses':dict(sorted(frequencies.items())),'usage':usage,
            'position_id_diagnostic':{'observed_choices':len(observed),'first_position':len([r for r in observed if r['selected_position']==0]),'route_0_id':len([r for r in observed if r['candidate_id']=='route_0'])},
            'trials':rows,'pairs':pairs,'presentation_robust_groups':robust,'metric_discrimination':contrasts,
            'distinct_structural_problems':4,'new_independent_structures':0,
            'decision':'close_completed_diagnostic_no_automatic_followup' if state=='complete' else 'preserve_incomplete_no_retry'}


def paired_tally(pairs, key):
    counts = [0, 0, 0, 0, 0]
    for left, right in pairs:
        x, y = left[key], right[key]
        if x is None or y is None:
            counts[4] += 1
        elif x is True and y is True:
            counts[0] += 1
        elif x is True:
            counts[1] += 1
        elif y is True:
            counts[2] += 1
        else:
            counts[3] += 1
    return dict(assigned=len(pairs), **dict(zip(['both_success', 'candidate_id_only', 'rule_ids_only', 'both_failure', 'not_comparable'], counts)))


def usage_tally(items):
    result = {}
    for field in prior.FIELDS:
        values = [x.get(field) for x in items]
        result[field] = {'sum_observed': sum(x for x in values if x is not None), 'missing': values.count(None)}
    return result


def paired_aggregate(plan, rows, statuses, usages, state):
    groups = {}
    wanted = ('totals', 'pairs', 'presentation_robust_groups', 'metric_discrimination',
              'position_id_diagnostic', 'usage', 'call_statuses')
    for v in ('candidate_id', 'rule_ids'):
        subset = [r for r in rows if r['selector_variant'] == v]
        ids = {r['trial_id'] for r in subset}
        actions = [o for o in plan['slots'] if o['trial_id'] in ids]
        r = group_aggregate(plan, subset, {o['id']: statuses[o['id']] for o in actions},
                            [usages[o['id']] for o in actions if o['id'] in usages], state)
        g = {k: r[k] for k in wanted}
        g['mapping'] = {m: tally([x['mapping_success'] for x in subset if x['metric'] == m]) for m in ('D', 'W')}
        g['conditional_choice'] = {m: tally([r['structural_choice_correct'] for r in subset if r['metric'] == m]) for m in ('D', 'W')}
        g['selection_statuses'] = dict(sorted(Counter(x['selector_status'] for x in subset).items()))
        g['usage_by_stage'] = {}
        for name in ('select', 'generation'):
            indices = [o['id'] for o in actions if (o['stage'] == 'select' if name == 'select' else o['stage'] != 'select')]
            items = [usages[i] for i in indices if i in usages]
            g['usage_by_stage'][name] = {'calls': len(items), 'fields': usage_tally(items)}
        groups[v] = g
    perunit = {}
    for r in rows:
        if r['arm'] == 'model':
            perunit.setdefault(r['unit_id'], {})[r['selector_variant']] = r
    matched = [(v['candidate_id'], v['rule_ids']) for k, v in sorted(perunit.items())]
    paired = {}
    comparisons = {}
    for m in ('D', 'W'):
        pairs = [(a, b) for a, b in matched if a['metric'] == m]
        paired[m] = {k: paired_tally(pairs, k) for k in ('mapping_success', 'selection_success', 'generator_success', 'metric_end_to_end')}
        pairs2 = []
        for a in groups['candidate_id']['pairs']:
            if a['metric'] != m:
                continue
            for b in groups['rule_ids']['pairs']:
                if all(a[k] == b[k] for k in ('metric', 'problem_id', 'seed', 'order', 'labels')):
                    pairs2.append((a, b))
        comparisons[m] = {k: paired_tally(pairs2, k) for k in ('selection_success', 'end_to_end_success')}
    return {'contract': 'v081-summary-r1', 'provenance': plan['provenance'], 'state': state,
            'groups': groups, 'paired_trials': paired, 'paired_pairs': comparisons,
            'reference': tally([r['reference_success'] for r in rows if r['arm'] == 'reference']),
            'reference_shared_not_duplicated': True, 'trials': rows,
            'call_statuses': dict(sorted(Counter(statuses.values()).items())),
            'usage': usage_tally(list(usages.values())),
            'copy_diagnostic_counts': dict(sorted(Counter(r['copy_diagnostic']['kind'] for r in rows if r['copy_diagnostic']).items())),
            'distinct_structural_problems': 4, 'new_independent_structures': 0,
            'decision': 'close_completed_paired_selector_batch_no_automatic_followup' if state == 'complete' else 'preserve_incomplete_no_retry'}
