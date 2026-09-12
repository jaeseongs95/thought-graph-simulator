"""최종 판정의 상수화·자기 일관성·응답 필드 순서를 분리한 읽기 전용 진단."""
from __future__ import annotations
import copy
from collections import Counter
from typing import Any

FIELDS = ('answer_only_accepts', 'proof_and_goal_accepts', 'gap_detected')


def witness_evidence(problem: dict, case: dict, payload: Any) -> dict:
    """출력 중간값과 최종값을 검사하되, 객체 순서를 내부 사고 순서로 해석하지 않는다."""
    out: dict = {'output_modified': False, 'internal_process_observed': False}
    if not isinstance(payload, dict):
        return dict(out, assessable=False, error='object_required')
    observed, primitives, finding = (payload.get(k) for k in ('observed', 'primitives', 'finding'))
    out['raw_object_key_order'] = list(payload)
    out['finding_serialized_before_primitives'] = (
        list(payload).index('finding') < list(payload).index('primitives')
        if 'finding' in payload and 'primitives' in payload else None)
    out['serialization_is_not_internal_reasoning_order'] = True
    if not (isinstance(observed, dict) and isinstance(primitives, dict) and isinstance(finding, dict)):
        return dict(out, assessable=False, error='three_stage_objects_required')
    if not (all(type(primitives.get(k)) is bool for k in ('same_as_goal', 'in_facts'))
            and all(type(finding.get(k)) is bool for k in FIELDS)):
        return dict(out, assessable=False, error='boolean_fields_required')
    atom = case['probe_atom']
    expected_observed = {'probe_atom': atom, 'goal_atom': problem['goal'], 'facts': problem['facts']}
    a, b = atom == problem['goal'], atom in problem['facts']
    expected = dict(zip(FIELDS, (a, a and b, a and not b)))
    x, y = primitives['same_as_goal'], primitives['in_facts']
    own = dict(zip(FIELDS, (x, x and y, x and not y)))
    observed_checks = {k: type(observed.get(k)) is type(v) and observed.get(k) == v
                       for k, v in expected_observed.items()}
    primitive_checks = {'same_as_goal': x == a, 'in_facts': y == b}
    finding_checks = {k: finding[k] == expected[k] for k in FIELDS}
    out.update(assessable=True, observed=copy.deepcopy(observed), primitives=copy.deepcopy(primitives),
               finding=copy.deepcopy(finding), expected=expected,
               observed_matches=observed_checks, primitive_matches=primitive_checks,
               finding_matches=finding_checks,
               finding_consistent_with_own_primitives=finding == own,
               expected_from_own_primitives=own,
               all_observed_correct=all(observed_checks.values()),
               all_primitives_correct=all(primitive_checks.values()),
               all_findings_correct=all(finding_checks.values()))
    out['failed_observable_component'] = next((name for name, checks in
        (('observed', observed_checks), ('primitives', primitive_checks), ('finding', finding_checks))
        if not all(checks.values())), None)
    out['note'] = ('출력된 값들의 논리 관계만 검사한다. primitives가 뒤에 실렸다면 '
                   '올바른 중간값을 먼저 생성한 뒤 결론을 틀렸다고 말할 수 없다.')
    return out


def aggregate_witnesses(records: list[dict]) -> dict:
    rows = []
    eligible = [r for r in records if r.get('case', {}).get('task') == 'criterion_witness']
    for record in eligible:
        ev = (record.get('task_diagnostics') or {}).get('criterion_witness')
        if ev and ev.get('assessable'):
            rows.append(ev)
    patterns = Counter(tuple(row['finding'][k] for k in FIELDS) for row in rows)
    classified = {}
    for field in FIELDS:
        tp = sum(row['expected'][field] and row['finding'][field] for row in rows)
        fn = sum(row['expected'][field] and not row['finding'][field] for row in rows)
        tn = sum(not row['expected'][field] and not row['finding'][field] for row in rows)
        fp = sum(not row['expected'][field] and row['finding'][field] for row in rows)
        classified[field] = {'tp':tp,'fn':fn,'tn':tn,'fp':fp,
            'sensitivity': tp/(tp+fn) if tp+fn else None,
            'specificity': tn/(tn+fp) if tn+fp else None,
            'balanced_accuracy': (tp/(tp+fn)+tn/(tn+fp))/2 if tp+fn and tn+fp else None}
    return {'recorded_witness_cases': len(eligible), 'not_assessable_cases': len(eligible)-len(rows),
        'assessable_cases': len(rows), 'observed_correct_cases': sum(r['all_observed_correct'] for r in rows),
        'primitives_correct_cases': sum(r['all_primitives_correct'] for r in rows),
        'finding_correct_cases': sum(r['all_findings_correct'] for r in rows),
        'own_primitive_inconsistency_cases': sum(not r['finding_consistent_with_own_primitives'] for r in rows),
        'finding_first_cases': sum(r['finding_serialized_before_primitives'] is True for r in rows),
        'actual_patterns': {','.join(str(v).lower() for v in k):n for k,n in patterns.items()},
        'constant_output_observed': len(patterns)==1 and len(rows)>1,
        'per_field_counts': classified,
        'note': '고정 입력의 기술 통계다. 표본 반복/일반 성능 추정/내부 원인 증명이 아니다.'}
