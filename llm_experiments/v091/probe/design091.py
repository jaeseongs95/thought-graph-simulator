"""새 선택·새 facts부터 시작하는 네 생성군. 출력 이력은 절대 재명명하지 않는다."""
from __future__ import annotations
from copy import deepcopy
import core091 as core
import bridge091
import design086 as frozen

SEPARATOR = '\nJSON 객체 하나만 출력한다. 출력 형식(JSON Schema):\n'
ARMS = ('baseline', 'short_uniform', 'atom_alias', 'atom_tagged')


def trial_for(plan, slot):
    return next(t for t in plan['trials'] if t['id'] == slot['trial_id'])


def data_from(body):
    return core.load(body['messages'][0]['content'].split('\n\ninput: ', 1)[1])


def history_nodes(history):
    result = []
    for item in history:
        value = core.load(item['content'])
        result.extend(value['nodes'] if 'nodes' in value else [value['node']])
    return result


def node_name(atom, number, arm):
    if arm == 'atom_alias':
        return atom
    if arm == 'atom_tagged':
        return 'node_' + atom
    if arm == 'short_uniform':
        return f'n{number:04d}'
    raise ValueError('ID를 지정하지 않는 군 또는 알 수 없는 군: ' + arm)


def fact_allocation(problem, arm):
    """이미 입력에 공개된 facts에 대한 ID만 지정. 출력 facts를 대신 만들지 않는다."""
    return [dict(atom=atom, id=node_name(atom, i, arm))
            for i, atom in enumerate(problem['facts'], 1)]


def rule_allocation(problem, requested_rule, position, arm):
    """원응답을 읽어 ID 충돌을 회피하지 않는다. 오류로 인한 충돌은 채점 실패다."""
    return node_name(requested_rule['conclusion'], len(problem['facts']) + position + 1, arm)


def schedule(s):
    trials, slots, actions = [], [], []
    def add(t, stage, pos=None, physical=None):
        suffix = f'rule_{pos:02d}' if stage == 'rule' else stage
        sid = physical or t['id'] + '_' + suffix
        slots.append(dict(id=sid, trial_id=t['id'], logical_id=t['input_unit_id']+'_'+suffix,
                          stage=stage, rule_position=pos))
        actions.append(dict(kind='slot', id=sid))
    for block in range(max(u['block'] for u in s['units'])+1):
        actions.append(dict(kind='metadata', id=f'b{block:02d}_before'))
        units = [u for u in s['units'] if u['block'] == block]
        for index, unit in enumerate(units):
            group = {}
            for arm in ARMS:
                t = dict(unit, id=unit['unit_id']+'_'+arm, phase='end_to_end', generator_arm=arm,
                    selector_variant='two_stage_values', variant='explicit_rule', metric='D',
                    arm='model', generate=True,
                    selection_slot_id=unit['unit_id']+'_two_stage_values_select',
                    comparison_slot_id=unit['unit_id']+'_two_stage_values_compare',
                    pair_id=unit['base_pair_id']+'_'+arm, control_candidate_id=None)
                group[arm] = t
            # 선택 원문은 네 군이 공유하되 호출/표본은 한 번만 센다.
            baseline = group['baseline']
            add(baseline, 'compare', physical=baseline['comparison_slot_id'])
            add(baseline, 'select', physical=baseline['selection_slot_id'])
            shift = (block + index // 3) % len(ARMS)
            ordered = ARMS[shift:] + ARMS[:shift]
            for arm in ordered:
                t = group[arm]
                trials.append(t)
                add(t, 'facts')
                n = max(len(r) for r in s['reference_plans'][t['problem_id']].values())
                for pos in range(n):
                    add(t, 'rule', pos)
                add(t, 'final')
        actions.append(dict(kind='metadata', id=f'b{block:02d}_after'))
    observed = (len(trials), len(slots), len(actions))
    expected = (s['trial_count'], s['max_inference_calls'], s['max_action_slots'])
    if observed != expected or len({o['id'] for o in slots}) != len(slots):
        raise ValueError('v091 동결 배정 불일치: ' + repr(observed))
    return trials, slots, actions


def disposition(plan, slot, responses):
    return frozen.disposition(plan, slot, responses)


def render_view(plan,slot):
    """감사 단위는 유일하게 유지하면서 원형/재명명 입력의 논리 표지는 맞춘다.

    응답 content는 수정하지 않는다. 이 view에는 현재 trial만 필요하며,
    과거 이력은 원 plan의 physical 슬롯에서 그대로 읽힌다.
    """
    t=trial_for(plan,slot);s=plan['protocol'];pid=t['problem_id'];shown=t['render_problem_id']
    p=next(p for p in s['problems'] if p['id']==pid)
    ps=dict(s,problems=[dict(p,id=shown)],
        reference_plans={shown:s['reference_plans'][pid]},
        frozen_profiles={shown:s['frozen_profiles'][pid]},depth_ranges={shown:s['depth_ranges'][pid]})
    return dict(plan,protocol=ps,trials=[dict(t,problem_id=shown,unit_id=t['input_unit_id'])])


def request_for(plan,slot,responses):
    import design090 as frozen_generator
    return frozen_generator.request_for(render_view(plan,slot),slot,responses)


def make_plan(baseline_path, run_name, provenance='live', audit_previous=True):
    if provenance not in ('live', 'synthetic'):
        raise ValueError('출처 구분 오류')
    from baseline091 import validate_inputs
    from audit091 import validate_protocol
    validate_inputs(baseline_path, run_verifier=audit_previous)
    s = core.spec()
    validate_protocol(s)
    trials, slots, actions = schedule(s)
    plan = dict(contract='v091-plan-r1', run_name=core.check_run_name(run_name), provenance=provenance,
        protocol=s, protocol_sha256=core.sha((core.ROOT/'data/protocol.json').read_bytes()),
        baseline_sha256=s['baseline_sha256'], source_hashes=core.source_hashes(),
        trials=trials, slots=slots, actions=actions)
    plan['plan_sha256'] = core.sha(core.wire(plan))
    return plan
