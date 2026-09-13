"""Separate within-condition instability from paired permutation contrasts."""
from collections import Counter
from .contracts import write_json
from .design import VARIANTS
from adm_pilot_v051.reporting import cost as execution_usage


def compare(a, b):
    observed = a['observed'] and b['observed']
    ma, mb = a['measurement'], b['measurement']
    sa, sb = a['role_match'], b['role_match']
    ra = ma['selected_rule_id'] if ma else None
    rb = mb['selected_rule_id'] if mb else None
    outcome = ('unobserved' if not observed else 'unmeasured' if sa is None or sb is None else
               'both_success' if sa and sb else 'a_only' if sa else 'b_only' if sb else 'neither')
    return {'a_slot_id': a['id'], 'b_slot_id': b['id'], 'both_observed': observed,
            'both_measured': bool(observed and sa is not None and sb is not None),
            'a_success': sa, 'b_success': sb, 'a_selected_rule_id': ra, 'b_selected_rule_id': rb,
            'selected_rule_changed': ra != rb if ra is not None and rb is not None else None,
            'outcome': outcome, 'b_minus_a': int(sb) - int(sa) if sa is not None and sb is not None else None}


def summarize(plan, trials, calls, complete):
    lookup = {(t['seed'], t['variant'], t['repeat']): t for t in trials}
    pairs, repeats, seed_rows = [], [], []
    for seed in plan['seeds']:
        for repeat in (0, 1):
            a, b = (lookup[seed, v, repeat] for v in VARIANTS)
            pairs.append({'seed': seed, 'repeat': repeat, **compare(a, b)})
        for variant in VARIANTS:
            a, b = (lookup[seed, variant, rep] for rep in (0, 1))
            repeats.append({'seed': seed, 'variant': variant, **compare(a, b)})
        rows = [lookup[seed, v, rep] for v in VARIANTS for rep in (0, 1)]
        matches = [t['role_match'] for t in rows]
        selected = [t['measurement']['selected_rule_id'] if t['measurement'] else None for t in rows]
        seed_rows.append({'seed': seed, 'sequence': rows[0]['sequence'],
            'slot_ids': [t['id'] for t in rows], 'selected_rule_ids_A0_A1_B0_B1': selected,
            'shallow_A0_A1_B0_B1': matches,
            'mean_B_minus_A': (sum(matches[2:]) - sum(matches[:2])) / 2 if all(x is not None for x in matches) else None,
            'stable_within_both': (selected[0] == selected[1] and selected[2] == selected[3]) if all(x is not None for x in selected) else None})

    def contrast_summary(rows):
        counts = Counter(p['outcome'] for p in rows)
        n = len(rows)
        comparable = sum(p['selected_rule_changed'] is not None for p in rows)
        measured = sum(p['both_measured'] for p in rows)
        changes = sum(p['selected_rule_changed'] is True for p in rows)
        return {'assigned_pairs': n, 'observed_pairs': sum(p['both_observed'] for p in rows),
                'measured_pairs': measured, 'selected_rule_comparable_pairs': comparable,
                'selected_rule_changed_pairs': changes,
                'selected_rule_changed_rate': changes / n if complete and comparable == n else None,
                'outcomes': {k: counts[k] for k in ('both_success', 'a_only', 'b_only', 'neither', 'unmeasured', 'unobserved')},
                'mean_b_minus_a': sum(p['b_minus_a'] for p in rows) / n if complete and measured == n else None}

    def group(rows):
        seen = [t for t in rows if t['observed']]
        measured = sum(t['role_match'] is not None for t in seen)
        success = sum(t['role_match'] is True for t in seen)
        return {'assigned_calls': len(rows), 'observed_calls': len(seen),
                'format_valid': sum(t['measurement']['format_valid'] for t in seen),
                'choice_valid': sum(t['measurement']['choice_valid'] is True for t in seen),
                'goal_reachable_choice': sum(t['measurement']['goal_reachable_choice'] is True for t in seen),
                'instruction_fulfilled': sum(t['measurement']['instruction_fulfilled'] is True for t in seen),
                'shallow_success': success, 'unmeasured': len(seen) - measured,
                'shallow_rate': success / len(rows) if complete and measured == len(rows) else None,
                'selected_rule_ids': dict(Counter(t['measurement']['selected_rule_id'] or 'unmeasured' for t in seen)),
                'selected_rule_positions': dict(Counter(str(t['measurement']['selected_rule_position']) if t['measurement']['selected_rule_position'] is not None else 'unmeasured' for t in seen)),
                'terminal_ranks': dict(Counter(str(t['measurement']['terminal_rank']) if t['measurement']['terminal_rank'] is not None else 'unmeasured' for t in seen)),
                'implied_depths': dict(Counter(str(t['measurement']['implied_depth']) if t['measurement']['implied_depth'] is not None else 'unmeasured' for t in seen))}

    variants = {v: group([t for t in trials if t['variant'] == v]) for v in VARIANTS}
    strata = {}
    for axis in ('sequence', 'period', 'previous_variant', 'repeat_distance'):
        values = sorted({str(t[axis]) for t in trials})
        strata[axis] = {value: {v: group([t for t in trials if str(t[axis]) == value and t['variant'] == v])
                              for v in VARIANTS if any(str(t[axis]) == value and t['variant'] == v for t in trials)} for value in values}
    diffs = [s['mean_B_minus_A'] for s in seed_rows]
    return {'contract': 'v060-terminal-position-report-r1', 'model': plan['identities']['candidate']['model'],
            'problem_id': 'K01', 'variants': variants, 'strata': strata, 'pairs': pairs,
            'within_variant_repeats': repeats, 'seed_rows': seed_rows,
            'cross_variant': contrast_summary(pairs),
            'repeat_instability': {v: contrast_summary([p for p in repeats if p['variant'] == v]) for v in VARIANTS},
            'seed_mean_B_minus_A': sum(diffs) / 10 if complete and all(d is not None for d in diffs) else None,
            'assigned_calls': 40, 'unique_seed_blocks': 10, 'independent_problem_count': 1,
            'actual_D': None, 'selective_D_control': None, 'causal_effect_identified': False,
            'historical_responses_are_new_observations': False, 'policy': plan['policy'],
            'unique_execution_usage': execution_usage(calls)}


def save_report(out, report):
    keys = ('contract', 'data_integrity', 'data_complete', 'comparative_analysis_ready', 'inference_calls',
            'max_inference_calls', 'plan_sha256', 'event_tip', 'run_state', 'failure_stage',
            'failure_kind', 'failure_slot_id', 'run_error')
    write_json(out / 'audit.json', {k: report[k] for k in keys})
    write_json(out / 'summary.json', report)
    lines = ['# v060 K01 terminal 위치 진단', '',
             f"무결성: {report['data_integrity']} / 완료: {report['data_complete']} / 호출: {report['inference_calls']}/40 / 출처: {report['evidence_kind']}", '',
             '10개 seed 블록에서 각 조건을 두 번 관측한다. 40호출은 독립 문제 40개가 아니다.',
             '선택 규칙의 implied_depth는 실제 생성 증명의 D가 아니다. 선택 ID·전체 위치·terminal 순위·goal 도달성·shallow 지시 이행을 분리한다.',
             '두 배열은 first-terminal과 absolute-second 가설에 반대 예측을 주지만 k10 후치, 캐시와 더 넓은 위치 기제는 식별하지 못한다.', '',
             '|조건|관측|형식 유효|goal 도달 선택|지시 이행|미측정|', '|---|---:|---:|---:|---:|---:|']
    for variant in VARIANTS:
        g = report['variants'][variant]
        lines.append(f"|{variant}|{g['observed_calls']}/20|{g['format_valid']}|{g['goal_reachable_choice']}|{g['instruction_fulfilled']}|{g['unmeasured']}|")
    lines.append('')
    for variant in VARIANTS:
        g = report['variants'][variant]
        lines.append(f"선택 위치 {variant}: {g['selected_rule_positions']} / terminal 순위: {g['terminal_ranks']}")
        lines.append('')
    lines += [f"seed별 평균 B−A: {report['seed_mean_B_minus_A']}",
              f"조건 간 선택 ID 변화: {report['cross_variant']['selected_rule_changed_pairs']}/20 대응 비교",
              '위 20개 비교는 seed 10개에 중첩된다. 조건별 반복 불일치와 sequence/period/직전 조건/반복 간격별 표는 summary.json에서 함께 확인한다.',
              '미완료이거나 해당 비교에 미측정이 있으면 전체 비율은 null이다. metadata는 캐시 초기화가 아니며 첫 호출도 과거 이력을 가질 수 있다.', '',
              f"계획 SHA-256: {report['plan_sha256']}", f"event tip: {report['event_tip']}"]
    (out / 'summary.ko.md').write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
