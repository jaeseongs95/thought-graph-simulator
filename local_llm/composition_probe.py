"""v0.4.6: 복합식 표기 대조와 실제 NOT→AND 모델 호출 연결.
기본 최대 12회: NOT 4회 + 피연산자 순서 대조 4회 + 후속 AND 4회.
이전 결과를 고치지 않는다. 모델의 NOT 반환값을 그대로 다음 호출의 입력으로 사용한다.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

from .common import (ContractError, bytes_hash, digest, load_core, read_json, require,
                     source_fingerprint, strict_json, wire_json, write_json, write_text)
from .operator_audit import load_operator_source
from .operator_probe import SCHEMA
from .protocol import validate_schema
from .report import read_records

CONTRACT = 'composition-v046'
ARMS = ('not', 'commuted', 'and_after_not')


def _payload(raw: dict) -> dict:
    require(raw.get('done') is True and raw.get('done_reason') == 'stop', '부모 응답의 정상 종료 필요')
    message = raw.get('message')
    require(isinstance(message, dict) and message.get('role') == 'assistant' and
            not message.get('tool_calls'), '부모 응답 종류 오류')
    value = strict_json(message.get('content'))
    validate_schema(value, SCHEMA)
    return value


def output_schema(case: dict) -> dict:
    return copy.deepcopy(SCHEMA)


def _select(source: dict) -> dict:
    return {(e['case']['operation'], e['case']['input_literals']['a'], e['case']['input_literals']['b']): e
            for e in source['entries']}


def _case(entry: dict, arm: str, source: dict, parent: dict | None = None) -> dict:
    old = entry['case']
    c = {k: copy.deepcopy(old[k]) for k in ('problem_id', 'problem_sha256', 'role', 'repeat',
                                          'seed', 'probe_atom', 'source_projection')}
    c.update(role_id=old['role_id'].split('__v045_')[0] + '__v046_' + arm,
             task='composition_gate', probe_contract=CONTRACT, calibration_version=4,
             diagnostic_group=arm, arm=arm,
             original_input=copy.deepcopy(old['input_literals']),
             source_request=copy.deepcopy(entry['request']),
             source_case_id=old['case_id'], source_run_sha256=source['manifest']['run_sha256'],
             source_response_sha256=entry['response_sha256'])
    if parent is not None: c['parent'] = copy.deepcopy(parent)
    c['case_id'] = digest(c)[:24]
    return c


def _plan(source: dict, cases: list[dict], phase: str, blocked=None) -> dict:
    f = source['manifest']['frozen']
    return {'profile': 'composition-probe', 'experiment_kind': 'calibration',
            'probe_contract': CONTRACT, 'phase': phase, 'cases': cases,
            'problems': copy.deepcopy(f['plan']['problems']), 'roles': [],
            'assigned_calls': len(cases), 'repeats': 1, 'seed': f['plan']['seed'],
            'reference_depths': copy.deepcopy(f['plan']['reference_depths']), 'warnings': [],
            'source_identity': {k: copy.deepcopy(f[k]) for k in ('config', 'core', 'model', 'ollama_server')},
            'source_run_sha256': source['manifest']['run_sha256'],
            'blocked_inputs': blocked or [],
            'scope': 'fresh_gate_calls_on_previously_observed_inputs_not_ADM_end_to_end',
            'design_note': '호스트는 NOT→AND 연결을 미리 제공한다. 반환된 NOT 값은 보정하지 않는다. '
                           'commuted는 expression 표기만 변경하고, 체인은 호출 구조를 변경한 별도 조건이다.'}


def build_phase_one(source: dict, chain_only: bool = False) -> dict:
    selected = _select(source); cases = []
    for a in (False, True):
        for b in (False, True):
            cases.append(_case(selected['not_b', a, b], 'not', source))
            if not chain_only:
                cases.append(_case(selected['and_not_b', a, b], 'commuted', source))
    return _plan(source, cases, 'first')


def build_phase_two(source: dict, first: dict) -> dict:
    selected = _select(source); cases, blocked = [], []
    parents = {tuple(e['case']['original_input'][k] for k in ('a', 'b')): e
               for e in first['entries'] if e['case']['arm'] == 'not'}
    require(set(parents) == {(a, b) for a in (False, True) for b in (False, True)}, 'NOT 네 입력의 기록 필요')
    for (a, b), entry in sorted(parents.items()):
        try:
            # 틀린 bool은 그대로 연결한다. JSON/종료 문제로 값이 없을 때만 자식 호출을 생략한다.
            _payload(entry['response'])
            require(entry['record']['status'] in ('accepted', 'invalid_task'), '부모 실행 프로토콜 실패')
        except (ContractError, TypeError, KeyError, ValueError):
            blocked.append({'input_ab': [a, b], 'parent_case_id': entry['case']['case_id'],
                            'parent_status': entry['record']['status'], 'reason': 'no_valid_boolean_parent',
                            'pipeline_pass': False})
            continue
        parent = {'run_sha256': first['manifest']['run_sha256'], 'case_id': entry['case']['case_id'],
                  'record_status': entry['record']['status'], 'response': entry['response'],
                  'response_sha256': entry['response_sha256'], 'request_sha256': entry['request_sha256']}
        cases.append(_case(selected['and_ab', a, b], 'and_after_not', source, parent))
    return _plan(source, cases, 'second', blocked)


def make_request(config: dict, case: dict, problem: dict) -> dict:
    require(case.get('probe_contract') == CONTRACT and case['arm'] in ARMS, '조합 계약 오류')
    original = case['original_input']; projection = case['source_projection']['primitives']
    require(set(original) == {'a', 'b'} and all(type(x) is bool for x in original.values()) and
            original == {'a': projection['same_as_goal'], 'b': projection['in_facts']}, '입력 투영 변경')
    source_body = copy.deepcopy(case['source_request']); body = copy.deepcopy(source_body)
    require(body['model'] == config['model'] and
            body['options'] == dict(config['options'], seed=case['seed']) and
            body.get('think') == config.get('think'), '원본과 모델/생성 설정 불일치')
    require(len(body['messages']) == 2 and body['messages'][1]['role'] == 'user', '원본 메시지 구조 오류')
    text = body['messages'][1]['content']
    require(text.startswith('input: '), '원본 입력 접두사 오류')
    data = strict_json(text[len('input: '):])
    require(data.get('a') is original['a'] and data.get('b') is original['b'], '원문 a/b 불일치')
    if case['arm'] == 'not':
        require(data['expression'] == '(NOT b)', 'NOT 기준선이 아닙니다.')
    elif case['arm'] == 'commuted':
        require(data['expression'] == '(a AND (NOT b))', '복합식 기준선이 아닙니다.')
        data['expression'] = '((NOT b) AND a)'
    else:
        require(data['expression'] == '(a AND b)', 'AND 기준선이 아닙니다.')
        parent = case['parent']['response']
        require(parent['model'] == config['model'], '부모와 현재 모델 불일치')
        data['b'] = _payload(parent)['value']
    body['messages'][1]['content'] = 'input: ' + wire_json(data)
    # 허용된 한 필드 외 HTTP 원문은 바뀌지 않는다.
    restored = copy.deepcopy(body)
    restored['messages'][1]['content'] = source_body['messages'][1]['content']
    require(wire_json(restored) == wire_json(source_body), '허용하지 않은 요청 변경')
    return body


def assess_payload(core, problem: dict, case: dict, payload: dict) -> dict:
    validate_schema(payload, SCHEMA)
    a, b = case['original_input']['a'], case['original_input']['b']
    source = case['source_projection']
    truth_a, truth_b = case['probe_atom'] == problem['goal'], case['probe_atom'] in problem['facts']
    comparisons = []
    def add(name, value, want):
        comparisons.append({'field': name, 'actual': copy.deepcopy(value), 'expected': copy.deepcopy(want),
                            'matches': type(value) is type(want) and value == want})
    add('source.observed', source['observed'], {'probe_atom': case['probe_atom'],
                                             'goal_atom': problem['goal'], 'facts': problem['facts']})
    add('source.primitives', source['primitives'], {'same_as_goal': truth_a, 'in_facts': truth_b})
    add('original_input', case['original_input'], {'a': truth_a, 'b': truth_b})
    parent_value = None
    if case['arm'] == 'not':
        expected = not b; local_expected = expected
    elif case['arm'] == 'commuted':
        expected = a and not b; local_expected = expected
    else:
        parent_value = _payload(case['parent']['response'])['value']
        add('parent.not_value', parent_value, not b)
        add('parent.status', case['parent']['record_status'], 'accepted')
        local_expected = a and parent_value
        expected = a and not b
    add('gate.value', payload['value'], local_expected)
    add('formula.value', payload['value'], expected)
    checks = {r['field']: r['matches'] for r in comparisons}
    return {'valid_completion': all(checks.values()), 'role_adherent': None,
            'calibration_task': 'composition_gate/' + case['arm'], 'task_checks': checks,
            'task_comparisons': comparisons,
            'details': {'arm': case['arm'], 'original_input': case['original_input'],
                        'actual': payload['value'], 'expected': expected,
                        'parent_returned_value': parent_value,
                        'bound_input_literals': {'a': a, 'b': parent_value if case['arm'] == 'and_after_not' else b},
                        'gate_consistent_with_supplied_values': payload['value'] == local_expected,
                        'final_formula_correct': payload['value'] == expected,
                        'source_and_parents_correct': all(v for k, v in checks.items()
                                                       if k not in ('gate.value', 'formula.value')),
                        'output_modified': False, 'ADM_success': False},
            'negative_controls': [], 'negative_controls_ok': None,
            'interpretation': '이전 입력을 재사용한 새 게이트 호출. 호스트가 연결 그래프를 제공하며 종단 간 ADM 성공이 아니다.'}


def validate_runtime(plan, info, config, metadata):
    from .decision_probe import validate_runtime as check
    check(plan, info, config, metadata)


def _read_phase(core, path: Path, expected_plan: dict) -> dict:
    from .runner import request_body, assess_response
    manifest = read_json(path / 'manifest.json'); frozen = manifest['frozen']
    require(frozen['plan'] == expected_plan and manifest['run_sha256'] == digest(frozen), '단계 manifest 불일치')
    require(frozen['runtime_sources_sha256'] == source_fingerprint(), '단계 실행 후 현재 소스가 변경됨')
    records = read_records(path, manifest)
    require(len(records) == len(expected_plan['cases']), '미완료 단계는 다음 단계로 넘기지 않습니다.')
    problems = {p['id']: p for p in expected_plan['problems']}; entries = []
    for record in records:
        c = record['case']; folder = path / 'cases' / c['case_id']
        raw_path = folder / 'response.raw.json'
        if not raw_path.is_file():
            entries.append({'case': c, 'record': record, 'response': {},
                            'response_sha256': None, 'request_sha256': None}); continue
        raw = read_json(raw_path); body = request_body(frozen['config'], c, problems[c['problem_id']])
        require((folder / 'request.wire.json').read_bytes() == wire_json(body).encode('utf-8'), '단계 HTTP 원문 변경')
        outcome, _ = assess_response(core, problems[c['problem_id']], c,
                                    expected_plan['reference_depths'][c['problem_id']], body, raw,
                                    frozen['config'].get('mode_policy'))
        for key in ('status', 'error', 'audit', 'usage', 'done_reason', 'response_channels'):
            require(record.get(key) == outcome.get(key), '단계 재검사 불일치: ' + key)
        entries.append({'case': c, 'record': record, 'response': raw,
                        'response_sha256': bytes_hash(raw_path.read_bytes()),
                        'request_sha256': bytes_hash((folder / 'request.wire.json').read_bytes())})
    return {'manifest': manifest, 'records': records, 'entries': entries}


def summarize(source: dict, first: dict, second: dict, second_plan: dict) -> dict:
    rows = []
    prior = _select(source)
    indexed = {(e['case']['arm'], e['case']['original_input']['a'], e['case']['original_input']['b']): e
               for data in (first, second) for e in data['entries']}
    for a in (False, True):
        for b in (False, True):
            def view(arm):
                e = indexed.get((arm, a, b))
                if e is None: return {'status': 'blocked_or_not_assigned', 'value': None, 'accepted': False}
                d = (e['record'].get('audit') or {}).get('details', {})
                return {'case_id': e['case']['case_id'], 'status': e['record']['status'],
                        'value': d.get('actual'), 'accepted': e['record']['status'] == 'accepted',
                        'response_sha256': e['response_sha256']}
            baseline = prior['and_not_b', a, b]['record']; n = view('not'); final = view('and_after_not')
            rows.append({'input_ab': [a, b], 'expected': a and not b,
                         'baseline_direct': {'status': baseline['status'],
                                             'value': (baseline.get('audit') or {}).get('details', {}).get('actual')},
                         'commuted': view('commuted'), 'not': n, 'and_after_not': final,
                         'pipeline_pass': n['accepted'] and final['accepted'],
                         'final_formula_correct': type(final['value']) is bool and final['value'] == (a and not b)})
    return {'rows': rows, 'pipeline_assigned': 4, 'pipeline_passed': sum(r['pipeline_pass'] for r in rows),
            'final_formula_correct': sum(r['final_formula_correct'] for r in rows),
            'blocked_inputs': second_plan['blocked_inputs'],
            'fresh_not_calls_recorded': sum(e['case']['arm'] == 'not' for e in first['entries']),
            'fresh_and_calls_recorded': len(second['entries']),
            'commuted_calls_recorded': sum(e['case']['arm'] == 'commuted' for e in first['entries']),
            'original_failures_preserved': True, 'host_evaluated_answer_in_request': False,
            'host_supplied_dependency_graph': 'NOT(b) -> AND(a, previous_model_value)',
            'ADM_success': False,
            'scope': '이전 중간 입력을 재사용한다. NOT와 AND는 새 호출이며 전처리 추출까지 포함한 신규 종단 간 실행은 아니다.',
            'causal_limit': '직접식 대 체인은 호출 수/식 구조/입력 배치가 함께 다르다. 일반적 모델 크기/양자화 효과나 내부 원인 확정이 아니다.'}


def save_summary(out: Path, summary: dict) -> None:
    write_json(out / 'composition_probe.json', summary)
    lines = ['# NOT→AND 연결 결과', '',
             f"네 파이프라인 중 모든 단계가 맞은 수: {summary['pipeline_passed']}/4", '',
             '| a,b | 정답 | 이전 직접식 | 순서 대조 | 새 NOT | 새 AND | 단계 전체 통과 |',
             '| --- | --- | --- | --- | --- | --- | --- |']
    for r in summary['rows']:
        values = [r[k]['value'] for k in ('baseline_direct', 'commuted', 'not', 'and_after_not')]
        lines.append('| ' + ' | '.join([str(r['input_ab']), str(r['expected']), *map(str, values), str(r['pipeline_pass'])]) + ' |')
    lines += ['', '정답과 일치한 최종값과 모든 의존 단계의 유효성을 구별한다. 중간 오답이 우연히 상쇄되어도 파이프라인 성공이 아니다.',
              summary['scope'], summary['causal_limit'], '과거 직접식 실패를 새로운 결과로 덮어쓰지 않는다.']
    write_text(out / 'summary.md', '\n'.join(lines) + '\n')


def main(argv=None) -> int:
    from .client import APIError
    from .runner import run
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, required=True); p.add_argument('--out', type=Path)
    p.add_argument('--plan-only', action='store_true'); p.add_argument('--resume', action='store_true')
    p.add_argument('--chain-only', action='store_true', help='표기 대조 없이 NOT→AND 최대 8회만 실행')
    args = p.parse_args(argv)
    try:
        core, info = load_core(); source = load_operator_source(core, info, args.input)
        first_plan = build_phase_one(source, args.chain_only)
        if args.plan_only:
            print(json.dumps({'model_called': False, 'network_called': False,
                              'max_new_llm_calls': 8 if args.chain_only else 12,
                              'source_validation': source['validation'],
                              'phase_one': len(first_plan['cases']), 'phase_two_max': 4,
                              'parent_invalid_json': '후속 호출 차단, 네 파이프라인 분모 유지',
                              'parent_wrong_boolean': '수정하지 않고 전달, 전체 단계 평가에서 실패',
                              'note': first_plan['design_note']}, ensure_ascii=False, indent=2)); return 0
        require(args.out is not None, '--out 새 폴더를 지정하세요.')
        out, src = args.out.resolve(), args.input.resolve()
        require(out != src and not out.is_relative_to(src) and not src.is_relative_to(out), '원본과 다른 위치 필요')
        config = copy.deepcopy(source['manifest']['frozen']['config'])
        spec = {'source_run_sha256': source['manifest']['run_sha256'], 'chain_only': args.chain_only,
                'sources': source_fingerprint(), 'contract': CONTRACT}
        if args.resume:
            require(out.is_dir() and read_json(out/'pipeline_spec.json') == spec, '재개 계약/소스/입력 변경')
        else:
            require(not out.exists() or (out.is_dir() and not any(out.iterdir())), '기존 결과를 덮어쓰지 않습니다.')
            out.mkdir(parents=True, exist_ok=True); write_json(out/'pipeline_spec.json', spec)
        path1, path2 = out/'phase_one', out/'phase_two'
        print('1단계: 새 NOT 응답과 복합식 표기 대조', flush=True)
        code = run(core, info, first_plan, config, path1, resume=args.resume and path1.exists())
        if code: return code
        first = _read_phase(core, path1, first_plan)
        second_plan = build_phase_two(source, first)
        if second_plan['cases']:
            print('2단계: 새 NOT 반환값을 그대로 다음 AND 입력에 연결', flush=True)
            code = run(core, info, second_plan, config, path2, resume=args.resume and path2.exists())
            if code: return code
            second = _read_phase(core, path2, second_plan)
        else: second = {'entries': [], 'records': []}
        data = summarize(source, first, second, second_plan); save_summary(out, data)
        print(f"파이프라인: {data['pipeline_passed']}/4 / 결과: {out/'summary.md'}")
        return 0
    except (ContractError, APIError, OSError, KeyError, TypeError, ValueError) as exc:
        print('오류: ' + str(exc), file=sys.stderr); return 2
    except KeyboardInterrupt: return 130


if __name__ == '__main__': raise SystemExit(main())
