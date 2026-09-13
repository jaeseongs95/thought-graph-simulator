"""동결 v065 배포 감사기로 이전 원문을 확인한다. evidence snapshot은 실행하지 않는다."""
from pathlib import Path
import os,subprocess,sys,tempfile,copy
import common
PREFIX='llm_experiments/v065/probe/'
SOURCE_SHA='6c399d7a017ffb465dd78be589a66a18942524fd4e2bebd63ded6f456b94cc5b'
_CACHE={}
def inspect_prior(raw):
    spec=common.spec();digest=common.sha(raw)
    if digest!=spec['baseline_sha256']:raise ValueError('v065 evidence SHA mismatch')
    packed=(common.ROOT/'prior/v065_source.zip').read_bytes()
    if common.sha(packed)!=SOURCE_SHA or spec['prior_verifier_source_sha256']!=SOURCE_SHA:raise ValueError('pinned v065 source mismatch')
    if (digest,SOURCE_SHA) not in _CACHE:
        files=common.unzip(packed);m=common.load(files.pop('RELEASE_MANIFEST.json'))
        if not common.exact(m['file_hashes'],{n:common.sha(b) for n,b in files.items()}) or not all(n.startswith(PREFIX) for n in files):raise ValueError('pinned package layout/hash')
        with tempfile.TemporaryDirectory(prefix='v066_prior_') as td:
            root=Path(td)
            for n,b in files.items():common.write(root/n,b)
            evidence=root/'v065.zip';common.write(evidence,raw)
            r=subprocess.run([sys.executable,'-X','utf8','-B',str(root/PREFIX/'verify.py'),str(evidence)],cwd=root/PREFIX,env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1'),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120)
            if r.returncode:raise ValueError('prior independent failed: '+r.stderr.decode('utf-8',errors='replace'))
            receipt=common.load(r.stdout)
            if receipt.get('verified') is not True or receipt.get('state')!='complete' or receipt.get('inference_calls')!=12 or receipt.get('differences'):raise ValueError('prior receipt')
            _CACHE[digest,SOURCE_SHA]=receipt
    files=common.unzip(raw);m=common.load(files['MANIFEST.json'])
    if not common.exact(m['file_hashes'],{n:common.sha(b) for n,b in files.items() if n!='MANIFEST.json'}):raise ValueError('prior member hash')
    p=common.load(files['plan.json'])
    if p['plan_sha256']!=spec['original_v065_plan_sha256']:raise ValueError('prior plan hash')
    for k in ('problems','seeds','depth_ranges'):
        if not common.exact(p['protocol'][k],spec[k]):raise ValueError('fixed '+k+' mismatch')
    if p['identity']['model']!=spec['model'] or p['identity']['digest']!=spec['model_digest']:raise ValueError('model mismatch')
    return files,p,copy.deepcopy(p['baseline_request']),_CACHE[digest,SOURCE_SHA]
