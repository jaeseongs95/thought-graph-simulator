# v090 새 선택·새 facts의 의미 ID D 종단 대조

상태: complete / 출처: live

| 생성군 | 새 facts 의미 성공 | ID 계약 성공 | D 종단 | 양방향 | 네 표시 전체 | 미관측 |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 128/128 | 128/128 | 106/128 | 43/64 | 9/16 | 0 |
| short_uniform | 128/128 | 128/128 | 75/128 | 18/64 | 2/16 | 0 |
| atom_alias | 128/128 | 128/128 | 121/128 | 57/64 | 13/16 | 0 |
| atom_tagged | 128/128 | 128/128 | 116/128 | 56/64 | 14/16 | 0 |

## 사전 주평가
새 선택·새 facts에서 시작한 엄격 양방향 D 종단 성공률의 atom_alias − baseline 차이. 구조별 2seed×4표시 8pair 평균 뒤 8구조 동일 가중.
차이: 21.8750%p

공통 two-stage 선택: 128/128

## 보조 대비
atom_tagged − baseline: 20.3125%p
short_uniform − baseline: -39.0625%p
atom_alias − short_uniform: 60.9375%p
atom_tagged − short_uniform: 59.3750%p
atom_tagged − atom_alias: -1.5625%p

## 해석 범위
과거 유효 facts/graph는 생성 입력으로 재사용하지 않는다. 네 군 모두 새 facts를 모델이 출력한다.
baseline은 기존 자유 ID 계약이다. 세 지정군은 공개 facts ID 표와 현재 규칙 ID 지원이 추가된다.
의미 명명만의 효과는 같은 지원 수준인 short_uniform과의 보조 대조로 구별한다.
같은 선택 응답 128개를 네 군이 공유하며 선택/호출을 4배로 세지 않는다.
독립 구조는 기존 8개다. seed·표시 반복을 독립 모집단 표본으로 해석하지 않는다.
부분 배치/미관측에서 전체 주평가를 계산하지 않는다. 원문 ID·전제·경로를 보정하지 않는다.
동일 원자를 중복 도출하지 않는 현재 primitive 경로에서만 의미 ID의 유일성을 보장한다.
일부 보고 집계는 공유한다. 핵심 집계는 audit_metrics090으로 별도 확인한다.
