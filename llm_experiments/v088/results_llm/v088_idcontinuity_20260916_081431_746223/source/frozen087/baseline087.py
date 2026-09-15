"""기준 evidence·동결 입력·유효 원문 anchor를 검사한다. 이전 성과를 새 표본으로 더하지 않는다."""
from pathlib import Path
import os,subprocess,sys,zipfile
from copy import deepcopy
import core087 as core

_CACHE={}

def validated_prefix(body):
    """대상 응답과 이후 graph를 읽지 않고 직전 이력만 의미 검산한다."""
    import bridge087
    from audit_model import stage_shape
    from audit_rows087 import step_check
    from collections import Counter
    try:
        data=core.load(body['messages'][0]['content'].split('\n\ninput: ',1)[1])
        problem=data['problem'];history=data['history'];path=data['provided_route_plan']['rule_ids'];index=data['operation']['index']
        if index<1 or len(history)!=index or data['operation']['requested_rule_id']!=path[index-1]:return None
        nodes=[]
        for pos,h in enumerate(history):
            obj=core.load(h['content']);stage='facts' if pos==0 else 'rule'
            if not stage_shape(stage,obj):return None
            if pos==0:
                ns=obj['nodes']
                if Counter(n['atom']for n in ns)!=Counter(problem['facts']):return None
                if any(n['rule']is not None or n['parents']for n in ns):return None
                if len({n['id']for n in ns})!=len(ns):return None
                nodes.extend(ns)
            else:
                if not step_check(problem,nodes,obj['node'],path[pos-1])['valid']:return None
                nodes.append(obj['node'])
        return nodes
    except (ValueError,KeyError,IndexError,TypeError,UnicodeError):return None


def select_prefix_anchors(z,s):
    """70개 규칙 각각에 대해 유효 prefix의 최초 trial을 고른다. target response/summary는 읽지 않는다."""
    plan=core.load(z.read('plan.json'));names=set(z.namelist());anchors=[];provenance=[]
    trials=sorted([t for t in plan['trials']if t['selector_variant']=='two_stage_values'and t['metric']=='D'],key=lambda t:t['id'])
    for problem in s['problems']:
        for kind in ('shallow','deep'):
            path=s['reference_plans'][problem['id']][s['reference_conditions'][int(kind=='deep')]]
            for pos,rid in enumerate(path):
                eligible=[]
                for t in trials:
                    if t['problem_id']!=problem['id']:continue
                    sid=t['id']+f'_rule_{pos:02d}';name='wire/'+sid+'/request.wire.json'
                    if name not in names:continue
                    raw=z.read(name);body=core.load(raw)
                    data=core.load(body['messages'][0]['content'].split('\n\ninput: ',1)[1])
                    if data['provided_route_plan']['rule_ids']!=path or validated_prefix(body)is None:continue
                    eligible.append((t,sid,raw,body))
                if not eligible:raise ValueError('no valid preceding history for '+problem['id']+' '+rid)
                t,sid,raw,body=eligible[0];aid=f"{problem['id']}_{kind}_r{pos:02d}"
                anchors.append({'id':aid,'problem_id':problem['id'],'route_kind':kind,'rule_position':pos,'rule_id':rid,
                                'source_trial_id':t['id'],'source_slot_id':sid,'source_request_sha256':core.sha(raw),'request_body':body})
                provenance.append({'anchor_id':aid,'source_trial_id':t['id'],'valid_prefix_candidates':len(eligible),
                                   'prefix_valid':True,'target_response_used_for_selection':False,'future_responses_used_for_selection':False})
    return anchors,provenance


def validate_inputs(path,run_verifier=True):
    path=Path(path);s=core.spec();raw=path.read_bytes();key=core.sha(raw)
    if key!=s['baseline_sha256']:raise ValueError('v086 baseline hash mismatch')
    if (key,run_verifier) in _CACHE:return _CACHE[key,run_verifier]
    with zipfile.ZipFile(path) as z:
        manifest=core.load(z.read('MANIFEST.json'));bp=core.load(z.read('plan.json'))
        if bp['plan_sha256']!=s['baseline_plan_sha256']:raise ValueError('baseline plan mismatch')
        old=bp['protocol']
        keys=['identity','model','problems','reference_plans','depth_ranges','seeds','conditions','reference_conditions','candidate_orders','candidate_ids','headers','selector_schema','api_defaults','generation_schema','num_predict','request_utf8_byte_limit','timeout_seconds','id_assignments','frozen_profiles','numeric_compare_schema','lookup_schema','numeric_compare_header','lookup_header']
        for k in keys:
            if not core.exact(s[k],old[k]):raise ValueError('frozen input drift: '+k)
        rawanchors=(core.ROOT/'data/anchors.json').read_bytes()
        if core.sha(rawanchors)!=s['anchors_sha256']:raise ValueError('anchor source hash')
        anchors=core.load(rawanchors)
        if [a['id'] for a in anchors]!=s['anchor_ids'] or len(anchors)!=70:raise ValueError('anchor schedule')
        units=[{k:t[k] for k in ('unit_id','block','problem_id','seed','candidate_order_index','id_assignment_index','condition','base_pair_id')} for t in bp['trials'] if t['selector_variant']=='two_stage_values' and t['metric']=='D']
        if not core.exact(units,s['units']):raise ValueError('logical condition drift')
        reconstructed,provenance=select_prefix_anchors(z,s)
        if not core.exact(anchors,reconstructed):raise ValueError('valid-prefix anchor policy mismatch')
        if not core.exact(core.load((core.ROOT/'data/anchor_provenance.json').read_bytes()),provenance):
            raise ValueError('anchor provenance mismatch')
    result={'baseline_sha256':key,'anchors':70,'observed_paths':16,'new_model_calls':0}
    if run_verifier:
        script=core.ROOT/'frozen086/verify086.py'
        proc=subprocess.run([sys.executable,'-X','utf8','-B',str(script),str(path)],cwd=script.parent,
                            env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1'),capture_output=True,timeout=600)
        if proc.returncode:raise ValueError('previous independent verifier: '+proc.stderr.decode('utf-8',errors='replace'))
        receipt=core.load(proc.stdout)
        if receipt.get('verified') is not True or receipt.get('state')!='complete' or receipt.get('observed_calls')!=s['baseline_observed_calls']:raise ValueError('baseline not complete/verified')
        result['prior_receipt']=receipt
    _CACHE[key,run_verifier]=result
    return result
