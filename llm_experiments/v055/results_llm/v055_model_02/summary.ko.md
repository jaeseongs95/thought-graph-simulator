# v055 두 소형 모델의 D 제어 비교

무결성: True / 완료: True / 호출: 240/240 / 출처: live_source_artifacts
방향 지정 160회와 중립 80회. 유효 증명 생성과 선택적 D 제어를 분리한다.

## reference: qwen3:4b-instruct

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

### 선택적 제어

|문제/순서|배정 쌍|둘 다 유효|선택적 성공|중립 대비 차이|
|---|---:|---:|---:|---:|
|K01/original|10|10|0|0.0%p|
|K01/swapped|10|10|0|0.0%p|
|T02/original|10|10|0|0.0%p|
|T02/swapped|10|0|0|0.0%p|

### 두 규칙순서 모두에서 유지되는 제어

|문제|배정 seed|4개 응답 유효|두 순서 모두 성공|
|---|---:|---:|---:|
|K01|10|10|0|
|T02|10|0|0|

### 순서 효과: 유효한 두 응답만 깊이 비교

|문제/방향|배정|둘 다 유효|깊이 변화|미측정|
|---|---:|---:|---:|---:|
|K01/shallow|10|10|10|0|
|K01/deep|10|10|10|0|
|K01/neutral|10|10|10|0|
|T02/shallow|10|0|0|10|
|T02/deep|10|0|0|10|
|T02/neutral|10|0|0|10|
## candidate: gemma3:4b

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
|T02/swapped/deep|10|10|2|2|{'unmeasured': 8, '4': 2}|
|T02/swapped/neutral|10|10|0|해당 없음|{'unmeasured': 10}|

### 선택적 제어

|문제/순서|배정 쌍|둘 다 유효|선택적 성공|중립 대비 차이|
|---|---:|---:|---:|---:|
|K01/original|10|0|0|0.0%p|
|K01/swapped|10|0|0|0.0%p|
|T02/original|10|0|0|0.0%p|
|T02/swapped|10|0|0|10.0%p|

### 두 규칙순서 모두에서 유지되는 제어

|문제|배정 seed|4개 응답 유효|두 순서 모두 성공|
|---|---:|---:|---:|
|K01|10|0|0|
|T02|10|0|0|

### 순서 효과: 유효한 두 응답만 깊이 비교

|문제/방향|배정|둘 다 유효|깊이 변화|미측정|
|---|---:|---:|---:|---:|
|K01/shallow|10|0|0|10|
|K01/deep|10|0|0|10|
|K01/neutral|10|0|0|10|
|T02/shallow|10|0|0|10|
|T02/deep|10|0|0|10|
|T02/neutral|10|0|0|10|

## 모델 간 선택적 제어 비교

|문제/순서|배정|미관측 쌍|둘 다 성공|Qwen만|Gemma만|둘 다 미성공|Gemma−Qwen|
|---|---:|---:|---:|---:|---:|---:|---:|
|K01/original|10|0|0|0|0|10|0.0%p|
|K01/swapped|10|0|0|0|0|10|0.0%p|
|T02/original|10|0|0|0|0|10|0.0%p|
|T02/swapped|10|0|0|0|0|10|0.0%p|

## 해석 범위

2문제×10 seed의 대응 기술통계. 숫자 seed를 공유해도 모델 사이 동일 난수 표본은 아님. 방향/순서/모델 비교는 같은 240응답 재집계이며 합산하지 않음.
요청의 model 필드만 바꿨다. 모델 패키지의 가중치·tokenizer·native template·한국어 처리 차이를 단독 분해한 실험은 아니다.
규칙 순서에 반응하는 것만으로 D 제어에 성공한 것이 아니다. 내부 사고·학습 우선순위·A/M 전체 제어를 직접 계측하지 않는다.
HTTP 실패는 자동 재시도하지 않는다. 원문을 보정하거나 정답 경로를 대신 채우지 않는다.
모델별 raw token/time은 summary.json에 있다. 캐시·로드 비용을 포함하므로 속도 우열 검정이 아니다.
계획 SHA-256: 3414191469c3955336beae9219569344dff5a1cedeb58b45fda8b2a085cb078e
event tip: d9f163a528ba37433c1dda798daced52ebe872dd311c2817189fa73e4a4b08c5
해시는 동봉 계획·원문 일관성 검사이며 외부 실행 전자서명이 아니다.
