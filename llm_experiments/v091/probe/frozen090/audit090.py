"""생산 design090을 사용하지 않는 배정·요청·지원 계약 독립 재구성."""
from pathlib import Path
from copy import deepcopy
from audit_bytes090 import load, dump, digest, need, same
import bridge090
import audit086 as previous
ROOT = Path(__file__).resolve().parent
SEP = '\nJSON 객체 하나만 출력한다. 출력 형식(JSON Schema):\n'
ARM_NAMES = ['baseline','short_uniform','atom_alias','atom_tagged']


def name_for(atom, ordinal, arm):
    if arm == 'short_uniform':
        return 'n%04d' % ordinal
    if arm == 'atom_alias':
        return atom
    if arm == 'atom_tagged':
        return 'node_%s' % atom
    raise ValueError('unknown allocated ID arm')


def facts_table(problem, arm):
    return [{'atom': a, 'id': name_for(a, i+1, arm)} for i,a in enumerate(problem['facts'])]


def rule_id(problem, rule, index, arm):
    return name_for(rule['conclusion'], len(problem['facts'])+index+1, arm)


def reconstruct_schedule(s):
    ts, ss, aa = [], [], []
    def emit(t, stage, n=None, physical=None):
        suffix = 'rule_%02d' % n if stage == 'rule' else stage
        sid = physical if physical is not None else t['id']+'_'+suffix
        ss.append({'id':sid,'trial_id':t['id'],'logical_id':t['unit_id']+'_'+suffix,
                   'stage':stage,'rule_position':n})
        aa.append({'kind':'slot','id':sid})
    for block in range(16):
        aa.append(dict(kind='metadata',id='b%02d_before' % block))
        unit_index = 0
        for u in s['units']:
            if u['block'] != block:
                continue
            candidates = []
            for arm in ARM_NAMES:
                t = deepcopy(u)
                t.update(id=u['unit_id']+'_'+arm,phase='end_to_end',generator_arm=arm,
                    selector_variant='two_stage_values',variant='explicit_rule',metric='D',arm='model',generate=True,
                    selection_slot_id=u['unit_id']+'_two_stage_values_select',
                    comparison_slot_id=u['unit_id']+'_two_stage_values_compare',
                    pair_id=u['base_pair_id']+'_'+arm,control_candidate_id=None)
                candidates.append(t)
            emit(candidates[0],'compare',physical=candidates[0]['comparison_slot_id'])
            emit(candidates[0],'select',physical=candidates[0]['selection_slot_id'])
            for k in range(4):
                t = candidates[(block+unit_index+k) % 4]
                ts.append(t)
                emit(t,'facts')
                maximum = max(len(path) for path in s['reference_plans'][u['problem_id']].values())
                for i in range(maximum):
                    emit(t,'rule',i)
                emit(t,'final')
            unit_index += 1
        aa.append(dict(kind='metadata',id='b%02d_after' % block))
    return ts, ss, aa


def expected_request(plan, slot, raws):
    skip, raw = previous.expected_request(plan, slot, raws)
    if skip is not None:
        return skip, raw
    t = next(x for x in plan['trials'] if x['id'] == slot['trial_id'])
    arm, stage = t['generator_arm'], slot['stage']
    if arm == 'baseline' or stage in ('compare','select','final'):
        return None, raw
    s = plan['protocol']
    body = load(raw)
    payload = load(body['messages'][0]['content'].split('\n\ninput: ',1)[1])
    shape = deepcopy(body['format'])
    title = s['headers']['generator']+'\n\n'+s['headers'][stage]
    if stage == 'facts':
        table = facts_table(payload['problem'],arm)
        payload['allocated_fact_ids'] = table
        shape['properties']['nodes']['items']['properties']['id']['enum'] = [r['id'] for r in table]
        title += '\n'+s['facts_id_header']
    else:
        need(stage == 'rule','unexpected generation stage')
        allocated = rule_id(payload['problem'],payload['operation']['requested_rule'],slot['rule_position'],arm)
        payload['allocated_node_id'] = allocated
        shape['properties']['node']['properties']['id'] = {'type':'string','enum':[allocated]}
        title += '\n'+s['allocated_id_header']
    body['format'] = shape
    body['messages'] = [{'role':'user','content':title+SEP+dump(shape).decode()+'\n\ninput: '+dump(payload).decode()}]
    raw = dump(body)
    need(len(raw) <= s['request_utf8_byte_limit'],'request size')
    return None,raw


def validate_protocol(s):
    prior = load((ROOT/'data/protocol_v089_snapshot.json').read_bytes())
    inherited = ('identity','model','problems','reference_plans','depth_ranges','seeds','conditions',
        'reference_conditions','candidate_orders','candidate_ids','headers','selector_schema','api_defaults',
        'generation_schema','num_predict','request_utf8_byte_limit','timeout_seconds','id_assignments',
        'frozen_profiles','numeric_compare_schema','lookup_schema','numeric_compare_header','lookup_header',
        'allocated_id_header','allocated_id_prefix','units')
    for key in inherited:
        need(same(prior[key],s[key]),'inherited v089 contract changed: '+key)
    need(s['contract']=='v090-fresh-semantic-id-end-to-end-r1','contract')
    need(s['generator_arms']==ARM_NAMES,'arms')
    need(s['primary_comparison']==['baseline','atom_alias'],'primary')
    need(s['secondary_comparisons']==[['baseline','atom_tagged'],['baseline','short_uniform'],
        ['short_uniform','atom_alias'],['short_uniform','atom_tagged'],['atom_alias','atom_tagged']], 'secondary')
    need((s['trial_count'],s['max_inference_calls'],s['max_action_slots'],
        s['expected_inference_calls_if_all_target_routes_selected'],s['minimum_inference_calls_if_mappable']) ==
        (512,3648,3680,3520,3392),'call allocation')
    need(s['baseline_sha256']=='8ba60eda9670e1c7298b6f10cf6801875bd5f7c67f4f39cb23ee473b4600838b','baseline SHA')
    need(s['baseline_plan_sha256']=='3f81d7e8f8d0c7aad4389db01b416994022b1fa183b46f75a00c565174b63bb5','prior plan')
    need(s['distinct_structures']==8 and s['new_independent_structures']==0,'not a holdout')
    need(s['selector_shared_across_arms'] is True and s['preserved_frozen_source_files']==146,'shared selector/frozen source')
    for key in ('automatic_retry','automatic_download','automatic_server_start','posthoc_repair',
                'raw_output_repair','holdout','iid_structure_sampling','old_output_reuse'):
        need(s[key] is False,'scope/safety flag: '+key)
    # 같은 원자를 두 번 도출하는 문제에서는 semantic ID가 충돌할 수 있다.
    # 이 배정에서만 injectivity를 검사하고 다른 문제에 일반화하지 않는다.
    for p in s['problems']:
        for path in s['reference_plans'][p['id']].values():
            emitted = list(p['facts'])
            need(len(emitted)==len(set(emitted)),'duplicate facts atom')
            for rid in path:
                rule = next(r for r in p['rules'] if r['id']==rid)
                need(all(a in emitted for a in rule['premises']),'invalid fixed route')
                need(rule['conclusion'] not in emitted,'semantic ID noninjective route')
                emitted.append(rule['conclusion'])
            need(p['goal'] in emitted,'missing goal in fixed route')
    ts,ss,aa = reconstruct_schedule(s)
    need((len(ts),len(ss),len(aa))==(512,3648,3680),'independent schedule')
    need(len({x['id'] for x in ss})==len(ss),'duplicate slot')
    need(sum(x['stage']=='facts' for x in ss)==512,'fresh facts per trial')
    need(sum(x['stage']=='compare' for x in ss)==128,'comparison shared once')
    need(sum(x['stage']=='select' for x in ss)==128,'lookup shared once')


def independent_summary(plan,records,raws,state):
    from audit_rows090 import independent_rows
    from tables090 import aggregate
    rows,states,usage = independent_rows(plan,records,raws)
    summary = aggregate(plan,rows,states,usage,state)
    from audit_metrics090 import check_aggregate
    check_aggregate(plan,rows,summary,state)
    return summary
