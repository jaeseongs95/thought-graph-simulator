"""독립 원응답 의미 판정. 생산 rows087/design087/measure/stages를 사용하지 않는다."""
from collections import Counter
import bridge087
from audit_bytes087 import load
import audit086 as old
from audit_graph import _semantic
from audit087 import expected_request,anchor_list

OUTPUT_BAD={'invalid_json','invalid_schema','lookup_null','skipped_invalid_comparison_output'}


def step_check(p,before,n,rid):
    errors=set();r=next((r for r in p['rules']if r['id']==rid),None)
    identifiers=[x['id']for x in before]
    if n['id']in identifiers:errors.add('duplicate_node_id')
    if n['rule']!=rid:errors.add('requested_rule_mismatch')
    if r is None:errors.add('unregistered_rule')
    elif n['atom']!=r['conclusion']:errors.add('wrong_atom')
    if len(n['parents'])!=len(set(n['parents'])):errors.add('duplicate_parent')
    located=[[x for x in before if x['id']==key]for key in n['parents']]
    if any(len(x)==0 for x in located):errors.add('missing_parent')
    if any(len(x)>1 for x in located):errors.add('ambiguous_parent_id')
    atoms=[x[0]['atom']for x in located]if all(len(x)==1 for x in located)else None
    absent=surplus=None
    if atoms is not None and r is not None:
        # 리스트 소거로 정확한 전제 다중집합을 독립 검산한다.
        rest=atoms[:];absent=[]
        for atom in r['premises']:
            if atom in rest:rest.remove(atom)
            else:absent.append(atom)
        surplus=sorted(rest);absent.sort()
        if absent or surplus:errors.add('premise_counter_mismatch')
    return {'valid':not errors,'error_codes':sorted(errors),'parent_count_valid':len(n['parents'])==len(r['premises'])if r else None,
            'missing_direct_atoms':absent,'extra_parent_atoms':surplus,'new_id_unique':n['id']not in identifiers}


def structural_features(p,route,rid):
    rr={r['id']:r for r in p['rules']};by={rr[k]['conclusion']:rr[k]['premises']for k in route}
    def ancestry(atom):
        result=set();todo=list(by.get(atom,[]))
        while todo:
            x=todo.pop()
            if x not in result:result.add(x);todo.extend(by.get(x,[]))
        return result
    ps=rr[rid]['premises']
    return {'premise_count':len(ps),'has_ancestor_among_direct_premises':any(x in ancestry(y)for x in ps for y in ps if x!=y)}


def route_metrics(p,route):return {'D':old.prior.route_depth(p,route),'W':len(route)}


def request_data(p,o,raws):
    _,raw=expected_request(p,o,raws);body=load(raw)
    return load(body['messages'][0]['content'].split('\n\ninput: ',1)[1])


def independent_rows(plan,records,raws):
    s=plan['protocol'];values={};states={};usage={};rows=[];anchors={a['id']:a for a in anchor_list()}
    bytrial={}
    for slot in plan['slots']:
        sid=slot['id'];st,value,u=old.decode(records.get(sid),raws.get(sid,b''),s,slot['stage'],'two_stage_values')
        states[sid]=st;values[sid]=value
        if records.get(sid,{}).get('kind')=='call':usage[sid]=u
        if slot['stage']in ('facts','rule','final'):bytrial.setdefault(slot['trial_id'],[]).append(slot)
    for t in plan['trials']:
        p=next(p for p in s['problems']if p['id']==t['problem_id']);own=bytrial[t['id']]
        basic={k:t[k]for k in ('unit_id','problem_id','seed','phase','generator_arm','condition')};basic['trial_id']=t['id']
        if t['phase']=='rule_probe':
            a=anchors[t['anchor_id']];op=own[0];sid=op['id'];d=load(a['request_body']['messages'][0]['content'].split('\n\ninput: ',1)[1]);before=[]
            for source in d['history']:
                payload=load(source['content']);before+=payload['nodes']if 'nodes'in payload else[payload['node']]
            check=None;sem=None;support=None
            if states[sid]=='ok':
                check=step_check(p,before,values[sid]['node'],a['rule_id']);sem=check['valid']
                q=request_data(plan,op,raws);support='allocated_node_id'not in q or values[sid]['node']['id']==q['allocated_node_id']
            elif states[sid]in OUTPUT_BAD:sem=False
            rows.append(dict(basic,anchor_id=a['id'],rule_id=a['rule_id'],rule_position=a['rule_position'],response_status=states[sid],
                             node_semantic_success=sem,support_contract_success=support,probe_success=None if sem is None else bool(sem and support is True),rule_check=check,
                             features=structural_features(p,d['provided_route_plan']['rule_ids'],a['rule_id'])))
            continue
        p,cards,source,route=old.context(plan,t,raws);metric={c['candidate_id']:route_metrics(p,[r['id']for r in c['rules']])for c in cards}
        target=sorted(v['D']for v in metric.values())[int(t['condition']=='deep')]
        cid,sid=t['comparison_slot_id'],t['selection_slot_id'];cst=states[cid];sst=states[sid]
        comparison=values[cid]['target_value']==target if cst=='ok'else False if cst in OUTPUT_BAD else None
        choice=metric[route['candidate_id']]['D']==target if sst=='ok'and route else False if sst in OUTPUT_BAD or (sst=='ok'and route is None)else None
        link=None
        if cst=='ok'and sst=='ok':link=bool(route and metric[route['candidate_id']]['D']==values[cid]['target_value'])
        elif sst in OUTPUT_BAD:link=False
        selected=None if None in (comparison,choice,link)else bool(comparison and choice and link)
        if sst=='ok'and route is None:selected=False
        observations=[];before=[];final=None;complete=bool(route);prefix_ok=True;support_flags=[]
        if route:
            own=[o for o in own if o['stage']!='rule' or o['rule_position']<len(route['rule_ids'])]
            for o in own:
                oid=o['id'];phase=o['stage'];row=dict(id=oid,stage=phase,status=states[oid],valid=None,error_codes=None,support_contract_success=None)
                if states[oid]!='ok':
                    complete=False;prefix_ok=False;observations.append(row);continue
                obj=values[oid]
                if phase=='facts':
                    nodes=obj['nodes'];errs=[]
                    if sorted(n['atom']for n in nodes)!=sorted(p['facts']):errs.append('initial_fact_multiset')
                    if any(n['rule']is not None or len(n['parents'])for n in nodes):errs.append('initial_fact_shape')
                    if len(set(n['id']for n in nodes))<len(nodes):errs.append('duplicate_node_id')
                    row.update(valid=not errs,error_codes=sorted(errs),support_contract_success=True);before.extend(nodes)
                elif phase=='rule':
                    if prefix_ok:row.update(step_check(p,before,obj['node'],route['rule_ids'][o['rule_position']]))
                    d=request_data(plan,o,raws);support=('allocated_node_id'not in d or d['allocated_node_id']==obj['node']['id'])
                    row['support_contract_success']=support;support_flags.append(support);before.append(obj['node'])
                else:
                    final=obj['final_node_id'];matches=[n for n in before if n['id']==final]
                    if prefix_ok:
                        errors=[]
                        if len(matches)!=1:errors.append('missing_or_ambiguous_final')
                        elif matches[0]['atom']!=p['goal']:errors.append('wrong_goal')
                        row.update(valid=not errors,error_codes=errors,support_contract_success=True)
                observations.append(row)
        graph={'nodes':before,'final_node_id':final}if complete else None
        gr=_semantic(p,graph)if graph is not None else None
        depth=gr['actual_D']if gr else None;w=sum(n['rule']is not None for n in before)if gr and gr['strict_valid']is True else None
        semantic=contract=None
        if complete:
            semantic=bool(gr['strict_valid']is True and all(row['valid']is True for row in observations)and
                          [n['rule']for n in before if n['rule']is not None]==route['rule_ids']and
                          depth==metric[route['candidate_id']]['D']and w==metric[route['candidate_id']]['W'])
            contract=all(support_flags)
        elif any(states[o['id']]in OUTPUT_BAD for o in own):semantic=False
        generated=None if semantic is None else bool(semantic and contract is True)
        goal=None if semantic is None else bool(semantic and depth==target)
        end=False if selected is False else None if selected is None or generated is None else bool(selected and generated and depth==target)
        rows.append(dict(basic,pair_id=t['pair_id'],base_pair_id=t['base_pair_id'],order=t['candidate_order_index'],labels=t['id_assignment_index'],
                         comparison_status=cst,lookup_status=sst,comparison_value=values[cid].get('target_value')if cst=='ok'else None,
                         comparison_success=comparison,lookup_adherence=link,final_choice_success=choice,selection_success=selected,
                         selected_candidate_id=route['candidate_id']if route else None,selected_rule_ids=route['rule_ids']if route else None,
                         selected_D=metric[route['candidate_id']]['D']if route else None,target_D=target,actual_D=depth,actual_W=w,
                         generator_semantic_success=semantic,support_contract_success=contract,generator_success=generated,
                         target_graph_success_without_trace=goal,end_to_end_success=end,graph_result=gr,step_checks=observations))
    return rows,states,usage
