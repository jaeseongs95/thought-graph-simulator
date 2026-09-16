"""생산 채점. 새 응답의 ID·부모·원자·오류를 정답으로 변환하지 않는다."""
from collections import Counter
import bridge088
import core088 as core
import design088 as design
import report086 as decoder
import rows087 as legacy_rows
import measure

BAD={'invalid_json','invalid_schema','lookup_null','skipped_invalid_comparison_output'}

def monitor_plan(plan):
    ts=[t for t in plan['trials'] if t['phase']=='end_to_end'];ids={t['id']for t in ts}
    s=dict(plan['protocol'],factors={'baseline':[False,False],'allocated_id':[False,True]})
    return dict(plan,protocol=s,trials=ts,slots=[o for o in plan['slots'] if o['trial_id']in ids])

def main_rows(plan,records,responses):
    s=plan['protocol'];rows,status,usage=legacy_rows.main_rows(monitor_plan(plan),records,responses)
    objects={}
    for o in plan['slots']:
        sid=o['id'];st,obj,u=decoder.parse_response(records.get(sid),responses.get(sid,b''),s,o['stage'],'two_stage_values')
        status[sid]=st;objects[sid]=obj
        if records.get(sid,{}).get('kind')=='call':usage[sid]=u
    for t in plan['trials']:
        if t['phase']=='end_to_end':continue
        basic={k:t[k] for k in ('unit_id','problem_id','seed','phase','generator_arm','condition')};basic['trial_id']=t['id']
        p=next(p for p in s['problems'] if p['id']==t['problem_id'])
        own=[o for o in plan['slots'] if o['trial_id']==t['id']]
        if t['phase']=='rename_probe':
            o=own[0];sid=o['id'];a=design.anchor_for(t)
            d=design.data_from(design.request_for(plan,o,responses));before=design.history_nodes(d['history'])
            detail=None;sem=None
            if status[sid]=='ok':detail=legacy_rows.rule_check(p,before,objects[sid]['node'],a['rule_id']);sem=detail['valid']
            elif status[sid] in BAD:sem=False
            rows.append(dict(basic,anchor_id=a['id'],rule_id=a['rule_id'],rule_position=a['rule_position'],response_status=status[sid],
                probe_success=sem,node_semantic_success=sem,rule_check=detail,
                prior_node_count=len(before),prior_atom_aliases=sum(n['id']==n['atom'] for n in before),
                features=legacy_rows.features(p,d['provided_route_plan']['rule_ids'],a['rule_id'])))
            continue
        history,expected_ids,mapping=design.continuation_seed(t);before=design.history_nodes(history)
        prefix_count=len(before);checks=[];allready=True;prefix_valid=True;final=None;flags=[]
        for o in own:
            sid=o['id'];stage=o['stage'];entry=dict(id=sid,stage=stage,status=status[sid],prefix_valid_before=prefix_valid,
                valid=None,error_codes=None,support_contract_success=None)
            if status[sid]!='ok':
                allready=False;prefix_valid=False;checks.append(entry);continue
            obj=objects[sid]
            if stage=='rule':
                detail=legacy_rows.rule_check(p,before,obj['node'],t['route_rule_ids'][o['rule_position']]);entry.update(detail)
                entry['support_contract_success']=obj['node']['id']==expected_ids[o['rule_position']];flags.append(entry['support_contract_success'])
                prefix_valid=prefix_valid and detail['valid'] and entry['support_contract_success'];before.append(obj['node'])
            else:
                final=obj['final_node_id'];matches=[n for n in before if n['id']==final];errs=[]
                if len(matches)!=1:errs.append('missing_or_ambiguous_final')
                elif matches[0]['atom']!=p['goal']:errs.append('wrong_goal')
                entry.update(valid=not errs,error_codes=errs,support_contract_success=True)
            checks.append(entry)
        graph=dict(nodes=before,final_node_id=final) if allready else None
        gr=measure.assess(p,graph) if graph is not None else None
        profile=s['frozen_profiles'][p['id']][int(t['condition']=='deep')]
        depth=gr['actual_D'] if gr else None;w=sum(n['rule'] is not None for n in before) if gr and gr['strict_valid'] else None
        semantic=contract=None
        if gr is not None:
            semantic=bool(gr['strict_valid'] and all(c['valid'] is True for c in checks) and
                [n['rule']for n in before[prefix_count:]]==t['route_rule_ids'] and depth==profile['goal_depth'] and w==profile['rule_count'])
            contract=all(flags)
        elif any(status[o['id']] in BAD for o in own):semantic=False
        success=None if semantic is None else bool(semantic and contract is True)
        rows.append(dict(basic,anchor_id=t['anchor_id'],pair_id=t['pair_id'],base_pair_id=t['base_pair_id'],
            target_D=profile['goal_depth'],actual_D=depth,actual_W=w,generator_semantic_success=semantic,support_contract_success=contract,
            continuation_success=success,graph_result=gr,step_checks=checks,observed_prefix_nodes=prefix_count,
            newly_generated_rules=sum(status[o['id']]=='ok' for o in own if o['stage']=='rule'),
            source_scope='old_valid_facts_plus_new_raw_rules;not_end_to_end',allocated_ids=expected_ids))
    order={t['id']:i for i,t in enumerate(plan['trials'])};rows.sort(key=lambda r:order[r['trial_id']])
    return rows,status,usage
