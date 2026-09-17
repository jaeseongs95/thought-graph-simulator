"""생산 원응답 채점. facts·ID 지원·전제 의미·전체 D 종단을 분리한다."""
from collections import Counter, defaultdict
import core091 as core
import design091 as design
import bridge091
import design086 as selector
import report086 as decode
from rows087 import rule_check
from measure import assess
BAD = {'invalid_json','invalid_schema','lookup_null','skipped_invalid_comparison_output'}


def conjoin(values):
    values = list(values)
    if any(v is False for v in values):
        return False
    return None if any(v is None for v in values) else True


def fact_check(problem, nodes):
    errors = []
    if Counter(n['atom'] for n in nodes) != Counter(problem['facts']):
        errors.append('initial_fact_multiset')
    if any(n['rule'] is not None or n['parents'] for n in nodes):
        errors.append('initial_fact_shape')
    if len({n['id'] for n in nodes}) != len(nodes):
        errors.append('duplicate_node_id')
    return dict(valid=not errors, error_codes=sorted(errors))


def facts_support(problem, nodes, arm):
    if arm == 'baseline':
        return True
    table = {x['atom']:x['id'] for x in design.fact_allocation(problem,arm)}
    return all(n['atom'] in table and n['id']==table[n['atom']] for n in nodes)


def main_rows(plan, records, responses):
    s = plan['protocol']
    objects, states, usage = {}, {}, {}
    own_slots = defaultdict(list)
    for o in plan['slots']:
        sid = o['id']
        st,obj,u = decode.parse_response(records.get(sid),responses.get(sid,b''),s,o['stage'],'two_stage_values')
        objects[sid],states[sid] = obj,st
        if records.get(sid,{}).get('kind') == 'call':
            usage[sid] = u
        if o['stage'] in ('facts','rule','final'):
            own_slots[o['trial_id']].append(o)
    rows = []
    for t in plan['trials']:
        p = next(p for p in s['problems'] if p['id']==t['problem_id'])
        arm = t['generator_arm']
        route = selector.selected_route(plan,t,responses)
        cards = selector.cards(plan,t)
        values = {x['candidate_id']:decode.route_values(p,[r['id'] for r in x['rules']]) for x in cards}
        target = (min if t['condition']=='shallow' else max)(v['D'] for v in values.values())
        ci,si = t['comparison_slot_id'],t['selection_slot_id']
        cst,sst = states[ci],states[si]
        cmp_ok = objects[ci]['target_value']==target if cst=='ok' else False if cst in BAD else None
        choice = (values[route['candidate_id']]['D']==target if route else False) if sst=='ok' else False if sst in BAD else None
        linkage = None
        if cst=='ok' and sst=='ok':
            linkage = bool(route and values[route['candidate_id']]['D']==objects[ci]['target_value'])
        elif sst in BAD:
            linkage = False
        selection = conjoin((cmp_ok,choice,linkage))
        own = own_slots[t['id']]
        if route:
            own = [o for o in own if o['stage']!='rule' or o['rule_position']<len(route['rule_ids'])]
        nodes, checks = [], []
        ready, prefix, final = bool(route), True, None
        facts_ok = facts_id_ok = None
        if route:
            for o in own:
                sid,stage = o['id'],o['stage']
                entry = dict(id=sid,stage=stage,status=states[sid],valid=None,error_codes=None,
                             support_contract_success=None,prefix_valid_before=prefix)
                if states[sid] != 'ok':
                    ready,prefix = False,False
                    if stage=='facts' and states[sid] in BAD:
                        facts_ok = False
                    checks.append(entry)
                    continue
                obj = objects[sid]
                if stage=='facts':
                    ns = obj['nodes']
                    entry.update(fact_check(p,ns))
                    entry['support_contract_success'] = facts_support(p,ns,arm)
                    facts_ok,facts_id_ok = entry['valid'],entry['support_contract_success']
                    nodes.extend(ns)
                elif stage=='rule':
                    rule = next(r for r in p['rules'] if r['id']==route['rule_ids'][o['rule_position']])
                    entry.update(rule_check(p,nodes,obj['node'],rule['id']))
                    entry['support_contract_success'] = (True if arm=='baseline' else
                        obj['node']['id']==design.rule_allocation(p,rule,o['rule_position'],arm))
                    nodes.append(obj['node'])
                else:
                    final = obj['final_node_id']
                    matches = [n for n in nodes if n['id']==final]
                    errors = ['missing_or_ambiguous_final'] if len(matches)!=1 else ['wrong_goal'] if matches[0]['atom']!=p['goal'] else []
                    entry.update(valid=not errors,error_codes=errors,support_contract_success=True)
                prefix = bool(prefix and entry['valid'] is True and entry['support_contract_success'] is True)
                checks.append(entry)
        graph = dict(nodes=nodes,final_node_id=final) if ready else None
        result = assess(p,graph) if graph is not None else None
        depth = result['actual_D'] if result else None
        width = sum(n['rule'] is not None for n in nodes) if result and result['strict_valid'] else None
        semantic = None
        support = conjoin(x['support_contract_success'] for x in checks) if checks else None
        if graph is not None:
            semantic = bool(result['strict_valid'] and all(x['valid'] is True for x in checks)
                and [n['rule'] for n in nodes if n['rule'] is not None]==route['rule_ids']
                and depth==values[route['candidate_id']]['D'] and width==values[route['candidate_id']]['W'])
        elif route and any(states[o['id']] in BAD for o in own):
            semantic = False
        generated = conjoin((semantic,support))
        targetgraph = None if semantic is None else bool(semantic and depth==target)
        endpoint = conjoin((selection,generated,targetgraph))
        basic = {k:t[k] for k in ('unit_id','problem_id','seed','phase','generator_arm','condition','cohort','topology_id','renaming_id','input_unit_id','presentation_id','sampling_seed','replicate_id')}
        rows.append(dict(basic,execution_id=plan['run_name']+'::'+t['id'],trial_id=t['id'],pair_id=t['pair_id'],base_pair_id=t['base_pair_id'],
            order=t['candidate_order_index'],labels=t['id_assignment_index'],
            comparison_status=cst,lookup_status=sst,comparison_value=objects[ci].get('target_value') if cst=='ok' else None,
            comparison_success=cmp_ok,lookup_adherence=linkage,final_choice_success=choice,selection_success=selection,
            selected_candidate_id=route['candidate_id'] if route else None,
            selected_rule_ids=route['rule_ids'] if route else None,selected_D=values[route['candidate_id']]['D'] if route else None,
            target_D=target,actual_D=depth,actual_W=width,initial_fact_success=facts_ok,initial_id_contract_success=facts_id_ok,
            generator_semantic_success=semantic,support_contract_success=support,generator_success=generated,
            target_graph_success_without_trace=targetgraph,end_to_end_success=endpoint,graph_result=result,step_checks=checks,
            source_scope='new_shared_selection_and_new_arm_specific_facts;no_old_graph_history'))
    return rows,states,usage
