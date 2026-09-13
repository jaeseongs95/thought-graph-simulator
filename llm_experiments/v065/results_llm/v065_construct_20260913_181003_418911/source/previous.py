"""검토된 v064 배포본으로 기존 원문을 검산한다. 증거의 source snapshot은 실행하지 않는다."""
from __future__ import annotations
import json,os,subprocess,sys,tempfile
from pathlib import Path
import common
SOURCE_SHA='238b4997ceaa4191fb79498cc12647010bd02056cf7ac96a0ca0752712ff4553'
PREFIX='llm_experiments/v064/probe/'
_RECEIPTS={}

def inspect_prior(raw:bytes):
    spec=common.spec();digest=common.sha(raw)
    if digest!=spec['baseline_sha256']:raise ValueError('v064 evidence SHA-256 mismatch')
    packed=(common.ROOT/'prior/v064_source_r3.zip').read_bytes()
    if common.sha(packed)!=SOURCE_SHA or spec['prior_verifier_source_sha256']!=SOURCE_SHA:raise ValueError('pinned v064 verifier source changed')
    key=(digest,SOURCE_SHA)
    if key not in _RECEIPTS:
        source=common.unzip(packed);manifest=common.load(source.pop('RELEASE_MANIFEST.json'))
        if not common.exact(manifest['file_hashes'],{k:common.sha(v) for k,v in source.items()}):raise ValueError('prior verifier package manifest')
        if not all(n.startswith(PREFIX) for n in source):raise ValueError('prior source prefix')
        with tempfile.TemporaryDirectory(prefix='v065_prior_audit_') as td:
            root=Path(td)
            for n,b in source.items():common.write(root/n,b)
            evidence=root/'v064_evidence.zip';common.write(evidence,raw)
            env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1')
            call=subprocess.run([sys.executable,'-X','utf8','-B',str(root/PREFIX/'verify.py'),str(evidence)],cwd=root/PREFIX,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120)
            if call.returncode:raise ValueError('v064 independent audit failed: '+call.stderr.decode('utf-8',errors='replace'))
            receipt=common.load(call.stdout)
            if receipt.get('verified') is not True or receipt.get('differences') or receipt.get('state')!='complete' or receipt.get('inference_calls')!=18:raise ValueError('v064 incomplete/invalid receipt')
            _RECEIPTS[key]=receipt
    files=common.unzip(raw);manifest=common.load(files['MANIFEST.json'])
    if not common.exact(manifest['file_hashes'],{n:common.sha(b) for n,b in files.items() if n!='MANIFEST.json'}):raise ValueError('v064 manifest mismatch')
    plan=common.load(files['plan.json'])
    if plan['plan_sha256']!=spec['original_v064_plan_sha256']:raise ValueError('original v064 plan changed')
    if not common.exact(plan['protocol']['problems'],spec['problems']) or not common.exact(plan['protocol']['seeds'],spec['seeds']):raise ValueError('v064 problems/seeds changed')
    if not common.exact(plan['protocol']['depth_ranges'],spec['depth_ranges']):raise ValueError('v064 depths changed')
    request=common.load(files['wire/'+spec['baseline_request_id']+'/request.wire.json'])
    if request['model']!=spec['model'] or plan['identity']['digest']!=spec['model_digest']:raise ValueError('prior model identity changed')
    return files,plan,request,_RECEIPTS[key]
