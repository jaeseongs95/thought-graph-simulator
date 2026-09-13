"""검증된 v062 원자료를 읽어 새 폴더에 오프라인 진단 결과만 보존한다."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from analyze_v062 import analyze
from verify_forensics import verify_report

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_SHA256 = 'baea752ac1a55dc7a20b42b41ced69b3c8e126105f65deea8ebecc8dde3f09fd'


def write_json(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def render_summary(result):
    lines = ['# v062 원자료의 오프라인 실패 진단', '',
             f"모델: {result['model']} / 기록 완료: {result['independent_receipt']['complete']}",
             f"입력 자료 출처: {result['source_evidence_kind']} / 이번 도구의 새 모델 호출: 없음",
             f"원래 진입 판정: {result['official_admission_gate_passed']}", '',
             '원래 증명 점수와 actual_D를 유지한다. 아래 표면 라벨·노드 위치 진단은 성공 점수가 아니다.', '',
             '|조건|관측/배정|형식|유효 증명|strict|공식 지시 이행|마지막 규칙 라벨 일치|목표 라벨 일치|최종 조상 밖 노드 존재|논리 오류가 밖에만 있음|',
             '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for variant, group in result['groups'].items():
        values = [f"{group['observed']}/{group['assigned']}"] + [str(group[key]) for key in (
            'format_valid', 'proof_valid', 'strict_valid', 'instruction_fulfilled',
            'final_rule_label_matches_target', 'final_atom_matches_goal',
            'has_nodes_outside_final_ancestry', 'errors_only_outside_final_ancestry')]
        lines.append('|' + variant + '|' + '|'.join(values) + '|')
    lines += ['', '미관측은 실패로 채우지 않고, 형식상 측정 불가능한 의미 지표는 null로 유지한다.',
              '노드를 삭제하거나 새 증명·보정 깊이를 만들지 않는다. 밖에만 오류가 있어도 원래 전체 풀이의 성공이 아니다.',
              '파싱 상태는 원문에서 다시 계산한다. 이전 parse_error 설명 문자열은 이 보고서의 근거로 사용하지 않는다.',
              '한 문제의 반복 seed 자료이며 인과·일반화·A/M·자유 D 제어를 입증하지 않는다.', '',
              '새 LLM 호출·프롬프트 수정·모델 다운로드는 없다. 세부 원문과 노드 오류는 analysis.json에 보존한다.', '',
              f"입력 ZIP SHA256: {result['bundle_sha256']}",
              f"원래 계획 SHA256: {result['plan_sha256']}"]
    return '\n'.join(lines) + '\n'


def run(bundle, out, expected_sha256=DEFAULT_INPUT_SHA256):
    # Analyze before creating output; invalid evidence does not create a success artifact.
    if out.exists():
        raise FileExistsError('기존 진단 폴더는 덮어쓰지 않습니다: ' + str(out))
    if bundle.stat().st_size > 100 * 1024**2:
        raise ValueError('입력 ZIP 크기 제한을 초과했습니다.')
    if hashlib.sha256(bundle.read_bytes()).hexdigest() != expected_sha256:
        raise ValueError('입력 ZIP이 지정한 SHA256과 다릅니다.')
    result = analyze(bundle)
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / 'analysis.json', result)
    receipt = verify_report(bundle, out / 'analysis.json')
    write_json(out / 'independent.json', receipt)
    with (out / 'summary.ko.md').open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(render_summary(result))
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    completion = {
        'contract': 'v063-offline-diagnostic-completion-r1',
        'completed_at_utc': datetime.now(timezone.utc).isoformat(),
        'input_bundle': str(bundle.resolve()), 'input_sha256': result['bundle_sha256'],
        'new_model_inference': False, 'official_scores_changed': False,
        'artifact_hashes': {name: digest(out / name) for name in
                           ('analysis.json', 'independent.json', 'summary.ko.md')},
        'diagnostic_python_sources': {path.relative_to(ROOT).as_posix(): digest(path)
            for path in sorted(ROOT.rglob('*.py')) if '__pycache__' not in path.parts},
    }
    if digest(bundle) != result['bundle_sha256']:
        raise ValueError('입력 ZIP이 작업 중 변경되었습니다. 완료로 기록하지 않습니다.')
    write_json(out / 'completion.json', completion)
    return completion


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--expected-sha256', default=DEFAULT_INPUT_SHA256,
                        help='기본값은 검토한 v062_construction_01 ZIP의 SHA256')
    args = parser.parse_args()
    print(json.dumps(run(args.bundle, args.out, args.expected_sha256), ensure_ascii=False, indent=2))
