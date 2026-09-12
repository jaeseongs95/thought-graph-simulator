"""문제의 의미를 고정한 채 직접 경로/연쇄 경로 블록의 제시 순서만 바꾼다."""
from copy import deepcopy
from depth_probe_v053.design import PROBLEMS as ORIGINAL_PROBLEMS
from .contracts import digest

PROBLEMS = deepcopy(ORIGINAL_PROBLEMS)
ARMS = ('original', 'swapped')
DIRECTIONS = ('shallow', 'deep', 'neutral')
ORDER_SEED = 5401729
MAX_CALLS = 120
# 방향/seed를 보지 않는 고정 순열. 연쇄 내부 순서는 유지한다.
RULE_ORDERS = {
    'K01': {'original': ['k10', 'k17', 'k03'], 'swapped': ['k03', 'k10', 'k17']},
    'T02': {'original': ['r83', 'r21', 'r57', 'r04', 'r69'],
            'swapped': ['r21', 'r57', 'r04', 'r69', 'r83']},
}
POLICY = {
    'primary': '두 문제×두 규칙순서×shallow/deep×전체 10 seed=80회. 중립 40회는 별도 대조',
    'intervention': '직접 경로/연쇄 경로의 규칙 블록만 교환. 각 블록 내부 순서, 규칙 ID·전제·결론·facts·goal 보존',
    'preserved': '모든 system 지시·JSON schema·모델 identity·옵션·seed 동일. original 요청 60개는 v053 original과 바이트 동일',
    'direction_independent': '규칙 순서는 요청 D/seed/모델 응답과 무관하게 사전 동결. 순서를 맞춰줘서 D 성공을 만들지 않음',
    'primary_metric': '같은 문제·순서·seed에서 shallow/deep이 둘 다 유효하고 각각 최소/최대 깊이이며 서로 달라야 성공',
    'robust_metric': '같은 문제·seed에서 두 순서 모두 선택적 성공해야 순서에 견디는 D 제어. 기존 4응답의 재집계이지 새 표본 아님',
    'order_effect': '같은 문제·방향·seed에서 순서 변경 전후 둘 다 유효하며 실제 깊이가 바뀌는지. 이 효과만으로 D 제어 성공 아님',
    'negative_control': '각 순서의 neutral은 방향 지시가 없다. 두 역할 재채점을 별도 호출/독립 표본으로 세지 않음',
    'no_answer_leak': '정답 깊이·정답 그래프·선택할 규칙을 프롬프트나 schema에 넣지 않음. 채점기는 요청 생성에 참여하지 않음',
    'retry': False, 'repair': False, 'host_answer_fill': False,
    'scope': '외부 증명 기록의 D 제어. A/M 통합 또는 모델 내부 hidden state의 제어 성공으로 확장하지 않음',
    'statistics': '고정 문제 2개와 전체 seed별 대응 기술통계. p-value, 독립 문제 수 확대 없음',
    'causality': '선정한 규칙 블록 순열의 수행 효과. 내부 알고리즘·주의·캐시 기전의 직접 계측은 아님',
    'order': '120요청을 고정 해시 순서로 한 배치에 섞는다. 완전한 carryover 균형 설계는 아님',
    'historical': 'v053 실패 자료를 수정하지 않는다. 정의 명시의 무효과·미등록 규칙 4건을 그대로 보존',
}

def schedule(seeds):
    slots = []
    for index, seed in enumerate(seeds):
        for pid in PROBLEMS:
            for arm in ARMS:
                for direction in DIRECTIONS:
                    slots.append({'id': f's{index:02d}_{pid}_{arm}_{direction}', 'seed': seed,
                        'cycle': 0, 'problem_id': pid, 'arm': arm, 'task': 'order_probe',
                        'direction': direction, 'role_id': None if direction == 'neutral' else direction, 'stage': 'graph'})
    slots.sort(key=lambda slot: digest([ORDER_SEED, slot['id']]))
    for position, slot in enumerate(slots):
        slot['position'] = position
    return slots

def role_for(slot):
    return None if slot['direction'] == 'neutral' else {'id': slot['direction'], 'D': slot['direction']}

def problem_for(slot):
    problem = deepcopy(PROBLEMS[slot['problem_id']])
    lookup = {r['id']: r for r in problem['rules']}
    problem['rules'] = [lookup[rid] for rid in RULE_ORDERS[slot['problem_id']][slot['arm']]]
    return problem
