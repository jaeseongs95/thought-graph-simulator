"""생산 design091을 사용하지 않는 배정·요청·지원 계약 독립 재구성."""
from pathlib import Path
from copy import deepcopy
from audit_bytes091 import load, dump, digest, need, same
import bridge091
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
        ss.append({'id':sid,'trial_id':t['id'],'logical_id':t['input_unit_id']+'_'+suffix,
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
                t = candidates[(block+unit_index//3+k) % 4]
                ts.append(t)
                emit(t,'facts')
                maximum = max(len(path) for path in s['reference_plans'][u['problem_id']].values())
                for i in range(maximum):
                    emit(t,'rule',i)
                emit(t,'final')
            unit_index += 1
        aa.append(dict(kind='metadata',id='b%02d_after' % block))
    return ts, ss, aa


def expected_request(plan,slot,raws):
    # 생산 render_view를 import하지 않고 같은 감사/모델 입력 경계를 별도로 구성.
    from audit090 import expected_request as frozen_request
    trial=next(v for v in plan['trials'] if v['id']==slot['trial_id'])
    t=deepcopy(trial);source=t['problem_id'];shown=t['render_problem_id'];t['unit_id']=t['input_unit_id'];t['problem_id']=shown
    protocol=dict(plan['protocol'])
    problem=deepcopy(next(v for v in protocol['problems'] if v['id']==source));problem['id']=shown
    protocol['problems']=[problem]
    for key in ('reference_plans','frozen_profiles','depth_ranges'):
        protocol[key]={shown:plan['protocol'][key][source]}
    return frozen_request(dict(plan,protocol=protocol,trials=[t]),slot,raws)


def validate_protocol(s):
    # 독립 판정기는 생산 baseline 모듈을 import하지 않는다.
    CONTRACT_KEYS=('identity','model','seeds','conditions','reference_conditions','candidate_orders','candidate_ids','headers',
        'selector_schema','api_defaults','generation_schema','num_predict','request_utf8_byte_limit','timeout_seconds','id_assignments',
        'numeric_compare_schema','lookup_schema','numeric_compare_header','lookup_header','allocated_id_header','allocated_id_prefix',
        'facts_id_header','generator_arms','styles')
    from audit_corpus091 import validate as validate_corpus
    prior=load((ROOT/'data/protocol_v090_snapshot.json').read_bytes())
    corpus_raw=(ROOT/'data/corpus.json').read_bytes();corpus=load(corpus_raw)
    need(digest(corpus_raw)==s['corpus_sha256'],'corpus hash')
    for key in CONTRACT_KEYS:need(same(prior[key],s[key]),'inherited renderer/support contract changed: '+key)
    for key in ('problems','reference_plans','frozen_profiles','depth_ranges','units'):
        need(same(corpus[key],s[key]),'corpus/protocol mismatch: '+key)
    need(s['contract']=='v091-frozen-generator-topology-renaming-r1','contract')
    need(s['generator_arms']==ARM_NAMES,'arms')
    need(s['primary_comparison']==['baseline','atom_alias'] and s['primary_cohort']=='new_topology','primary')
    need(s['secondary_comparisons']==[['baseline','atom_tagged'],['baseline','short_uniform'],['short_uniform','atom_alias'],['short_uniform','atom_tagged'],['atom_alias','atom_tagged']],'secondary')
    need(s['cohorts']==['known_original','known_renamed','new_topology'],'cohort split')
    need((s['trial_count'],s['max_inference_calls'],s['max_action_slots'],s['expected_inference_calls_if_all_target_routes_selected'],s['minimum_inference_calls_if_mappable'])==(1536,10944,10976,10560,10176),'frozen allocation')
    need(s['baseline_sha256']=='8618917543a25bf72ec09827a2e29f1b23687bc6342a8e3fa4346869899b3d37','baseline hash')
    need(s['baseline_plan_sha256']=='c70fe47fa5e9c8fef773d15c61816491c9ed1bb3e7e98ac4b260f55ee0be4b95','baseline plan')
    need(s['holdout'] is True and s['new_independent_structures']==8 and s['distinct_structures']==16 and s['represented_problems']==24,'new versus renamed structures')
    need(s['selector_shared_across_arms'] is True and s['preserved_frozen_source_files']==178,'source/selector')
    for key in ('automatic_retry','automatic_download','automatic_server_start','posthoc_repair','raw_output_repair','iid_structure_sampling','old_output_reuse'):
        need(s[key] is False,'safety flag: '+key)
    validate_corpus(corpus,prior)
    ts,ss,aa=reconstruct_schedule(s)
    need((len(ts),len(ss),len(aa))==(1536,10944,10976),'independent schedule totals')
    need(len({x['id'] for x in ss})==len(ss) and len({x['id'] for x in ts})==len(ts),'duplicate physical id')
    for stage,n in [('facts',1536),('compare',384),('select',384)]:
        need(sum(x['stage']==stage for x in ss)==n,'stage count '+stage)


def independent_summary(plan,records,raws,state):
    from audit_rows091 import independent_rows
    from tables091 import aggregate
    rows,states,usage = independent_rows(plan,records,raws)
    summary = aggregate(plan,rows,states,usage,state)
    from audit_metrics091 import check_aggregate
    check_aggregate(plan,rows,summary,state)
    return summary
