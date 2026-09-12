"""기준선 재감사, 조건·정책·순서·소스의 사전 동결."""
import copy,collections
from . import __version__
from .contracts import *
from .design import PROBLEMS,ROLES,CYCLES,ORDER_SEED,MAX_CALLS,TASK_COUNTS,POLICY,schedule
from .calibration import reference_record

def prepare(bundle,out):
    from .evidence import import_v051
    require(not out.exists(),'기존 계획 덮어쓰기 금지')
    baseline,ref=import_v051(bundle);old=strict_json(unb64(ref['plan_b64']))
    p={'contract':'adm-diagnostic-v052-r1','software_version':__version__,'created_at':utc_now(),
       'baseline':baseline,'reference':ref,'problems':copy.deepcopy(PROBLEMS),'roles':copy.deepcopy(ROLES),
       'seeds':old['seeds'],'cycles':CYCLES,'order_seed':ORDER_SEED,'max_calls':MAX_CALLS,
       'task_counts':copy.deepcopy(TASK_COUNTS),'policy':copy.deepcopy(POLICY),
       'copy_records':{k:reference_record(k) for k in PROBLEMS},
       'slots':schedule(old['seeds']),'source_fingerprint':source_fingerprint()}
    p['plan_sha256']=digest(p);validate_plan(p);write_json(out,p,exclusive=True);return p

def validate_plan(p,*,check_sources=True):
    from adm_pilot_v051.plan import validate_plan as old_validate
    keys={'contract','software_version','created_at','baseline','reference','problems','roles','seeds',
          'cycles','order_seed','max_calls','task_counts','policy','copy_records','slots','source_fingerprint','plan_sha256'}
    require(isinstance(p,dict) and set(p)==keys and p['contract']=='adm-diagnostic-v052-r1','v052 계획 형식')
    require(p['plan_sha256']==digest({k:v for k,v in p.items() if k!='plan_sha256'}),'계획 해시')
    require(p['software_version']==__version__,'버전 변경')
    r=p['reference'];require(r['contract']=='audited-v051-bundle-reference-r1' and r['anchor']=='bundled_external_plan','외부 v051 기준선 필요')
    require(r['receipt_sha256']==digest({k:v for k,v in r.items() if k!='receipt_sha256'}),'기준선 영수증 변경')
    raw=unb64(r['plan_b64']);require(sha(raw)==r['plan_bytes_sha256'],'기준선 원문 해시')
    old=strict_json(raw);old_validate(old,check_sources=check_sources)
    require(old['plan_sha256']==r['plan_sha256'] and canonical(old['baseline'])==canonical(p['baseline']),'기준선 변경')
    require(p['seeds']==old['seeds'] and len(p['seeds'])==10,'전체 seed 보존')
    for k,v in [('problems',PROBLEMS),('roles',ROLES),('policy',POLICY),('task_counts',TASK_COUNTS),
                ('slots',schedule(p['seeds'])),('copy_records',{k:reference_record(k) for k in PROBLEMS})]:
        require(canonical(p[k])==canonical(v),k+': 계획 변경')
    for k,v in [('cycles',CYCLES),('order_seed',ORDER_SEED),('max_calls',MAX_CALLS)]:
        require(type(p[k]) is int and p[k]==v,k+': 범위 변경')
    require(len(p['slots'])==MAX_CALLS and dict(collections.Counter(s['task'] for s in p['slots']))==TASK_COUNTS,'배정 수 오류')
    if check_sources:require(p['source_fingerprint']==source_fingerprint(),'계획 후 코드 변경')

def slots(p):return p['slots']
def dependency_ids(slot):return []
