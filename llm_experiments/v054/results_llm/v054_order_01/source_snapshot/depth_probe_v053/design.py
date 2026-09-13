"""문제·모델·seed·출력 형식을 고정하고 D 정의 문단의 유무만 비교한다."""
from copy import deepcopy
from adm_diagnostic_v052.design import PROBLEMS as ORIGINAL_PROBLEMS
from .contracts import digest

PROBLEMS = deepcopy(ORIGINAL_PROBLEMS)
ARMS = ('original', 'defined')
DIRECTIONS = ('shallow', 'deep', 'neutral')
ORDER_SEED = 5301729
MAX_CALLS = 120
POLICY = {
    'primary': '두 문제×두 지시문×얕음/깊음×전체 10 seed=80회. 중립 40회는 별도 대조다.',
    'intervention': 'defined에는 깊이의 재귀적 정의 문단 하나만 추가한다. 원래 경로 선택 문장은 동일하다.',
    'preserved': 'K01/T02 facts/rules/goal, 모델 identity, 모든 seed와 샘플링, GRAPH 출력 schema 보존',
    'negative_control': '각 지시문에서 얕음/깊음 지시를 뺀 중립 1회/seed. 재채점은 독립 표본 아님',
    'primary_metric': '같은 seed의 shallow/deep 둘 다 유효하고 각각 최소/최대 실제 깊이이며 서로 달라야 선택적 성공',
    'validity_not_control': '유효 증명만 만들거나 한쪽 방향만 맞으면 D 선택적 제어의 성공이 아님',
    'no_answer_leak': '최소/최대 깊이의 정답 숫자·선택할 규칙·예시 정답 그래프를 요청에 넣지 않음',
    'retry': False, 'repair': False, 'host_answer_fill': False,
    'scope': '외부 증명 기록의 D 제어. A/M 및 통합 제어와 내부 hidden state는 이번 분모에서 제외',
    'statistics': 'seed별 대응 기술통계. 새 문제 120개나 독립 대응쌍으로 취급하지 않음. p-value 없음',
    'causality': '정의 문단 추가의 작동 효과를 비교한다. 의미 명확화와 길이/주의 효과를 내부 기전으로 분리하지 않음',
    'order': '120요청을 고정 해시 순서로 같은 배치에서 실행. 완전한 carryover 균형 설계는 아님',
    'historical': 'original 방향 지정 40요청은 v052 D 단독과 바이트 동일. 새 배치에서 다시 수집',
}

def schedule(seeds):
    slots = []
    for index, seed in enumerate(seeds):
        for pid in PROBLEMS:
            for arm in ARMS:
                for direction in DIRECTIONS:
                    slots.append({'id': f's{index:02d}_{pid}_{arm}_{direction}', 'seed': seed,
                                  'cycle': 0, 'problem_id': pid, 'arm': arm, 'task': 'depth_probe',
                                  'direction': direction, 'role_id': None if direction == 'neutral' else direction,
                                  'stage': 'graph'})
    slots.sort(key=lambda s: digest([ORDER_SEED, s['id']]))
    for position, slot in enumerate(slots):
        slot['position'] = position
    return slots

def role_for(slot):
    return None if slot['direction'] == 'neutral' else {'id': slot['direction'], 'D': slot['direction']}

def problem_for(slot):
    return deepcopy(PROBLEMS[slot['problem_id']])
