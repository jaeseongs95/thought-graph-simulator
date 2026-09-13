"""계획·스케줄 고정. 모델 결과를 보고 case나 seed를 선택하지 않는다."""
from __future__ import annotations
import copy,itertools
from pathlib import Path
from . import __version__
from .contracts import *
from .dataset import cases,SOURCE
CONTRACT='criterion-reintegration-v050-r1'
CYCLES=2
ORDER_SEED=5001729
ARMS=('oneshot_original','oneshot_commuted','staged_commuted','staged_pipeline')
POLICY={
 'scope':'고정 단독 사실 주장: observed→same_as_goal/in_facts→세 finding 재통합. A/D/M 축 조작 아님',
 'seeds':'v049의 10 seed 전체 재사용. 새 seed/새 논리 문제 검증 아님',
 'control':'두 oneshot은 gap 식의 피연산자 순서만 다름. schema/나머지 prompt 동일',
 'shared':'staged 두 경로는 실제 extract와 proof 호출을 공유. 독립 반복으로 세거나 비용을 중복 합산하지 않음',
 'answer_only':'실제 extract.primitives.same_as_goal 값을 그대로 연결. 호스트 논리 계산/정답 보충 아님',
 'scoring':'최종 finding 세 값·gap 단독·observed·primitives·전체 경로를 분리. 중간 오류 은폐는 전체 성공 아님',
 'schedule':'동결된 3개 실행 묶음 순열을 배정, cycle1은 역순. 단계 의존성 때문에 HTTP순서까지 균형 아님',
 'repeats':'동일 seed 2회는 재현 확인. 기술통계만, IID p-value 없음',
 'staging_contrast':'oneshot 대 staged는 prompt/출력 schema/호출구성 묶음 비교. 순수 호출수 효과라고 해석하지 않음',
 'errors':'형식 오류도 관측 실패. 유효한 오답 부모값 그대로 전달. 통신/다른모델 오류는 재시도 없이 중단',
 'cost':'실제 유일 호출 총합과 경로별 호출 합계를 분리. 공유 경로별 합계는 동일 실행의 실측 호출을 재사용한 합산',
 'no_retry':True,'warmup_calls':0,'max_calls':560,'cycles':CYCLES,
 'dataset_source':SOURCE,
}

def schedule(seeds):
    orders=list(itertools.permutations(('oneshot_original','oneshot_commuted','split')))
    branch=list(itertools.permutations(('proof','gap_direct','pipeline')))
    base=[(s,c['id']) for s in seeds for c in cases()]
    ranked=sorted(base,key=lambda x:digest([ORDER_SEED,'assignment',*x]));result=[]
    for cycle in range(CYCLES):
        wave=[]
        for s,c in base:
            i=ranked.index((s,c));g=list(orders[i%6]);b=list(branch[(i//6+i)%6])
            if cycle:g.reverse();b.reverse()
            wave.append({'id':f's{seeds.index(s):02d}_r{cycle:02d}_{c}','seed':s,'cycle':cycle,'case_id':c,'groups':g,'branches':b})
        wave.sort(key=lambda x:digest([ORDER_SEED,'wave',cycle,x['id']]))
        result.extend(wave)
    return result

def slots(plan):
    result=[]
    for block in plan['blocks']:
        for pos,group in enumerate(block['groups']):
            stages=[group] if group!='split' else ['extract']+[s for b in block['branches'] for s in (('not','gap_and') if b=='pipeline' else (b,))]
            for stage in stages:
                result.append({'id':block['id']+'__'+stage,'block_id':block['id'],'seed':block['seed'],'cycle':block['cycle'],'case_id':block['case_id'],'stage':stage,'group':group,'group_position':pos})
    return result

def dependency_ids(slot):
    if slot['stage'] in ('oneshot_original','oneshot_commuted','extract'):return []
    ids=[slot['block_id']+'__extract']
    if slot['stage']=='gap_and':ids.append(slot['block_id']+'__not')
    return ids

def prepare(bundle:Path,out:Path):
    from .evidence import import_v049
    require(not out.exists(),'기존 계획을 덮어쓰지 않습니다: '+str(out))
    baseline,ref=import_v049(bundle);old=strict_json(unb64(ref['plan_b64']))
    p={'contract':CONTRACT,'software_version':__version__,'created_at':utc_now(),'baseline':baseline,'reference':ref,
       'seeds':old['seeds'],'cycles':CYCLES,'order_seed':ORDER_SEED,'cases':cases(),'blocks':schedule(old['seeds']),
       'max_calls':560,'policy':copy.deepcopy(POLICY),'source_fingerprint':source_fingerprint()}
    p['plan_sha256']=digest(p);validate_plan(p);write_json(out,p,exclusive=True);return p

def validate_plan(p,*,check_sources=True):
    from paired_probe_v049.plan import validate_plan as v49
    keys={'contract','software_version','created_at','baseline','reference','seeds','cycles','order_seed','cases','blocks','max_calls','policy','source_fingerprint','plan_sha256'}
    require(isinstance(p,dict) and set(p)==keys and p['contract']==CONTRACT,'v050 계획 계약/필드 오류')
    require(p['plan_sha256']==digest({k:v for k,v in p.items() if k!='plan_sha256'}),'계획 해시 불일치')
    require(p['software_version']==__version__ and canonical(p['policy'])==canonical(POLICY),'버전/등록 정책 변경')
    r=p['reference'];require(r['contract']=='audited-v049-bundle-reference-r1' and r['anchor']=='bundled_external_plan','기준선 계약 오류')
    require(r['receipt_sha256']==digest({k:v for k,v in r.items() if k!='receipt_sha256'}),'기준선 영수증 변경')
    raw=unb64(r['plan_b64']);require(sha(raw)==r['plan_bytes_sha256'],'기준선 계획 바이트 변경')
    old=strict_json(raw);v49(old,check_sources=check_sources)
    require(old['plan_sha256']==r['plan_sha256'] and canonical(p['baseline'])==canonical(old['baseline']),'기준선 설정 변경')
    require(len(p['seeds'])==10 and p['seeds']==old['seeds'] and all(type(s) is int for s in p['seeds']),'전체 seed 유지 필요')
    require(type(p['cycles']) is int and p['cycles']==CYCLES and type(p['max_calls']) is int and p['max_calls']==560 and type(p['order_seed']) is int and p['order_seed']==ORDER_SEED,'반복/호출/순서 고정')
    require(canonical(p['cases'])==canonical(cases()) and canonical(p['blocks'])==canonical(schedule(p['seeds'])),'고정 문제/배정 변경')
    if check_sources:require(p['source_fingerprint']==source_fingerprint(),'계획 고정 후 코드 변경')
