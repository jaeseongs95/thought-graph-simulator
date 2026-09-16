"""새 선택·새 facts부터 시작하는 네 생성군. 출력 이력은 절대 재명명하지 않는다."""
from __future__ import annotations
from copy import deepcopy
import core090 as core
import bridge090
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
        slots.append(dict(id=sid, trial_id=t['id'], logical_id=t['unit_id']+'_'+suffix,
                          stage=stage, rule_position=pos))
        actions.append(dict(kind='slot', id=sid))
    for block in range(len(s['problems']) * len(s['seeds'])):
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
            shift = (block + index) % len(ARMS)
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
        raise ValueError('v090 동결 배정 불일치: ' + repr(observed))
    return trials, slots, actions


def disposition(plan, slot, responses):
    return frozen.disposition(plan, slot, responses)


def request_for(plan, slot, responses):
    body = frozen.request_for(plan, slot, responses)
    t = trial_for(plan, slot)
    arm, stage = t['generator_arm'], slot['stage']
    if arm == 'baseline' or stage in ('compare', 'select', 'final'):
        return body
    s = plan['protocol']
    data = data_from(body)
    schema = deepcopy(body['format'])
    header = s['headers']['generator'] + '\n\n' + s['headers'][stage]
    if stage == 'facts':
        allocation = fact_allocation(data['problem'], arm)
        data['allocated_fact_ids'] = allocation
        # 원자/부모/규칙은 기존 자유도 유지. ID의 허용 값만 지원한다.
        schema['properties']['nodes']['items']['properties']['id']['enum'] = [x['id'] for x in allocation]
        header += '\n' + s['facts_id_header']
    elif stage == 'rule':
        allocation = rule_allocation(data['problem'], data['operation']['requested_rule'],
                                     slot['rule_position'], arm)
        data['allocated_node_id'] = allocation
        schema['properties']['node']['properties']['id'] = dict(type='string', enum=[allocation])
        header += '\n' + s['allocated_id_header']
    else:
        raise ValueError('지원하지 않는 생성 단계')
    body['format'] = schema
    body['messages'] = [dict(role='user', content=header + SEPARATOR + core.wire(schema).decode()
                            + '\n\ninput: ' + core.wire(data).decode())]
    if len(core.wire(body)) > s['request_utf8_byte_limit']:
        raise ValueError('요청 바이트 상한 초과: 잘라내거나 보정하지 않는다')
    return body


def make_plan(baseline_path, run_name, provenance='live', audit_previous=True):
    if provenance not in ('live', 'synthetic'):
        raise ValueError('출처 구분 오류')
    from baseline090 import validate_inputs
    from audit090 import validate_protocol
    validate_inputs(baseline_path, run_verifier=audit_previous)
    s = core.spec()
    validate_protocol(s)
    trials, slots, actions = schedule(s)
    plan = dict(contract='v090-plan-r1', run_name=core.check_run_name(run_name), provenance=provenance,
        protocol=s, protocol_sha256=core.sha((core.ROOT/'data/protocol.json').read_bytes()),
        baseline_sha256=s['baseline_sha256'], source_hashes=core.source_hashes(),
        trials=trials, slots=slots, actions=actions)
    plan['plan_sha256'] = core.sha(core.wire(plan))
    return plan
