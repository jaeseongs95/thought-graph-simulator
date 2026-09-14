"""해시 고정 v072 배포 검산기로 종료된 증거를 읽는다. 기존 원문/점수는 수정하지 않는다."""
from pathlib import Path
import copy, os, subprocess, sys, tempfile
import common
PREFIX='llm_experiments/v072/probe/'
SOURCE_SHA='604094b0a9310cb042dce427f5aabfe5cb285afca235d492503972dedb4e1614'
_CACHE={}

def inspect_prior(raw: bytes):
    spec=common.spec();digest=common.sha(raw)
    if digest!=spec['baseline_sha256']:raise ValueError('v072 evidence SHA mismatch')
    source=(common.ROOT/'prior/v072_source.zip').read_bytes()
    if common.sha(source)!=SOURCE_SHA or spec['prior_verifier_source_sha256']!=SOURCE_SHA:
        raise ValueError('prior source SHA mismatch')
    if digest not in _CACHE:
        src=common.unzip(source);manifest=common.load(src.pop('RELEASE_MANIFEST.json'))
        if not common.exact(manifest['file_hashes'],{n:common.sha(b) for n,b in src.items()}) or any(not n.startswith(PREFIX) for n in src):
            raise ValueError('prior release manifest')
        with tempfile.TemporaryDirectory(prefix='v073_prior_') as td:
            root=Path(td)
            for name,data in src.items():common.write(root/name,data)
            evidence=root/'v072.zip';common.write(evidence,raw)
            proc=subprocess.run([sys.executable,'-X','utf8','-B',str(root/PREFIX/'verify.py'),str(evidence)],
                cwd=root/PREFIX,env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1'),
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=180)
            if proc.returncode:raise ValueError('v072 audit failed: '+proc.stderr.decode('utf-8',errors='replace'))
            receipt=common.load(proc.stdout)
        if receipt.get('verified') is not True or receipt.get('state')!='complete' or receipt.get('inference_calls')!=100 or receipt.get('differences'):
            raise ValueError('v072 complete audit missing')
        files=common.unzip(raw);m=common.load(files['MANIFEST.json'])
        if not common.exact(m['file_hashes'],{n:common.sha(b) for n,b in files.items() if n!='MANIFEST.json'}):raise ValueError('prior evidence manifest')
        plan=common.load(files['plan.json'])
        if plan['plan_sha256']!=spec['original_v072_plan_sha256']:raise ValueError('prior plan changed')
        if not common.exact(plan['protocol']['seeds'],spec['seeds']):raise ValueError('prior seeds changed')
        for key in ('compare','shallow','deep'):
            if plan['protocol']['headers'][key]!=spec['headers'][key]:raise ValueError('prior header changed')
        result=common.load(files['summary.json'])['overall']
        observed=[result['depth_reports']['successes'],result['oracle_selection']['successes'],result['model_selection']['successes'],result['model_pipeline']['successes'],result['oracle_pair_successes'],result['model_pipeline_pair_successes'],result['pipeline_ready']]
        if not common.exact(observed,[2,20,26,4,0,2,False]):raise ValueError('v072 result changed')
        if plan['identity']['model']!=spec['model'] or plan['identity']['digest']!=spec['model_digest']:raise ValueError('prior identity')
        request=common.load(files[spec['baseline_request_member']])
        if request['format']!=spec['schema'] or request['options']['num_predict']!=spec['num_predict']:raise ValueError('prior schema/budget changed')
        _CACHE[digest]=(files,plan,request,receipt)
    return copy.deepcopy(_CACHE[digest])
