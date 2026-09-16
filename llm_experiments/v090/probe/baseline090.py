"""기존 v089 evidence와 계약·동결 소스 확인. 과거 응답을 새 facts로 사용하지 않는다."""
from pathlib import Path
import os
import subprocess
import sys
import zipfile
import core090 as core

CONTRACT_KEYS = ('identity','model','problems','reference_plans','depth_ranges','seeds','conditions',
    'reference_conditions','candidate_orders','candidate_ids','headers','selector_schema','api_defaults',
    'generation_schema','num_predict','request_utf8_byte_limit','timeout_seconds','id_assignments',
    'frozen_profiles','numeric_compare_schema','lookup_schema','numeric_compare_header','lookup_header',
    'allocated_id_header','allocated_id_prefix','units')
_CACHE = {}


def validate_inputs(path, run_verifier=True):
    path = Path(path)
    s = core.spec()
    digest = core.sha(path.read_bytes())
    if digest != s['baseline_sha256']:
        raise ValueError('v089 baseline ZIP SHA-256 불일치')
    if (digest, run_verifier) in _CACHE:
        return _CACHE[digest, run_verifier]
    with zipfile.ZipFile(path) as z:
        plan = core.load(z.read('plan.json'))
        if plan['plan_sha256'] != s['baseline_plan_sha256']:
            raise ValueError('v089 기준선 plan 불일치')
        for key in CONTRACT_KEYS:
            if not core.exact(plan['protocol'][key], s[key]):
                raise ValueError('유지할 기존 계약 변경: ' + key)
        frozen = core.ROOT/'frozen089'
        local = {p.relative_to(frozen).as_posix(): p.read_bytes() for p in frozen.rglob('*')
                 if p.is_file() and '__pycache__' not in p.parts}
        original = {n[7:]: z.read(n) for n in z.namelist() if n.startswith('source/')}
        if local != original:
            raise ValueError('v089 동결 소스가 실제 원본과 다름')
    result = dict(baseline_sha256=digest, retained_source_files=len(local),
                  old_responses_reused_as_facts=0, new_model_calls=0)
    if run_verifier:
        script = frozen/'verify089.py'
        p = subprocess.run([sys.executable,'-X','utf8','-B',str(script),str(path)], cwd=frozen,
            env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1'), capture_output=True)
        if p.returncode:
            raise ValueError('v089 독립 검산 실패: ' + p.stderr.decode('utf-8',errors='replace'))
        receipt = core.load(p.stdout)
        if (receipt.get('verified') is not True or receipt.get('state') != 'complete'
                or receipt.get('observed_calls') != 3824):
            raise ValueError('v089 기준선 미완료/검산 불일치')
        result['prior_receipt'] = receipt
    _CACHE[digest,run_verifier] = result
    return result
