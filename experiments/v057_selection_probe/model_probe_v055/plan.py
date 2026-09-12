"""모델 metadata를 먼저 동결하고, 이후 prepare는 오프라인으로 수행한다."""
from __future__ import annotations
from copy import deepcopy
from . import __version__
from .contracts import *
from .design import MODELS, CANDIDATE, MAX_CALLS, POLICY, PROBLEMS, ARMS, DIRECTIONS, RULE_ORDERS, schedule, actions
from .metadata import validate_pair

def prepare(bundle, capture_path, out):
    from .evidence import import_v054
    require(not out.exists(),'기존 계획 덮어쓰기 금지')
    baseline,reference=import_v054(bundle)
    cap=read_json(capture_path)
    previous=strict_json(unb64(reference['plan_b64']))
    plan={'contract':'model-probe-v055-r1','software_version':__version__,'created_at':utc_now(),
        'baseline':baseline,'reference':reference,'capture':cap,
        'identities':validate_pair(cap['metadata'],baseline),'model_keys':list(MODELS),
        'problems':deepcopy(PROBLEMS),'arms':list(ARMS),'directions':list(DIRECTIONS),'rule_orders':deepcopy(RULE_ORDERS),
        'seeds':previous['seeds'],'max_calls':MAX_CALLS,'policy':deepcopy(POLICY),
        'slots':schedule(previous),'source_fingerprint':source_fingerprint()}
    plan['actions']=actions(plan['slots']);plan['plan_sha256']=digest(plan)
    validate_plan(plan);write_json(out,plan,exclusive=True)
    stored=read_plan_json(out)
    require(canonical(stored)==canonical(plan),'v055 계획 저장/재읽기 불일치')
    return plan

def validate_plan(plan, *, check_sources=True):
    from order_probe_v054.plan import validate_plan as validate_previous
    from order_probe_v054.requests import request_bytes as previous_request
    keys={'contract','software_version','created_at','baseline','reference','capture','identities','model_keys',
        'problems','arms','directions','rule_orders','seeds','max_calls','policy','slots','source_fingerprint','actions','plan_sha256'}
    require(isinstance(plan,dict) and set(plan)==keys,'v055 계획 필드 불일치')
    require(plan['contract']=='model-probe-v055-r1' and plan['software_version']==__version__,'계약/버전 변경')
    require(plan['plan_sha256']==digest({k:v for k,v in plan.items() if k!='plan_sha256'}),'계획 해시 불일치')
    ref=plan['reference']
    refkeys={'contract','bundle_sha256','plan_b64','plan_bytes_sha256','plan_sha256','event_tip','recorded_calls','evidence_kind','request_bank','request_bank_sha256','note','receipt_sha256'}
    require(isinstance(ref,dict) and set(ref)==refkeys and ref['contract']=='audited-v054-reference-r1','v054 기준선 영수증 필드')
    require(ref['receipt_sha256']==digest({k:v for k,v in ref.items() if k!='receipt_sha256'}),'기준선 영수증 해시')
    raw=unb64(ref['plan_b64']);require(sha(raw)==ref['plan_bytes_sha256'],'기준선 계획 바이트')
    previous=strict_json(raw);validate_previous(previous,check_sources=check_sources)
    require(ref['plan_sha256']==previous['plan_sha256'] and type(ref['recorded_calls']) is int and ref['recorded_calls']==120,'기준선 계획/호출수')
    require(canonical(plan['baseline'])==canonical(previous['baseline']),'원래 기준선 변경')
    require(ref['evidence_kind']==plan['baseline']['evidence_kind'],'실제/합성 출처 변경')
    require(ref['request_bank_sha256']==digest(ref['request_bank']),'요청 은행 해시')
    require(set(ref['request_bank'])=={s['id'] for s in previous['slots']},'원래 120요청 누락/추가')
    for slot in previous['slots']:
        require(unb64(ref['request_bank'][slot['id']])==previous_request(previous,slot),'기준선 동결 요청 변경: '+slot['id'])
    cap=plan['capture']
    capkeys={'contract','state','created_at','baseline_bundle_sha256','endpoint','source_fingerprint','metadata','identities','error','inference_calls'}
    require(isinstance(cap,dict) and set(cap)==capkeys and cap['contract']=='v055-metadata-capture-r1','capture 형식')
    require(cap['state']=='complete' and cap['error'] is None and type(cap['inference_calls']) is int and cap['inference_calls']==0,'완료된 무추론 capture 필요')
    require(cap['baseline_bundle_sha256']==ref['bundle_sha256'] and cap['endpoint']==plan['baseline']['config']['endpoint'],'capture 기준선/endpoint 변경')
    require(cap['source_fingerprint']==plan['source_fingerprint'],'capture 이후 소스 변경')
    ids=validate_pair(cap['metadata'],plan['baseline'])
    require(canonical(ids)==canonical(plan['identities'])==canonical(cap['identities']),'모델 identity snapshot 불일치')
    expected={'model_keys':list(MODELS),'problems':PROBLEMS,'arms':list(ARMS),'directions':list(DIRECTIONS),
        'rule_orders':RULE_ORDERS,'seeds':previous['seeds'],'max_calls':MAX_CALLS,'policy':POLICY,'slots':schedule(previous)}
    expected['actions']=actions(expected['slots'])
    for key,value in expected.items():require(canonical(plan[key])==canonical(value),'계획 조건 변경: '+key)
    require(type(plan['max_calls']) is int and len(plan['seeds'])==10,'실험 크기 변경')
    if check_sources:require(plan['source_fingerprint']==source_fingerprint(),'계획 이후 소스 변경')
