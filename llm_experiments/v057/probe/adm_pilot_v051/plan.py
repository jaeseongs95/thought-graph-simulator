"""실험 전 계획 고정. 새 추론·정답에 따른 선택을 수행하지 않는다."""
from __future__ import annotations
import copy
from . import __version__
from .contracts import *
from .design import PROBLEM, ROLES, CYCLES, ORDER_SEED, MAX_CALLS, POLICY, schedule


def prepare(bundle, out):
    from .evidence import import_v050
    require(not out.exists(), '기존 계획 덮어쓰기 금지: ' + str(out))
    baseline, ref = import_v050(bundle)
    old = strict_json(unb64(ref['plan_b64']))
    p = {'contract': 'fixed-adm-pilot-v051-r1', 'software_version': __version__,
         'created_at': utc_now(), 'baseline': baseline, 'reference': ref,
         'problem': copy.deepcopy(PROBLEM), 'problem_sha256': digest(PROBLEM),
         'roles': copy.deepcopy(ROLES), 'seeds': old['seeds'], 'cycles': CYCLES,
         'order_seed': ORDER_SEED, 'max_calls': MAX_CALLS, 'policy': copy.deepcopy(POLICY),
         'slots': schedule(old['seeds']), 'source_fingerprint': source_fingerprint()}
    p['plan_sha256'] = digest(p)
    validate_plan(p)
    write_json(out, p, exclusive=True)
    return p


def validate_plan(p, *, check_sources=True):
    from criterion_probe_v050.plan import validate_plan as validate_old
    keys = {'contract', 'software_version', 'created_at', 'baseline', 'reference', 'problem',
            'problem_sha256', 'roles', 'seeds', 'cycles', 'order_seed', 'max_calls', 'policy',
            'slots', 'source_fingerprint', 'plan_sha256'}
    require(isinstance(p, dict) and set(p) == keys and p['contract'] == 'fixed-adm-pilot-v051-r1', 'v051 계획 계약 오류')
    require(p['plan_sha256'] == digest({k:v for k,v in p.items() if k != 'plan_sha256'}), '계획 해시 불일치')
    require(p['software_version'] == __version__ and canonical(p['policy']) == canonical(POLICY), '버전/정책 변경')
    r = p['reference']
    require(r['contract'] == 'audited-v050-bundle-reference-r1' and r['anchor'] == 'bundled_external_plan', 'v050 기준선 필요')
    require(r['receipt_sha256'] == digest({k:v for k,v in r.items() if k != 'receipt_sha256'}), '기준선 영수증 변경')
    raw = unb64(r['plan_b64']); require(sha(raw) == r['plan_bytes_sha256'], '기준선 바이트 변경')
    old = strict_json(raw); validate_old(old, check_sources=check_sources)
    require(old['plan_sha256'] == r['plan_sha256'] and canonical(p['baseline']) == canonical(old['baseline']), '기준선 설정 변경')
    require(p['seeds'] == old['seeds'] and len(p['seeds']) == 10 and len(set(p['seeds'])) == 10 and all(type(s) is int for s in p['seeds']), '전체 10 seed 유지')
    require(canonical(p['problem']) == canonical(PROBLEM) and p['problem_sha256'] == digest(PROBLEM), '고정 문제/목표 변경')
    require(canonical(p['roles']) == canonical(ROLES) and canonical(p['slots']) == canonical(schedule(p['seeds'])), '역할/스케줄 변경')
    for key, value in [('cycles', CYCLES), ('order_seed', ORDER_SEED), ('max_calls', MAX_CALLS)]:
        require(type(p[key]) is int and p[key] == value, key + ': 계획 변경')
    require(len(p['slots']) == MAX_CALLS, '슬롯 수 오류')
    if check_sources:
        require(p['source_fingerprint'] == source_fingerprint(), '계획 후 코드 변경')


def slots(p):
    return p['slots']


def dependency_ids(slot):
    return []
