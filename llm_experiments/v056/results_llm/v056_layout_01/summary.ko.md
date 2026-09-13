# v056 입력 메시지 배치 대조

무결성: True / 완료: True / 호출: 480/480 / 출처: live_source_artifacts
split: 기존 system/user 분리. merged: 같은 텍스트를 하나의 user 메시지로 연결. 방향 지정 320 + 중립 160.

## qwen3:4b-instruct / split

|문제/순서/방향|배정|관측|유효 증명|방향 일치|깊이|
|---|---:|---:|---:|---:|---|
|K01/original/shallow|10|10|10|0|{'2': 10}|
|K01/original/deep|10|10|10|10|{'2': 10}|
|K01/original/neutral|10|10|10|해당 없음|{'2': 10}|
|K01/swapped/shallow|10|10|10|10|{'1': 10}|
|K01/swapped/deep|10|10|10|0|{'1': 10}|
|K01/swapped/neutral|10|10|10|해당 없음|{'1': 10}|
|T02/original/shallow|10|10|10|10|{'1': 10}|
|T02/original/deep|10|10|10|0|{'1': 10}|
|T02/original/neutral|10|10|10|해당 없음|{'1': 10}|
|T02/swapped/shallow|10|10|0|0|{'unmeasured': 10}|
|T02/swapped/deep|10|10|0|0|{'unmeasured': 10}|
|T02/swapped/neutral|10|10|0|해당 없음|{'unmeasured': 10}|

### 선택적 D 제어
|문제/순서|배정 쌍|둘 다 유효|선택적 성공|
|---|---:|---:|---:|
|K01/original|10|10|0|
|K01/swapped|10|10|0|
|T02/original|10|10|0|
|T02/swapped|10|0|0|

### 두 규칙 순서 모두에서 유지되는 제어
|문제|배정 seed 묶음|네 증명 모두 유효|두 순서 모두 선택적 성공|
|---|---:|---:|---:|
|K01|10|10|0|
|T02|10|0|0|

### 중립 대조
|문제/순서|측정 가능한 seed 묶음|방향 지정 − 중립 평균|
|---|---:|---:|
|K01/original|10|0.0|
|K01/swapped|10|0.0|
|T02/original|10|0.0|
|T02/swapped|10|0.0|
중립 응답 한 개를 두 방향 기준에 재채점한 값이며, 두 개의 독립 응답으로 세지 않는다.

원래 호출만 한 번 집계한 비용: `{'calls': 120, 'prompt_eval_count': 60660, 'prompt_eval_count_missing': 0, 'prompt_eval_cached_count': 43152, 'prompt_eval_cached_count_missing': 0, 'eval_count': 18584, 'eval_count_missing': 0, 'total_duration': 254415257100, 'total_duration_missing': 0, 'load_duration': 3646347500, 'load_duration_missing': 0, 'prompt_eval_duration': 5238512994, 'prompt_eval_duration_missing': 0, 'eval_duration': 231056474000, 'eval_duration_missing': 0, 'http_median_ms': 1846.88715, 'http_mean_ms': 2135.107288333333}`
## gemma3:4b / split

|문제/순서/방향|배정|관측|유효 증명|방향 일치|깊이|
|---|---:|---:|---:|---:|---|
|K01/original/shallow|10|10|0|0|{'unmeasured': 10}|
|K01/original/deep|10|10|0|0|{'unmeasured': 10}|
|K01/original/neutral|10|10|0|해당 없음|{'unmeasured': 10}|
|K01/swapped/shallow|10|10|0|0|{'unmeasured': 10}|
|K01/swapped/deep|10|10|0|0|{'unmeasured': 10}|
|K01/swapped/neutral|10|10|0|해당 없음|{'unmeasured': 10}|
|T02/original/shallow|10|10|0|0|{'unmeasured': 10}|
|T02/original/deep|10|10|0|0|{'unmeasured': 10}|
|T02/original/neutral|10|10|0|해당 없음|{'unmeasured': 10}|
|T02/swapped/shallow|10|10|0|0|{'unmeasured': 10}|
|T02/swapped/deep|10|10|0|0|{'unmeasured': 10}|
|T02/swapped/neutral|10|10|0|해당 없음|{'unmeasured': 10}|

### 선택적 D 제어
|문제/순서|배정 쌍|둘 다 유효|선택적 성공|
|---|---:|---:|---:|
|K01/original|10|0|0|
|K01/swapped|10|0|0|
|T02/original|10|0|0|
|T02/swapped|10|0|0|

### 두 규칙 순서 모두에서 유지되는 제어
|문제|배정 seed 묶음|네 증명 모두 유효|두 순서 모두 선택적 성공|
|---|---:|---:|---:|
|K01|10|0|0|
|T02|10|0|0|

### 중립 대조
|문제/순서|측정 가능한 seed 묶음|방향 지정 − 중립 평균|
|---|---:|---:|
|K01/original|10|0.0|
|K01/swapped|10|0.0|
|T02/original|10|0.0|
|T02/swapped|10|0.0|
중립 응답 한 개를 두 방향 기준에 재채점한 값이며, 두 개의 독립 응답으로 세지 않는다.

원래 호출만 한 번 집계한 비용: `{'calls': 120, 'prompt_eval_count': 57200, 'prompt_eval_count_missing': 0, 'prompt_eval_cached_count': 25241, 'prompt_eval_cached_count_missing': 0, 'eval_count': 25693, 'eval_count_missing': 0, 'total_duration': 372823340800, 'total_duration_missing': 0, 'load_duration': 20149402800, 'load_duration_missing': 0, 'prompt_eval_duration': 16946223997, 'prompt_eval_duration_missing': 0, 'eval_duration': 325835594000, 'eval_duration_missing': 0, 'http_median_ms': 2749.9448, 'http_mean_ms': 3121.8230633333333}`
## qwen3:4b-instruct / merged

|문제/순서/방향|배정|관측|유효 증명|방향 일치|깊이|
|---|---:|---:|---:|---:|---|
|K01/original/shallow|10|10|10|0|{'2': 10}|
|K01/original/deep|10|10|10|10|{'2': 10}|
|K01/original/neutral|10|10|7|해당 없음|{'2': 7, 'unmeasured': 3}|
|K01/swapped/shallow|10|10|10|10|{'1': 10}|
|K01/swapped/deep|10|10|10|0|{'1': 10}|
|K01/swapped/neutral|10|10|10|해당 없음|{'1': 10}|
|T02/original/shallow|10|10|10|10|{'1': 10}|
|T02/original/deep|10|10|10|0|{'1': 10}|
|T02/original/neutral|10|10|10|해당 없음|{'1': 10}|
|T02/swapped/shallow|10|10|0|0|{'unmeasured': 10}|
|T02/swapped/deep|10|10|0|0|{'unmeasured': 10}|
|T02/swapped/neutral|10|10|0|해당 없음|{'unmeasured': 10}|

### 선택적 D 제어
|문제/순서|배정 쌍|둘 다 유효|선택적 성공|
|---|---:|---:|---:|
|K01/original|10|10|0|
|K01/swapped|10|10|0|
|T02/original|10|10|0|
|T02/swapped|10|0|0|

### 두 규칙 순서 모두에서 유지되는 제어
|문제|배정 seed 묶음|네 증명 모두 유효|두 순서 모두 선택적 성공|
|---|---:|---:|---:|
|K01|10|10|0|
|T02|10|0|0|

### 중립 대조
|문제/순서|측정 가능한 seed 묶음|방향 지정 − 중립 평균|
|---|---:|---:|
|K01/original|10|0.15|
|K01/swapped|10|0.0|
|T02/original|10|0.0|
|T02/swapped|10|0.0|
중립 응답 한 개를 두 방향 기준에 재채점한 값이며, 두 개의 독립 응답으로 세지 않는다.

원래 호출만 한 번 집계한 비용: `{'calls': 120, 'prompt_eval_count': 60060, 'prompt_eval_count_missing': 0, 'prompt_eval_cached_count': 41785, 'prompt_eval_cached_count_missing': 0, 'eval_count': 18708, 'eval_count_missing': 0, 'total_duration': 263691385000, 'total_duration_missing': 0, 'load_duration': 15738110000, 'load_duration_missing': 0, 'prompt_eval_duration': 5509552993, 'prompt_eval_duration_missing': 0, 'eval_duration': 232521116000, 'eval_duration_missing': 0, 'http_median_ms': 1820.4245999999998, 'http_mean_ms': 2212.4527541666666}`
## gemma3:4b / merged

|문제/순서/방향|배정|관측|유효 증명|방향 일치|깊이|
|---|---:|---:|---:|---:|---|
|K01/original/shallow|10|10|0|0|{'unmeasured': 10}|
|K01/original/deep|10|10|0|0|{'unmeasured': 10}|
|K01/original/neutral|10|10|0|해당 없음|{'unmeasured': 10}|
|K01/swapped/shallow|10|10|0|0|{'unmeasured': 10}|
|K01/swapped/deep|10|10|0|0|{'unmeasured': 10}|
|K01/swapped/neutral|10|10|0|해당 없음|{'unmeasured': 10}|
|T02/original/shallow|10|10|0|0|{'unmeasured': 10}|
|T02/original/deep|10|10|0|0|{'unmeasured': 10}|
|T02/original/neutral|10|10|0|해당 없음|{'unmeasured': 10}|
|T02/swapped/shallow|10|10|1|0|{'unmeasured': 9, '4': 1}|
|T02/swapped/deep|10|10|2|2|{'4': 2, 'unmeasured': 8}|
|T02/swapped/neutral|10|10|0|해당 없음|{'unmeasured': 10}|

### 선택적 D 제어
|문제/순서|배정 쌍|둘 다 유효|선택적 성공|
|---|---:|---:|---:|
|K01/original|10|0|0|
|K01/swapped|10|0|0|
|T02/original|10|0|0|
|T02/swapped|10|0|0|

### 두 규칙 순서 모두에서 유지되는 제어
|문제|배정 seed 묶음|네 증명 모두 유효|두 순서 모두 선택적 성공|
|---|---:|---:|---:|
|K01|10|0|0|
|T02|10|0|0|

### 중립 대조
|문제/순서|측정 가능한 seed 묶음|방향 지정 − 중립 평균|
|---|---:|---:|
|K01/original|10|0.0|
|K01/swapped|10|0.0|
|T02/original|10|0.0|
|T02/swapped|10|0.1|
중립 응답 한 개를 두 방향 기준에 재채점한 값이며, 두 개의 독립 응답으로 세지 않는다.

원래 호출만 한 번 집계한 비용: `{'calls': 120, 'prompt_eval_count': 56600, 'prompt_eval_count_missing': 0, 'prompt_eval_cached_count': 25907, 'prompt_eval_cached_count_missing': 0, 'eval_count': 25195, 'eval_count_missing': 0, 'total_duration': 347218308900, 'total_duration_missing': 0, 'load_duration': 1621387900, 'load_duration_missing': 0, 'prompt_eval_duration': 16024192988, 'prompt_eval_duration_missing': 0, 'eval_duration': 319533223999, 'eval_duration_missing': 0, 'http_median_ms': 2822.35725, 'http_mean_ms': 2908.4733333333334}`

## 증명 유효성의 배치 효과
|모델|배정 쌍|미관측|둘 다 유효|분리만 유효|병합만 유효|둘 다 무효|병합−분리|
|---|---:|---:|---:|---:|---:|---:|---:|
|reference|120|0|87|3|0|30|-0.025|
|candidate|120|0|0|0|3|117|0.025|

## 배치별 선택적 제어 비교
|모델/문제/순서|배정|미관측|둘 다 성공|분리만|병합만|둘 다 미성공|병합−분리|
|---|---:|---:|---:|---:|---:|---:|---:|
|reference/K01/original|10|0|0|0|0|10|0.0|
|reference/K01/swapped|10|0|0|0|0|10|0.0|
|reference/T02/original|10|0|0|0|0|10|0.0|
|reference/T02/swapped|10|0|0|0|0|10|0.0|
|candidate/K01/original|10|0|0|0|0|10|0.0|
|candidate/K01/swapped|10|0|0|0|0|10|0.0|
|candidate/T02/original|10|0|0|0|0|10|0.0|
|candidate/T02/swapped|10|0|0|0|0|10|0.0|

## 해석 경계
증명 유효성 개선만으로 D 제어 성공이 아니다. 중립도 유지한다. 같은 480응답을 관점별 재집계하며 독립 표본으로 합산하지 않는다.
역할·턴 경계·특수 토큰 배치가 함께 달라진 대조다. 내부 정책 우선순위나 학습 원인을 직접 측정하지 않는다.
한국어 내용/규칙/목표/출력 계약은 유지했고 정답 경로를 제공하거나 호스트가 보정하지 않는다.
이전 계획은 재귀 JSON으로 포함하지 않는다. 감사된 기준선 ZIP을 별도 바이트 파일로 보존한다.
계획 SHA-256: e9105f9de8dd8ad9b635dbc0f97696596168336d725882852ad2ae6059c604dc
event tip: 7b0bf4dd755f5ba0a5300ca993d997d178735caaa912ad65b5764c56368d9993
