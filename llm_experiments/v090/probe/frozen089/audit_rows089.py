"""생산 rows/design/measure를 사용하지 않는 규칙·연속 이력 의미 판정."""
import bridge089
from audit_bytes089 import load
from audit089 import expected_request,get_anchor,continuing
from audit_rows087 import independent_rows as old_rows,step_check,structural_features
from audit_graph import _semantic
import audit086 as decoder
BAD={'invalid_json','invalid_schema','lookup_null','skipped_invalid_comparison_output'}

def independent_rows(plan,records,raws):
    ts=[t for t in plan['trials'] if t['phase']=='end_to_end'];ids={t['id']for t in ts}
    m=dict(plan,trials=ts,slots=[o for o in plan['slots']if o['trial_id']in ids])
    rows,states,usage=old_rows(m,records,raws);values={};s=plan['protocol']
    for o in plan['slots']:
        sid=o['id'];st,obj,u=decoder.decode(records.get(sid),raws.get(sid,b''),s,o['stage'],'two_stage_values')
        states[sid]=st;values[sid]=obj
        if records.get(sid,{}).get('kind')=='call':usage[sid]=u
    for t in plan['trials']:
        if t['phase']=='end_to_end':continue
        basic=dict(unit_id=t['unit_id'],problem_id=t['problem_id'],seed=t['seed'],phase=t['phase'],generator_arm=t['generator_arm'],condition=t['condition'],trial_id=t['id'])
        basic.update(initial_id_style=t['initial_id_style'],output_id_style=t['output_id_style'])
        p=next(x for x in s['problems']if x['id']==t['problem_id']);own=[o for o in plan['slots']if o['trial_id']==t['id']]
        history,allocation,_=continuing(t);nodes=load(history[0]['content'])['nodes'];n_prefix=len(nodes)
        observations=[];complete=True;prefix_ok=True;final=None;support=[]
        for o in own:
            sid=o['id'];stage=o['stage'];entry=dict(id=sid,stage=stage,status=states[sid],prefix_valid_before=prefix_ok,valid=None,error_codes=None,support_contract_success=None)
            if states[sid]!='ok':complete=False;prefix_ok=False;observations.append(entry);continue
            obj=values[sid]
            if stage=='rule':
                detail=step_check(p,nodes,obj['node'],t['route_rule_ids'][o['rule_position']]);entry.update(detail)
                ok=obj['node']['id']==allocation[o['rule_position']];entry['support_contract_success']=ok;support.append(ok)
                prefix_ok=bool(prefix_ok and detail['valid'] and ok);nodes.append(obj['node'])
            else:
                final=obj['final_node_id'];matches=[n for n in nodes if n['id']==final]
                errors=['missing_or_ambiguous_final']if len(matches)!=1 else ['wrong_goal']if matches[0]['atom']!=p['goal']else []
                entry.update(valid=not errors,error_codes=errors,support_contract_success=True)
            observations.append(entry)
        graph=dict(nodes=nodes,final_node_id=final)if complete else None
        gr=_semantic(p,graph)if complete else None
        target=decoder.prior.route_depth(p,t['route_rule_ids']);width=len(t['route_rule_ids'])
        d=gr['actual_D']if gr else None;w=len([n for n in nodes if n['rule']is not None])if gr and gr['strict_valid'] else None
        sem=contract=None
        if gr is not None:
            sem=bool(gr['strict_valid'] and all(e['valid']is True for e in observations) and
                [n['rule']for n in nodes[n_prefix:]]==t['route_rule_ids']and d==target and w==width)
            contract=all(support)
        elif any(states[o['id']]in BAD for o in own):sem=False
        ok=None if sem is None else bool(sem and contract is True)
        rows.append(dict(basic,anchor_id=t['anchor_id'],pair_id=t['pair_id'],base_pair_id=t['base_pair_id'],target_D=target,actual_D=d,actual_W=w,
            generator_semantic_success=sem,support_contract_success=contract,continuation_success=ok,graph_result=gr,step_checks=observations,
            observed_prefix_nodes=n_prefix,newly_generated_rules=sum(states[o['id']]=='ok'for o in own if o['stage']=='rule'),
            source_scope='old_valid_facts_plus_new_raw_rules;not_end_to_end',allocated_ids=allocation))
    order={t['id']:i for i,t in enumerate(plan['trials'])};rows.sort(key=lambda row:order[row['trial_id']])
    return rows,states,usage
