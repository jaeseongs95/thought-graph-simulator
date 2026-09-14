"""해시 고정 v070 배포 검산기로 직전 실제 증거를 재감사한다. 임의 첨부 코드를 실행하지 않는다."""
from pathlib import Path
import copy, os, subprocess, sys, tempfile
import common
PREFIX = 'llm_experiments/v070/probe/'
SOURCE_SHA = 'c75af924dce0b30ade2cf1b77df0f39d41defd0cd6b838dc5acbb7f441d971f9'
_CACHE = {}

def inspect_prior(raw):
    spec = common.spec()
    digest = common.sha(raw)
    if digest != spec['baseline_sha256']:
        raise ValueError('v070 evidence SHA mismatch')
    source = (common.ROOT / 'prior/v070_source.zip').read_bytes()
    if common.sha(source) != SOURCE_SHA or spec['prior_verifier_source_sha256'] != SOURCE_SHA:
        raise ValueError('prior source SHA mismatch')
    if digest not in _CACHE:
        src = common.unzip(source)
        manifest = common.load(src.pop('RELEASE_MANIFEST.json'))
        if not common.exact(manifest['file_hashes'], {n:common.sha(b) for n,b in src.items()}) or any(not n.startswith(PREFIX) for n in src):
            raise ValueError('prior release manifest')
        with tempfile.TemporaryDirectory(prefix='v071_prior_') as td:
            root = Path(td)
            for name, data in src.items():
                common.write(root/name, data)
            evidence = root/'v070.zip'
            common.write(evidence, raw)
            proc = subprocess.run([sys.executable, '-X','utf8','-B',str(root/PREFIX/'verify.py'),str(evidence)],
                cwd=root/PREFIX,env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1'),
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=180)
            if proc.returncode:
                raise ValueError('v070 audit failed: '+proc.stderr.decode('utf-8',errors='replace'))
            receipt = common.load(proc.stdout)
        if receipt.get('verified') is not True or receipt.get('state')!='complete' or receipt.get('inference_calls')!=40 or receipt.get('differences'):
            raise ValueError('prior complete audit missing')
        files = common.unzip(raw)
        m = common.load(files['MANIFEST.json'])
        if not common.exact(m['file_hashes'], {n:common.sha(b) for n,b in files.items() if n!='MANIFEST.json'}):
            raise ValueError('prior evidence manifest')
        plan = common.load(files['plan.json'])
        if plan['plan_sha256']!=spec['original_v070_plan_sha256'] or not common.exact(plan['protocol']['problems'],spec['prior_problems']):
            raise ValueError('prior plan/problems changed')
        if not common.exact(plan['protocol']['seeds'],spec['seeds']):
            raise ValueError('prior seeds changed')
        result = common.load(files['summary.json'])['overall']
        if result['successes']!=20 or result['paired_successes']!=0 or result['selector_ready'] is not False:
            raise ValueError('v070 observed result changed')
        if plan['identity']['model']!=spec['model'] or plan['identity']['digest']!=spec['model_digest']:
            raise ValueError('prior identity')
        _CACHE[digest]=(files,plan,plan['baseline_request'],receipt)
    # Caller mutations must never change a previously verified cache entry.
    return copy.deepcopy(_CACHE[digest])
