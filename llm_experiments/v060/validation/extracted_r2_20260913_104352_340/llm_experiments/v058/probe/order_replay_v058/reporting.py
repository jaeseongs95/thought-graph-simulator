"""Within-seed order contrasts without treating repeated seeds as independent samples."""
from collections import Counter
from .contracts import write_json
from .design import MODELS, MODES
from adm_pilot_v051.reporting import cost as execution_usage

OUTCOMES = ('both_success', 'first_only', 'second_only', 'neither', 'unmeasured', 'unobserved')

def summarize(plan, trials, calls, complete):
    lookup = {(t['model_key'], t['seed'], t['mode'], t['position_in_group']): t for t in trials}
    pairs = []
    for model in MODELS:
        for seed in plan['seeds']:
            for mode in MODES:
                first, second = (lookup[model, seed, mode, pos] for pos in (0, 1))
                both = bool(first['observed'] and second['observed'])
                a = first['role_match'] if first['observed'] else None
                b = second['role_match'] if second['observed'] else None
                measured = bool(both and a is not None and b is not None)
                outcome = 'unobserved' if not both else ('unmeasured' if not measured else
                    ('both_success' if a and b else ('first_only' if a else ('second_only' if b else 'neither'))))
                first_id = first['measurement'].get('selected_rule_id') if first['measurement'] is not None and mode == 'choice' else None
                second_id = second['measurement'].get('selected_rule_id') if second['measurement'] is not None and mode == 'choice' else None
                changed = None if first_id is None or second_id is None else first_id != second_id
                pairs.append({'model_key': model, 'seed': seed, 'mode': mode,
                    'first_slot_id': first['id'], 'second_slot_id': second['id'],
                    'both_observed': both, 'both_measured': measured,
                    'first_success': a, 'second_success': b,
                    'first_task_valid': None if first['measurement'] is None else first['measurement']['task_valid'],
                    'second_task_valid': None if second['measurement'] is None else second['measurement']['task_valid'],
                    'first_D': None if first['measurement'] is None else first['measurement'].get('D'),
                    'second_D': None if second['measurement'] is None else second['measurement'].get('D'),
                    'first_selected_rule_id': first_id, 'second_selected_rule_id': second_id, 'selected_rule_changed': changed,
                    'outcome': outcome, 'second_minus_first': int(b)-int(a) if measured else None})
    models = {}
    groups = {}
    for model in MODELS:
        modes = {}
        for mode in MODES:
            ts = [t for t in trials if (t['model_key'], t['mode']) == (model, mode)]
            ps = [p for p in pairs if (p['model_key'], p['mode']) == (model, mode)]
            counts = Counter(p['outcome'] for p in ps)
            measured = sum(p['both_measured'] for p in ps)
            modes[mode] = {'assigned_calls': 20, 'observed_calls': sum(t['observed'] for t in ts),
                'format_valid': sum(t['measurement']['format_valid'] for t in ts if t['observed']),
                'task_valid': sum(t['measurement']['task_valid'] is True for t in ts if t['observed']),
                'task_unmeasured': sum(t['measurement']['task_valid'] is None for t in ts if t['observed']),
                'assigned_pairs': 10, 'observed_pairs': sum(p['both_observed'] for p in ps), 'measured_pairs': measured,
                'order_outcomes': {k: counts[k] for k in OUTCOMES},
                'discordant_pairs': counts['first_only'] + counts['second_only'],
                'second_minus_first_rate': (counts['second_only']-counts['first_only'])/10 if complete and measured == 10 else None,
                'unique_execution_usage': execution_usage([c for c in calls if (c['model_key'], c['mode']) == (model, mode)])}
            if mode == 'choice':
                comparable = sum(p['selected_rule_changed'] is not None for p in ps)
                changed = sum(p['selected_rule_changed'] is True for p in ps)
                modes[mode].update(selected_rule_comparable_pairs=comparable, selected_rule_changed_pairs=changed,
                    selected_rule_changed_rate=changed/10 if complete and comparable == 10 else None)
            for pos in (0, 1):
                rows = [t for t in ts if t['position_in_group'] == pos]
                seen = [t for t in rows if t['observed']]
                groups[f'{model}/{mode}/{pos}'] = {'model_key': model, 'mode': mode, 'position_in_group': pos,
                    'assigned': 10, 'observed': len(seen),
                    'format_valid': sum(t['measurement']['format_valid'] for t in seen),
                    'task_valid': sum(t['measurement']['task_valid'] is True for t in seen),
                    'shallow_success': sum(t['role_match'] is True for t in seen),
                    'unmeasured_success': sum(t['role_match'] is None for t in seen),
                    'actual_D_distribution': dict(Counter(str(t['measurement']['D']) if t['measurement']['D'] is not None else 'unmeasured' for t in seen)) if mode == 'graph' else None,
                    'choice_implied_depth_distribution': dict(Counter(str(t['measurement']['implied_depth']) if t['measurement']['implied_depth'] is not None else 'unmeasured' for t in seen)) if mode == 'choice' else None}
        models[model] = {'model': plan['identities'][model]['model'], 'boundary_cell': plan['boundary_cells'][model], 'modes': modes}
    return {'contract': 'v058-order-replay-report-r1', 'models': models, 'groups': groups, 'pairs': pairs,
            'policy': plan['policy'], 'assigned_calls': 80, 'unique_model_seed_blocks': 20,
            'selective_D_control': None, 'historical_responses_are_new_observations': False}

def save_report(out, report):
    keys = ('contract','data_integrity','data_complete','comparative_analysis_ready','inference_calls','max_inference_calls',
            'plan_sha256','event_tip','run_state','failure_stage','failure_kind','failure_slot_id','run_error')
    write_json(out/'audit.json', {k: report[k] for k in keys})
    write_json(out/'summary.json', report)
    lines = ['# v058 경계 조건의 과제 순서 재실행', '',
        f"무결성: {report['data_integrity']} / 완료: {report['data_complete']} / 호출: {report['inference_calls']}/80 / 출처: {report['evidence_kind']}", '',
        'v057 관측 후 선정한 두 경계 조건의 탐색적 진단이다. 모델 전체 비교나 shallow/deep 선택적 제어 결과로 해석하지 않는다.',
        '각 seed에서 graph→choice와 choice→graph를 새로 실행했다. 그룹의 첫 호출에도 이전 호출 이력이 있을 수 있고, metadata 조회는 캐시 초기화가 아니다.', '',
        '|모델|과제|관측 호출|유효 결과|둘 다 성공|그룹 첫 호출만 성공|그룹 두 번째 호출만 성공|둘 다 실패|측정 불가|미관측|',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for model in MODELS:
        for mode in MODES:
            m = report['models'][model]['modes'][mode]
            c = m['order_outcomes']
            lines.append(f"|{report['models'][model]['model']}|{mode}|{m['observed_calls']}/20|{m['task_valid']}|" + '|'.join(str(c[k]) for k in OUTCOMES) + '|')
    lines += ['', '선택 ID 변화는 방향 성공률의 불일치와 별도로 집계한다.',
              '|모델|선택 ID 변화 쌍|비교 가능한 쌍|전체 10쌍 변화율|', '|---|---:|---:|---:|']
    for model in MODELS:
        choice = report['models'][model]['modes']['choice']
        lines.append(f"|{report['models'][model]['model']}|{choice['selected_rule_changed_pairs']}|{choice['selected_rule_comparable_pairs']}|{choice['selected_rule_changed_rate']}|")
    lines += ['', 'choice의 implied_depth는 문제에 대응하는 선택 깊이이며 생성된 증명의 D가 아니다. 실제 D는 graph 원문에서 계산한다.',
              '같은 seed의 재실행을 독립 문제 표본으로 합산하지 않는다. 순서 차이가 관측돼도 특정 캐시나 내부 처리 원인을 확정하지 않는다.',
              '미완료 실행과 측정 불가 쌍이 있는 전체 비교율은 null이다.', '', f"계획 SHA-256: {report['plan_sha256']}", f"event tip: {report['event_tip']}"]
    (out/'summary.ko.md').write_text('\n'.join(lines)+'\n', encoding='utf-8', newline='\n')
