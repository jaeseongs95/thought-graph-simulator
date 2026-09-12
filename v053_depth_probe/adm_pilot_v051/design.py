"""문제·목표·역할·순서가 사전에 고정된 단일 문제 factorial pilot."""
from __future__ import annotations
import copy
import itertools
from .contracts import digest

PROBLEM = {'id': 'K01', 'facts': ['Ca'], 'rules': [
    {'id': 'k10', 'premises': ['Ca'], 'conclusion': 'Cb'},
    {'id': 'k17', 'premises': ['Cb'], 'conclusion': 'Cc'},
    {'id': 'k03', 'premises': ['Ca'], 'conclusion': 'Cc'}], 'goal': 'Cc'}
CYCLES = 2
ORDER_SEED = 5101729
MAX_CALLS = 240
AXES = {'A': ['instance', 'schema'], 'D': ['shallow', 'deep'], 'M': [0, 1, 2]}
ROLES = [{'id': f'{a}_{d}_M{m}', 'A': a, 'D': d, 'M': m}
         for a, d, m in itertools.product(AXES['A'], AXES['D'], AXES['M'])]
POLICY = {
    'scope': '단일 K01 고정 문제·목표의 실제 LLM A/D/M 조작 예비실험. 확증·효율·내부 사고 검증 아님',
    'A': '모든 노드의 유효한 사례 표현 또는 실제 사용 근거에 접지된 보편 명제 도식',
    'D': '고정 규칙 집합에서 최종 목표 지지 DAG의 깊이: shallow=1, deep=2. 텍스트 길이/호출 수 아님',
    'M': '0=검토 없음, 1=최종 증명 검토 하나, 2=기준 검토 하나. M2가 M1 뒤에 올 필요는 없음',
    'role_separation': '역할은 생성 요청만 바꿈. 실제 측정기는 요청 A/D/M를 읽지 않고 기록을 검사',
    'common_schema': True, 'answer_repair': False, 'automatic_retry': False,
    'host_answer_fill': False, 'fixed_goal': 'Cc',
    'calls_per_role': 1, 'cycles': CYCLES, 'max_calls': MAX_CALLS,
    'seeds': 'v050의 10개 전체 유지. 새로운 seed나 새로운 문제 일반화 아님',
    'repeats': '동일 seed 반복의 바이트·의미 불일치도 기록. 새로운 문제 표본으로 합산하지 않음',
    'baseline': 'v050 자료의 유효성만 수입 조건. v050 성공을 전제하지 않음',
    'comparison': 'A/D/M 한 축씩 달라지는 대응쌍. 실패·누락 포함 분모와 양쪽 유효쌍 분모를 함께 기록',
    'claims': 'A/D가 맞고 M2가 틀린 결과를 분리. M 라벨과 올바른 메타 판정을 동일시하지 않음',
    'schedule': 'seed별 역할 순서를 hash로 동결, 둘째 반복 역순. 12조건 전순열 균형설계는 아님',
    'budget': '1회 호출은 같지만 토큰·지연은 달라질 수 있음. 동일 FLOPs 효과 주장 없음',
    'next': '성공률로 조건·seed를 삭제하지 않는다. 파일럿 결과 후 별도 holdout 문제 계획을 수립',
}


def schedule(seeds):
    result = []
    for cycle in range(CYCLES):
        order = sorted(seeds, key=lambda s: digest([ORDER_SEED, 'seed', cycle, s]))
        for seed in order:
            roles = sorted(ROLES, key=lambda r: digest([ORDER_SEED, 'role', seed, r['id']]))
            if cycle:
                roles = list(reversed(roles))
            for pos, role in enumerate(roles):
                result.append({'id': f's{seeds.index(seed):02d}_r{cycle:02d}_{role["id"]}',
                               'seed': seed, 'cycle': cycle, 'position': pos,
                               'role_id': role['id'], 'stage': 'trace'})
    return result


def role_for(slot):
    return copy.deepcopy(next(r for r in ROLES if r['id'] == slot['role_id']))
