# v086 보조 원문 진단

고유 요청 수는 독립 구조/새 산술 문제 수가 아니다. 수치 하위 과제가 중복되어도 graph는 시행마다 별도 측정한다. 동일 경로의 생성기 코드가 같아도 selection_original의 공백/개행이 다르면 생성 입력 바이트가 다르다. oracle 동일 요청은 독립 문제로 가산하지 않는다. usage 누락을 0으로 채우지 않으며 duration 합계는 벽시계 시간이 아니다.

## 숫자 비교·조회 고유 입력

| 군 | 지표 | 단계 | 저장 요청 | seed 포함 고유 | seed 제외 고유 |
|---|---|---|---:|---:|---:|
| candidate_id | D | select | 128 | 128 | 64 |
| candidate_id | W | select | 64 | 64 | 32 |
| correct_values | D | select | 128 | 128 | 64 |
| correct_values | W | select | 64 | 64 | 32 |
| oracle_lookup | D | select | 128 | 96 | 48 |
| oracle_lookup | W | select | 64 | 32 | 16 |
| two_stage_values | D | compare | 128 | 40 | 20 |
| two_stage_values | D | select | 128 | 96 | 48 |
| two_stage_values | W | compare | 64 | 16 | 8 |
| two_stage_values | W | select | 64 | 32 | 16 |

## 동일 경로 생성·조회 중복

같은 경로를 선택한 D 쌍: 106. facts 요청 바이트 동일: 13. 생성 성패가 달라진 쌍: 6.
두 단계/oracle 조회의 같은 요청: 192/192 배정쌍. 미관측은 동일 요청으로 세지 않는다.
metric만 다른 조회 대조: 64. 그중 후보가 바뀐 쌍: 16. oracle 대조는 실제 두 단계 대조와 중복될 수 있다.

생성 실패 시행: 45. 겹치는 오류 코드와 실패 단계 원문은 diagnostics.json에 보존한다.

## D 본실험 사용량 — 참조·W·oracle 제외

| 군 | 보존 응답 | 관측 입력 토큰 합 | 관측 생성 토큰 합 | 입력/생성 토큰 누락 응답 |
|---|---:|---:|---:|---|
| candidate_id | 946 | 952171 | 38883 | 0 / 0 |
| correct_values | 948 | 968565 | 38840 | 0 / 0 |
| two_stage_values | 1072 | 912837 | 42857 | 0 / 0 |
