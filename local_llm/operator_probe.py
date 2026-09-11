"""v0.4.5: 모델의 a/b 값을 그대로 투영해 연산 하나씩 묻는 분리 진단.
기본 16회: COPY(a), AND(a,b), NOT(b), AND(a,NOT(b)) × 네 입력.
정답 생성/보정은 하지 않는다. 모델의 세 반환값을 조립한 조건부 결과는 ADM 성과와 별도다.
"""
from __future__ import annotations

import argparse
import copy
import json
import random
import sys
from pathlib import Path

from .common import ContractError, digest, load_core, require, require_core_compatible, wire_json
from .factor_audit import load_factor_source
from .protocol import obj, validate_schema

CONTRACT = 'operator-v045'
OPERATIONS = {'copy_a': 'a', 'and_ab': '(a AND b)', 'not_b': '(NOT b)',
              'and_not_b': '(a AND (NOT b))'}
# 점수용 유한 계약. 이 표는 프롬프트/스키마에 넣지 않는다.
TABLE = {
    (False, False): {'copy_a': False, 'and_ab': False, 'not_b': True, 'and_not_b': False},
    (False, True): {'copy_a': False, 'and_ab': False, 'not_b': False, 'and_not_b': False},
    (True, False): {'copy_a': True, 'and_ab': False, 'not_b': True, 'and_not_b': True},
    (True, True): {'copy_a': True, 'and_ab': True, 'not_b': False, 'and_not_b': False},
}
SCHEMA = obj({'value': {'type': 'boolean'}})


def output_schema(case: dict) -> dict:
    return copy.deepcopy(SCHEMA)


def build_plan(source: dict, *, format_mode: str = 'schema', comparison_model: str | None = None) -> dict:
    require(format_mode in ('schema', 'json', 'none'), 'format은 schema/json/none 중 하나입니다.')
    if comparison_model is not None:
        require(isinstance(comparison_model, str) and bool(comparison_model.strip()), '비교 모델 이름이 필요합니다.')
    f = source['manifest']['frozen']
    cases = []
    for selected in source['selected']:
        old = selected['case']
        projection = copy.deepcopy(old['source_projection'])
        primitives = projection['primitives']
        require(all(type(primitives.get(k)) is bool for k in ('same_as_goal', 'in_facts')),
                '원래 모델이 반환한 불리언 중간값이 없습니다.')
        for op in OPERATIONS:
            case = {'problem_id': old['problem_id'], 'problem_sha256': old['problem_sha256'],
                    'role': copy.deepcopy(old['role']),
                    'role_id': old['role_id'].split('__v044_')[0] + '__v045_' + op,
                    'repeat': old['repeat'], 'seed': old['seed'], 'task': 'operator_atom',
                    'calibration_version': 4, 'probe_contract': CONTRACT, 'operation': op,
                    'diagnostic_group': op, 'format_mode': format_mode, 'probe_atom': old['probe_atom'],
                    'source_projection': projection,
                    'input_literals': {'a': primitives['same_as_goal'], 'b': primitives['in_facts']},
                    'source_case_id': old['case_id'],
                    'source_status': selected['record']['status'],
                    'source_run_sha256': source['manifest']['run_sha256']}
            case['case_id'] = digest(case)[:24]
            cases.append(case)
    require(len(cases) == 16, '실패 포함 네 입력 × 네 연산이 필요합니다.')
    random.Random(451729).shuffle(cases)
    return {'profile': 'operator-probe', 'experiment_kind': 'calibration', 'probe_contract': CONTRACT,
            'cases': cases, 'problems': copy.deepcopy(f['plan']['problems']), 'roles': [],
            'assigned_calls': 16, 'repeats': 1, 'seed': f['plan']['seed'],
            'reference_depths': copy.deepcopy(f['plan']['reference_depths']), 'warnings': [],
            'scope': 'atomic_boolean_diagnostic_not_ADM_result', 'comparison_model': comparison_model,
            'format_mode': format_mode,
            'source_identity': {k: copy.deepcopy(f[k]) for k in ('config', 'core', 'model', 'ollama_server')},
            'source_validation': copy.deepcopy(source['validation']),
            'source_run_sha256': source['manifest']['run_sha256'],
            'design_note': '중간값을 a,b로 투영하고 한 호출에 한 식만 계산한다. 입력 추출·문맥·출력 부담의 묶음 변화이며 '
                           '순수한 단계 수 효과로 해석하지 않는다. 기존 정답/실패를 덮어쓰지 않는다.'}


def make_request(config: dict, case: dict, problem: dict) -> dict:
    require(case.get('probe_contract') == CONTRACT and case.get('operation') in OPERATIONS, '연산 계약 오류')
    previous = case['source_projection']['primitives']
    require(case['input_literals'] == {'a': previous['same_as_goal'], 'b': previous['in_facts']}
            and all(type(x) is bool for x in case['input_literals'].values()),
            '모델 중간값을 그대로 투영한 입력이어야 합니다.')
    system = ('입력의 a와 b는 불리언이다. expression의 식 하나만 계산해 value에 기록한다.\n'
              'AND는 두 피연산자가 모두 true일 때 true다. NOT은 true와 false를 뒤집는다. '
              '괄호 안의 연산을 먼저 적용한다.\n'
              'JSON 객체 하나만 출력한다. 다음 스키마는 자료형만 제한하며 정답을 지정하지 않는다.\n'
              + wire_json(SCHEMA))
    body = {'model': config['model'],
            'messages': [{'role': 'system', 'content': system},
                         {'role': 'user', 'content': 'input: ' + wire_json(
                             dict(case['input_literals'], expression=OPERATIONS[case['operation']]))}],
            'stream': False, 'keep_alive': '10m',
            'options': dict(config['options'], seed=case['seed'])}
    if config.get('think') is not None:
        body['think'] = config['think']
    mode = case['format_mode']
    require(mode in ('schema', 'json', 'none'), '알 수 없는 format')
    if mode == 'schema':
        body['format'] = output_schema(case)
    elif mode == 'json':
        body['format'] = 'json'
    return body


def assess_payload(core, problem: dict, case: dict, payload: dict) -> dict:
    validate_schema(payload, SCHEMA)
    op = case['operation']
    require(op in OPERATIONS, '알 수 없는 연산')
    a, b = case['input_literals']['a'], case['input_literals']['b']
    require(type(a) is bool and type(b) is bool, '정확한 불리언 입력이 필요합니다.')
    prior = case['source_projection']
    correct_observed = {'probe_atom': case['probe_atom'], 'goal_atom': problem['goal'], 'facts': problem['facts']}
    true_a, true_b = case['probe_atom'] == problem['goal'], case['probe_atom'] in problem['facts']
    checks = {
        'source.observed': prior['observed'] == correct_observed,
        'source.primitives': prior['primitives'] == {'same_as_goal': true_a, 'in_facts': true_b}
                             and all(type(x) is bool for x in prior['primitives'].values()),
        'input_projection': case['input_literals'] == {'a': prior['primitives']['same_as_goal'],
                                                     'b': prior['primitives']['in_facts']},
        'operator.value': payload['value'] == TABLE[a, b][op],
    }
    comparisons = [
        {'field': 'source.observed', 'actual': copy.deepcopy(prior['observed']),
         'expected': correct_observed, 'matches': checks['source.observed']},
        {'field': 'source.primitives', 'actual': copy.deepcopy(prior['primitives']),
         'expected': {'same_as_goal': true_a, 'in_facts': true_b}, 'matches': checks['source.primitives']},
        {'field': 'input_projection', 'actual': copy.deepcopy(case['input_literals']),
         'expected': {'a': prior['primitives']['same_as_goal'], 'b': prior['primitives']['in_facts']},
         'matches': checks['input_projection']},
        {'field': 'operator.value', 'actual': payload['value'], 'expected': TABLE[a, b][op],
         'matches': checks['operator.value']}]
    return {'valid_completion': all(checks.values()), 'role_adherent': None,
            'calibration_task': 'operator_atom/' + op, 'task_checks': checks,
            'task_comparisons': comparisons,
            'details': {'operation': op, 'input_ab': [a, b], 'actual': payload['value'],
                        'expected_from_supplied_values': TABLE[a, b][op],
                        'source_prerequisites_correct': all(checks[k] for k in checks if k != 'operator.value'),
                        'operator_correct': checks['operator.value'],
                        'source_status': case['source_status'], 'output_modified': False},
            'negative_controls': [], 'negative_controls_ok': None,
            'interpretation': '단일 연산 진단이다. 모델 반환값을 보정하지 않고 원래 ADM 성공률에 합산하지 않는다.'}


def validate_runtime(plan: dict, info: dict, config: dict, metadata: dict) -> None:
    from .decision_probe import validate_runtime as same_runtime
    identity = plan['source_identity']
    if not plan.get('comparison_model'):
        same_runtime(plan, info, config, metadata)
        return
    # 다른 모델은 사용자가 명시한 별도 기준선으로만 허용한다. 다운로드는 수행하지 않는다.
    require_core_compatible(identity['core'], info, 'core 내용 변경')
    require(metadata['server'] == identity['ollama_server'], '모델 비교 중 서버 버전도 변경됐습니다.')
    require(config['model'] == plan['comparison_model'], '명시한 비교 모델과 다릅니다.')
    for key in ('endpoint', 'timeout_seconds', 'protocol', 'prompt_profile', 'options'):
        require(config[key] == identity['config'][key], '모델 외 설정도 변경됐습니다: ' + key)
    require(config['mode_policy']['resolved_mode'] == 'non-thinking',
            '이 비교는 non-thinking 체크포인트만 허용합니다. 추론 모드 변경을 섞지 않습니다.')


def summary(plan: dict, records: list[dict]) -> dict:
    lookup = {r['case']['case_id']: r for r in records}
    groups = {op: {'assigned': 4, 'recorded': 0, 'accepted': 0, 'correct_values': 0,
                   'positive_expected': 0, 'positive_detected': 0, 'false_positive': 0,
                   'not_assessable': 0, 'rows': []} for op in OPERATIONS}
    by_input: dict[tuple[bool, bool], dict] = {}
    for c in plan['cases']:
        r = lookup.get(c['case_id']); g = groups[c['operation']]
        a, b = c['input_literals']['a'], c['input_literals']['b']
        details = ((r or {}).get('audit') or {}).get('details', {})
        actual = details.get('actual')
        known = type(actual) is bool
        expected = TABLE[a, b][c['operation']]
        row = {'case_id': c['case_id'], 'input_ab': [a, b], 'expected': expected,
               'actual': actual if known else None, 'status': r['status'] if r else 'not_started',
               'source_prerequisites_correct': details.get('source_prerequisites_correct', False),
               'operator_correct': known and actual == expected}
        g['recorded'] += int(r is not None); g['accepted'] += int(bool(r and r['status'] == 'accepted'))
        g['correct_values'] += int(row['operator_correct'])
        g['positive_expected'] += int(expected)
        g['positive_detected'] += int(known and expected and actual)
        g['false_positive'] += int(known and not expected and actual)
        g['not_assessable'] += int(not known); g['rows'].append(row)
        by_input.setdefault((a, b), {})[c['operation']] = row
    pipelines = []
    for ab, rows in sorted(by_input.items()):
        used = [rows.get(k) for k in ('copy_a', 'and_ab', 'and_not_b')]
        complete = all(r and type(r.get('actual')) is bool for r in used)
        # 응답값의 일대일 조립만 한다. 계산한 정답이나 NOT 진단값으로 누락을 보충하지 않는다.
        actual = [r['actual'] for r in used] if complete else None
        pipelines.append({'input_ab': list(ab), 'model_output_assembly': actual,
                          'accepted': complete and all(r['status'] == 'accepted' for r in used),
                          'source_case_ids': [r['case_id'] for r in used if r],
                          'prior_inputs_reused': True, 'ADM_success': False})
    all_atomic = all(g['accepted'] == 4 for g in groups.values())
    primitives_passed = all(groups[k]['accepted'] == 4 for k in ('copy_a', 'and_ab', 'not_b'))
    completed = all(g['recorded'] == 4 for g in groups.values())
    if not completed:
        diagnostic = 'not_completed'
    elif all_atomic:
        diagnostic = 'all_single_output_operators_passed'
    elif primitives_passed:
        diagnostic = 'composite_formula_failure_with_primitives_passed'
    else:
        diagnostic = 'primitive_failures_remain'
    # 기존 all_atomic_correct는 파일 호환성용으로 남기되, 복합식과 단일 게이트를 구분한다.
    classification = {'primitive_operations': ['copy_a', 'and_ab', 'not_b'],
                      'composite_operations': ['and_not_b'],
                      'primitive_groups_all_passed': primitives_passed,
                      'all_single_output_tasks_passed': all_atomic,
                      'composite_failure_does_not_prove_primitive_failure': True}
    return {'groups': groups, 'conditional_assemblies': pipelines,
            'conditional_assembly_successes': sum(r['accepted'] for r in pipelines),
            'all_atomic_correct': all_atomic, 'diagnostic': diagnostic, 'classification': classification,
            'comparison_model': plan.get('comparison_model'), 'format_mode': plan['format_mode'],
            'new_calls_assigned': 16, 'original_records_modified': False,
            'interpretation': '단일 연산 과제의 조건부 결과다. 문맥·입력명·출력 부담의 변경이 포함되므로 단일 요인의 인과 증명이 아니다.'}


def summary_markdown(data: dict) -> str:
    lines = ['\n## 한 출력 과제별 진단 — 단일 게이트와 복합식 구분', '',
             '| 연산 | 성공/배정 | 양성 검출/양성 입력 | 거짓 양성 | 평가 불가 |',
             '| --- | ---: | ---: | ---: | ---: |']
    for op, g in data['groups'].items():
        lines.append(f"| {op} | {g['accepted']}/{g['assigned']} | {g['positive_detected']}/{g['positive_expected']} | "
                     f"{g['false_positive']} | {g['not_assessable']} |")
    lines += ['', f"세 모델 반환값을 그대로 조립한 조건부 성공: {data['conditional_assembly_successes']}/4.",
              'NOT 단독 결과로 다른 답을 자동 보충하지 않는다. 과거 중간값 재사용이므로 신규 종단 간 ADM 성공이 아니다.',
              'and_not_b는 출력이 하나여도 NOT→AND 두 게이트의 복합식이다. 다른 세 과제의 성공과 구분한다. 원인으로 모델 크기나 NOT 단독의 수행 불가를 자동 지목하지 않는다.']
    return '\n'.join(lines) + '\n'


def main(argv=None) -> int:
    from .client import APIError
    from .runner import run
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--plan-only', action='store_true')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--format', dest='format_mode', choices=('schema', 'json', 'none'), default='schema')
    parser.add_argument('--comparison-model', help='이미 설치한 별도 non-thinking 모델. 자동 다운로드 없음')
    args = parser.parse_args(argv)
    try:
        core, info = load_core()
        source = load_factor_source(core, info, args.input)
        plan = build_plan(source, format_mode=args.format_mode, comparison_model=args.comparison_model)
        if args.plan_only:
            print(json.dumps({'model_called': False, 'network_called': False,
                              'source_validation': source['validation'],
                              'core_compatibility': source['core_compatibility'],
                              'new_llm_calls': 16, 'operations': OPERATIONS,
                              'comparison_model': args.comparison_model, 'format': args.format_mode,
                              'note': plan['design_note']}, ensure_ascii=False, indent=2))
            return 0
        require(args.out is not None, '--out 새 결과 폴더를 지정하세요.')
        a, b = args.input.resolve(), args.out.resolve()
        require(a != b and not a.is_relative_to(b) and not b.is_relative_to(a), '원본과 다른 위치가 필요합니다.')
        config = copy.deepcopy(source['manifest']['frozen']['config'])
        if args.comparison_model:
            config['model'] = args.comparison_model
            config['config_stage'] = 'unresolved'
            config['requested_mode'] = 'non-thinking'
            config['think'] = None
            config.pop('mode_policy', None)
        print('단일 연산 진단: 16회 / 기존 중간값 사용 / 정답 보정 없음', flush=True)
        return run(core, info, plan, config, b, resume=args.resume)
    except (ContractError, APIError, OSError, KeyError, TypeError, ValueError) as exc:
        print('오류: ' + str(exc), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
