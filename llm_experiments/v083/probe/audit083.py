"""독립 선택·요청·증명 검산. 생산 design083/report083/measure/stages를 import하지 않는다."""
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
        pi,si=divmod(block,2);p=s['problems'][pi]
        entries=[('reference',si,0,'D','shallow'),('reference',si,0,'D','deep')]
        for pos in (0,1):
            for lab in (0,1):
                metrics=s['metrics_by_problem'][p['id']][:]
                if (pi+si+pos+lab)&1:metrics.reverse()
                for metric in metrics:
                    ds=['shallow','deep']
                    if (pi+si+pos+lab+(metric=='W'))&1:ds.reverse()
                    entries.extend(('model',pos,lab,metric,d) for d in ds)
        if si:entries.reverse()
        actions.append({'kind':'metadata','id':'b%02d_before'%block})
        for arm,pos,lab,metric,direction in entries:
            unit='t%03d'%number;number+=1
            variants=['reference']
            if arm=='model':
                offset=(pos*2+lab+si+pi+(direction=='deep')+(metric=='W'))%4
                variants=[s['selector_variants'][(i+offset)%4] for i in range(4)]
            group=[]
            for variant in variants:
                suffix='_explicit_rule' if variant in ('candidate_id','reference') else '_'+variant
                tid=unit+suffix
                sid=None if arm=='reference' else unit+('_select' if variant=='candidate_id' else '_'+variant+'_select')
                pair=f'p{pi}_s{si}_o{pos}_l{lab}_{metric}' if arm=='model' else None
                control=None
                if arm=='reference':
                    loc=s['candidate_orders'][pos].index(int(direction=='deep'))
                    control=s['candidate_ids'][s['id_assignments'][lab][loc]]
                generate=arm=='reference' or (metric=='D' and variant in ('candidate_id','correct_full','correct_values'))
                t=dict(id=tid,unit_id=unit,variant='explicit_rule',selector_variant=variant,selection_slot_id=sid,
                    block=block,arm=arm,problem_id=p['id'],seed=s['seeds'][si],candidate_order_index=pos,
                    id_assignment_index=lab,metric=metric,condition=direction,
                    pair_id=pair+'_'+variant if pair else None,base_pair_id=pair,generate=generate,control_candidate_id=control)
                trials.append(t);group.append(t)
                if sid:
                    ops.append(dict(id=sid,trial_id=tid,logical_id=unit+'_select',stage='select',rule_position=None))
                    actions.append({'kind':'slot','id':sid})
            for t in group:
                if not t['generate']:continue
                paths=s['reference_plans'][p['id']]
                n=max(len(v) for v in paths.values()) if arm=='model' else len(paths[s['reference_conditions'][int(direction=='deep')]])
                for j in range(n+2):
                    phase='facts' if j==0 else 'final' if j==n+1 else 'rule'
                    idx=j-1 if phase=='rule' else None
                    tail='rule_%02d'%idx if phase=='rule' else phase
                    oid=t['id']+'_'+tail
                    ops.append(dict(id=oid,trial_id=t['id'],logical_id=unit+'_'+tail,stage=phase,rule_position=idx))
                    actions.append({'kind':'slot','id':oid})
        actions.append({'kind':'metadata','id':'b%02d_after'%block})
    return trials,ops,actions


def reference_profile(s,p,kind):
    """생산의 순차 깊이 계산과 별도인 원자 재귀 방식."""
    names=s['reference_plans'][p['id']][s['reference_conditions'][kind]]
    rules=[next(r for r in p['rules'] if r['id']==name) for name in names]
    by_atom={r['conclusion']:r for r in rules}
    def depth(atom,visiting=frozenset()):
        if atom in p['facts']:return 0
        need(atom not in visiting,'cycle in control')
        return 1+max(depth(a,visiting|{atom}) for a in by_atom[atom]['premises'])
    return {'facts':[{'atom':a,'depth':0} for a in p['facts']],
            'steps':[{'rule_id':r['id'],'conclusion':r['conclusion'],
                      'premises':[{'atom':a,'depth':depth(a)} for a in r['premises']],
                      'depth':depth(r['conclusion'])} for r in rules],
            'goal_depth':depth(p['goal']),'rule_count':len(rules)}


def controlled_measurements(plan,t,cs):
    s=plan['protocol'];kinds=s['candidate_orders'][t['candidate_order_index']]
    p=next(x for x in s['problems'] if x['id']==t['problem_id'])
    profiles=[reference_profile(s,p,k) for k in kinds]
    variant=t['selector_variant']
    if variant=='candidate_id':return []
    if variant!='correct_full':profiles=[{k:row[k] for k in ('goal_depth','rule_count')} for row in profiles]
    if variant=='swapped_values':
        metric_field='goal_depth' if t['metric']=='D' else 'rule_count'
        initial=[row[metric_field] for row in profiles]
        for index,row in enumerate(profiles):row[metric_field]=initial[1-index]
    return [{'candidate_id':card['candidate_id'],'content':dump(row).decode()} for card,row in zip(cs,profiles)]


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
        if type(value) is dict and set(value) == {'candidate_id'}:
            matches = [c for c in cs if c['candidate_id'] == value['candidate_id']]
        if len(matches) == 1:
            route = {'candidate_id': matches[0]['candidate_id'], 'rule_ids': [r['id'] for r in matches[0]['rules']]}
    except (ValueError, UnicodeError):
        pass
    return p, cs, src, route


def decode(record, raw, spec, phase, strategy):
    return prior.decode(record, raw, spec, phase, 'explicit_rule')


def expected_request(plan,slot,raws):
    t=next(t for t in plan['trials'] if t['id']==slot['trial_id']);s=plan['protocol'];phase=slot['stage']
    p,cs,src,route=context(plan,t,raws)
    if phase != 'select':
        if route is None:return 'unmappable_selection',None
        if phase=='rule' and slot['rule_position']>=len(route['rule_ids']):return 'outside_selected_route',None
    body=deepcopy(s['api_defaults']);body['options']['seed']=t['seed']
    if phase == 'select':
        schema = deepcopy(s['selector_schema'])
        if t['metric'] == 'D':
            field, demand, header = 'requested_depth', s['headers'][t['condition']], s['headers']['select']
        else:
            field, demand, header = 'requested_rule_count', s['count_conditions'][t['condition']], s['count_select_header']
        data = {'problem': {k:p[k] for k in ('facts','rules','goal')}, 'candidates': cs, field: demand}
        if t['selector_variant'] != 'candidate_id':
            data['candidate_measurements'] = controlled_measurements(plan,t,cs)
            header += '\n' + s['control_select_addendum']

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
            if pre['trial_id']==t['id'] and pre['stage'] != 'select' and pre['id'] in raws:
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
    need(s['contract']=='v083-frozen-accuracy-representation-swap-r1','protocol version')
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
    need(s['selector_variants']==['candidate_id','correct_full','correct_values','swapped_values'],'four frozen arms')
    need(s['generation_selector_variants']==['candidate_id','correct_full','correct_values'] and s['generation_metrics']==['D'],'generation scope')
    need(s['support_origin']=='experimenter_constructed_before_inference_not_model_computation','correct source attribution')
    need(s['support_only_in_selector'] is True and s['profile_calls']==0,'no model worksheet or support to generator')
    need(s['swapped_field_policy']=='exchange_only_requested_metric_between_candidates','fixed swap intervention')
    expected_controls={p['id']:[reference_profile(s,p,i) for i in (0,1)] for p in s['problems']}
    need(dump(s['frozen_profiles'])==dump(expected_controls),'independent exact controls; not copied model errors')
    ts,ss,aa=reconstruct_schedule(s)
    need((len(ts),len(ss),len(aa))==(400,1628,1644),'frozen counts')
    need(sum(t['generate'] for t in ts)==208,'proof count')
    need(sum(o['stage']=='select' for o in ss)==384,'selector calls')
    need(s['selector_calls']==384 and s['assigned_control_trials']==16,'shared reference counts')
    need(len(ss)==s['max_inference_calls'] and len(aa)==s['max_action_slots'],'slot budget')
    expected=minimum=384
    for t in ts:
        if not t['generate']:continue
        paths=list(s['reference_plans'][t['problem_id']].values())
        expected+=2+len(paths[int(t['condition']=='deep')])
        minimum+=2+(len(paths[int(t['condition']=='deep')]) if t['arm']=='reference' else min(map(len,paths)))
    need(expected==s['expected_inference_calls_if_all_target_routes_selected']==1580,'expected call budget')
    need(minimum==s['minimum_inference_calls_if_all_selections_mappable']==1532,'minimum mapped budget')
    need(not any(o['stage']=='profile' for o in ss),'no live profile calls')


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
                if op['trial_id']==t['id'] and op['stage'] != 'select':
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
        if not t['generate']:
            gen=end=depth=work=goal=None
            genstatus='not_scheduled_by_design'
        rows.append({'generation_scheduled':t['generate'],'trial_id':t['id'],'unit_id':t['unit_id'],'selector_variant':t['selector_variant'],'arm':t['arm'],
                     'problem_id':t['problem_id'],'seed':t['seed'],'metric':t['metric'],'condition':t['condition'],
                     'order':t['candidate_order_index'],'labels':t['id_assignment_index'],'pair_id':t['pair_id'],
                     'selector_format_status':formatted,'selector_status':status,'mapping_success':mapping,
                     'structural_choice_correct':choice,
                     'candidate_id':route['candidate_id'] if route else None,'selected_rule_ids':route['rule_ids'] if route else None,
                     'selected_position':next(i for i,c in enumerate(cs) if c['candidate_id']==route['candidate_id']) if route else None,
                     'selected_D':chosen['D'] if chosen else None,'selected_W':chosen['W'] if chosen else None,
                     'target_value':target,'selection_success':selected,'generator_success':gen,'generator_status':genstatus,
                     'actual_D':depth,'actual_W':work,'metric_end_to_end':end,'reference_success':goal if t['arm']=='reference' else None,
                     'graph_result':gr,'step_checks':checks})
    result=paired_aggregate(plan,rows,statuses,usages,state)
    return result



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


def paired_tally(items, field):
    totals=[0,0,0,0,0]
    for left,right in items:
        a,b=left[field],right[field]
        index=4 if a is None or b is None else 0 if a and b else 1 if a else 2 if b else 3
        totals[index]+=1
    return dict(assigned=len(items),**dict(zip(('both_success','left_only','right_only','both_failure','not_comparable'),totals)))


def usage_tally(items):
    return {k:{'sum_observed':sum(x.get(k) for x in items if x.get(k) is not None),
               'missing':sum(x.get(k) is None for x in items)} for k in prior.FIELDS}


def pair_key(p):
    return p['metric'],p['problem_id'],p['seed'],p['order'],p['labels']


def paired_aggregate(plan, rows, statuses, usages, state):
    spec=plan['protocol']; by_strategy={}
    for r in rows:
        r['support_diagnostic']=None
        if r['arm']!='model' or r['selector_variant']=='candidate_id':continue
        t=next(t for t in plan['trials'] if t['id']==r['trial_id']); _,cs,_,_=context(plan,t,{})
        materials=controlled_measurements(plan,t,cs)
        field={'D':'goal_depth','W':'rule_count'}[r['metric']]
        vals=[load(x['content'])[field] for x in materials]
        extreme=sorted(vals)[int(r['condition']=='deep')]
        cid=next(x['candidate_id'] for x,v in zip(materials,vals) if v==extreme)
        r['support_diagnostic']={'origin':'experimenter_frozen_control_not_model_output',
            'supplied_requested_values':vals,'supplied_extreme_candidate_id':cid,
            'follows_supplied_extreme':(cid==r['candidate_id']) if r['selector_status']=='ok' else None}
    for strategy in spec['selector_variants']:
        selected=[r for r in rows if r['selector_variant']==strategy]
        pair_groups={}
        for r in selected:pair_groups.setdefault(r['pair_id'],{})[r['condition']]=r
        pairs=[]
        for key in sorted(pair_groups):
            lo,hi=pair_groups[key]['shallow'],pair_groups[key]['deep'];m=lo['metric']
            scheduled=lo['generation_scheduled'] and hi['generation_scheduled']
            pairs.append({'pair_id':key,'problem_id':lo['problem_id'],'seed':lo['seed'],'order':lo['order'],'labels':lo['labels'],
                'metric':m,'generation_scheduled':scheduled,
                'selection_success':both([lo['selection_success'],hi['selection_success']]),
                'end_to_end_success':both([lo['metric_end_to_end'],hi['metric_end_to_end']]) if scheduled else None,
                'selection_direction':sign([lo['selected_'+m],hi['selected_'+m]]),
                'valid_graph_direction':sign([lo['actual_'+m],hi['actual_'+m]]) if scheduled else 'not_scheduled'})
        grouping={}
        for pair in pairs:grouping.setdefault(pair_key(pair)[:3],[]).append(pair)
        robust=[]
        for (m,pid,seed),ps in sorted(grouping.items()):
            scheduled=all(p['generation_scheduled'] for p in ps)
            robust.append({'metric':m,'problem_id':pid,'seed':seed,'generation_scheduled':scheduled,
                           'selection_success':both([p['selection_success'] for p in ps]),
                           'end_to_end_success':both([p['end_to_end_success'] for p in ps]) if scheduled else None})
        contrasts=[]
        for key in sorted(set((r['problem_id'],r['seed'],r['order'],r['labels']) for r in selected if r['metric']=='W')):
            four=[r for r in selected if (r['problem_id'],r['seed'],r['order'],r['labels'])==key]
            contrasts.append(dict(zip(('problem_id','seed','order','labels'),key),
                all_four_selections_correct=both([r['selection_success'] for r in four]),end_to_end_scheduled=False))
        totals={}
        for metric in ('D','W'):
            rs=[r for r in selected if r['metric']==metric];gs=[r for r in rs if r['generation_scheduled']]
            ps=[r for r in pairs if r['metric']==metric];rb=[r for r in robust if r['metric']==metric]
            totals[metric]={}
            for key,items,field in [
                ('mapping_success',rs,'mapping_success'),('selection_success',rs,'selection_success'),
                ('conditional_choice',[r for r in rs if r['mapping_success'] is True],'structural_choice_correct'),
                ('generator_success',gs,'generator_success'),('metric_end_to_end',gs,'metric_end_to_end'),
                ('selection_pairs',ps,'selection_success'),('end_to_end_pairs',[p for p in ps if p['generation_scheduled']],'end_to_end_success'),
                ('presentation_robust_selection',rb,'selection_success'),
                ('presentation_robust_end_to_end',[r for r in rb if r['generation_scheduled']],'end_to_end_success')]:
                totals[metric][key]=tally([r[field] for r in items])
            totals[metric]['follows_supplied_extreme']=tally([r['support_diagnostic']['follows_supplied_extreme'] for r in rs if r['support_diagnostic'] is not None])
        tids={r['trial_id'] for r in selected};ops=[o for o in plan['slots'] if o['trial_id'] in tids]
        stage_usage={}
        for stage in ('select','generation'):
            applicable=('select',) if stage=='select' else ('facts','rule','final')
            us=[usages[o['id']] for o in ops if o['id'] in usages and o['stage'] in applicable]
            stage_usage[stage]={'calls':len(us),'fields':usage_tally(us)}
        bias={}
        for m in ('D','W'):
            known=[r for r in selected if r['metric']==m and r['selector_status']=='ok']
            bias[m]={'observed_choices':len(known),'first_position':sum(r['selected_position']==0 for r in known),
                     'route_0_id':sum(r['candidate_id']=='route_0' for r in known)}
        by_strategy[strategy]={'totals':totals,'pairs':pairs,'presentation_robust_groups':robust,'metric_discrimination':contrasts,
             'position_id_diagnostic':bias,'usage_by_stage':stage_usage,
             'selection_statuses':dict(sorted(Counter(r['selector_status'] for r in selected).items()))}
    comparisons={}
    specs=[('H1_accuracy_support','candidate_id','correct_full'),('H2_representation','correct_full','correct_values'),('H3_value_swap','correct_values','swapped_values')]
    for name,left,right in specs:
        comparisons[name]={'left':left,'right':right,'by_metric':{}}
        idx={(r['unit_id'],r['selector_variant']):r for r in rows if r['arm']=='model'}
        units=sorted(set(u for u,v in idx));matches=[(idx[u,left],idx[u,right]) for u in units]
        for m in ('D','W'):
            match=[(a,b) for a,b in matches if a['metric']==m]
            generated=[(a,b) for a,b in match if a['generation_scheduled'] and b['generation_scheduled']]
            pair_idx={pair_key(p):p for p in by_strategy[right]['pairs']}
            pp=[(a,pair_idx[pair_key(a)]) for a in by_strategy[left]['pairs'] if a['metric']==m]
            comparisons[name]['by_metric'][m]={
                'selection':paired_tally(match,'selection_success'),
                'generator':paired_tally(generated,'generator_success'),
                'end_to_end':paired_tally(generated,'metric_end_to_end'),
                'selection_pairs':paired_tally(pp,'selection_success'),
                'end_to_end_pairs':paired_tally([(a,b) for a,b in pp if a['generation_scheduled'] and b['generation_scheduled']],'end_to_end_success'),
                'changed_path':tally([None if a['selector_status']!='ok' or b['selector_status']!='ok' else a['selected_rule_ids']!=b['selected_rule_ids'] for a,b in match]),
                'both_follow_supplied_extreme':tally([both([a['support_diagnostic']['follows_supplied_extreme'],b['support_diagnostic']['follows_supplied_extreme']]) for a,b in match if a['support_diagnostic'] is not None and b['support_diagnostic'] is not None])}
    return {'contract':'v083-summary-r1','provenance':plan['provenance'],'state':state,'groups':by_strategy,'hypothesis_comparisons':comparisons,
            'reference':tally([r['reference_success'] for r in rows if r['arm']=='reference']),
            'reference_shared_not_duplicated':True,'trials':rows,'call_statuses':dict(sorted(Counter(statuses.values()).items())),
            'usage':usage_tally(list(usages.values())),'distinct_structural_problems':4,'new_independent_structures':0,
            'frozen_control_origin':'experimenter_not_model_generated','model_profile_calls':0,
            'diagnostic_only':'W all arms and swapped_values D: no graph scheduled; not zero successes or unobserved execution',
            'decision':'close_frozen_three_hypothesis_batch_no_automatic_followup' if state=='complete' else 'preserve_incomplete_no_retry'}
