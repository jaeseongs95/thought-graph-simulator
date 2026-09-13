"""Report conditional construction layers without treating repeats as new problems."""
from collections import Counter

from adm_pilot_v051.reporting import cost as execution_usage

from .contracts import write_json
from .design import TARGET_RULES, VARIANTS


def _comparison(a, b):
    observed = a['observed'] and b['observed']
    ma, mb = a['measurement'], b['measurement']
    ia, ib = a['role_match'], b['role_match']
    selected_a = ma['selected_rule_id'] if ma else None
    selected_b = mb['selected_rule_id'] if mb else None
    outcome = ('unobserved' if not observed else 'unmeasured'
               if ia is None or ib is None else 'both_success' if ia and ib
               else 'a_only' if ia else 'b_only' if ib else 'neither')
    return {
        'a_slot_id': a['id'], 'b_slot_id': b['id'], 'both_observed': observed,
        'both_measured': bool(observed and ia is not None and ib is not None),
        'a_success': ia, 'b_success': ib,
        'a_selected_rule_id': selected_a, 'b_selected_rule_id': selected_b,
        'a_actual_D': ma['actual_D'] if ma else None,
        'b_actual_D': mb['actual_D'] if mb else None,
        'selected_rule_changed': (selected_a != selected_b
                                  if selected_a is not None and selected_b is not None else None),
        'actual_D_changed': (ma['actual_D'] != mb['actual_D']
                             if ma and mb and ma['actual_D'] is not None
                             and mb['actual_D'] is not None else None),
        'outcome': outcome,
    }


def _group(rows, complete):
    seen = [trial for trial in rows if trial['observed']]
    measured = [trial for trial in seen
                if trial['measurement']['instruction_fulfilled'] is not None]
    def count(name):
        return sum(trial['measurement'][name] is True for trial in seen)
    def distribution(name):
        return dict(Counter(str(trial['measurement'][name])
                            if trial['measurement'][name] is not None else 'unmeasured'
                            for trial in seen))
    return {
        'assigned_calls': len(rows), 'observed_calls': len(seen),
        'format_valid': sum(trial['measurement']['format_valid'] for trial in seen),
        'proof_valid': count('proof_valid'), 'strict_valid': count('strict_valid'),
        'goal_reached': count('goal_reached'), 'target_rule_match': count('target_rule_match'),
        'instruction_fulfilled': count('instruction_fulfilled'),
        'instruction_rate': (count('instruction_fulfilled') / len(rows)
                             if complete and len(measured) == len(rows) else None),
        'unmeasured': len(seen) - len(measured),
        'selected_rule_ids': distribution('selected_rule_id'),
        'selected_rule_positions': distribution('selected_rule_position'),
        'terminal_ranks': distribution('terminal_rank'),
        'actual_depths': distribution('actual_D'),
        'node_counts': distribution('node_count'),
        'errors': dict(Counter(error for trial in seen
                               for error in trial['measurement']['errors'])),
    }


def _contrast_summary(rows, complete):
    outcomes = Counter(pair['outcome'] for pair in rows)
    comparable_ids = sum(pair['selected_rule_changed'] is not None for pair in rows)
    comparable_depths = sum(pair['actual_D_changed'] is not None for pair in rows)
    measured = sum(pair['both_measured'] for pair in rows)
    return {
        'assigned_pairs': len(rows), 'observed_pairs': sum(pair['both_observed'] for pair in rows),
        'measured_pairs': measured, 'selected_rule_comparable_pairs': comparable_ids,
        'selected_rule_changed_pairs': sum(pair['selected_rule_changed'] is True for pair in rows),
        'actual_D_comparable_pairs': comparable_depths,
        'actual_D_changed_pairs': sum(pair['actual_D_changed'] is True for pair in rows),
        'both_success_and_changed_pairs': sum(
            pair['outcome'] == 'both_success' and pair['selected_rule_changed'] is True
            for pair in rows),
        'selected_rule_changed_rate': (
            sum(pair['selected_rule_changed'] is True for pair in rows) / len(rows)
            if complete and comparable_ids == len(rows) else None),
        'outcomes': {name: outcomes[name] for name in (
            'both_success', 'a_only', 'b_only', 'neither', 'unmeasured', 'unobserved')},
    }


def summarize(plan, trials, calls, complete):
    lookup = {(trial['seed'], trial['variant'], trial['repeat']): trial for trial in trials}
    pairs, repeats, seed_rows = [], [], []
    for seed in plan['seeds']:
        cells = {variant: [lookup[seed, variant, repeat] for repeat in (0, 1)]
                 for variant in VARIANTS}
        for repeat in (0, 1):
            pairs.append({'seed': seed, 'repeat': repeat,
                          **_comparison(cells[VARIANTS[0]][repeat], cells[VARIANTS[1]][repeat])})
        for variant in VARIANTS:
            repeats.append({'seed': seed, 'variant': variant,
                            **_comparison(cells[variant][0], cells[variant][1])})
        ordered = [cells[variant][repeat] for variant in VARIANTS for repeat in (0, 1)]
        measurements = [trial['measurement'] for trial in ordered]
        signatures = [
            (m['selected_rule_id'], m['actual_D'], m['strict_valid'],
             m['instruction_fulfilled']) if m else None for m in measurements
        ]
        all_strict = all(m is not None and m['strict_valid'] is True for m in measurements)
        stable = ((signatures[0] == signatures[1] and signatures[2] == signatures[3])
                  if all_strict else None)
        seed_rows.append({
            'seed': seed, 'sequence': ordered[0]['sequence'],
            'slot_ids': [trial['id'] for trial in ordered],
            'selected_rule_ids_A0_A1_B0_B1': [signature[0] if signature else None for signature in signatures],
            'actual_D_A0_A1_B0_B1': [signature[1] if signature else None for signature in signatures],
            'strict_A0_A1_B0_B1': [signature[2] if signature else None for signature in signatures],
            'instruction_A0_A1_B0_B1': [signature[3] if signature else None for signature in signatures],
            'stable_within_both': stable,
        })
    variants = {variant: _group([trial for trial in trials if trial['variant'] == variant], complete)
                for variant in VARIANTS}
    strata = {}
    for axis in ('sequence', 'period', 'previous_variant', 'repeat_distance'):
        strata[axis] = {}
        for value in sorted({str(trial[axis]) for trial in trials}):
            strata[axis][value] = {
                variant: _group([trial for trial in trials
                                 if str(trial[axis]) == value and trial['variant'] == variant], complete)
                for variant in VARIANTS
                if any(str(trial[axis]) == value and trial['variant'] == variant for trial in trials)
            }
    expected_depth = {'target_k03': 1, 'target_k17': 2}
    gate_trials = all(
        trial['observed'] and trial['measurement']['strict_valid'] is True
        and trial['measurement']['target_rule_match'] is True
        and trial['measurement']['actual_D'] == expected_depth[trial['variant']]
        for trial in trials)
    seed_stable = all(row['stable_within_both'] is True for row in seed_rows)
    return {
        'contract': 'v062-conditional-construction-report-r1',
        'model': plan['identities']['candidate']['model'], 'problem_id': 'K01',
        'task': 'conditional_construction', 'variants': variants, 'strata': strata,
        'pairs': pairs, 'within_variant_repeats': repeats, 'seed_rows': seed_rows,
        'cross_variant': _contrast_summary(pairs, complete),
        'repeat_instability': {
            variant: _contrast_summary([pair for pair in repeats if pair['variant'] == variant], complete)
            for variant in VARIANTS},
        # A partial run cannot be read as a failed admission gate: the protocol
        # reserves False for a complete, measured 40-call run that misses it.
        'admission_gate_passed': (
            bool(gate_trials and seed_stable) if complete else None),
        'admission_gate': {
            'required_calls': 40, 'strict_target_depth_calls': sum(
                trial['observed'] and trial['measurement']['strict_valid'] is True
                and trial['measurement']['target_rule_match'] is True
                and trial['measurement']['actual_D'] == expected_depth[trial['variant']]
                for trial in trials),
            'stable_seed_blocks': sum(row['stable_within_both'] is True for row in seed_rows),
            'expected_actual_D': expected_depth,
        },
        'assigned_calls': 40, 'unique_seed_blocks': 10, 'independent_problem_count': 1,
        'causal_effect_identified': False, 'historical_responses_are_new_observations': False,
        'policy': plan['policy'], 'unique_execution_usage': execution_usage(calls),
    }


def save_report(out, report):
    keys = ('contract', 'data_integrity', 'data_complete', 'comparative_analysis_ready',
            'inference_calls', 'max_inference_calls', 'plan_sha256', 'event_tip',
            'run_state', 'failure_stage', 'failure_kind', 'failure_slot_id', 'run_error')
    write_json(out / 'audit.json', {key: report[key] for key in keys})
    write_json(out / 'summary.json', report)
    lines = [
        '# v062 K01 조건부 최소 DAG 구성', '',
        f"무결성: {report['data_integrity']} / 완료: {report['data_complete']} / 호출: {report['inference_calls']}/40 / 출처: {report['evidence_kind']}", '',
        '10개 seed 블록에서 target_k03와 target_k17을 각각 두 번 관측한다. 40호출은 독립 문제 40개가 아니다.',
        '이 과제는 마지막 규칙을 외부에서 지정한 조건부 구성이다. 자유 선택, 깊이 지시 이행, A/M1/M2 또는 일반 D 제어를 측정하지 않는다.',
        '|조건|관측|형식 유효|proof 유효|strict 유효|goal|target 일치|이행|미측정|',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for variant in VARIANTS:
        group = report['variants'][variant]
        lines.append(
            f"|{variant}|{group['observed_calls']}/20|{group['format_valid']}|{group['proof_valid']}|{group['strict_valid']}|{group['goal_reached']}|{group['target_rule_match']}|{group['instruction_fulfilled']}|{group['unmeasured']}|")
    lines += ['', f"조건 간 선택 ID 변화: {report['cross_variant']['selected_rule_changed_pairs']}/20 대응 비교",
              f"양쪽 이행과 ID 변화 동시 충족: {report['cross_variant']['both_success_and_changed_pairs']}/20 대응 비교",
              f"사전 진입 gate: {report['admission_gate_passed']} ({report['admission_gate']['strict_target_depth_calls']}/40 strict·target·예상 D, 안정 seed {report['admission_gate']['stable_seed_blocks']}/10)",
              'strict가 아니어도 proof_valid이면 D는 실제 parents에서 계산한다. 미측정은 실패나 0으로 바꾸지 않는다.',
              'metadata와 블록 경계는 캐시 초기화를 뜻하지 않으며, 내부 기제나 일반 효과를 확정하지 않는다.', '',
              f"계획 SHA-256: {report['plan_sha256']}", f"event tip: {report['event_tip']}"]
    (out / 'summary.ko.md').write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
