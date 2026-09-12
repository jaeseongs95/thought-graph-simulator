# v057 전체 증명 생성 / 마지막 규칙 선택 대조

무결성: True / 완료: True / 호출: 480/480 / 출처: live_source_artifacts
두 모델 모두 merged 배치. graph 240회 + choice 240회. 방향 지정 320회 + 중립 160회.

**choice 성공은 마지막 규칙을 고른 성공이다. 전체 증명이나 A/D/M 제어 성공이 아니다.**

## qwen3:4b-instruct

|과제|관측/배정|과제 유효|선택적 대응 성공|전체 증명 D 제어|
|---|---:|---:|---:|---|
|graph|120/120|82|0/40|0|
|choice|120/120|120|33/40|측정 안 함|

과제별 대응 결과: `{'both_selective': 0, 'graph_only': 0, 'choice_only': 33, 'neither': 7, 'unobserved': 0}`
choice_only: 축소된 선택 과제만 성공. 같은 생성 내부에서 선택을 이해했다가 잊었다는 판정이 아니다.

### graph 세부 결과
|문제/순서/방향|관측|과제 유효|방향 이행|깊이|
|---|---:|---:|---:|---|
|K01/original/shallow|10|10|0|{'2': 10}|
|K01/original/deep|10|10|10|{'2': 10}|
|K01/original/neutral|10|2|None|{'2': 2, 'unmeasured': 8}|
|K01/swapped/shallow|10|10|10|{'1': 10}|
|K01/swapped/deep|10|10|0|{'1': 10}|
|K01/swapped/neutral|10|10|None|{'1': 10}|
|T02/original/shallow|10|10|10|{'1': 10}|
|T02/original/deep|10|10|0|{'1': 10}|
|T02/original/neutral|10|10|None|{'1': 10}|
|T02/swapped/shallow|10|0|0|{'unmeasured': 10}|
|T02/swapped/deep|10|0|0|{'unmeasured': 10}|
|T02/swapped/neutral|10|0|None|{'unmeasured': 10}|
graph의 깊이는 실제 유효한 증명에서만 계산한다.

중복 없이 원래 호출 비용만 집계: `{'calls': 120, 'prompt_eval_count': 60060, 'prompt_eval_count_missing': 0, 'prompt_eval_cached_count': 42742, 'prompt_eval_cached_count_missing': 0, 'eval_count': 18894, 'eval_count_missing': 0, 'total_duration': 253788652800, 'total_duration_missing': 0, 'load_duration': 3786349400, 'load_duration_missing': 0, 'prompt_eval_duration': 5233581993, 'prompt_eval_duration_missing': 0, 'eval_duration': 235320100000, 'eval_duration_missing': 0, 'http_median_ms': 1817.19365, 'http_mean_ms': 2131.1067733333334}`

### choice 세부 결과
|문제/순서/방향|관측|과제 유효|방향 이행|깊이|
|---|---:|---:|---:|---|
|K01/original/shallow|10|10|10|{'1': 10}|
|K01/original/deep|10|10|10|{'2': 10}|
|K01/original/neutral|10|10|None|{'2': 10}|
|K01/swapped/shallow|10|10|10|{'1': 10}|
|K01/swapped/deep|10|10|10|{'2': 10}|
|K01/swapped/neutral|10|10|None|{'1': 10}|
|T02/original/shallow|10|10|3|{'4': 7, '1': 3}|
|T02/original/deep|10|10|10|{'4': 10}|
|T02/original/neutral|10|10|None|{'4': 10}|
|T02/swapped/shallow|10|10|10|{'1': 10}|
|T02/swapped/deep|10|10|10|{'4': 10}|
|T02/swapped/neutral|10|10|None|{'4': 10}|
choice의 깊이는 문제 명세에서 선택 규칙에 대응하는 값이다. 생성된 증명의 실제 깊이가 아니다.

중복 없이 원래 호출 비용만 집계: `{'calls': 120, 'prompt_eval_count': 38100, 'prompt_eval_count_missing': 0, 'prompt_eval_cached_count': 22362, 'prompt_eval_cached_count_missing': 0, 'eval_count': 1200, 'eval_count_missing': 0, 'total_duration': 42264405900, 'total_duration_missing': 0, 'load_duration': 15910283900, 'load_duration_missing': 0, 'prompt_eval_duration': 4768012996, 'prompt_eval_duration_missing': 0, 'eval_duration': 13465339000, 'eval_duration_missing': 0, 'http_median_ms': 250.13315, 'http_mean_ms': 368.11437083333334}`

## gemma3:4b

|과제|관측/배정|과제 유효|선택적 대응 성공|전체 증명 D 제어|
|---|---:|---:|---:|---|
|graph|120/120|5|0/40|0|
|choice|120/120|120|7/40|측정 안 함|

과제별 대응 결과: `{'both_selective': 0, 'graph_only': 0, 'choice_only': 7, 'neither': 33, 'unobserved': 0}`
choice_only: 축소된 선택 과제만 성공. 같은 생성 내부에서 선택을 이해했다가 잊었다는 판정이 아니다.

### graph 세부 결과
|문제/순서/방향|관측|과제 유효|방향 이행|깊이|
|---|---:|---:|---:|---|
|K01/original/shallow|10|0|0|{'unmeasured': 10}|
|K01/original/deep|10|0|0|{'unmeasured': 10}|
|K01/original/neutral|10|0|None|{'unmeasured': 10}|
|K01/swapped/shallow|10|1|1|{'unmeasured': 9, '1': 1}|
|K01/swapped/deep|10|0|0|{'unmeasured': 10}|
|K01/swapped/neutral|10|0|None|{'unmeasured': 10}|
|T02/original/shallow|10|0|0|{'unmeasured': 10}|
|T02/original/deep|10|0|0|{'unmeasured': 10}|
|T02/original/neutral|10|0|None|{'unmeasured': 10}|
|T02/swapped/shallow|10|0|0|{'unmeasured': 10}|
|T02/swapped/deep|10|4|4|{'4': 4, 'unmeasured': 6}|
|T02/swapped/neutral|10|0|None|{'unmeasured': 10}|
graph의 깊이는 실제 유효한 증명에서만 계산한다.

중복 없이 원래 호출 비용만 집계: `{'calls': 120, 'prompt_eval_count': 56600, 'prompt_eval_count_missing': 0, 'prompt_eval_cached_count': 19951, 'prompt_eval_cached_count_missing': 0, 'eval_count': 26151, 'eval_count_missing': 0, 'total_duration': 380993525800, 'total_duration_missing': 0, 'load_duration': 20199208900, 'load_duration_missing': 0, 'prompt_eval_duration': 17735336996, 'prompt_eval_duration_missing': 0, 'eval_duration': 331399846997, 'eval_duration_missing': 0, 'http_median_ms': 3149.2960000000003, 'http_mean_ms': 3190.5620008333335}`

### choice 세부 결과
|문제/순서/방향|관측|과제 유효|방향 이행|깊이|
|---|---:|---:|---:|---|
|K01/original/shallow|10|10|5|{'1': 5, '2': 5}|
|K01/original/deep|10|10|10|{'2': 10}|
|K01/original/neutral|10|10|None|{'1': 10}|
|K01/swapped/shallow|10|10|10|{'1': 10}|
|K01/swapped/deep|10|10|0|{'1': 10}|
|K01/swapped/neutral|10|10|None|{'1': 10}|
|T02/original/shallow|10|10|10|{'1': 10}|
|T02/original/deep|10|10|2|{'1': 8, '4': 2}|
|T02/original/neutral|10|10|None|{'1': 10}|
|T02/swapped/shallow|10|10|0|{'4': 10}|
|T02/swapped/deep|10|10|10|{'4': 10}|
|T02/swapped/neutral|10|10|None|{'4': 10}|
choice의 깊이는 문제 명세에서 선택 규칙에 대응하는 값이다. 생성된 증명의 실제 깊이가 아니다.

중복 없이 원래 호출 비용만 집계: `{'calls': 120, 'prompt_eval_count': 35720, 'prompt_eval_count_missing': 0, 'prompt_eval_cached_count': 5785, 'prompt_eval_cached_count_missing': 0, 'eval_count': 1440, 'eval_count_missing': 0, 'total_duration': 44025047700, 'total_duration_missing': 0, 'load_duration': 1753462800, 'load_duration_missing': 0, 'prompt_eval_duration': 14425590988, 'prompt_eval_duration_missing': 0, 'eval_duration': 16991354000, 'eval_duration_missing': 0, 'http_median_ms': 380.71315, 'http_mean_ms': 382.463285}`

## 중립 대조
중립 응답 하나를 두 방향 기준에 재채점하며 두 독립 표본으로 세지 않는다.
|모델/과제/문제/순서|관측 묶음|방향 지정−중립 평균|
|---|---:|---:|
|reference/graph/K01/original|10|0.4|
|reference/graph/K01/swapped|10|0.0|
|reference/graph/T02/original|10|0.0|
|reference/graph/T02/swapped|10|0.0|
|reference/choice/K01/original|10|0.5|
|reference/choice/K01/swapped|10|0.5|
|reference/choice/T02/original|10|0.15|
|reference/choice/T02/swapped|10|0.5|
|candidate/graph/K01/original|10|0.0|
|candidate/graph/K01/swapped|10|0.05|
|candidate/graph/T02/original|10|0.0|
|candidate/graph/T02/swapped|10|0.2|
|candidate/choice/K01/original|10|0.25|
|candidate/choice/K01/swapped|10|0.0|
|candidate/choice/T02/original|10|0.1|
|candidate/choice/T02/swapped|10|0.0|

## 해석 경계
모델 응답의 자동 보정/재시도/정답 경로 주입 없음. 두 과제는 출력 요구가 다르다. 내부 정책·이해·학습 원인 단독 식별 아님.
같은 응답을 여러 표로 재집계해도 새로운 독립 실험으로 합산하지 않는다.
계획 SHA-256: fcacb55543a2c76895a16c0da439a31dd03ee633253a6d4321a8da78fc55eade
event tip: 4edc29f43c26671619eee99e67cc89ee8bc7244f4dac0a0a8d602959dadb8234
