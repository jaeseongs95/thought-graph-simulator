"""v0.4.4.1 factor 결과의 읽기 전용 재검사. 저장된 Python을 실행하지 않는다."""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path

from .approved_v0441 import APPROVED_SOURCES
from .common import (ContractError, bytes_hash, digest, load_core, read_json, require,
                     require_core_compatible, source_text_identity, wire_json,
                     write_json, write_text)
from .decision_table import summarize_records, summary_markdown
from .factor_probe import DEFAULT_ARMS, check_delta
from .report import read_records


def load_factor_source(core, core_info: dict, source: Path) -> dict:
    """검토된 16건 전체만 기준선으로 사용한다. 실패 행을 제외하지 않는다."""
    from .runner import assess_response, request_body
    source = source.resolve()
    manifest = read_json(source / 'manifest.json')
    frozen = manifest['frozen']
    plan = frozen['plan']
    require(manifest['run_sha256'] == digest(frozen), 'manifest 해시 불일치')
    require(frozen.get('extension_version') == '0.4.4.1', 'v0.4.4.1 factor 실행 결과가 필요합니다.')
    require(plan.get('probe_contract') == 'factor-v044', 'factor-v044 결과 폴더를 지정하세요.')
    require(frozen.get('runtime_sources_sha256') == APPROVED_SOURCES,
            '검토된 v0.4.4.1 런타임 지문과 다릅니다.')
    snapshot = source / 'source_snapshot'
    for name, expected in APPROVED_SOURCES.items():
        require(bytes_hash((snapshot / name).read_bytes()) == expected,
                '스냅샷 바이트 불일치: ' + name)
    core_bytes = (snapshot / 'adm_minimal.py').read_bytes()
    require(bytes_hash(core_bytes) == frozen['core']['sha256'], '기록 core의 원본 해시 불일치')
    compatibility = require_core_compatible(source_text_identity(core_bytes), core_info,
                                            '현재 core의 실제 내용이 기록과 다릅니다.')
    cases = plan['cases']
    require(len(cases) == 16 and len({c['case_id'] for c in cases}) == 16,
            '네 군의 16개 고유 조건이 필요합니다.')
    problems = {p['id']: p for p in plan['problems']}
    require(len(problems) == len(plan['problems']), '중복 문제 식별자')
    for p in problems.values():
        core.check_problem(p)
    arm_inputs: dict[str, set[tuple[bool, bool]]] = {}
    for c in cases:
        require(re.fullmatch(r'[a-f0-9]{24}', c['case_id']) is not None, 'case_id 형식 오류')
        require(digest({k: v for k, v in c.items() if k != 'case_id'})[:24] == c['case_id'],
                'case 내용 해시 불일치')
        require(c.get('probe_contract') == 'factor-v044' and c['arm'] in DEFAULT_ARMS,
                '허용하지 않은 비교군')
        p = problems[c['problem_id']]
        require(c['problem_sha256'] == core.digest(p), '문제와 조건 결합 불일치')
        ab = (c['probe_atom'] == p['goal'], c['probe_atom'] in p['facts'])
        require(ab not in arm_inputs.setdefault(c['arm'], set()), '군 안에서 중복된 불리언 입력')
        arm_inputs[c['arm']].add(ab)
    require(set(arm_inputs) == set(DEFAULT_ARMS)
            and all(len(v) == 4 for v in arm_inputs.values()), '네 군의 네 입력이 모두 필요합니다.')
    records = read_records(source, manifest)
    require(len(records) == 16, '실패를 포함한 원문 16건이 모두 필요합니다.')
    replayed, selected, evidence = [], [], []
    for record in records:
        c = record['case']
        p = problems[c['problem_id']]
        folder = source / 'cases' / c['case_id']
        request = read_json(folder / 'request.json')
        raw = read_json(folder / 'response.raw.json')
        body = request_body(frozen['config'], c, p)
        wire = (folder / 'request.wire.json').read_bytes()
        require(request['case_id'] == c['case_id']
                and request['run_sha256'] == manifest['run_sha256'], '요청 식별자 불일치')
        require(wire == wire_json(body).encode('utf-8') == wire_json(request['body']).encode('utf-8'),
                'HTTP 요청의 내용/순서 재현 실패')
        require(request['wire_sha256'] == bytes_hash(wire), 'HTTP 원문 해시 불일치')
        delta = check_delta(c, body)
        outcome, _ = assess_response(core, p, c, plan['reference_depths'][p['id']], body, raw,
                                    frozen['config'].get('mode_policy'))
        # 읽기 전용 진단의 필드 추가는 채점 변경이 아니다. 핵심 판정 객체는 모두 대조한다.
        for field in ('status', 'error', 'audit', 'usage', 'done_reason', 'response_channels'):
            require(record.get(field) == outcome.get(field),
                    f'기존 판정 재현 실패: {c["role_id"]}/{field}')
        replayed.append(dict(record, **outcome))
        evidence.append({'case_id': c['case_id'], 'arm': c['arm'], 'status': outcome['status'],
                         'request_sha256': bytes_hash(wire),
                         'response_sha256': bytes_hash((folder / 'response.raw.json').read_bytes()),
                         'allowed_delta': delta, 'response_content': raw['message']['content']})
        if c['arm'] == 'replay':
            # 성공/실패에 무관하게, 네 입력의 원래 모델 중간값을 선택한다.
            selected.append({'case': copy.deepcopy(c), 'problem': copy.deepcopy(p),
                             'request': copy.deepcopy(body), 'record': dict(record, **outcome)})
    return {'manifest': manifest, 'records': replayed, 'selected': selected,
            'core_compatibility': compatibility,
            'tables': summarize_records(plan, replayed), 'evidence': evidence,
            'validation': {'records_replayed': 16, 'request_wires_reproduced': 16,
                           'selected_inputs': 4, 'source_files_checked': len(APPROVED_SOURCES),
                           'snapshot_code_executed': False, 'network_called': False,
                           'model_called': False, 'original_failures_preserved': True}}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        core, info = load_core()
        data = load_factor_source(core, info, args.input)
        src, out = args.input.resolve(), args.out.resolve()
        require(src != out and not src.is_relative_to(out) and not out.is_relative_to(src),
                '원본과 분리된 결과 폴더를 지정하세요.')
        require(not out.exists() or (out.is_dir() and not any(out.iterdir())), '기존 결과는 덮어쓰지 않습니다.')
        out.mkdir(parents=True, exist_ok=True)
        write_json(out / 'validation.json', data['validation'])
        write_json(out / 'core_compatibility.json', data['core_compatibility'])
        write_json(out / 'decision_tables.json', data['tables'])
        write_json(out / 'evidence.json', data['evidence'])
        write_text(out / 'summary.md', '# factor 원문 재검사\n\nLLM 호출 없음. 원래 판정은 유지합니다.\n'
                   + summary_markdown(data['tables']))
        print(json.dumps({'model_called': False, 'validation': data['validation'],
                          'core_compatibility': data['core_compatibility'],
                          'groups': {k: {j: v[j] for j in ('correct_full_rows', 'correct_bits',
                                     'false_acceptance_count', 'per_field', 'final_field_inconsistency_count')}
                                     for k, v in data['tables'].items()}, 'out': str(out)},
                         ensure_ascii=False, indent=2))
        return 0
    except (ContractError, OSError, ValueError, KeyError, TypeError) as exc:
        print('오류: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
