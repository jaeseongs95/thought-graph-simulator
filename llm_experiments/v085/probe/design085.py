"""관측된 구조의 값 비교·후보 ID 연결 분리와 실제 D 종단 대조 계획. 사후 보정 없음."""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import bootstrap
import design as legacy
import core085 as core


def condition_entries(spec, pi, si):
    problem = spec['problems'][pi]
    entries = [('reference', si % 2, 0, 'D', 'shallow'),
               ('reference', si % 2, 0, 'D', 'deep')]
    for order in range(2):
        for labels in range(2):
            metrics = list(spec['metrics_by_problem'][problem['id']])
            if (pi + si + order + labels) % 2:
                metrics.reverse()
            for metric in metrics:
                directions = list(spec['conditions'])
                if (pi + si + order + labels + int(metric == 'W')) % 2:
                    directions.reverse()
                entries += [('model', order, labels, metric, d) for d in directions]
    return entries[::-1] if si % 2 else entries


def schedule(spec):
    """두 선택 계약을 교차하며 D 두 군만 증명을 생성한다."""
    trials, slots, actions = [], [], []
    unit = 0
    for pi, problem in enumerate(spec['problems']):
        for si, seed in enumerate(spec['seeds']):
            block = pi * len(spec['seeds']) + si
            actions.append({'kind': 'metadata', 'id': f'b{block:02d}_before'})
            for arm, order, labels, metric, condition in condition_entries(spec, pi, si):
                uid = f't{unit:03d}'
                unit += 1
                variants = list(spec['selector_variants']) if arm == 'model' else ['reference']
                if arm == 'model':
                    shift = (2*order + labels + si + pi + int(condition=='deep') + int(metric=='W')) % len(variants)
                    variants = variants[shift:] + variants[:shift]
                ids = [spec['candidate_ids'][j] for j in spec['id_assignments'][labels]]
                index = spec['candidate_orders'][order].index(int(condition == 'deep'))
                base_pair = f'p{pi}_s{si}_o{order}_l{labels}_{metric}' if arm == 'model' else None
                group = []
                for selector in variants:
                    suffix = '_explicit_rule' if selector in ('candidate_id','reference') else '_' + selector
                    tid = uid + suffix
                    selection = uid + ('_select' if selector=='candidate_id' else '_' + selector + '_select') if arm=='model' else None
                    generate = arm=='reference' or (selector in spec['generation_selector_variants'] and metric in spec['generation_metrics'])
                    t = {'id': tid, 'unit_id': uid, 'variant': 'explicit_rule', 'selector_variant': selector,
                         'selection_slot_id': selection, 'comparison_slot_id': uid+'_two_stage_values_compare' if selector=='two_stage_values' else None, 'block': block, 'arm': arm,
                         'problem_id': problem['id'], 'seed': seed, 'candidate_order_index': order,
                         'id_assignment_index': labels, 'metric': metric, 'condition': condition,
                         'pair_id': base_pair + '_' + selector if base_pair else None,
                         'base_pair_id': base_pair, 'generate': generate,
                         'control_candidate_id': ids[index] if arm=='reference' else None}
                    trials.append(t); group.append(t)
                    if selector=='two_stage_values':
                        cid=t['comparison_slot_id']
                        slots.append({'id':cid,'trial_id':tid,'logical_id':uid+'_compare','stage':'compare','rule_position':None})
                        actions.append({'kind':'slot','id':cid})
                    if selection:
                        slots.append({'id': selection, 'trial_id': tid, 'logical_id': uid+'_select',
                                      'stage': 'select', 'rule_position': None})
                        actions.append({'kind': 'slot', 'id': selection})
                # 참고자료는 선택기에만 제공한다. 두 군의 생성 이력은 독립적으로 보존한다.
                for t in group:
                    if not t['generate']: continue
                    paths = spec['reference_plans'][problem['id']]
                    n = max(map(len, paths.values())) if arm=='model' else len(paths[spec['reference_conditions'][int(condition=='deep')]])
                    for stage, pos in [('facts',None)] + [('rule',i) for i in range(n)] + [('final',None)]:
                        suffix = f'rule_{pos:02d}' if stage=='rule' else stage
                        sid = t['id'] + '_' + suffix
                        slots.append({'id':sid,'trial_id':t['id'],'logical_id':uid+'_'+suffix,'stage':stage,'rule_position':pos})
                        actions.append({'kind':'slot','id':sid})
            actions.append({'kind':'metadata','id':f'b{block:02d}_after'})
    if (len(trials),len(slots),len(actions)) != (800,spec['max_inference_calls'],spec['max_action_slots']):
        raise ValueError('사전 동결 시행·슬롯 수 불일치')
    return trials, slots, actions


def make_plan(baseline_path, run_name, provenance='live', audit_previous=True):
    if provenance not in ('live', 'synthetic'):
        raise ValueError('provenance')
    spec = core.spec()
    from audit085 import validate_protocol
    validate_protocol(spec)
    raw = Path(baseline_path).read_bytes()
    if core.sha(raw) != spec['baseline_sha256']:
        raise ValueError('v084 baseline hash mismatch')
    if audit_previous:
        from previous085 import audit
        audit(raw)
    trials, slots, actions = schedule(spec)
    plan = {'contract': 'v085-plan-r1', 'run_name': core.check_run_name(run_name), 'provenance': provenance,
            'protocol': spec, 'protocol_sha256': core.sha((core.ROOT / 'data/protocol.json').read_bytes()),
            'baseline_sha256': core.sha(raw), 'source_hashes': core.source_hashes(),
            'trials': trials, 'slots': slots, 'actions': actions}
    plan['plan_sha256'] = core.sha(core.wire(plan))
    return plan


def trial_for(plan, slot):
    return next(t for t in plan['trials'] if t['id'] == slot['trial_id'])


def problem_for(plan, trial):
    return legacy.problem_for(plan, trial)


def cards(plan, trial):
    # legacy.cards는 읽기 전용이며 반환 규칙만 deepcopy한다. 전체 protocol 복사는 불필요하다.
    s = dict(plan['protocol'])
    s['candidate_ids'] = [s['candidate_ids'][i] for i in s['id_assignments'][trial['id_assignment_index']]]
    return legacy.cards(dict(plan, protocol=s), trial)


def source_for(plan, trial, responses):
    if trial['arm'] == 'reference':
        return {'source_type': 'experimenter_reference', 'source_id': trial['unit_id'] + '_reference',
                'content': core.wire({'candidate_id': trial['control_candidate_id']}).decode('utf-8')}
    raw = responses.get(trial['selection_slot_id'])
    # 감사용 물리 슬롯명은 evidence에 보존하되 입력에는 두 군 공통 논리명을 사용한다.
    return {'source_type': 'model', 'source_id': trial['unit_id'] + '_select',
            'content': None if raw is None else legacy.raw_content(raw)}


def selected_route(plan, trial, responses):
    raw = source_for(plan, trial, responses)['content']
    try:
        value = core.load(raw) if raw is not None else None
    except (ValueError, UnicodeError):
        return None
    if not isinstance(value, dict) or set(value) != {'candidate_id'}:
        return None
    matches = [c for c in cards(plan, trial) if c['candidate_id'] == value['candidate_id']]
    if len(matches) != 1:
        return None
    c = matches[0]
    return {'candidate_id': c['candidate_id'], 'rule_ids': [r['id'] for r in c['rules']]}


def measurements_for(plan, trial):
    """추론 전 동결한 실험자 자료. 모델 응답을 읽거나 교정하지 않는다."""
    variant = trial['selector_variant']
    kinds = plan['protocol']['candidate_orders'][trial['candidate_order_index']]
    profiles = plan['protocol']['frozen_profiles'][trial['problem_id']]
    if variant == 'candidate_id': return []
    items = []
    for card, kind in zip(cards(plan,trial), kinds):
        profile = deepcopy(profiles[kind])
        if variant != 'correct_full':
            profile = {key:profile[key] for key in ('goal_depth','rule_count')}
        items.append({'candidate_id':card['candidate_id'],'value':profile})
    if variant == 'swapped_values':
        key = 'goal_depth' if trial['metric']=='D' else 'rule_count'
        items[0]['value'][key], items[1]['value'][key] = items[1]['value'][key], items[0]['value'][key]
    return [{'candidate_id':x['candidate_id'],'content':core.wire(x['value']).decode()} for x in items]


def disposition(plan, slot, responses):
    if slot['stage'] == 'compare':
        return None
    if slot['stage'] == 'select':
        t=trial_for(plan,slot)
        if t['selector_variant']=='two_stage_values':
            status, _, _=comparison_result(plan,t,responses)
            if status!='ok':
                return 'invalid_comparison_output' if status in ('invalid_json','invalid_schema') else 'unusable_comparison_response'
        return None
    route = selected_route(plan, trial_for(plan, slot), responses)
    if route is None:
        return 'unmappable_selection'
    if slot['stage'] == 'rule' and slot['rule_position'] >= len(route['rule_ids']):
        return 'outside_selected_route'
    return None


def request_for(plan, slot, responses):
    if disposition(plan, slot, responses) is not None:
        raise ValueError('skip 대상은 요청하지 않는다')
    t = trial_for(plan, slot)
    spec, problem, stage = plan['protocol'], problem_for(plan, t), slot['stage']
    body = deepcopy(spec['api_defaults'])
    body['options']['seed'] = t['seed']
    if stage=='compare' or (stage=='select' and t['selector_variant'] in ('two_stage_values','oracle_lookup')):
        return diagnostic_request(plan,slot,responses)
    if stage == 'select':
        schema = deepcopy(spec['selector_schema'])
        if t['metric'] == 'D':
            header, key, demand = spec['headers']['select'], 'requested_depth', spec['headers'][t['condition']]
        else:
            header, key, demand = spec['count_select_header'], 'requested_rule_count', spec['count_conditions'][t['condition']]
        data = {'problem': {k: problem[k] for k in ('facts', 'rules', 'goal')},
                'candidates': cards(plan, t), key: demand}
        if t['selector_variant'] != 'candidate_id':
            header += '\n' + spec['control_select_addendum']
            data['candidate_measurements'] = measurements_for(plan, t)

    else:
        route = selected_route(plan, t, responses)
        props = spec['generation_schema']['properties']
        prop = {'facts': ('nodes', props['nodes']), 'rule': ('node', props['nodes']['items']),
                'final': ('final_node_id', props['final_node_id'])}[stage]
        schema = {'type': 'object', 'properties': {prop[0]: deepcopy(prop[1])},
                  'required': [prop[0]], 'additionalProperties': False}
        if stage == 'facts':
            ns = schema['properties']['nodes']
            ns.update(minItems=len(problem['facts']), maxItems=len(problem['facts']))
            ns['items']['properties']['rule'] = {'type': 'null'}
            ns['items']['properties']['parents']['maxItems'] = 0
        history = []
        for previous in plan['slots']:
            if previous['id'] == slot['id']:
                break
            if previous['trial_id'] == t['id'] and previous['stage'] in ('facts','rule','final') and previous['id'] in responses:
                history.append({'source_slot_id': previous['logical_id'], 'content': legacy.raw_content(responses[previous['id']])})
        rid = route['rule_ids'][slot['rule_position']] if stage == 'rule' else None
        index = 0 if stage == 'facts' else slot['rule_position'] + 1 if stage == 'rule' else len(route['rule_ids']) + 1
        data = {'problem': problem, 'selection_original': source_for(plan, t, responses),
                'provided_route_plan': route,
                'operation': {'stage': stage, 'index': index, 'requested_rule_id': rid}, 'history': history}
        if stage == 'rule':
            data['operation']['requested_rule'] = deepcopy(next(r for r in problem['rules'] if r['id'] == rid))
        header = spec['headers']['generator'] + '\n\n' + spec['headers'][stage]
    text = header + '\nJSON 객체 하나만 출력한다. 출력 형식(JSON Schema):\n' + core.wire(schema).decode()
    text += '\n\ninput: ' + core.wire(data).decode()
    body['messages'] = [{'role': 'user', 'content': text}]
    body['format'] = schema
    if len(core.wire(body)) > spec['request_utf8_byte_limit']:
        raise ValueError('request budget; no truncation')
    return body


def comparison_result(plan, trial, responses):
    """생산 envelope 검사와 정수 계약. 잘못된 정수라도 정답값으로 치환하지 않는다."""
    from numeric085 import decode
    sid=trial.get('comparison_slot_id')
    raw=responses.get(sid)
    record=None if raw is None else {'kind':'call','http_status':200,'error':None}
    return decode(record,raw or b'',plan['protocol'],'compare')


def supplied_value_content(plan,trial,responses):
    if trial['selector_variant']=='oracle_lookup':
        field='goal_depth' if trial['metric']=='D' else 'rule_count'
        ms=measurements_for(plan,trial)
        values=[core.load(x['content'])[field] for x in ms]
        # 명시적으로 배정된 양성 대조에만 실험자의 목표값을 제공한다.
        target=(min if trial['condition']=='shallow' else max)(values)
        return core.wire({'target_value':target}).decode()
    raw=responses.get(trial['comparison_slot_id'])
    return None if raw is None else legacy.raw_content(raw)


def diagnostic_request(plan,slot,responses):
    t=trial_for(plan,slot);s=plan['protocol'];phase=slot['stage']
    field='goal_depth' if t['metric']=='D' else 'rule_count'
    ms=measurements_for(plan,t)
    if phase=='compare':
        header=s['numeric_compare_header'];schema=deepcopy(s['numeric_compare_schema'])
        data={'metric':t['metric'],'direction':'min' if t['condition']=='shallow' else 'max',
              'values':[core.load(x['content'])[field] for x in ms]}
    else:
        header=s['lookup_header'];schema=deepcopy(s['lookup_schema'])
        data={'candidate_measurements':ms,'metric':t['metric'],
              'value_original':supplied_value_content(plan,t,responses)}
    body=deepcopy(s['api_defaults']);body['options']['seed']=t['seed']
    text=header+'\nJSON 객체 하나만 출력한다. 출력 형식(JSON Schema):\n'+core.wire(schema).decode()
    text+='\n\ninput: '+core.wire(data).decode()
    body['messages']=[{'role':'user','content':text}];body['format']=schema
    if len(core.wire(body))>s['request_utf8_byte_limit']:raise ValueError('request budget; no truncation')
    return body
