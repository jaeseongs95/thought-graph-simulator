"""사용자가 제출한 v057 다섯 파일을 원문·생산 감사·독립 계산과 대조한다."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

DEPENDENCY = Path(__file__).resolve().parents[3] / 'v057' / 'probe'
sys.path.insert(0, str(DEPENDENCY))
sys.path.insert(0, str(DEPENDENCY / 'tools'))
from selection_probe_v057.contracts import read_plan_json, strict_json, sha
from selection_probe_v057.evidence import safe_unpack
from selection_probe_v057.audit import audit_run
from independent_verify_v057 import verify
from independent_verify_v056 import metadata


def input_files(directory: Path, name: str, experiments_directory: Path | None = None):
    """Resolve the split v057 layout while accepting the original flat layout."""
    experiment_root = experiments_directory or directory.parent / 'experiments'
    files = {}
    for suffix in ('.plan.json', '.plan.baseline.zip', '.preflight.json'):
        legacy = directory / (name + suffix)
        files[suffix] = legacy if legacy.is_file() else experiment_root / (name + suffix)
    for suffix in ('_evidence.zip', '_independent.json'):
        files[suffix] = directory / (name + suffix)
    return files


def validate(directory: Path, name: str, experiments_directory: Path | None = None):
    files = input_files(directory, name, experiments_directory)
    raw = {k: p.read_bytes() for k, p in files.items()}
    with tempfile.TemporaryDirectory(prefix='v058_input_review_') as td:
        root = Path(td)
        safe_unpack(raw['_evidence.zip'], root)
        if raw['.plan.json'] != (root / 'external_plan/v057.plan.json').read_bytes():
            raise ValueError('외부 계획과 증거 계획 바이트 불일치')
        if raw['.plan.baseline.zip'] != (root / 'run/baseline/v056_evidence.zip').read_bytes():
            raise ValueError('별도 기준선과 내장 기준선 바이트 불일치')
        plan = read_plan_json(files['.plan.json'])
        pre = strict_json(raw['.preflight.json'])
        if not (pre['contract'] == 'v057-preflight-r1' and pre['plan_sha256'] == plan['plan_sha256']
                and pre['state'] == 'complete' and pre['failure'] is None and pre['inference_calls'] == 0):
            raise ValueError('사전 검사 계획/완료 상태 불일치')
        if set(pre['metadata']) != set(plan['identities']):
            raise ValueError('사전 검사 모델 목록 불일치')
        for key, identity in plan['identities'].items():
            if metadata(pre['metadata'][key], identity) is not None:
                raise ValueError('사전 검사 identity 불일치: ' + key)
        production = audit_run(root / 'external_plan/v057.plan.json', root / 'run', write_report=False)
        if production != strict_json((root / 'run/summary.json').read_bytes()):
            raise ValueError('생산 원문 재감사와 저장 요약 불일치')
    independent = verify(files['_evidence.zip'])
    if independent != strict_json(raw['_independent.json']):
        raise ValueError('독립 재계산과 제출 검산 불일치')
    return {'contract': 'v058-input-review-r1', 'input_sha256': {files[k].name: sha(v) for k, v in raw.items()},
            'external_plan_bytes_equal': True, 'baseline_bytes_equal': True, 'preflight_identity_valid': True,
            'production_summary_equal': True, 'independent_report_equal': True,
            'independent': independent, 'new_model_inference': False,
            'limitation': '해시·원문 일관성 검사이며 외부 실행을 인증하는 전자서명은 아니다.'}


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--directory', type=Path, required=True)
    ap.add_argument('--experiments-directory', type=Path)
    ap.add_argument('--name', default='v057_selection_01')
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()
    result = validate(a.directory, a.name, a.experiments_directory)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with a.out.open('x', encoding='utf-8', newline='\n') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')
    print('5 inputs, production audit, independent audit: PASS')
