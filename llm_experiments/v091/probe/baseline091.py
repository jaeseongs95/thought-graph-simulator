"""v090 원 evidence와 보존 소스를 대조한다. 원응답은 새 모델 입력으로 재사용하지 않는다."""
from pathlib import Path
import os,subprocess,sys,zipfile
import core091 as core
CONTRACT_KEYS=('identity','model','seeds','conditions','reference_conditions','candidate_orders','candidate_ids','headers',
    'selector_schema','api_defaults','generation_schema','num_predict','request_utf8_byte_limit','timeout_seconds','id_assignments',
    'numeric_compare_schema','lookup_schema','numeric_compare_header','lookup_header','allocated_id_header','allocated_id_prefix',
    'facts_id_header','generator_arms','styles')
_CACHE={}


def validate_inputs(path,run_verifier=True):
    path=Path(path);s=core.spec();digest=core.sha(path.read_bytes())
    if digest!=s['baseline_sha256']:raise ValueError('v090 기준선 ZIP SHA 불일치')
    if (digest,run_verifier) in _CACHE:return _CACHE[digest,run_verifier]
    with zipfile.ZipFile(path) as z:
        plan=core.load(z.read('plan.json'))
        if plan['plan_sha256']!=s['baseline_plan_sha256']:raise ValueError('v090 기준선 plan 불일치')
        snapshot=core.load((core.ROOT/'data/protocol_v090_snapshot.json').read_bytes())
        if not core.exact(plan['protocol'],snapshot):raise ValueError('v090 protocol snapshot 불일치')
        for k in CONTRACT_KEYS:
            if not core.exact(s[k],snapshot[k]):raise ValueError('동결 생성·선택 계약 변경: '+k)
        frozen=core.ROOT/'frozen090'
        local={p.relative_to(frozen).as_posix():p.read_bytes() for p in frozen.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
        actual={n[7:]:z.read(n) for n in z.namelist() if n.startswith('source/')}
        if local!=actual:raise ValueError('v090 보존 소스 불일치')
    result=dict(baseline_sha256=digest,retained_source_files=len(local),old_responses_reused_as_facts=0,new_model_calls=0)
    if run_verifier:
        p=subprocess.run([sys.executable,'-X','utf8','-B',str(frozen/'verify090.py'),str(path)],cwd=frozen,
            env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1'),capture_output=True)
        if p.returncode:raise ValueError('v090 검산 실패: '+p.stderr.decode('utf-8',errors='replace'))
        r=core.load(p.stdout)
        if r.get('verified') is not True or r.get('state')!='complete':raise ValueError('v090 완료 기준선 아님')
        result['prior_receipt']=r
    _CACHE[digest,run_verifier]=result
    return result
