"""생산 원응답 판정. 원문에 노드·전제·식별자를 추가하거나 바꾸지 않는다."""
from collections import Counter,defaultdict
import bridge087
import core087 as core
import design087 as design
import design086 as frozen
import report086 as decode_base
import stages,measure

BAD_OUTPUT={'invalid_json','invalid_schema','lookup_null','skipped_invalid_comparison_output'}
USAGE=('prompt_eval_count','eval_count','total_duration','prompt_eval_duration','eval_duration')


def data_from(body):return core.load(body['messages'][0]['content'].split('\n\ninput: ',1)[1])


def rule_check(problem,emitted,node,rid):
    """식별자와 전제 원자 multiset을 별도로 검사한다. 중복을 덮어쓰지 않는다."""
    index=defaultdict(list)
    for n in emitted:index[n['id']].append(n)
    errors=[];rules={r['id']:r for r in problem['rules']};r=rules.get(rid)
    if node['id'] in index:errors.append('duplicate_node_id')
    if node['rule']!=rid:errors.append('requested_rule_mismatch')
    if r is None:errors.append('unregistered_rule')
    elif node['atom']!=r['conclusion']:errors.append('wrong_atom')
    if len(set(node['parents']))!=len(node['parents']):errors.append('duplicate_parent')
    if any(p not in index for p in node['parents']):errors.append('missing_parent')
    if any(len(index.get(p,[]))>1 for p in node['parents']):errors.append('ambiguous_parent_id')
    can_count=all(len(index.get(p,[]))==1 for p in node['parents'])
    actual=Counter(index[p][0]['atom'] for p in node['parents']) if can_count else None
    expected=Counter(r['premises']) if r else None
    if expected is not None and actual is not None and expected!=actual:errors.append('premise_counter_mismatch')
    return {'valid':not errors,'error_codes':sorted(set(errors)),
            'parent_count_valid':None if r is None else len(node['parents'])==len(r['premises']),
            'missing_direct_atoms':None if actual is None or expected is None else sorted((expected-actual).elements()),
            'extra_parent_atoms':None if actual is None or expected is None else sorted((actual-expected).elements()),
            'new_id_unique':node['id'] not in index}


def support_success(data,payload):
    if 'allocated_node_id' not in data:return True
    return payload['node']['id']==data['allocated_node_id']


def features(problem,route,rid):
    rules={r['id']:r for r in problem['rules']};dep={a:set() for a in problem['facts']}
    for i in route:
        r=rules[i];dep[r['conclusion']]=set(r['premises']).union(*(dep[a] for a in r['premises']))
    premises=rules[rid]['premises']
    return {'premise_count':len(premises),'has_ancestor_among_direct_premises':any(a!=b and a in dep[b] for a in premises for b in premises)}


def main_rows(plan,records,responses):
    objects={};statuses={};usages={};s=plan['protocol'];ts={t['id']:t for t in plan['trials']}
    for slot in plan['slots']:
        sid=slot['id'];status,obj,u=decode_base.parse_response(records.get(sid),responses.get(sid,b''),s,slot['stage'],'two_stage_values')
        objects[sid]=obj;statuses[sid]=status
        if records.get(sid,{}).get('kind')=='call':usages[sid]=u
    result=[]
    anchors={a['id']:a for a in design.anchors()}
    for t in plan['trials']:
        problem=next(p for p in s['problems'] if p['id']==t['problem_id'])
        basic={k:t[k] for k in ('unit_id','problem_id','seed','phase','generator_arm','condition')};basic['trial_id']=t['id']
        own=[op for op in plan['slots'] if op['trial_id']==t['id'] and op['stage'] in ('facts','rule','final')]
        if t['phase']=='rule_probe':
            op=own[0];sid=op['id'];a=anchors[t['anchor_id']];data=data_from(a['request_body']);emitted=[]
            for h in data['history']:
                x=core.load(h['content']);emitted.extend(x['nodes'] if 'nodes'in x else [x['node']])
            checks=None;support=None;semantic=None
            if statuses[sid]=='ok':
                checks=rule_check(problem,emitted,objects[sid]['node'],a['rule_id']);semantic=checks['valid']
                req_data=data_from(design.request_for(plan,op,responses));support=support_success(req_data,objects[sid])
            elif statuses[sid] in BAD_OUTPUT:semantic=False
            result.append(dict(basic,anchor_id=a['id'],rule_id=a['rule_id'],rule_position=a['rule_position'],
                               response_status=statuses[sid],node_semantic_success=semantic,support_contract_success=support,
                               probe_success=None if semantic is None else bool(semantic and support is True),
                               rule_check=checks,features=features(problem,data['provided_route_plan']['rule_ids'],a['rule_id'])))
            continue
        route=frozen.selected_route(plan,t,responses);cs=frozen.cards(plan,t)
        vals={c['candidate_id']:decode_base.route_values(problem,[r['id']for r in c['rules']]) for c in cs}
        target=(min if t['condition']=='shallow' else max)(v['D']for v in vals.values())
        cmpid,selid=t['comparison_slot_id'],t['selection_slot_id'];cst= statuses[cmpid];sst=statuses[selid]
        cmp_ok=objects[cmpid]['target_value']==target if cst=='ok' else False if cst in BAD_OUTPUT else None
        choice=vals[route['candidate_id']]['D']==target if route is not None and sst=='ok' else False if sst in BAD_OUTPUT or (sst=='ok' and route is None) else None
        lookup=None
        if cst=='ok' and sst=='ok':lookup=False if route is None else vals[route['candidate_id']]['D']==objects[cmpid]['target_value']
        elif sst in BAD_OUTPUT:lookup=False
        selection=None if any(x is None for x in (cmp_ok,choice,lookup)) else bool(cmp_ok and choice and lookup)
        if sst=='ok' and route is None:selection=False
        checks=[];emitted=[];final=None;supportvals=[];allready=bool(route);prefix=True
        if route:
            own=[op for op in own if op['stage']!='rule' or op['rule_position']<len(route['rule_ids'])]
            for op in own:
                sid=op['id'];phase=op['stage'];entry={'id':sid,'stage':phase,'status':statuses[sid],'valid':None,'error_codes':None,'support_contract_success':None}
                if statuses[sid]!='ok':allready=False;prefix=False;checks.append(entry);continue
                obj=objects[sid]
                if phase=='facts':
                    ns=obj['nodes'];errs=[]
                    if Counter(n['atom'] for n in ns)!=Counter(problem['facts']):errs.append('initial_fact_multiset')
                    if any(n['rule'] is not None or n['parents']for n in ns):errs.append('initial_fact_shape')
                    if len({n['id']for n in ns})!=len(ns):errs.append('duplicate_node_id')
                    entry.update(valid=not errs,error_codes=sorted(errs),support_contract_success=True);emitted+=ns
                elif phase=='rule':
                    rid=route['rule_ids'][op['rule_position']]
                    if prefix:
                        detail=rule_check(problem,emitted,obj['node'],rid);entry.update(detail)
                    data=data_from(design.request_for(plan,op,responses));ss=support_success(data,obj)
                    entry['support_contract_success']=ss;supportvals.append(ss);emitted.append(obj['node'])
                else:
                    final=obj['final_node_id'];matched=[n for n in emitted if n['id']==final]
                    if prefix:
                        errors=[]
                        if len(matched)!=1:errors.append('missing_or_ambiguous_final')
                        elif matched[0]['atom']!=problem['goal']:errors.append('wrong_goal')
                        entry.update(valid=not errors,error_codes=errors,support_contract_success=True)
                checks.append(entry)
        graph={'nodes':emitted,'final_node_id':final} if allready else None
        gr=measure.assess(problem,graph) if graph is not None else None
        actual=gr['actual_D']if gr else None
        actual_w=sum(n['rule']is not None for n in emitted)if gr and gr['strict_valid'] is True else None
        semantic=None;contract=None
        if graph is not None:
            semantic=bool(gr['strict_valid'] is True and all(e['valid']is True for e in checks)
                          and [n['rule']for n in emitted if n['rule']is not None]==route['rule_ids']
                          and actual==vals[route['candidate_id']]['D'] and actual_w==vals[route['candidate_id']]['W'])
            contract=all(supportvals)
        elif any(statuses[o['id']]in BAD_OUTPUT for o in own):semantic=False
        generated=None if semantic is None else bool(semantic and contract is True)
        targetgraph=None if semantic is None else bool(semantic and actual==target)
        end=False if selection is False else None if selection is None or generated is None else bool(selection and generated and actual==target)
        result.append(dict(basic,pair_id=t['pair_id'],base_pair_id=t['base_pair_id'],order=t['candidate_order_index'],labels=t['id_assignment_index'],
                           comparison_status=cst,lookup_status=sst,comparison_value=objects[cmpid].get('target_value')if cst=='ok'else None,
                           comparison_success=cmp_ok,lookup_adherence=lookup,final_choice_success=choice,selection_success=selection,
                           selected_candidate_id=route['candidate_id']if route else None,selected_rule_ids=route['rule_ids']if route else None,
                           selected_D=vals[route['candidate_id']]['D']if route else None,target_D=target,
                           actual_D=actual,actual_W=actual_w,generator_semantic_success=semantic,support_contract_success=contract,
                           generator_success=generated,target_graph_success_without_trace=targetgraph,end_to_end_success=end,
                           graph_result=gr,step_checks=checks))
    return result,statuses,usages
