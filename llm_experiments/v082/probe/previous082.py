"""해시 고정된 v081 종료 증거의 기존 독립 검산을 재실행한다. 새 성과로 합산하지 않는다."""
from pathlib import Path
import os, subprocess, sys, tempfile
import core082 as common
_CACHE={}

def audit(raw):
    s=common.spec();h=common.sha(raw)
    if h!=s['baseline_sha256']:raise ValueError('baseline hash')
    if h in _CACHE:return _CACHE[h]
    source=(common.ROOT/'prior/v081_source.zip').read_bytes()
    if common.sha(source)!=s['prior_verifier_source_sha256']:raise ValueError('prior source hash')
    files=common.unzip(source);manifest=common.load(files.pop('RELEASE_MANIFEST.json'))
    if not common.exact(manifest['file_hashes'],{n:common.sha(b) for n,b in files.items()}):raise ValueError('prior source manifest')
    with tempfile.TemporaryDirectory(prefix='v082_prior_') as d:
        root=Path(d)
        for n,b in files.items():common.write(root/n,b)
        path=root/'baseline.zip';common.write(path,raw)
        script=root/'llm_experiments/v081/probe/verify081.py'
        proc=subprocess.run([sys.executable,'-X','utf8','-B',str(script),str(path)],cwd=script.parent,
                            env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1'),
                            stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=180)
        if proc.returncode:raise ValueError('v081 audit failed: '+proc.stderr.decode('utf-8',errors='replace'))
        receipt=common.load(proc.stdout)
    if (receipt.get('verified') is not True or receipt.get('state')!='complete' or
        receipt.get('inference_calls')!=s['prior_observed_calls'] or receipt.get('differences')):raise ValueError('v081 not complete/consistent')
    z=common.unzip(raw)
    if common.load(z['plan.json'])['plan_sha256']!=s['baseline_plan_sha256']:raise ValueError('v081 plan')
    _CACHE[h]=receipt
    return receipt
