"""생산 설계 함수를 import하지 않는 교차 배정·ID 변환·요청 바이트 검산."""
from pathlib import Path
from functools import lru_cache
from copy import deepcopy
import bridge089
from audit_bytes089 import load, dump, digest, need, same
import audit086 as frozen
import audit087 as previous
ROOT = Path(__file__).resolve().parent
SEP = '\nJSON 객체 하나만 출력한다. 출력 형식(JSON Schema):\n'
STYLES = ('atom_alias', 'short', 'long', 'atom_tagged')

@lru_cache(maxsize=1)
def anchor_list():
    return load((ROOT/'data/anchors.json').read_bytes())

def get_anchor(t):
    return next(a for a in anchor_list() if a['id'] == t['anchor_id'])

def data(body):
    return load(body['messages'][0]['content'].split('\n\ninput: ', 1)[1])

def renamed_initial(history, style):
    need(len(history) == 1, 'only initial facts may be renamed')
    obj = load(history[0]['content'])
    need(set(obj) == {'nodes'}, 'initial payload')
    table = {}
    for number, n in enumerate(obj['nodes'], 1):
        need(n['rule'] is None and n['parents'] == [], 'not a fact')
        if style == 'atom_alias':
            name = n['atom']
        elif style == 'atom_tagged':
            name = 'node_' + n['atom']
        elif style == 'short':
            name = 'n%04d' % number
        elif style == 'long':
            name = 'v087_node_%04d' % number
        else:
            raise ValueError('unrecognized style')
        need(n['id'] not in table, 'duplicate original ID')
        table[n['id']] = name
    need(len(set(table.values())) == len(table), 'not injective')
    for n in obj['nodes']:
        n['id'] = table[n['id']]
    return [dict(history[0], content=dump(obj).decode())], table

def continuing(t):
    d = data(get_anchor(t)['request_body'])
    originals = d['history']
    versions = [renamed_initial(originals, style) for style in STYLES]
    blocked = set()
    for history, _ in versions:
        blocked.update(n['id'] for n in load(history[0]['content'])['nodes'])
    next_number = len(load(originals[0]['content'])['nodes'])
    allocation = []
    for rule_id in t['route_rule_ids']:
        rule = next(r for r in d['problem']['rules'] if r['id'] == rule_id)
        style = t['output_id_style']
        if style in ('atom_alias', 'atom_tagged'):
            candidate = rule['conclusion'] if style == 'atom_alias' else 'node_'+rule['conclusion']
            need(candidate not in blocked, 'semantic ID collision')
        else:
            while True:
                next_number += 1
                candidate = ('n' if style == 'short' else 'v087_node_') + ('%04d' % next_number)
                if candidate not in blocked:
                    break
        allocation.append(candidate)
        blocked.add(candidate)
    hs, mapping = versions[STYLES.index(t['initial_id_style'])]
    return hs, allocation, mapping

def reconstruct_schedule(s):
    trials, slots, actions = [], [], []
    def emit(t, stage, position=None, physical=None):
        suffix = ('rule_%02d' % position) if stage == 'rule' else stage
        sid = physical or t['id']+'_'+suffix
        slots.append(dict(id=sid, trial_id=t['id'], logical_id=t['unit_id']+'_'+suffix,
                          stage=stage, rule_position=position))
        actions.append(dict(kind='slot', id=sid))
    for block in range(16):
        problem_index, seed_index = divmod(block, 2)
        p = s['problems'][problem_index]
        actions.append(dict(kind='metadata', id='b%02d_before' % block))
        for deep, kind in enumerate(('shallow', 'deep')):
            route = s['reference_plans'][p['id']][s['reference_conditions'][deep]]
            for offset in range(16):
                index = (block+8*deep+offset) % 16
                first, later = STYLES[index//4], STYLES[index%4]
                arm = first+'__'+later
                uid = 'x%02ds%d_%s' % (problem_index, seed_index, kind)
                t = dict(id=uid+'_'+arm, unit_id=uid, phase='continuation', generator_arm=arm,
                    initial_id_style=first, output_id_style=later,
                    anchor_id=p['id']+'_'+kind+'_r00', problem_id=p['id'], seed=s['seeds'][seed_index],
                    block=block, condition=kind, metric='D', selector_variant='two_stage_values',
                    variant='explicit_rule', selection_slot_id=None, comparison_slot_id=None,
                    pair_id='x%02ds%d_%s' % (problem_index, seed_index, arm),
                    base_pair_id='x%02ds%d' % (problem_index, seed_index), route_rule_ids=route)
                trials.append(t)
                for pos in range(len(route)):
                    emit(t, 'rule', pos)
                emit(t, 'final')
        for u in s['units']:
            if u['block'] != block:
                continue
            t = deepcopy(u)
            t.update(id=u['unit_id']+'_baseline', phase='end_to_end', generator_arm='baseline',
                selector_variant='two_stage_values', variant='explicit_rule', metric='D', arm='model', generate=True,
                selection_slot_id=u['unit_id']+'_two_stage_values_select',
                comparison_slot_id=u['unit_id']+'_two_stage_values_compare',
                pair_id=u['base_pair_id']+'_baseline', control_candidate_id=None)
            trials.append(t)
            emit(t, 'compare', physical=t['comparison_slot_id'])
            emit(t, 'select', physical=t['selection_slot_id'])
            emit(t, 'facts')
            for pos in range(max(len(route) for route in s['reference_plans'][p['id']].values())):
                emit(t, 'rule', pos)
            emit(t, 'final')
        actions.append(dict(kind='metadata', id='b%02d_after' % block))
    return trials, slots, actions

def expected_request(plan, slot, raws):
    t = next(t for t in plan['trials'] if t['id'] == slot['trial_id'])
    if t['phase'] == 'end_to_end':
        return previous.expected_request(plan, slot, raws)
    s = plan['protocol']
    anchor = get_anchor(t)
    body = deepcopy(anchor['request_body'])
    payload = data(body)
    history, allocated, _ = continuing(t)
    for old in plan['slots']:
        if old['id'] == slot['id']:
            break
        if old['trial_id'] == t['id'] and old['id'] in raws:
            history.append(dict(source_slot_id=old['logical_id'], content=frozen.prior.content(raws[old['id']])))
    payload['history'] = history
    path = t['route_rule_ids']
    if slot['stage'] == 'rule':
        pos = slot['rule_position']
        rid = path[pos]
        rule = next(r for r in payload['problem']['rules'] if r['id'] == rid)
        payload['operation'] = dict(stage='rule', index=pos+1, requested_rule_id=rid, requested_rule=deepcopy(rule))
        payload['allocated_node_id'] = allocated[pos]
        shape = deepcopy(anchor['request_body']['format'])
        shape['properties']['node']['properties']['id'] = dict(type='string', enum=[allocated[pos]])
        header = s['headers']['generator']+'\n\n'+s['headers']['rule']+'\n'+s['allocated_id_header']
    else:
        payload['operation'] = dict(stage='final', index=len(path)+1, requested_rule_id=None)
        shape = dict(type='object', properties={'final_node_id':deepcopy(s['generation_schema']['properties']['final_node_id'])},
                     required=['final_node_id'], additionalProperties=False)
        header = s['headers']['generator']+'\n\n'+s['headers']['final']
    body['options']['seed'] = t['seed']
    body['format'] = shape
    body['messages'] = [dict(role='user', content=header+SEP+dump(shape).decode()+'\n\ninput: '+dump(payload).decode())]
    raw = dump(body)
    need(len(raw) <= s['request_utf8_byte_limit'], 'request size')
    return None, raw

def validate_protocol(s):
    prior = load((ROOT/'data/protocol_v088_snapshot.json').read_bytes())
    preserved = ('identity','model','problems','reference_plans','depth_ranges','seeds','conditions',
        'reference_conditions','candidate_orders','candidate_ids','headers','selector_schema','api_defaults',
        'generation_schema','num_predict','request_utf8_byte_limit','timeout_seconds','id_assignments',
        'frozen_profiles','numeric_compare_schema','lookup_schema','numeric_compare_header','lookup_header',
        'allocated_id_header','allocated_id_prefix','units')
    for key in preserved:
        need(same(prior[key], s[key]), 'v088 inherited contract drift: '+key)
    need(s['contract'] == 'v089-id-transition-factorial-r1', 'v089 contract')
    need(s['initial_id_styles'] == list(STYLES) == s['output_id_styles'], '4x4 styles')
    need(s['continuation_arms'] == [i+'__'+j for i in STYLES for j in STYLES], 'full crossing')
    need(s['monitor_arms'] == ['baseline'] and s['probe_arms'] == [], 'baseline only; no local probes')
    need(s['primary_components'] == [['atom_alias__short','short__short'],['atom_alias__long','long__long']], 'primary definition')
    need((s['trial_count'], s['max_inference_calls'], s['max_action_slots'],
          s['expected_inference_calls_if_all_target_routes_selected']) == (640,3856,3888,3824), 'frozen counts')
    need(s['minimum_inference_calls_if_mappable'] == 3792, 'minimum mapped calls')
    need(not any(s[k] for k in ('automatic_retry','automatic_download','automatic_server_start','posthoc_repair','raw_output_repair','holdout','iid_structure_sampling')), 'scope/safety flags')
    need(s['new_independent_structures'] == 0 and s['distinct_structures'] == 8, 'diagnostic structures')
    need(s['baseline_sha256'] == '2d9c2324aa9a9a64d97beb74cc158b24f1e7cf4f59df599a4a154ff110fcfbff', 'baseline SHA')
    need(s['baseline_plan_sha256'] == 'f2b6959359274f2cc98bd78a60bbc2d8f856dc428300172d077d805793267314', 'prior plan')
    aa = anchor_list()
    need(len(aa) == 16 and [a['id'] for a in aa] == s['anchor_ids'], 'anchor set')
    need(digest((ROOT/'data/anchors.json').read_bytes()) == s['anchors_sha256'], 'anchor SHA')
    for anchor in aa:
        p = next(p for p in s['problems'] if p['id'] == anchor['problem_id'])
        payload = data(anchor['request_body'])
        path = s['reference_plans'][p['id']][s['reference_conditions'][int(anchor['route_kind']=='deep')]]
        need(same(payload['problem'], p) and payload['provided_route_plan']['rule_ids'] == path, 'anchor task')
        need(anchor['rule_position'] == 0 and anchor['rule_id'] == path[0], 'initial anchor position')
        need(digest(dump(anchor['request_body'])) == anchor['source_request_sha256'], 'anchor request SHA')
        for style in STYLES:
            hs, _ = renamed_initial(payload['history'], style)
            nodes = load(hs[0]['content'])['nodes']
            need(sorted(n['atom'] for n in nodes) == sorted(p['facts']), 'initial fact multiset')
        atoms = list(p['facts'])
        for rid in path:
            rule = next(r for r in p['rules'] if r['id'] == rid)
            need(all(a in atoms for a in rule['premises']), 'invalid route premise')
            need(rule['conclusion'] not in atoms, 'nonunique atom: semantic IDs not injective')
            atoms.append(rule['conclusion'])
    ts, ops, actions = reconstruct_schedule(s)
    need((len(ts),len(ops),len(actions)) == (640,3856,3888), 'independent schedule count')
    for t in ts:
        if t['phase'] == 'continuation':
            continuing(t)

def independent_summary(plan, records, raws, state):
    from audit_rows089 import independent_rows
    from tables089 import aggregate
    rows, statuses, usage = independent_rows(plan, records, raws)
    return aggregate(plan, rows, statuses, usage, state)
