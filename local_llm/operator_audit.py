"""v0.4.5 연산별 원문 감사. 저장된 Python은 실행하지 않으며 실패도 모두 보존한다."""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path

from .approved_v045 import APPROVED_SOURCES
from .common import (ContractError, bytes_hash, digest, load_core, read_json, require,
                     require_core_compatible, source_text_identity, wire_json,
                     write_json, write_text)
from .operator_probe import OPERATIONS, summary, summary_markdown
from .report import read_records


def load_operator_source(core, info: dict, source: Path) -> dict:
    from .runner import assess_response, request_body
    source = source.resolve()
    manifest = read_json(source / 'manifest.json')
    frozen = manifest['frozen']; plan = frozen['plan']
    require(manifest['run_sha256'] == digest(frozen), 'manifest 해시 불일치')
    require(frozen.get('extension_version') == '0.4.5' and plan.get('probe_contract') == 'operator-v045',
            'v0.4.5 operator 실행 결과가 필요합니다.')
    require(frozen.get('runtime_sources_sha256') == APPROVED_SOURCES, '검토한 v0.4.5 소스 지문과 다릅니다.')
    snapshot = source / 'source_snapshot'
    for name, expected in APPROVED_SOURCES.items():
        require(bytes_hash((snapshot / name).read_bytes()) == expected, '스냅샷 바이트 불일치: ' + name)
    core_bytes = (snapshot / 'adm_minimal.py').read_bytes()
    require(bytes_hash(core_bytes) == frozen['core']['sha256'], '기록 core 원본 해시 불일치')
    compatibility = require_core_compatible(source_text_identity(core_bytes), info,
                                            '현재 core의 실제 내용이 기록과 다릅니다.')
    require(digest(manifest['ollama_metadata']['show']) == frozen['model']['show_sha256'],
            '모델 메타데이터 해시 불일치')
    require(manifest['ollama_metadata']['tag']['digest'] == frozen['model']['digest'] and
            manifest['ollama_metadata']['server'] == frozen['ollama_server'], '모델/서버 기록 불일치')
    cases = plan['cases']
    require(len(cases) == 16 and len({c['case_id'] for c in cases}) == 16, '실패 포함 16개 고유 조건이 필요합니다.')
    problems = {p['id']: p for p in plan['problems']}
    require(len(problems) == len(plan['problems']), '중복 문제 ID')
    for p in problems.values(): core.check_problem(p)
    combos = set()
    for c in cases:
        require(re.fullmatch('[a-f0-9]{24}', c['case_id']) is not None, 'case_id 형식 오류')
        require(digest({k: v for k, v in c.items() if k != 'case_id'})[:24] == c['case_id'], '조건 해시 불일치')
        require(c.get('probe_contract') == 'operator-v045' and c['operation'] in OPERATIONS,
                '허용하지 않은 과제')
        p = problems[c['problem_id']]
        require(c['problem_sha256'] == core.digest(p), '문제와 조건 결합 불일치')
        require(set(c['input_literals']) == {'a', 'b'} and
                all(type(x) is bool for x in c['input_literals'].values()), '정확한 불리언 입력 필요')
        key = c['operation'], c['input_literals']['a'], c['input_literals']['b']
        require(key not in combos, '연산/입력 조합 중복'); combos.add(key)
    require(combos == {(op, a, b) for op in OPERATIONS for a in (False, True) for b in (False, True)},
            '연산별 네 입력이 필요합니다.')
    records = read_records(source, manifest)
    require(len(records) == 16, '실패 포함 원문 응답 16건이 모두 필요합니다.')
    entries, replayed = [], []
    for r in records:
        c = r['case']; p = problems[c['problem_id']]; folder = source / 'cases' / c['case_id']
        request = read_json(folder / 'request.json'); raw = read_json(folder / 'response.raw.json')
        body = request_body(frozen['config'], c, p); wire = (folder / 'request.wire.json').read_bytes()
        require(request['case_id'] == c['case_id'] and request['run_sha256'] == manifest['run_sha256'],
                '요청 식별자 불일치')
        require(wire == wire_json(body).encode('utf-8') == wire_json(request['body']).encode('utf-8'),
                'HTTP 내용/순서 재현 실패')
        require(request['wire_sha256'] == bytes_hash(wire), 'HTTP 해시 불일치')
        outcome, _ = assess_response(core, p, c, plan['reference_depths'][p['id']], body, raw,
                                    frozen['config'].get('mode_policy'))
        for key in ('status', 'error', 'audit', 'usage', 'done_reason', 'response_channels'):
            require(r.get(key) == outcome.get(key), '기존 판정 재현 실패: ' + c['role_id'] + '/' + key)
        record = dict(r, **outcome); replayed.append(record)
        entries.append({'case': copy.deepcopy(c), 'problem': copy.deepcopy(p), 'request': body,
                        'record': record, 'response': raw,
                        'response_sha256': bytes_hash((folder / 'response.raw.json').read_bytes()),
                        'request_sha256': bytes_hash(wire)})
    data = summary(plan, replayed)
    return {'path': source, 'manifest': manifest, 'records': replayed, 'entries': entries,
            'summary': data, 'core_compatibility': compatibility,
            'validation': {'records_replayed': 16, 'request_wires_reproduced': 16,
                           'source_files_checked': len(APPROVED_SOURCES), 'snapshot_code_executed': False,
                           'network_called': False, 'model_called': False,
                           'upstream_projection_checked_against_problem': True,
                           'upstream_new_inference_performed': False,
                           'note': '해시 검사는 보존 파일의 일관성 검사이며 외부 서명 인증이 아니다.'}}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        core, info = load_core(); data = load_operator_source(core, info, args.input)
        src, out = args.input.resolve(), args.out.resolve()
        require(src != out and not src.is_relative_to(out) and not out.is_relative_to(src), '원본과 다른 위치 필요')
        require(not out.exists() or (out.is_dir() and not any(out.iterdir())), '기존 결과는 덮어쓰지 않습니다.')
        out.mkdir(parents=True, exist_ok=True)
        for name in ('validation', 'core_compatibility', 'summary'):
            write_json(out / (name + '.json'), data[name])
        write_json(out / 'evidence.json', data['entries'])
        write_text(out / 'summary.md', '# v0.4.5 원문 감사\n\n새 LLM 호출 없음. 보존된 원문 판정 유지.\n'
                   + summary_markdown(data['summary']))
        print(json.dumps({'validation': data['validation'], 'core_compatibility': data['core_compatibility'],
                          'diagnostic': data['summary']['diagnostic'], 'out': str(out)}, ensure_ascii=False, indent=2))
        return 0
    except (ContractError, OSError, KeyError, TypeError, ValueError) as exc:
        print('오류: ' + str(exc), file=sys.stderr); return 2


if __name__ == '__main__': raise SystemExit(main())
