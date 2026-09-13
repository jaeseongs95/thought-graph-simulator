"""별도 고정 배포본으로 실제 v066 전체 원문을 검산한다. 임의 snapshot 실행 없음."""
from pathlib import Path
import os,subprocess,sys,tempfile,copy
import common
PREFIX='llm_experiments/v066/probe/'
SOURCE_SHA='375d5fd79bc81a4b547d07567a97eb33d8e8176256b24d013c87c54f97785331'
_CACHE={}
def inspect_prior(raw):
    spec=common.spec();digest=common.sha(raw)
    if digest!=spec['baseline_sha256']:raise ValueError('v066 evidence SHA mismatch')
    source=(common.ROOT/'prior/v066_source.zip').read_bytes()
    if common.sha(source)!=SOURCE_SHA or spec['prior_verifier_source_sha256']!=SOURCE_SHA:raise ValueError('prior source SHA mismatch')
    if (digest,SOURCE_SHA) not in _CACHE:
        files=common.unzip(source);m=common.load(files.pop('RELEASE_MANIFEST.json'))
        if not common.exact(m['file_hashes'],{n:common.sha(b) for n,b in files.items()}) or any(not n.startswith(PREFIX) for n in files):raise ValueError('prior source manifest')
        with tempfile.TemporaryDirectory(prefix='v067_prior_') as td:
            root=Path(td)
            for n,b in files.items():common.write(root/n,b)
            evidence=root/'v066.zip';common.write(evidence,raw)
            proc=subprocess.run([sys.executable,'-X','utf8','-B',str(root/PREFIX/'verify.py'),str(evidence)],cwd=root/PREFIX,env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1'),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=180)
            if proc.returncode:raise ValueError('v066 audit failed: '+proc.stderr.decode('utf-8',errors='replace'))
            rec=common.load(proc.stdout)
            if rec.get('verified') is not True or rec.get('state')!='complete' or rec.get('inference_calls')!=36 or rec.get('differences'):raise ValueError('prior incomplete audit')
            _CACHE[digest,SOURCE_SHA]=rec
    f=common.unzip(raw);m=common.load(f['MANIFEST.json'])
    if not common.exact(m['file_hashes'],{n:common.sha(b) for n,b in f.items() if n!='MANIFEST.json'}):raise ValueError('prior manifest')
    p=common.load(f['plan.json'])
    if p['plan_sha256']!=spec['original_v066_plan_sha256']:raise ValueError('prior plan changed')
    for k in ('problems','seeds','depth_ranges'):
        if not common.exact(p['protocol'][k],spec[k]):raise ValueError('prior specification changed: '+k)
    if p['identity']['model']!=spec['model'] or p['identity']['digest']!=spec['model_digest']:raise ValueError('prior identity')
    return f,p,copy.deepcopy(p['baseline_request']),_CACHE[digest,SOURCE_SHA]
