"""독립 선택·요청·증명 검산. 생산 design085/report085/measure/stages를 import하지 않는다."""
from copy import deepcopy
from collections import Counter
import bootstrap
import audit_model as prior
from audit_graph import _semantic
from audit_io import load, dump, need


def reconstruct_schedule(s):
    trials, ops, actions = [], [], []
    number = 0
    for block in range(len(s['problems'])*len(s['seeds'])):
        pi,si=divmod(block,len(s['seeds']));p=s['problems'][pi]
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
                offset=(pos*2+lab+si+pi+(direction=='deep')+(metric=='W'))%len(s['selector_variants'])
                variants=[s['selector_variants'][(i+offset)%len(s['selector_variants'])] for i in range(len(s['selector_variants']))]
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
                generate=arm=='reference' or (metric=='D' and variant in ('candidate_id','correct_values','two_stage_values'))
                t=dict(id=tid,unit_id=unit,variant='explicit_rule',selector_variant=variant,selection_slot_id=sid,comparison_slot_id=unit+'_two_stage_values_compare' if variant=='two_stage_values' else None,
                    block=block,arm=arm,problem_id=p['id'],seed=s['seeds'][si],candidate_order_index=pos,
                    id_assignment_index=lab,metric=metric,condition=direction,
                    pair_id=pair+'_'+variant if pair else None,base_pair_id=pair,generate=generate,control_candidate_id=control)
                trials.append(t);group.append(t)
                if variant=='two_stage_values':
                    cid=t['comparison_slot_id']
                    ops.append(dict(id=cid,trial_id=tid,logical_id=unit+'_compare',stage='compare',rule_position=None))
                    actions.append({'kind':'slot','id':cid})
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
    status,obj,usage=prior.decode(record,raw,spec,phase,'explicit_rule')
    if not (phase=='compare' or phase=='select' and strategy in ('two_stage_values','oracle_lookup')):
        return status,obj,usage
    if status not in ('ok','invalid_schema'):return status,obj,usage
    valid=False
    if type(obj) is dict:
        if phase=='compare':
            valid=set(obj)=={'target_value'} and type(obj.get('target_value')) is int and 0<=obj['target_value']<=128
        else:
            valid=set(obj)=={'candidate_id'} and (obj.get('candidate_id') is None or type(obj.get('candidate_id')) is str and obj['candidate_id'] in spec['candidate_ids'])
    return ('ok' if valid else 'invalid_schema'),obj,usage


def independent_value_status(plan,t,raws):
    sid=t.get('comparison_slot_id');raw=raws.get(sid)
    rec={'kind':'call','http_status':200,'error':None} if raw is not None else None
    return decode(rec,raw or b'',plan['protocol'],'compare','two_stage_values')


def lookup_original(plan,t,cs,raws):
    if t['selector_variant']=='oracle_lookup':
        s=plan['protocol'];p=next(p for p in s['problems'] if p['id']==t['problem_id'])
        vals=[prior.route_depth(p,[r['id'] for r in c['rules']]) if t['metric']=='D' else len(c['rules']) for c in cs]
        target=sorted(vals)[int(t['condition']=='deep')]
        return dump({'target_value':target}).decode()
    raw=raws.get(t['comparison_slot_id'])
    return None if raw is None else prior.content(raw)



def expected_request(plan,slot,raws):
    t=next(t for t in plan['trials'] if t['id']==slot['trial_id']);s=plan['protocol'];phase=slot['stage']
    p,cs,src,route=context(plan,t,raws)
    if phase=='select' and t['selector_variant']=='two_stage_values':
        status,_,_=independent_value_status(plan,t,raws)
        if status!='ok':
            return ('invalid_comparison_output' if status in ('invalid_json','invalid_schema') else 'unusable_comparison_response'),None
    if phase not in ('select','compare'):
        if route is None:return 'unmappable_selection',None
        if phase=='rule' and slot['rule_position']>=len(route['rule_ids']):return 'outside_selected_route',None
    body=deepcopy(s['api_defaults']);body['options']['seed']=t['seed']
    if phase=='compare':
        header=s['numeric_compare_header'];schema=deepcopy(s['numeric_compare_schema'])
        field='goal_depth' if t['metric']=='D' else 'rule_count'
        vals=[load(row['content'])[field] for row in controlled_measurements(plan,t,cs)]
        data={'metric':t['metric'],'direction':('min','max')[int(t['condition']=='deep')],'values':vals}
    elif phase=='select' and t['selector_variant'] in ('two_stage_values','oracle_lookup'):
        schema=deepcopy(s['lookup_schema']);header=s['lookup_header']
        data={'candidate_measurements':controlled_measurements(plan,t,cs),'metric':t['metric'],'value_original':lookup_original(plan,t,cs,raws)}
    elif phase == 'select':
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
            if pre['trial_id']==t['id'] and pre['stage'] in ('facts','rule','final') and pre['id'] in raws:
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


def isomorphic_pair(left_problem, left_paths, right_problem, right_paths):
    """규칙/원자 이름을 보지 않는 독립 전단사 검사. 생산 정규형 구현을 import하지 않는다."""
    from itertools import permutations
    if len(left_problem['facts']) != len(right_problem['facts']):return False
    if [len(p) for p in left_paths] != [len(p) for p in right_paths]:return False
    left_rules={r['id']:r for r in left_problem['rules']}
    right_rules={r['id']:r for r in right_problem['rules']}
    for fs in permutations(right_problem['facts']):
        common=dict(zip(left_problem['facts'],fs))
        common[left_problem['goal']]=right_problem['goal']
        all_routes=True
        for path_a,path_b in zip(left_paths,right_paths):
            aa=[left_rules[i] for i in path_a];bb=[right_rules[i] for i in path_b]
            internal_a=[r['conclusion'] for r in aa if r['conclusion']!=left_problem['goal']]
            internal_b=[r['conclusion'] for r in bb if r['conclusion']!=right_problem['goal']]
            expected={(r['conclusion'],tuple(sorted(r['premises']))) for r in bb}
            found=False
            for remap in permutations(internal_b):
                mapping=dict(common);mapping.update(zip(internal_a,remap))
                actual={(mapping[r['conclusion']],tuple(sorted(mapping[a] for a in r['premises']))) for r in aa}
                if actual==expected:found=True;break
            if not found:all_routes=False;break
        if all_routes:return True
    return False


def validate_protocol(s):
    """동결된 이전 원본 계약과 새 배정·처치를 독립적으로 확인한다."""
    from pathlib import Path
    from audit_io import same,digest
    base_path=Path(__file__).resolve().parent/'data/v084_protocol.json'
    previous=load(base_path.read_bytes())
    need(digest(base_path.read_bytes())==s['previous_protocol_sha256'],'previous protocol hash')
    need(s['contract']=='v085-value-linkage-r1','protocol version')
    frozen=('model','identity','seeds','conditions','reference_conditions','candidate_orders',
        'candidate_ids','selector_schema','generation_schema','headers','api_defaults','num_predict',
        'request_utf8_byte_limit','timeout_seconds','generator_variants','id_assignments',
        'count_select_header','count_conditions','control_select_addendum','support_origin','support_only_in_selector',
        'problems','reference_plans','depth_ranges','frozen_profiles','structure_signatures','metrics_by_problem')
    for key in frozen:need(same(s[key],previous[key]),'v084 anchored contract drift: '+key)
    need(s['selector_variants']==['candidate_id','correct_values','two_stage_values','oracle_lookup'],'four fixed arms')
    need(s['generation_selector_variants']==s['selector_variants'][:3] and s['generation_metrics']==['D'],'D generation scope')
    need(s['diagnostic_only_variants']==['oracle_lookup'] and s['lookup_only_variants']==['oracle_lookup'],'diagnostic scope')
    need(s['holdout'] is False and s['diagnostic_case_reuse'] is True and s['independent_new_structures']==s['new_structures']==0,'not new holdout')
    need(s['iid_structure_sampling'] is False and s['outcome_based_case_selection'] is False,'all previous cases, not selected subset')
    need(not any(s[k] for k in ('automatic_retry','automatic_download','automatic_server_start','posthoc_repair')),'no automatic repairs')
    need(s['numeric_compare_schema']=={'type':'object','properties':{'target_value':{'type':'integer','minimum':0,'maximum':128}},'required':['target_value'],'additionalProperties':False},'numeric schema does not force correct value')
    need(s['lookup_schema']=={'type':'object','properties':{'candidate_id':{'enum':['route_0','route_1',None]}},'required':['candidate_id'],'additionalProperties':False},'lookup null contract')
    need(all(s[k] is True for k in ('numeric_stage_sees_only_values','lookup_stage_receives_no_direction','comparison_value_never_corrected','oracle_lookup_diagnostic_only','lookup_null_is_observed_abstention','target_D_success_requires_every_assigned_selection_stage')),'stage boundaries')
    need(s['primary_comparison']==['correct_values','two_stage_values'],'fixed primary comparison')
    need(s['primary_unit']=='previously_observed_structural_case_not_seed_or_presentation' and s['no_automatic_p_value'] is True,'analysis units')
    expected={'T01':[(2,4),(3,4)],'T02':[(3,4),(4,4)],'T03':[(3,5),(4,5)],'T04':[(3,5),(4,5)],
              'T05':[(2,4),(3,3)],'T06':[(3,5),(4,4)],'T07':[(3,5),(4,4)],'T08':[(3,5),(4,4)]}
    need([p['id'] for p in s['problems']]==list(expected),'eight prespecified cases')
    need(s['metrics_by_problem']=={pid:['D'] if i<4 else ['D','W'] for i,pid in enumerate(expected)},'metric assignment')
    routes={}
    for p in s['problems']:
        pid=p['id'];ids=[r['id'] for r in p['rules']]
        need(len(ids)==len(set(ids)) and len(p['facts'])==len(set(p['facts']))==3,'unique rules/facts')
        need(all(r['premises'] and len(r['premises'])==len(set(r['premises'])) for r in p['rules']),'nonempty unique premises')
        routes[pid]=[s['reference_plans'][pid][k] for k in s['reference_conditions']]
        need(not set(routes[pid][0])&set(routes[pid][1]),'disjoint rules between routes')
        need(set(ids)==set(routes[pid][0]+routes[pid][1]),'no unscheduled distractor rule')
        for i,path in enumerate(routes[pid]):
            need(len(path)==len(set(path)) and set(path)<=set(ids),'unique path rule ids')
            d=prior.route_depth(p,path)
            need((d,len(path))==expected[pid][i],'actual candidate D/W')
            need(type(s['depth_ranges'][pid][i]) is int and s['depth_ranges'][pid][i]==d,'depth range')
            subset=[r for r in p['rules'] if r['id'] in path]
            rules={r['conclusion']:r for r in subset}
            need(len(rules)==len(path) and not set(rules)&set(p['facts']),'unique derived atoms')
            seen=set();used=set()
            def visit(atom,stack=frozenset()):
                need(atom not in stack,'cycle')
                seen.add(atom)
                if atom in p['facts']:return
                need(atom in rules,'missing antecedent')
                r=rules[atom];used.add(r['id'])
                for a in r['premises']:visit(a,stack|{atom})
            visit(p['goal'])
            need(set(p['facts'])<=seen and used==set(path),'all candidate nodes support goal')
        x,y=expected[pid];m=s['problem_metadata'][pid]
        need(m['family']==('equal_rule_count' if x[1]==y[1] else 'inverted_rule_count'),'family')
        need(m['prior_exposure_batches']==['v084'],'known diagnostic set provenance')
        need((m['shallow_D'],m['deep_D'],m['shallow_rule_count'],m['deep_rule_count'])==(x[0],y[0],x[1],y[1]),'metadata D/W')

    expected_controls={p['id']:[reference_profile(s,p,i) for i in (0,1)] for p in s['problems']}
    need(same(s['frozen_profiles'],expected_controls),'independent exact controls')
    ts,ss,aa=reconstruct_schedule(s)
    need((len(ts),len(ss),len(aa))==(800,3708,3740),'fixed schedule counts')
    need(sum(t['generate'] for t in ts)==s['assigned_graph_trials']==416,'proof count')
    need(sum(o['stage']=='select' for o in ss)==s['selector_calls']==768,'lookup/select count')
    need(sum(o['stage']=='compare' for o in ss)==s['numeric_comparison_calls']==192,'comparison count')
    need(s['assigned_control_trials']==32 and s['metadata_slots']==32,'shared refs/metadata')
    need(len(ss)==s['max_inference_calls'] and len(aa)==s['max_action_slots'],'slot budget')
    expected_calls=minimum=960
    for trial in ts:
        if not trial['generate']:continue
        lengths=[len(x) for x in s['reference_plans'][trial['problem_id']].values()]
        expected_calls+=2+lengths[int(trial['condition']=='deep')]
        minimum+=2+(lengths[int(trial['condition']=='deep')] if trial['arm']=='reference' else min(lengths))
    need(expected_calls==s['expected_inference_calls_if_all_target_routes_selected']==3612,'expected call budget')
    need(minimum==s['minimum_inference_calls_if_all_selections_mappable']==3516,'minimum mapped budget')
    need(s['profile_calls']==0 and not any(o['stage']=='profile' for o in ss),'no model DAG depth worksheet')


def independent_summary(plan, records, raws, state):
    s = plan['protocol']; statuses={}; formats={}; objects={}; usages={}; rows=[]
    for op in plan['slots']:
        t=next(x for x in plan['trials'] if x['id']==op['trial_id'])
        rec=records.get(op['id'])
        status,obj,u=decode(rec,raws.get(op['id'],b''),s,op['stage'],t['selector_variant'])
        formats[op['id']]=status
        if op['stage']=='select' and status=='ok' and context(plan,t,raws)[3] is None:
            status='lookup_null' if t['selector_variant'] in ('two_stage_values','oracle_lookup') and obj.get('candidate_id') is None else 'unmappable_selection'
        statuses[op['id']]=status;objects[op['id']]=obj
        if rec is not None and rec['kind']=='call':usages[op['id']]=u
    model_failures=('invalid_schema','invalid_json','unmappable_selection','lookup_null','skipped_invalid_comparison_output')
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
                if op['trial_id']==t['id'] and op['stage'] in ('facts','rule','final'):
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
    for row in rows:
        annotate_pipeline(plan,row,objects,statuses,formats)
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
        for stage in ('compare','select','generation'):
            applicable=(stage,) if stage in ('compare','select') else ('facts','rule','final')
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
    specs=[('C0_anchor_support','candidate_id','correct_values'),('C1_two_stage_vs_supported','correct_values','two_stage_values'),('C2_oracle_lookup_vs_supported','correct_values','oracle_lookup')]
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
    return {'stage_diagnostics':independent_stage_diagnostics(plan,rows),'structural_comparison':structural_diagnostics(plan,by_strategy,rows),'contract':'v085-summary-r1','provenance':plan['provenance'],'state':state,'groups':by_strategy,'hypothesis_comparisons':comparisons,
            'reference':tally([r['reference_success'] for r in rows if r['arm']=='reference']),
            'reference_shared_not_duplicated':True,'trials':rows,'call_statuses':dict(sorted(Counter(statuses.values()).items())),
            'usage':usage_tally(list(usages.values())),'distinct_structural_problems':8,'new_heldout_structural_cases':0,'iid_structure_sampling':False,
            'frozen_control_origin':'experimenter_not_model_generated','model_profile_calls':0,
            'diagnostic_only':'W all arms and oracle_lookup: selection/lookup only; not D end-to-end evidence',
            'decision':'close_frozen_diagnostic_batch_no_automatic_followup' if state=='complete' else 'preserve_incomplete_no_retry'}


def structural_diagnostics(plan, groups, rows):
    output=[];left,right=plan['protocol']['primary_comparison']
    for p in plan['protocol']['problems']:
        identifier=p['id'];bank={};arms={}
        for variant in plan['protocol']['generation_selector_variants']:
            bank[variant]={(r['seed'],r['order'],r['labels']):r for r in groups[variant]['pairs'] if r['metric']=='D' and r['problem_id']==identifier}
            rr=[r for r in rows if r['metric']=='D' and r['problem_id']==identifier and r['selector_variant']==variant];pp=list(bank[variant].values())
            arms[variant]={'selection':tally([r['selection_success'] for r in rr]),'end_to_end':tally([r['metric_end_to_end'] for r in rr]),
                          'pairs':tally([r['end_to_end_success'] for r in pp]),'all_seeds_all_presentations':both([r['end_to_end_success'] for r in pp])}
        need(set(bank[left])==set(bank[right]) and len(bank[left])==8,'structural pair keys')
        match=[(bank[left][k],bank[right][k]) for k in sorted(bank[left])];comparison=paired_tally(match,'end_to_end_success')
        difference=None if comparison['not_comparable'] else sum(int(b['end_to_end_success'])-int(a['end_to_end_success']) for a,b in match)/8
        refs={d:tally([r['reference_success'] for r in rows if r['problem_id']==identifier and r['arm']=='reference' and r['condition']==d]) for d in ('shallow','deep')}
        output.append(dict(problem_id=identifier,family=plan['protocol']['problem_metadata'][identifier]['family'],arms=arms,
                           paired_end_to_end=comparison,pair_rate_difference=difference,reference_by_direction=refs))
    outcomes=Counter();observed=[]
    for item in output:
        d=item['pair_rate_difference']
        if d is None:outcomes['unmeasured_structures']+=1
        else:
            observed.append(d);outcomes['improved_structures' if d>0 else 'worsened_structures' if d<0 else 'unchanged_structures']+=1
    subgroups={}
    for family in ('equal_rule_count','inverted_rule_count'):
        ds=[r['pair_rate_difference'] for r in output if r['family']==family]
        subgroups[family]={'assigned_structures':len(ds),'complete_structures':sum(x is not None for x in ds),'mean_pair_rate_difference':None if None in ds else sum(ds)/len(ds)}
    return {'unit':'previously_observed_structural_case','left':left,'right':right,'assigned_structures':len(output),'complete_structures':len(observed),
            **{k:outcomes[k] for k in ('improved_structures','worsened_structures','unchanged_structures','unmeasured_structures')},
            'mean_pair_rate_difference':sum(observed)/len(output) if len(observed)==len(output) else None,
            'families':subgroups,'cases':output,'inferential_p_value':None,
            'interpretation':'v084에서 관측한 8개 구조 전체의 후속 진단이다. 새 holdout이 아니며 seed/표시 반복과 반복 숫자 요청은 독립 구조가 아니다.'}


def annotate_pipeline(plan,row,objects,statuses,formats):
    trial=next(x for x in plan['trials'] if x['id']==row['trial_id']);kind=trial['selector_variant']
    row['diagnostic_only']=kind=='oracle_lookup';row['final_choice_success']=row['selection_success']
    row['comparison_status']='not_scheduled';row['comparison_value']=None;row['comparison_success']=None
    row['lookup_value_source']=None;row['lookup_input_value']=None;row['lookup_adherence']=None
    generated=row['generator_success']
    row['target_graph_success_without_selection_trace']=None if generated is None else generated and row['actual_'+row['metric']]==row['target_value']
    if kind not in ('two_stage_values','oracle_lookup'):return
    if kind=='oracle_lookup':
        value=row['target_value'];row['lookup_value_source']='experimenter_target_diagnostic_only'
    else:
        cid=trial['comparison_slot_id'];state=statuses[cid];row['comparison_status']=state
        value=objects[cid]['target_value'] if state=='ok' else None
        row['comparison_value']=value;row['lookup_value_source']='model_comparison'
        if state=='ok':row['comparison_success']=value==row['target_value']
        elif state in ('invalid_json','invalid_schema'):row['comparison_success']=False
    row['lookup_input_value']=value
    sid=trial['selection_slot_id'];fmt=formats[sid]
    if value is not None:
        if fmt=='ok':
            p,cards,_,_=context(plan,trial,{})
            expected=[]
            for card in cards:
                actual=prior.route_depth(p,[r['id'] for r in card['rules']]) if row['metric']=='D' else len(card['rules'])
                if actual==value:expected.append(card['candidate_id'])
            row['lookup_adherence']=objects[sid]['candidate_id']==(expected[0] if len(expected)==1 else None)
        elif fmt in ('invalid_json','invalid_schema'):row['lookup_adherence']=False
    if kind=='two_stage_values':
        comp=row['comparison_success']
        choice=False if comp is False else None if comp is None else both([comp,row['lookup_adherence'],row['final_choice_success']])
        row['selection_success']=choice
        if row['generation_scheduled']:
            if choice is False and row['candidate_id'] is None:row['metric_end_to_end']=False
            else:row['metric_end_to_end']=None if choice is None or generated is None else choice and row['target_graph_success_without_selection_trace']


def independent_stage_diagnostics(plan,rows):
    result={}
    trial_index={t['id']:t for t in plan['trials']}
    for variant in plan['protocol']['selector_variants']:
        metrics={}
        for metric in ('D','W'):
            rr=[r for r in rows if r['selector_variant']==variant and r['metric']==metric]
            cells={(i,c):[] for i in (0,1) for c in plan['protocol']['candidate_ids']}
            for r in rr:
                p,cs,_,_=context(plan,trial_index[r['trial_id']],{})
                for i,card in enumerate(cs):
                    n=prior.route_depth(p,[x['id'] for x in card['rules']]) if metric=='D' else len(card['rules'])
                    if n==r['target_value']:cells[i,card['candidate_id']].append(r)
            cc={f'position_{i+1}_{cid}':{'final_choice':tally([r['final_choice_success'] for r in vals]),'full_selection':tally([r['selection_success'] for r in vals])} for (i,cid),vals in cells.items()}
            metrics[metric]={'comparison':tally([r['comparison_success'] for r in rr]) if variant=='two_stage_values' else tally([]),
                'lookup_adherence':tally([r['lookup_adherence'] for r in rr]) if variant in ('two_stage_values','oracle_lookup') else tally([]),
                'lookup_given_correct_comparison':tally([r['lookup_adherence'] for r in rr if r['comparison_success'] is True]),
                'final_choice_without_trace':tally([r['final_choice_success'] for r in rr]),
                'target_graph_without_trace':tally([r['target_graph_success_without_selection_trace'] for r in rr if r['generation_scheduled']]),
                'accidental_target_graph_after_wrong_comparison':tally([r['target_graph_success_without_selection_trace'] for r in rr if r['comparison_success'] is False and r['generation_scheduled']]),
                'target_position_id_cells':cc}
        result[variant]=metrics
    return result
