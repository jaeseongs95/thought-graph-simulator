"""v087 원응답 기준선과 결과를 보지 않는 유효 직전 이력 선정."""
from pathlib import Path
import os, subprocess, sys, zipfile
import core088 as core
import bridge088
from baseline087 import validated_prefix

_CACHE = {}
CONTRACT_KEYS = ('identity','model','problems','reference_plans','depth_ranges','seeds','conditions',
 'reference_conditions','candidate_orders','candidate_ids','headers','selector_schema','api_defaults',
 'generation_schema','num_predict','request_utf8_byte_limit','timeout_seconds','id_assignments',
 'frozen_profiles','numeric_compare_schema','lookup_schema','numeric_compare_header','lookup_header',
 'allocated_id_header','allocated_id_prefix','units')

def select_prefix_anchors(archive, protocol):
    """요청 속 직전 이력만 검사한다. 대상 응답·summary·향후 결과를 읽지 않는다."""
    plan=core.load(archive.read('plan.json'));names=set(archive.namelist())
    trials=sorted((t for t in plan['trials'] if t['phase']=='end_to_end' and t['generator_arm']=='baseline'),key=lambda t:t['id'])
    result=[];provenance=[]
    for p in protocol['problems']:
        for kind in ('shallow','deep'):
            path=protocol['reference_plans'][p['id']][protocol['reference_conditions'][int(kind=='deep')]]
            for pos,rid in enumerate(path):
                candidates=[]
                for t in trials:
                    if t['problem_id']!=p['id']:continue
                    sid=t['id']+f'_rule_{pos:02d}';name=f'wire/{sid}/request.wire.json'
                    if name not in names:continue
                    raw=archive.read(name);body=core.load(raw)
                    data=core.load(body['messages'][0]['content'].split('\n\ninput: ',1)[1])
                    if data['provided_route_plan']['rule_ids']!=path or validated_prefix(body) is None:continue
                    candidates.append((t,sid,raw,body))
                if not candidates:raise ValueError('유효 직전 이력 없음: '+p['id']+' '+rid)
                t,sid,raw,body=candidates[0];aid=f'{p["id"]}_{kind}_r{pos:02d}'
                result.append(dict(id=aid,problem_id=p['id'],route_kind=kind,rule_position=pos,rule_id=rid,
                    source_trial_id=t['id'],source_slot_id=sid,source_request_sha256=core.sha(raw),request_body=body))
                provenance.append(dict(anchor_id=aid,source_trial_id=t['id'],valid_prefix_candidates=len(candidates),prefix_valid=True,
                    target_response_used_for_selection=False,future_responses_used_for_selection=False))
    return result,provenance

def validate_inputs(path,run_verifier=True):
    path=Path(path);raw=path.read_bytes();s=core.spec();h=core.sha(raw)
    if h!=s['baseline_sha256']:raise ValueError('v087 baseline hash mismatch')
    if (h,run_verifier) in _CACHE:return _CACHE[h,run_verifier]
    with zipfile.ZipFile(path) as z:
        old=core.load(z.read('plan.json'))
        if old['plan_sha256']!=s['baseline_plan_sha256']:raise ValueError('baseline plan')
        for k in CONTRACT_KEYS:
            if not core.exact(old['protocol'][k],s[k]):raise ValueError('기존 계약 변경 '+k)
        a,provenance=select_prefix_anchors(z,s)
        if not core.exact(a,core.load((core.ROOT/'data/anchors.json').read_bytes())):raise ValueError('anchor mismatch')
        if not core.exact(provenance,core.load((core.ROOT/'data/anchor_provenance.json').read_bytes())):raise ValueError('anchor provenance')
    result=dict(baseline_sha256=h,anchors=len(a),observed_paths=16,new_model_calls=0)
    if run_verifier:
        script=core.ROOT/'frozen087/verify087.py'
        p=subprocess.run([sys.executable,'-X','utf8','-B',str(script),str(path)],cwd=script.parent,
            env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1'),capture_output=True,timeout=600)
        if p.returncode:raise ValueError('이전 독립 검산 실패: '+p.stderr.decode('utf-8',errors='replace'))
        receipt=core.load(p.stdout)
        if receipt.get('verified') is not True or receipt.get('state')!='complete' or receipt.get('observed_calls')!=4080:raise ValueError('이전 evidence 미완료')
        result['prior_receipt']=receipt
    _CACHE[h,run_verifier]=result
    return result
