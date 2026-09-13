"""준비는 오프라인이다. 원 v056 전체를 감사하고 두 모델 merged 조건을 동일하게 사용한다."""
from copy import deepcopy
from .contracts import *
from .design import MODELS,MODES,REFERENCE_LAYOUT,MAX_CALLS,POLICY,PROBLEMS,ARMS,DIRECTIONS,RULE_ORDERS,schedule,actions
from . import __version__

def make_plan(reference):
    p={'contract':'selection-probe-v057-r1','software_version':__version__,'created_at':utc_now(),
       'reference':deepcopy(reference),'baseline':{'config':deepcopy(reference['config'])},'identities':deepcopy(reference['identities']),
       'model_keys':list(MODELS),'modes':list(MODES),'reference_layout':REFERENCE_LAYOUT,'problems':deepcopy(PROBLEMS),
       'arms':list(ARMS),'directions':list(DIRECTIONS),'rule_orders':deepcopy(RULE_ORDERS),'seeds':reference['seeds'],
       'max_calls':MAX_CALLS,'policy':deepcopy(POLICY),'slots':schedule(reference),'source_fingerprint':source_fingerprint()}
    p['actions']=actions(p['slots']);p['plan_sha256']=digest(p);validate_plan(p);return p

def prepare(bundle,out):
    from .evidence import import_v056
    require(not out.exists() and not out.with_suffix('.baseline.zip').exists(),'기존 계획/기준선 보존')
    ref=import_v056(bundle);p=make_plan(ref);raw=bundle.read_bytes();require(sha(raw)==ref['bundle_sha256'],'계획 준비 중 기준선 변경')
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.with_suffix('.baseline.zip').open('xb') as f:f.write(raw)
    write_json(out,p,exclusive=True);require(canonical(read_plan_json(out))==canonical(p),'계획 저장 재읽기 불일치');return p

def validate_plan(p,*,check_sources=True):
    fields={'contract','software_version','created_at','reference','baseline','identities','model_keys','modes','reference_layout',
            'problems','arms','directions','rule_orders','seeds','max_calls','policy','slots','source_fingerprint','actions','plan_sha256'}
    require(isinstance(p,dict) and set(p)==fields,'계획 필드')
    require(p['contract']=='selection-probe-v057-r1' and p['software_version']==__version__,'계약/버전')
    require(p['plan_sha256']==digest({k:v for k,v in p.items() if k!='plan_sha256'}),'계획 해시')
    ref=p['reference'];fields={'contract','bundle_sha256','plan_sha256','event_tip','recorded_calls','selected_calls','selected_layout',
        'evidence_kind','config','identities','seeds','slots','request_bank','receipt_sha256'}
    require(isinstance(ref,dict) and set(ref)==fields and ref['contract']=='audited-v056-compact-r1','기준선 영수증 필드')
    require(ref['receipt_sha256']==digest({k:v for k,v in ref.items() if k!='receipt_sha256'}),'기준선 영수증 해시')
    require(type(ref['recorded_calls']) is int and ref['recorded_calls']==480 and type(ref['selected_calls']) is int and ref['selected_calls']==240,'기준선 호출수')
    require(ref['selected_layout']==REFERENCE_LAYOUT and len(ref['slots'])==240,'공통 기준 배치')
    require(len(ref['seeds'])==10 and len(set(ref['seeds']))==10 and all(type(s) is int for s in ref['seeds']),'10 seed')
    require(set(ref['request_bank'])=={s['id'] for s in ref['slots']},'기준선 요청 누락/추가')
    require(set(ref['identities'])==set(MODELS),'두 모델 식별자')
    require(ref['identities']['reference']['digest']!=ref['identities']['candidate']['digest'],'같은 모델 중복 비교')
    require(ref['evidence_kind'] in ('live_source_artifacts','synthetic_fixture'),'출처')
    for s in ref['slots']:
        require(s['layout']==REFERENCE_LAYOUT,'기준 배치 변경')
        q=strict_json(unb64(ref['request_bank'][s['id']]))
        require(q['model']==ref['identities'][s['model_key']]['model'] and q['options']['seed']==s['seed'],'모델/seed')
        require(len(q['messages'])==1 and set(q['messages'][0])=={'role','content'} and q['messages'][0]['role']=='user','기준 user 메시지 하나')
    expected={'baseline':{'config':ref['config']},'identities':ref['identities'],'model_keys':list(MODELS),'modes':list(MODES),
              'reference_layout':REFERENCE_LAYOUT,'problems':PROBLEMS,'arms':list(ARMS),'directions':list(DIRECTIONS),
              'rule_orders':RULE_ORDERS,'seeds':ref['seeds'],'max_calls':MAX_CALLS,'policy':POLICY,'slots':schedule(ref)}
    expected['actions']=actions(expected['slots'])
    for k,v in expected.items():require(canonical(p[k])==canonical(v),'동결 조건 변경: '+k)
    require(type(p['max_calls']) is int and len(p['slots'])==480 and len(p['actions'])==520,'실험 크기')
    if check_sources:require(p['source_fingerprint']==source_fingerprint(),'계획 이후 소스 변경')
