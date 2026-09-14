# v072 — Gemma에서 v071 깊이 계산·수치 선택 계약 재현

v071 Qwen 원문 재검산 결과는 깊이 계산 **2/20**, 정답 깊이 선택 **28/40**, 모델 원문 실제 경로 선택 **24/40**, 정확한 계산→선택 전체 **2/40**, 전체 비교 쌍 **0/20**이다. v071의 Qwen 수치 분해 계약은 종료한다.

v072는 문구·예시·seed를 조정하는 반복이 아니다. 첨부 evidence의 설치 목록에 있는 **gemma3:4b**에서 같은 계약을 한 번 검사한다. Gemma의 성공을 미리 전제하지 않는다.

## 실행

`Run-v072-Auto.ps1` 하나를 다운로드 폴더에 저장하고, 기존 Ollama 서버가 켜진 상태에서 실행한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v072-Auto.ps1"
```

이 자동화에는 소스 ZIP이 내장돼 있다. 모델 다운로드·갱신·서버 시작은 하지 않는다. 기존 모델 중 요청 대상을 Gemma로 지정하며, Qwen의 새 추론 호출은 하지 않는다.

기준 evidence는 다음 원본이다. 파일명에 `(1)`이 붙어도 바이트 해시가 같으면 된다.

```text
v071_depthcompare_20260913_221758_352826_evidence.zip
SHA-256 7a995a40d9db35cf06472b421ace231083e2d0b705d9bc6a336f3d35d0eae535
```

자동 탐색 위치는 저장소 `llm_experiments/v071/results_llm`, 저장소 `results_llm`, 사용자 `Downloads`다. 탐색되지 않는 경우 명시 경로를 사용한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v072-Auto.ps1" -RepoRoot "D:\codex\AI논문\thought-graph-simulator" -Baseline "C:\경로\v071_depthcompare_20260913_221758_352826_evidence.zip"
```

`-CheckOnly`는 설치·오프라인 논리시험·v071 원문 재감사·계획 생성만 수행한다. `-AllTests`는 합성 HTTP 시험을 포함한 전체 코드 시험을 수행한다. 이는 실제 모델 성능 측정이 아니다. 자동화와 모델 실행은 같은 배치의 기존 결과를 덮어쓰거나 오류 뒤 새 RunName으로 반복하지 않는다.

## 실험

5문제 × 2seed × 2후보 순서 = 20개 block이다. v071과 호출 순서도 같다.

|단계|제공 내용|호출 수|
|---|---|---:|
|깊이 계산|문제, 규칙, 후보 경로 2개. 정답 깊이/선택 방향은 미제공|20|
|모델 원문 선택|같은 block에서 나온 Gemma 깊이 계산 원문 + 작은/큰 D 요구|40|
|정답 숫자 양성 대조|명시적으로 참 깊이 2개 제공 + 작은/큰 D 요구|40|
|합계|metadata 40회(각 3개 HTTP 조회)를 포함하면 140개 action|100 추론|

고정 입력 60개의 API 요청은 v071과 비교할 때 `model` 필드만 달라진다. 원문 의존 선택 40개는 **이번 Gemma 출력**에 의존하므로 실제 입력값이 달라질 수 있다. 동일 원문에 대한 요청 생성 동등성도 회귀시험한다.

`temperature=0.7`, `top_p=0.8`, `top_k=20`, `min_p=0`, `repeat_penalty=1`, `num_ctx=8192`, `num_predict=4096`, 두 seed 및 그 밖의 명시 옵션을 유지한다. 원문 요청의 모델 필드 외 변화가 필요한 서버 오류는 자동 완화하지 않고 중단한다.

## 무보정과 채점

초기 사실 D=0, 규칙 결과 D=1+max(전제 D)다. 규칙 수를 깊이로 대체하지 않는다. 깊이 계산은 `{"depths":[d0,d1]}`, 선택은 `{"candidate_index":0}` 또는 1이다. 추가 필드, bool/float, 잘못된 범위는 측정 실패로 분리한다.

Gemma의 중간 `message.content` 문자열을 그대로 전달한다. 잘못된 숫자/JSON/공백도 교정하지 않는다. 정답 숫자는 오직 별도 양성 대조에만 제공한다. 계산이 틀리고 마지막 선택만 맞으면 전체 성공이 아니다. 미실행·HTTP·파싱·identity·길이 종료도 구분하며, 미측정을 오답/D=0으로 채우지 않는다.

100개 호출 중 계산은 20번이며, 각 계산을 두 선택이 공유한다. 문제별 집계, 후보 순서별 성패, 정답/모델 숫자군, 고유 요청 수를 따로 보고한다. 고유 요청 수도 통계적 독립성의 보장은 아니다.

## 모델 식별

Gemma 이름/digest/tag details와 Ollama 버전은 첨부 v071 metadata에 고정한다.

```text
gemma3:4b
a2af6cc3eb7fa8be8504abaf9b04e88f17a119ec3f04a3addf55f92841195f5a
```

Gemma template 등은 아직 관측하지 않았으므로 Qwen 값으로 채우지 않는다. 첫 추론 전 metadata `b00_before`에서 실제 native template/system/parameters/model_info/details/capabilities/projector_info를 보존하고 이후 metadata에서 같은지 확인한다. 파라미터 문자열의 줄 순서만 정규화한다. 누락 또는 변경이면 중단하며 모델을 설치/업데이트하지 않는다.

## 성공·종료 기준

전체 완료·측정 가능할 때 깊이 계산 20/20, 정답 숫자 선택 40/40 및 20/20쌍, 정확한 모델 계산→선택 40/40 및 20/20쌍을 충족해야 이 **Gemma/동일 계약**의 기준선이다. 미측정·미완료는 전체 gate null이다. 각 실패 항목과 부분 성공을 보존하고 한 배치 후 종료한다.

Qwen의 v069 구성 12/12는 보존하지만 Gemma의 구성 성공으로 옮기지 않는다. 생성기 호출은 0회이며, 성공해도 전체 graph의 종단 D 제어를 입증한 것이 아니다. 과거 Qwen과의 비동시 비교이므로 네이티브 템플릿 등을 포함한 모델 패키지 비교이지 가중치만 바꾼 인과 비교는 아니다. 사용한 문제들은 독립 holdout이 아니다.

## 결과

```text
llm_experiments/v072/results_llm/v072_gemma_<시각>_evidence.zip
llm_experiments/v072/results_llm/v072_gemma_<시각>_independent.json
```

분석에는 위 두 파일을 전달한다. 자동화 로그는 `results_llm/automation_logs`에 있다.

`verify.py`는 생산 design/depths/measure/reference/report/run을 import하지 않는다. 공유하는 것은 바이트/JSON 계약·동결 프로토콜·고정된 이전 소스 감사 래퍼다. 번들 내부 검산은 외부 장비 실행의 인증이 아니다.

개발 환경에서 실제 Gemma/Qwen 추론은 수행하지 않았다. Windows 네이티브 실행 시험은 Windows에서만 실행된다. 자세한 이전 결과는 `docs/REVIEW_AND_CHANGES.ko.md`에 있다.
