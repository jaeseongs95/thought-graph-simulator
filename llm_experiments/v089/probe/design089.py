"""초기 ID × 후속 ID의 완전 교차와 변경 없는 기존 D 종단 모니터."""
from __future__ import annotations
from copy import deepcopy
from functools import lru_cache
import core089 as core
import bridge089
import design086 as frozen

SEPARATOR = '\nJSON 객체 하나만 출력한다. 출력 형식(JSON Schema):\n'
STYLES = ('atom_alias', 'short', 'long', 'atom_tagged')

@lru_cache(maxsize=1)
def anchors():
    return core.load((core.ROOT/'data/anchors.json').read_bytes())

def anchor_for(t):
    return next(a for a in anchors() if a['id'] == t['anchor_id'])

def trial_for(plan, slot):
    return next(t for t in plan['trials'] if t['id'] == slot['trial_id'])

def data_from(body):
    return core.load(body['messages'][0]['content'].split('\n\ninput: ', 1)[1])

def history_nodes(history):
    nodes = []
    for record in history:
        x = core.load(record['content'])
        nodes.extend(x['nodes'] if 'nodes' in x else [x['node']])
    return nodes

def initial_name(node, position, style):
    if style == 'atom_alias':
        return node['atom']
    if style == 'atom_tagged':
        return 'node_' + node['atom']
    if style == 'short':
        return f'n{position:04d}'
    if style == 'long':
        return f'v087_node_{position:04d}'
    raise ValueError('지원하지 않는 ID 방식: ' + style)

def rename_initial(history, style):
    """지원받은 초기 facts만 변환한다. 새 응답은 이 함수 입력이 될 수 없다."""
    if len(history) != 1:
        raise ValueError('초기 facts 하나 이외의 history 재명명 금지')
    payload = core.load(history[0]['content'])
    if set(payload) != {'nodes'} or any(n['rule'] is not None or n['parents'] for n in payload['nodes']):
        raise ValueError('초기 사실이 아닌 이력 재명명 금지')
    nodes = payload['nodes']
    old = [n['id'] for n in nodes]
    new = [initial_name(n, i, style) for i, n in enumerate(nodes, 1)]
    if len(set(old)) != len(old) or len(set(new)) != len(new):
        raise ValueError('비전단사 초기 재명명')
    mapping = dict(zip(old, new))
    for node in nodes:
        node['id'] = mapping[node['id']]
    return [dict(history[0], content=core.wire(payload).decode())], mapping

def continuation_seed(t):
    """출력 sequence는 모든 초기형의 ID 합집합을 기준으로 한 번 정한다."""
    data = data_from(anchor_for(t)['request_body'])
    original = data['history']
    all_histories = {style: rename_initial(original, style) for style in STYLES}
    used = {n['id'] for history, _ in all_histories.values() for n in history_nodes(history)}
    rules = {r['id']: r for r in data['problem']['rules']}
    ids = []
    counter = len(history_nodes(original)) + 1
    style = t['output_id_style']
    for rid in t['route_rule_ids']:
        atom = rules[rid]['conclusion']
        if style in ('atom_alias', 'atom_tagged'):
            new = atom if style == 'atom_alias' else 'node_' + atom
            if new in used:
                raise ValueError('alias/tagged ID 충돌: 재명명 보정하지 않고 설계 거부')
        else:
            prefix = 'n' if style == 'short' else 'v087_node_'
            new = prefix + f'{counter:04d}'
            while new in used:
                counter += 1
                new = prefix + f'{counter:04d}'
            counter += 1
        ids.append(new)
        used.add(new)
    history, mapping = all_histories[t['initial_id_style']]
    return history, ids, mapping

def schedule(s):
    trials, slots, actions = [], [], []
    def add(t, stage, pos=None, physical=None):
        tail = f'rule_{pos:02d}' if stage == 'rule' else stage
        slot = dict(id=physical or t['id']+'_'+tail, trial_id=t['id'],
                    logical_id=t['unit_id']+'_'+tail, stage=stage, rule_position=pos)
        slots.append(slot)
        actions.append(dict(kind='slot', id=slot['id']))
    for block in range(len(s['problems'])*len(s['seeds'])):
        pi, si = divmod(block, len(s['seeds']))
        problem = s['problems'][pi]
        actions.append(dict(kind='metadata', id=f'b{block:02d}_before'))
        for kind in ('shallow', 'deep'):
            path = s['reference_plans'][problem['id']][s['reference_conditions'][int(kind == 'deep')]]
            arms = s['continuation_arms']
            shift = (block + 8*int(kind == 'deep')) % len(arms)
            for arm in arms[shift:]+arms[:shift]:
                initial, output = arm.split('__')
                uid = f'x{pi:02d}s{si}_{kind}'
                t = dict(id=uid+'_'+arm, unit_id=uid, phase='continuation', generator_arm=arm,
                    initial_id_style=initial, output_id_style=output,
                    anchor_id=problem['id']+'_'+kind+'_r00', problem_id=problem['id'],
                    seed=s['seeds'][si], block=block, condition=kind, metric='D',
                    selector_variant='two_stage_values', variant='explicit_rule',
                    selection_slot_id=None, comparison_slot_id=None,
                    pair_id=f'x{pi:02d}s{si}_'+arm, base_pair_id=f'x{pi:02d}s{si}', route_rule_ids=path)
                trials.append(t)
                for pos in range(len(path)):
                    add(t, 'rule', pos)
                add(t, 'final')
        # 기존 baseline의 physical/logical slot ID까지 보존해 원문 회귀가 가능하다.
        for u in (u for u in s['units'] if u['block'] == block):
            arm = 'baseline'
            t = dict(u, id=u['unit_id']+'_'+arm, phase='end_to_end', generator_arm=arm,
                selector_variant='two_stage_values', variant='explicit_rule', metric='D',
                arm='model', generate=True,
                selection_slot_id=u['unit_id']+'_two_stage_values_select',
                comparison_slot_id=u['unit_id']+'_two_stage_values_compare',
                pair_id=u['base_pair_id']+'_'+arm, control_candidate_id=None)
            trials.append(t)
            add(t, 'compare', physical=t['comparison_slot_id'])
            add(t, 'select', physical=t['selection_slot_id'])
            add(t, 'facts')
            for pos in range(max(map(len, s['reference_plans'][problem['id']].values()))):
                add(t, 'rule', pos)
            add(t, 'final')
        actions.append(dict(kind='metadata', id=f'b{block:02d}_after'))
    if (len(trials), len(slots), len(actions)) != (640, 3856, 3888):
        raise ValueError('동결 배정 수 불일치: ' + str((len(trials), len(slots), len(actions))))
    if len({o['id'] for o in slots}) != len(slots):
        raise ValueError('중복 slot')
    return trials, slots, actions

def render_body(template, data, header, schema, seed):
    body = deepcopy(template)
    body['options']['seed'] = seed
    body['format'] = deepcopy(schema)
    body['messages'] = [dict(role='user', content=header+SEPARATOR+core.wire(schema).decode()
                            +'\n\ninput: '+core.wire(data).decode())]
    return body

def disposition(plan, slot, responses):
    if trial_for(plan, slot)['phase'] == 'end_to_end':
        return frozen.disposition(plan, slot, responses)
    return None

def request_for(plan, slot, responses):
    t = trial_for(plan, slot)
    s = plan['protocol']
    if t['phase'] == 'end_to_end':
        body = frozen.request_for(plan, slot, responses)
    else:
        anchor = anchor_for(t)
        data = data_from(anchor['request_body'])
        history, ids, _ = continuation_seed(t)
        for prior in plan['slots']:
            if prior['id'] == slot['id']:
                break
            if prior['trial_id'] == t['id'] and prior['id'] in responses:
                history.append(dict(source_slot_id=prior['logical_id'],
                                    content=frozen.legacy.raw_content(responses[prior['id']])))
        data['history'] = history
        path = t['route_rule_ids']
        if slot['stage'] == 'rule':
            pos = slot['rule_position']
            rid = path[pos]
            data['operation'] = dict(stage='rule', index=pos+1, requested_rule_id=rid,
                requested_rule=deepcopy(next(r for r in data['problem']['rules'] if r['id'] == rid)))
            data['allocated_node_id'] = ids[pos]
            schema = deepcopy(anchor['request_body']['format'])
            schema['properties']['node']['properties']['id'] = {'type': 'string', 'enum': [ids[pos]]}
            header = s['headers']['generator']+'\n\n'+s['headers']['rule']+'\n'+s['allocated_id_header']
        else:
            data['operation'] = dict(stage='final', index=len(path)+1, requested_rule_id=None)
            schema = dict(type='object', properties={'final_node_id':deepcopy(s['generation_schema']['properties']['final_node_id'])},
                          required=['final_node_id'], additionalProperties=False)
            header = s['headers']['generator']+'\n\n'+s['headers']['final']
        body = render_body(anchor['request_body'], data, header, schema, t['seed'])
    if len(core.wire(body)) > s['request_utf8_byte_limit']:
        raise ValueError('요청 바이트 상한 초과: 절단하지 않음')
    return body

def make_plan(baseline_path, run_name, provenance='live', audit_previous=True):
    if provenance not in ('live', 'synthetic'):
        raise ValueError('출처 구분 오류')
    from baseline089 import validate_inputs
    from audit089 import validate_protocol
    validate_inputs(baseline_path, run_verifier=audit_previous)
    s = core.spec()
    validate_protocol(s)
    ts, ss, aa = schedule(s)
    plan = dict(contract='v089-plan-r1', run_name=core.check_run_name(run_name), provenance=provenance,
        protocol=s, protocol_sha256=core.sha((core.ROOT/'data/protocol.json').read_bytes()),
        baseline_sha256=s['baseline_sha256'], source_hashes=core.source_hashes(),
        trials=ts, slots=ss, actions=aa)
    plan['plan_sha256'] = core.sha(core.wire(plan))
    return plan
