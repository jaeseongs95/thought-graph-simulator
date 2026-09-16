# v089 초기 ID × 후속 ID 교차 실험

상태: complete / 출처: live

## A. 초기 유효 facts 지원 후 연속 생성 — 4×4

| 초기 ID | 후속 ID | 유효 연속 graph | 양방향 | 미관측 |
|---|---|---:|---:|---:|
| atom_alias | atom_alias | 29/32 | 13/16 | 0 |
| atom_alias | short | 5/32 | 0/16 | 0 |
| atom_alias | long | 0/32 | 0/16 | 0 |
| atom_alias | atom_tagged | 5/32 | 0/16 | 0 |
| short | atom_alias | 7/32 | 1/16 | 0 |
| short | short | 18/32 | 5/16 | 0 |
| short | long | 13/32 | 3/16 | 0 |
| short | atom_tagged | 12/32 | 4/16 | 0 |
| long | atom_alias | 8/32 | 1/16 | 0 |
| long | short | 12/32 | 5/16 | 0 |
| long | long | 19/32 | 6/16 | 0 |
| long | atom_tagged | 17/32 | 5/16 | 0 |
| atom_tagged | atom_alias | 3/32 | 0/16 | 0 |
| atom_tagged | short | 13/32 | 4/16 | 0 |
| atom_tagged | long | 20/32 | 6/16 | 0 |
| atom_tagged | atom_tagged | 28/32 | 12/16 | 0 |

주평가: 같은 계열의 중립 초기 ID − atom_alias 초기 ID, short/long 동일 가중·구조 동일 가중.
차이: 34.3750%p

## B. 새 선택·새 facts에서 시작한 기존 D 종단 기준선

baseline: 종단 111/128, 양방향 48/64, 네 표시 9/16

공통 two-stage 선택: 128/128

## 판정 범위

교차군은 과거 유효 facts 지원을 받은 연속 생성이며 C의 새 facts 종단과 합산하지 않는다.
4×4는 16개 명명 조건이지 16개의 독립 문제 집합이 아니다. 구조는 8개, seed는 2개다.
의미 ID 처치는 의미 단서를 포함한다. 문자열 길이만의 효과나 모델 내부 기제를 식별하지 않는다.
미관측/부분 실행은 실패 또는 0 깊이로 채우지 않는다. 전체 주효과는 완료 배치에서만 계산한다.
집계와 한국어 렌더링은 독립 채점기와 공유한다. 의미 판정/요청 재구성은 별도 구현이다.
