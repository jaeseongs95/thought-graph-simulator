"""생산 rows/design/measure를 호출하지 않는 새 facts부터의 독립 의미 판정."""
from audit_bytes091 import load
from audit091 import facts_table, rule_id
import bridge091
import audit086 as decoder
from audit_rows087 import step_check
from audit_graph import _semantic
OUTPUT_BAD = {'invalid_json','invalid_schema','lookup_null','skipped_invalid_comparison_output'}


def combine(items):
    seen_unknown = False
    for value in items:
        if value is False:
            return False
        if value is None:
            seen_unknown = True
    return None if seen_unknown else True


def initial_check(p, nodes):
    errors = set()
    if sorted(n['atom'] for n in nodes) != sorted(p['facts']):
        errors.add('initial_fact_multiset')
    for n in nodes:
        if n['rule'] is not None or len(n['parents']) != 0:
            errors.add('initial_fact_shape')
    ids = [n['id'] for n in nodes]
    if len(ids) > len(set(ids)):
        errors.add('duplicate_node_id')
    return {'valid':not errors,'error_codes':sorted(errors)}


def initial_support(p, nodes, arm):
    if arm=='baseline':
        return True
    table = facts_table(p,arm)
    for n in nodes:
        match = [r for r in table if r['atom']==n['atom']]
        if len(match)!=1 or match[0]['id']!=n['id']:
            return False
    return True


def independent_rows(plan,records,raws):
    s = plan['protocol']
    outputs, status, usage, rows = {}, {}, {}, []
    bytrial = {}
    for slot in plan['slots']:
        sid = slot['id']
        state,value,counts = decoder.decode(records.get(sid),raws.get(sid,b''),s,slot['stage'],'two_stage_values')
        outputs[sid],status[sid] = value,state
        if records.get(sid,{}).get('kind')=='call':
            usage[sid] = counts
        if slot['stage'] in ('facts','rule','final'):
            bytrial.setdefault(slot['trial_id'],[]).append(slot)
    for t in plan['trials']:
        p,cards,source,route = decoder.context(plan,t,raws)
        metrics = {x['candidate_id']:{'D':decoder.prior.route_depth(p,[r['id'] for r in x['rules']]),'W':len(x['rules'])} for x in cards}
        target = sorted(m['D'] for m in metrics.values())[int(t['condition']=='deep')]
        cmpid,selid = t['comparison_slot_id'],t['selection_slot_id']
        a,b = status[cmpid],status[selid]
        cmpok = outputs[cmpid]['target_value']==target if a=='ok' else False if a in OUTPUT_BAD else None
        chosen = (metrics[route['candidate_id']]['D']==target if route else False) if b=='ok' else False if b in OUTPUT_BAD else None
        lookup = None
        if a=='ok' and b=='ok':
            lookup = bool(route and metrics[route['candidate_id']]['D']==outputs[cmpid]['target_value'])
        elif b in OUTPUT_BAD:
            lookup = False
        selection = combine([cmpok,chosen,lookup])
        sequence = bytrial[t['id']]
        nodes,observations = [],[]
        complete,prefix_ok,final = bool(route),True,None
        initial_semantic = initial_contract = None
        if route:
            sequence = [o for o in sequence if o['stage']!='rule' or o['rule_position']<len(route['rule_ids'])]
            for op in sequence:
                oid,stage = op['id'],op['stage']
                check = {'id':oid,'stage':stage,'status':status[oid],'valid':None,'error_codes':None,
                         'support_contract_success':None,'prefix_valid_before':prefix_ok}
                if status[oid]!='ok':
                    complete,prefix_ok = False,False
                    if stage=='facts' and status[oid] in OUTPUT_BAD:
                        initial_semantic=False
                    observations.append(check)
                    continue
                obj = outputs[oid]
                if stage=='facts':
                    check.update(initial_check(p,obj['nodes']))
                    check['support_contract_success']=initial_support(p,obj['nodes'],t['generator_arm'])
                    initial_semantic,initial_contract=check['valid'],check['support_contract_success']
                    nodes += obj['nodes']
                elif stage=='rule':
                    rid = route['rule_ids'][op['rule_position']]
                    check.update(step_check(p,nodes,obj['node'],rid))
                    rule = next(r for r in p['rules'] if r['id']==rid)
                    expected = None if t['generator_arm']=='baseline' else rule_id(p,rule,op['rule_position'],t['generator_arm'])
                    check['support_contract_success'] = expected is None or expected==obj['node']['id']
                    nodes += [obj['node']]
                else:
                    final = obj['final_node_id']
                    located = [n for n in nodes if n['id']==final]
                    errs = ['missing_or_ambiguous_final'] if len(located)!=1 else ['wrong_goal'] if located[0]['atom']!=p['goal'] else []
                    check.update(valid=not errs,error_codes=errs,support_contract_success=True)
                prefix_ok = bool(prefix_ok and check['valid'] is True and check['support_contract_success'] is True)
                observations.append(check)
        gr = _semantic(p,{'nodes':nodes,'final_node_id':final}) if complete else None
        d = gr['actual_D'] if gr else None
        w = len([n for n in nodes if n['rule'] is not None]) if gr and gr['strict_valid'] else None
        sem = None
        contract = combine(x['support_contract_success'] for x in observations) if observations else None
        if complete:
            sem = bool(gr['strict_valid'] and all(o['valid'] is True for o in observations)
                and [n['rule'] for n in nodes if n['rule'] is not None]==route['rule_ids']
                and d==metrics[route['candidate_id']]['D'] and w==metrics[route['candidate_id']]['W'])
        elif route and any(status[o['id']] in OUTPUT_BAD for o in sequence):
            sem=False
        generated=combine([sem,contract])
        goal=None if sem is None else bool(sem and d==target)
        end=combine([selection,generated,goal])
        basic={k:t[k] for k in ('unit_id','problem_id','seed','phase','generator_arm','condition','cohort','topology_id','renaming_id','input_unit_id','presentation_id','sampling_seed','replicate_id')}
        rows.append(dict(basic,execution_id=plan['run_name']+'::'+t['id'],trial_id=t['id'],pair_id=t['pair_id'],base_pair_id=t['base_pair_id'],
            order=t['candidate_order_index'],labels=t['id_assignment_index'],comparison_status=a,lookup_status=b,
            comparison_value=outputs[cmpid].get('target_value') if a=='ok' else None,
            comparison_success=cmpok,lookup_adherence=lookup,final_choice_success=chosen,selection_success=selection,
            selected_candidate_id=route['candidate_id'] if route else None,selected_rule_ids=route['rule_ids'] if route else None,
            selected_D=metrics[route['candidate_id']]['D'] if route else None,target_D=target,actual_D=d,actual_W=w,
            initial_fact_success=initial_semantic,initial_id_contract_success=initial_contract,
            generator_semantic_success=sem,support_contract_success=contract,generator_success=generated,
            target_graph_success_without_trace=goal,end_to_end_success=end,graph_result=gr,step_checks=observations,
            source_scope='new_shared_selection_and_new_arm_specific_facts;no_old_graph_history'))
    return rows,status,usage
