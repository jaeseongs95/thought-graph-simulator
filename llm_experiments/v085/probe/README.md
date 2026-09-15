# v085 — 값 비교·후보 ID 연결 분리와 실제 D 종단

v084에서 관측한 T01~T08을 그대로 사용하여, 정확한 숫자의 작은/큰 값 선택과 해당 값의 후보 ID 조회를 분리한다. 기존 직접 선택과 수치 지원 선택을 비교 기준으로 유지하고, 새 절차도 기존 `explicit_rule` 생성기로 실제 proof DAG까지 평가한다. **새 holdout이나 모델 내부 원인 식별 실험으로 표시하지 않는다.**

## 근거와 이번 질문

v084의 D 양방향 종단은 직접군 3/64, 수치 지원군 30/64였다. 지원군의 선택 오류 30건은 모두 정답이 두 번째인 조건에서 첫 번째를 고른 사례였다. 두 번째 정답의 ID가 `route_1`이면 30/32, `route_0`이면 4/32였다. 생성기만 바꾸기보다 선택의 관측 가능한 하위 과제를 분리할 근거다. 근거는 기존 evidence 및 `v084_결과분석_2026-09-15.md`이며, 수치는 v085 결과가 아니다.

이번 질문은 **값 비교→ID 조회의 명시적 절차가 기존 수치 지원보다 실제 D 양방향 종단과 표시 강건성을 높이는가**다. 개선과 악화 모두 같은 기준으로 보존한다.

## 비교군

| 군 | 선택 절차 | D 증명 생성 | 역할 |
|---|---|---|---|
| `candidate_id` | 기존 v084 직접 선택 | 128건 | 지원 없는 비교 기준 |
| `correct_values` | 기존 v084 정확한 D/W 수치 지원 | 128건 | 주 비교 기준 |
| `two_stage_values` | 값 비교 원응답 → 값과 후보 ID 조회 | 128건 | 새 절차의 실제 종단 평가 |
| `oracle_lookup` | 실험자가 정확한 목표값 제공 → ID 조회 | 없음 | 조회만의 양성 대조 |

네 군 모두 W는 선택만 배정한다. 지정 경로 생성 참조 32건은 한 번만 실행하고 군별 D 성과에 합산하지 않는다.

### 두 단계의 입력 경계

첫 단계는 `metric`, `direction`, `values`만 받는다. 후보 ID·규칙·문제·정답 ID를 주지 않는다. `{"target_value":2}` 형태의 정수를 출력한다. 스키마는 0~128 정수 범위이며 정답 후보 숫자만 강제하는 enum이 아니다.

두 번째 단계는 후보별 D/W 측정표, 지표, **첫 응답의 원문 문자열**을 받는다. 요구 방향과 원문 문제·규칙은 주지 않는다. 원문이 잘못된 숫자여도 정답으로 교체하지 않는다. 일치하는 후보가 정확히 하나일 때 해당 ID를 반환하고, 일치하지 않으면 `null`을 반환하도록 한다. `null`은 관측된 기권이며 증명 생성은 미실행으로 남긴다.

비교가 틀렸는데 조회까지 틀려 우연히 올바른 경로를 선택한 경우도 있을 수 있다. 그런 경우 유효 목표 graph 도달은 별도로 기록하지만 **모든 선택 단계와 실제 graph가 맞아야 하는 종단 성공으로 세지 않는다.**

`oracle_lookup`의 정확한 목표값은 실험자가 제공한 양성 대조다. 그 성공은 모델 자력 비교나 실제 D 종단 성과가 아니다.

## 사전 배정

- 관측된 구조 8개: 같은 규칙 수에서 D가 다른 4개, 얕은 경로의 규칙 수가 더 많은 4개. 문제·원자·규칙·후보 경로를 변경하지 않는다.
- 기존 두 seed, 위치 2종×ID 배정 2종, shallow/deep를 유지한다. 실패한 표시만 선별하지 않는다.
- 군별 D 선택 128건, W 선택 64건. 선택/조회 합계 768건.
- 두 단계군의 추가 숫자 비교 192건. 모델이 DAG 깊이 계산표를 작성하는 요청은 0건이다.
- D 본실험 graph 384건, 공통 참조 32건: 총 416건.
- 모든 선택이 목표 경로를 택하면 추론 3,612회. 동결 최대 3,708회, metadata를 포함한 action 3,740개.
- 경로가 짧으면 여분 규칙 슬롯은 정상 제외한다. 잘못된 비교 출력·null·transport 중단으로 미실행된 슬롯은 별도 상태로 남긴다.

## 성공 판정과 해석

주평가는 **구조별 D 양방향 종단 성공률〔two_stage_values−correct_values〕의 동일 가중치 평균**이다. 군당 64쌍을 64개의 독립 구조로 세지 않는다. 각 구조 내부의 두 seed×네 표시는 반복이다. 한 구조가 미관측이면 해당 차이를 추정하지 않고, 전체 8개가 완전 비교되지 않으면 전체 주효과를 산출하지 않는다.

단방향·양방향·네 표시 전체 통과·위치/ID별 선택·숫자 비교·조회 준수·선택 후 생성·규칙 연결 실패·사용량을 따로 보고한다. D는 최종 goal의 유효한 proof DAG에서 초기 사실 0, 유도 결과 `1 + max(전제 깊이)`로 다시 계산한다. W는 규칙 수다. 중간 비교·후보 ID·graph를 보정하지 않는다.

새 군은 입력 문맥 축소, 응답 형식, 호출 수와 단계 분리를 함께 변경한다. 따라서 좋은 결과가 나와도 그중 하나의 단독 효과나 v084 내부 사고 순서를 증명한 것으로 쓰지 않는다. 이 실험이 확인하는 것은 **명시한 절차의 효과와 분리된 외부 하위 과제의 수행 패턴**이다. 지원군 성과를 자력 D 계산, A/M 제어 또는 hidden layer 제어로 확장하지 않는다.

## Windows 실행

권장 환경은 기존 Windows 11 / Python 3.12 / Ollama다. 런처는 Python 3.10 이상을 요구한다. Python 표준 라이브러리만 사용하며 패키지 설치는 하지 않는다. 기존 모델 identity와 API 설정은 v084 기준으로 고정돼 있어 다른 서버·모델 상태면 실행을 중단한다.

`Run-v085-Auto.ps1`에는 고정 소스 ZIP이 내장되어 있다. Downloads에 저장한 다음 실행한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v085-Auto.ps1"
```

실제 Ollama 조회·추론 없이 설치, 전체 자체시험, 측정기 점검 및 계획 생성만 수행하려면:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v085-Auto.ps1" -CheckOnly -AllTests
```

`-AllTests`는 기존 사용법 호환 인자다. 생략해도 전체 자체시험을 수행한다. `-CheckOnly`는 frozen batch를 시작하지 않는다. 실제 실행은 서버가 이미 켜져 있어야 한다. 다운로드·모델 업데이트·서버 시작·자동 재시도는 하지 않는다.

기준 evidence `v084_holdout_20260915_143819_336235_evidence.zip`이 필요하다. v084/results_llm, 저장소 results_llm, Downloads에서 **파일 해시가 일치하는 원본만** 찾는다. 자동 탐색이 안 되면 `-RepoRoot`, `-Baseline`, `-PythonPath`를 명시할 수 있다. 동일 이름의 다른 evidence로 대체하지 않는다.

원본 v084 SHA-256:

```text
98b6963b27ecfb4c111a543da7d6c23ace37b02303804d64e3e4ddfe0ae63304
```

### 소스 ZIP으로 실행

ZIP 전체를 추출하면 `RELEASE_MANIFEST.json`과 `llm_experiments/v085/probe`가 있다. 그 안의 `launch.py`를 다음처럼 호출할 수 있다.

```text
python -X utf8 -B launch.py --repo-root <기존_저장소> --baseline <v084_evidence.zip> --check-only --all-tests
```

원래 v084 probe/evidence는 변경하지 않는다. v085의 다른 소스나 기존 manifest가 있으면 자동 교체하지 않는다. 실행이 시작된 frozen batch는 다른 RunName으로 우회 재실행하지 않는다. 중단되면 다음 읽기 전용 명령으로 상태를 확인한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v085-Auto.ps1" -InspectOnly
```

## 결과와 독립 검산

```text
llm_experiments/v085/results_llm/
  v085_valuelink_<timestamp>/
  v085_valuelink_<timestamp>_evidence.zip
  v085_valuelink_<timestamp>_independent.json
```

`summary.ko.md`와 `summary.json`은 결과 폴더/ZIP 안에 있다. 독립 검산은 원문 요청·응답, 동결 계획, dispatch 표지, 상태와 event chain을 재구성하여 계산한다. `verified=true`는 번들 내부 일관성 검산이지 외부 실행 사실의 별도 인증이 아니다. evidence에는 source snapshot과 v084 기준 evidence가 포함된다. 새 결과와 기준 evidence를 중복 표본으로 합산하지 않는다.

수동 검산:

```text
python -X utf8 -B verify085.py <v085_evidence.zip>
```

정확한 CLI 옵션은 각 파일의 `--help`로 확인할 수 있다. 소스·계획·원응답을 바꾸면 검산이 거부되므로, evidence를 수정해 통과시키지 않는다.

## 개발 검증

`tests/`는 실제 모델 대신 합성 HTTP 응답과 보존된 v084 기록을 사용한다. 자체시험 성공은 연구 가설 지지가 아니다. `selftest085.py --out <json>`은 개별 시험 ID, 통과·실패·제외, 시험한 source hash와 실제 Qwen 호출 0을 기록한다. Windows 네이티브 PowerShell 파서가 없는 환경은 해당 시험을 제외로 표시한다.

상세 사전등록: `docs/PREREGISTRATION.ko.md`. 구현 검토: `docs/IMPLEMENTATION_REVIEW.ko.md`. 실제 배포 검증 수치와 플랫폼은 함께 전달한 `VALIDATION_RESULT_v085.json`을 기준으로 한다.
