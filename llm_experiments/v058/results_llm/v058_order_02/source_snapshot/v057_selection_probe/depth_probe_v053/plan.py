"""완료한 v052 원문을 재감사하고 새 120회 계획을 오프라인으로 동결한다."""
from copy import deepcopy
from . import __version__
from .contracts import (require, read_json, write_json, strict_json, unb64, canonical, sha, digest,
                        utc_now, source_fingerprint)
from .design import PROBLEMS, ARMS, DIRECTIONS, ORDER_SEED, MAX_CALLS, POLICY, schedule

def prepare(bundle, out):
    from .evidence import import_v052
    require(not out.exists(), '기존 계획 덮어쓰기 금지')
    baseline, reference = import_v052(bundle)
    previous = strict_json(unb64(reference['plan_b64']))
    plan = {'contract': 'depth-probe-v053-r1', 'software_version': __version__, 'created_at': utc_now(),
            'baseline': baseline, 'reference': reference, 'problems': deepcopy(PROBLEMS),
            'arms': list(ARMS), 'directions': list(DIRECTIONS), 'seeds': previous['seeds'],
            'cycles': 1, 'order_seed': ORDER_SEED, 'max_calls': MAX_CALLS, 'policy': deepcopy(POLICY),
            'slots': schedule(previous['seeds']), 'source_fingerprint': source_fingerprint()}
    plan['plan_sha256'] = digest(plan)
    validate_plan(plan); write_json(out, plan, exclusive=True)
    return plan

def validate_plan(plan, *, check_sources=True):
    from adm_diagnostic_v052.plan import validate_plan as validate_old
    keys = {'contract','software_version','created_at','baseline','reference','problems','arms','directions',
            'seeds','cycles','order_seed','max_calls','policy','slots','source_fingerprint','plan_sha256'}
    require(isinstance(plan, dict) and set(plan) == keys, 'v053 계획 필드 불일치')
    require(plan['contract'] == 'depth-probe-v053-r1' and plan['software_version'] == __version__, '계약/버전 변경')
    require(plan['plan_sha256'] == digest({k:v for k,v in plan.items() if k != 'plan_sha256'}), '계획 해시 불일치')
    ref = plan['reference']
    refkeys = {'contract','anchor','bundle_sha256','source_bundle_name','audited_at','plan_b64','plan_bytes_sha256',
               'plan_sha256','event_tip','recorded_calls','evidence_kind','note','receipt_sha256'}
    require(isinstance(ref, dict) and set(ref) == refkeys, '기준선 영수증 필드 불일치')
    require(ref['contract'] == 'audited-v052-bundle-reference-r1' and ref['anchor'] == 'bundled_external_plan', 'v052 외부 기준선 필요')
    require(ref['receipt_sha256'] == digest({k:v for k,v in ref.items() if k != 'receipt_sha256'}), '영수증 해시')
    raw = unb64(ref['plan_b64']); require(sha(raw) == ref['plan_bytes_sha256'], '기준선 계획 바이트')
    previous = strict_json(raw); validate_old(previous, check_sources=check_sources)
    require(previous['plan_sha256'] == ref['plan_sha256'] and ref['recorded_calls'] == 440, '기준선 호출/계획 오류')
    require(canonical(plan['baseline']) == canonical(previous['baseline']), '모델/옵션/endpoint/출처 변경')
    require(ref['evidence_kind'] == plan['baseline']['evidence_kind'], '합성/실제 기준선 출처 변경')
    require(plan['seeds'] == previous['seeds'] and len(plan['seeds']) == 10, '전체 seed 보존 필요')
    for key, expected in [('problems', PROBLEMS), ('arms', list(ARMS)), ('directions', list(DIRECTIONS)),
                          ('policy', POLICY), ('slots', schedule(plan['seeds']))]:
        require(canonical(plan[key]) == canonical(expected), '계획 조건 변경: ' + key)
    for key, expected in [('cycles', 1), ('order_seed', ORDER_SEED), ('max_calls', MAX_CALLS)]:
        require(type(plan[key]) is int and plan[key] == expected, '배정 범위 변경: ' + key)
    if check_sources:
        require(plan['source_fingerprint'] == source_fingerprint(), '계획 이후 소스 변경')

def slots(plan):
    return plan['slots']

def dependency_ids(slot):
    return []
