"""v0.4.4: 기준 판정의 필요조건·b 민감도와 근거 없는 수락을 분리하는 읽기 전용 진단.
정답은 원래 계약의 유한 진리표다. 출력 교정/다수결/성공 조건 선별에 사용하지 않는다.
"""
from __future__ import annotations
import copy
from collections import Counter
from .decision_evidence import FIELDS

TRUTH_TABLE = {
    (False, False): (False, False, False),
    (False, True): (False, False, False),
    (True, False): (True, False, True),
    (True, True): (True, True, False),
}


def row_evidence(problem: dict, case: dict, payload: object) -> dict:
    out = {'output_modified': False, 'internal_process_observed': False,
           'scope': 'observable_contract_not_model_internals'}
    if not isinstance(payload, dict):
        return dict(out, assessable=False, error='object_required')
    staged = case.get('task') == 'decision_stage'
    source = case.get('source_projection') if staged else payload
    if not isinstance(source, dict):
        return dict(out, assessable=False, error='source_required')
    finding = payload.get('finding')
    mapping = case.get('output_key_map', {k: k for k in FIELDS})
    observed, primitives = source.get('observed'), source.get('primitives')
    if not (isinstance(observed, dict) and isinstance(primitives, dict) and isinstance(finding, dict)):
        return dict(out, assessable=False, error='fields_required')
    if not (all(type(primitives.get(k)) is bool for k in ('same_as_goal', 'in_facts'))
            and all(type(finding.get(mapping[k])) is bool for k in FIELDS)):
        return dict(out, assessable=False, error='strict_boolean_required')
    a, b = case['probe_atom'] == problem['goal'], case['probe_atom'] in problem['facts']
    actual = tuple(finding[mapping[k]] for k in FIELDS)
    x, y = primitives['same_as_goal'], primitives['in_facts']
    want = TRUTH_TABLE[a, b]
    prior_ok = (observed == {'probe_atom': case['probe_atom'], 'goal_atom': problem['goal'], 'facts': problem['facts']}
                and (x, y) == (a, b))
    violations = []
    if actual[0] != a: violations.append('answer_equality')
    if actual[1] and not b: violations.append('strict_accept_without_initial_fact')
    if actual[1] and not a: violations.append('strict_accept_without_goal_match')
    if actual[1] != want[1]: violations.append('strict_conjunction')
    if actual[2] != want[2]: violations.append('gap_conjunction_with_negation')
    return dict(out, assessable=True, input_ab=[a,b], reported_primitives=[x,y],
                source_prerequisites_correct=prior_ok,
                source_provenance='previous_response' if staged else 'same_response',
                actual=list(actual), expected=list(want),
                field_matches={k: actual[i] == want[i] for i,k in enumerate(FIELDS)},
                consistent_with_supplied_primitives=actual == TRUTH_TABLE[x,y],
                false_acceptance=actual[1] and not want[1],
                matches_ignore_b_shortcut=actual == (a,a,False),
                violations=violations, output_keys=list(finding),
                note='중간값의 출처와 출력 키 순서는 기록하지만 내부 생성 원인으로 단정하지 않는다.')


def table_summary(rows: list[dict], assigned: int | None = None) -> dict:
    """한 행당 한 실제 응답. 반복 결과가 있으면 네 행의 함수라고 확정하지 않는다."""
    usable = [r for r in rows if r.get('assessable')]
    counts = Counter(tuple(r['input_ab']) for r in usable)
    complete = set(counts) == set(TRUTH_TABLE) and all(n == 1 for n in counts.values())
    by_input = {tuple(r['input_ab']): r for r in usable} if complete else {}
    critical = None
    if complete:
        no_fact, fact = by_input[True,False], by_input[True,True]
        critical = {'a_fixed': True, 'b_values': [False,True],
                    'actual_without_fact': no_fact['actual'], 'actual_with_fact': fact['actual'],
                    'outputs_identical': no_fact['actual'] == fact['actual'],
                    'both_rows_correct': all(r['actual'] == r['expected'] and r['source_prerequisites_correct']
                                             for r in (no_fact,fact)),
                    'note': '실제 네 응답의 대응 관찰. b 무시가 내부 알고리즘이라는 증거는 아니다.'}
    return {'assigned': assigned, 'recorded': len(rows), 'assessable': len(usable),
            'not_assessable': len(rows)-len(usable), 'complete_four_input_table': complete,
            'correct_full_rows': sum(r.get('status')=='accepted' and r['actual']==r['expected'] and r['source_prerequisites_correct'] for r in usable),
            'correct_value_rows': sum(r['actual']==r['expected'] and r['source_prerequisites_correct'] for r in usable),
            'correct_bits': sum(sum(r['field_matches'].values()) for r in usable),
            'false_acceptance_count': sum(r['false_acceptance'] for r in usable),
            'ignore_b_shortcut_matching_rows': sum(r['matches_ignore_b_shortcut'] for r in usable),
            'all_four_rows_match_ignore_b_shortcut': complete and all(r['matches_ignore_b_shortcut'] for r in usable),
            'critical_b_pair': critical,
            'all_conditions_verified': complete and all(r.get('status')=='accepted' and r['actual']==r['expected'] and r['source_prerequisites_correct'] for r in usable),
            'rows': copy.deepcopy(rows),
            'interpretation': '3/4만으로 계약 수행을 승인하지 않는다. true/false 양쪽 허용 여부와 핵심 필요조건을 분리한다.'}


def summarize_records(plan: dict, records: list[dict]) -> dict:
    groups = {}
    for case in plan['cases']:
        if case.get('task') not in ('decision_stage', 'criterion_witness'): continue
        group = case.get('arm', 'baseline_schema')
        groups.setdefault(group, {'assigned': 0, 'rows': []})['assigned'] += 1
    for record in records:
        case = record['case']
        if case.get('task') not in ('decision_stage', 'criterion_witness'): continue
        group = case.get('arm', 'baseline_schema')
        ev = copy.deepcopy((record.get('task_diagnostics') or {}).get('decision_contract') or {'assessable':False})
        ev.update(case_id=case['case_id'], role_id=case['role_id'], status=record['status'])
        groups.setdefault(group, {'assigned': 0, 'rows': []})['rows'].append(ev)
    return {g: table_summary(v['rows'],v['assigned']) for g,v in groups.items()}


def summary_markdown(data: dict) -> str:
    lines = ['\n## 필요조건과 입력 민감도 진단', '',
             '| 군 | 기록/배정 | 정확한 행 | 근거 없는 strict 수락 | b 무시 단순식 일치 |',
             '| --- | ---: | ---: | ---: | ---: |']
    for name,d in data.items():
        lines.append(f"| {name} | {d['recorded']}/{d['assigned']} | {d['correct_full_rows']} | {d['false_acceptance_count']} | {d['ignore_b_shortcut_matching_rows']} |")
        if d['all_four_rows_match_ignore_b_shortcut']:
            lines.append(f"\n`{name}`: 네 응답이 모두 `(a, a, false)`와 일치한다. 3/4라도 b 필요조건 검증 성공이 아니다.\n")
    lines.append('\n이는 유한 입력의 기술적 진단이다. 원래 성공/실패는 변경하지 않으며 내부 원인을 확정하지 않는다.')
    return '\n'.join(lines)+'\n'
