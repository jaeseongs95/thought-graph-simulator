# v086 — 동결한 값 비교·ID 조회 절차의 신규 구조 재현

## r2 재검토 수정

연구 protocol·문제·seed·요청 생성·스키마·채점·배정은 r1과 동일하다. 보조 진단의
`graph_result.error_codes` 누락과 HTTP 본문 조기 종료/불완전 chunk 처리만 고쳤다.
불완전 본문은 보존 후 transport_error로 중단하며 자동 재시도하지 않는다.
수정 근거와 회귀 범위는 `docs/REVIEW_FIXES_r2.ko.md`에 있다.

자동 실행 파일 이름은 **Run-v086-Auto-r2.ps1**이다. 미시작한 정확한 r1 설치본은
`probe.pre_r2_review` 및 `RELEASE_MANIFEST.pre_r2_review.json`에 보존한 뒤 교체한다.
실행 시작 흔적이 있거나 사용자가 수정한 파일이면 교체하지 않는다. 기존 r1 evidence는
r1 검산기로 읽으며, r2 소스로 소급 재채점하지 않는다.


v085의 직접 선택, 정확한 수치 지원, 값 비교→후보 ID 조회, `explicit_rule` 생성 계약을 그대로 유지하고 **새로운 8개 구조쌍 U01~U08에서 실제 D 종단과 표시 강건성을 확인**한다. 생성기나 W 조회 프롬프트를 동시에 고치는 실험이 아니다.

## 근거와 이번 질문

v085 동일 배치에서 D 양방향 종단은 기존 수치 지원군 31/64, 두 단계군 60/64였다. 두 단계군의 D 선택은 128/128, 네 표시 전체 종단은 13/16이었다. 단, 이는 v084에서 이미 관측한 T01~T08을 재사용한 결과다. 원본 근거는 `v085_valuelink_20260915_160544_012189_evidence.zip`의 plan/원응답/summary 및 `v085_결과분석_2026-09-15.md`다. 이 숫자는 v086 연구 결과가 아니다.

이번 질문은 **절차와 생성기를 고정하면 새 proof 구조에서도 두 단계군의 양방향 D 종단과 위치·ID 강건성이 재현되는가**다. 남은 생성 실패와 W 조회의 지표 의존성은 별도 진단으로 보존한다. 동일 구조에서 프롬프트를 반복 수정해 성공을 찾는 작업으로 대체하지 않는다.

## 비교군과 고정 조건

| 군 | 선택 절차 | 실제 D graph | 역할 |
|---|---|---:|---|
| `candidate_id` | 기존 직접 선택 | 128건 | 지원 없는 기준선 |
| `correct_values` | 기존 정확한 D/W 수치 지원 | 128건 | 주 비교 기준 |
| `two_stage_values` | 값 비교 원응답 → 후보 ID 조회 | 128건 | 동결 절차의 재현 평가 |
| `oracle_lookup` | 실험자의 정확한 목표값 → ID 조회 | 없음 | 조회 양성 대조 |

네 군은 v085와 같은 순서 교차를 사용한다. 모델 identity, 두 seed(64001001/64001002), API 옵션, 프롬프트 헤더, 스키마, 후보 ID, 두 위치×두 ID 배정, 생성기·원문 전달 방식도 유지한다. 구조를 바꾸므로 실제 새 문제 요청 바이트가 v085와 같다는 뜻은 아니다. **동일한 문제·이력 입력을 넣었을 때 기존 요청을 재구성하는 회귀시험**으로 계약 보존을 확인한다.

숫자 비교에는 `metric/direction/values`만 준다. 조회에는 수치표, 지표, 비교 원응답 문자열만 준다. 잘못된 숫자·ID·부모·규칙·final을 보정하지 않는다. 비교 오류와 조회 오류가 상쇄되어 우연히 goal graph만 맞아도 전체 종단 성공은 아니다. 정확한 외부 D/W는 실험자가 사전 계산한 지원 정보이며 모델 자력 DAG 깊이 계산 성과가 아니다.

## 새 구조

| 구조 | D: 얕음/깊음 | 규칙 수: 얕음/깊음 |
|---|---:|---:|
| U01 | 2 / 3 | 4 / 4 |
| U02 | 2 / 4 | 4 / 4 |
| U03 | 3 / 5 | 5 / 5 |
| U04 | 4 / 5 | 5 / 5 |
| U05 | 2 / 3 | 4 / 3 |
| U06 | 3 / 4 | 5 / 4 |
| U07 | 3 / 4 | 5 / 4 |
| U08 | 3 / 4 | 5 / 4 |

초기 사실 3개, primitive 규칙의 전제 1~3개, 모든 사실·규칙의 goal ancestry 포함을 요구한다. 두 경로는 같은 facts/goal을 공유하고 내부 결과 원자는 공유하지 않는다. 불필요한 규칙이나 토큰으로 깊이를 부풀리지 않는다.

`cases086.py`는 고정 SHA-256 후보 순서에서 원하는 D/W와 구조 신규성을 만족하는 첫 경로를 선택한다. 모델 호출·모델 결과·성공률을 보지 않는다. 후보 검사 횟수는 생성 provenance이며 연구 시행 수가 아니다. 동결된 `data/protocol.json`과 재생성 결과를 일치 검사한다.

생산 정규형과 별도 독립 전단사 검사로 기존 H01~H04 및 T01~T08의 12개 구조쌍, 신규 구조쌍끼리의 중복을 막는다. 더 강하게 신규 16개 개별 경로도 기존 24개 경로 및 다른 신규 경로와 비동형이어야 한다. 부분 모티프 공유는 허용된다. 새 구조는 무작위 IID 표본이 아니다. U01/U05~U08은 기존 D/W 조합의 구조 재현 5개이며, U02~U04는 이전에 없던 깊이 조합 2/4, 3/5, 4/5를 포함한다. 이 세 구조에서는 숫자 범위도 D=5까지 넓어진다. 두 범주의 성과는 별도로 보고한다. 숫자 과제의 반복 횟수를 독립 구조 수로 세지 않는다.

## 사전 배정과 판단

D 본실험 graph는 3군×128건=384건이다. 공통 지정 경로 참조 32건은 한 번만 실행한다. W는 규칙 수가 다른 U05~U08에서 군당 64건의 선택만 평가한다. oracle_lookup는 D/W 모두 조회만 평가한다.

선택·조회 768호출, 두 단계 숫자 비교 192호출, 총 graph 416건이다. 모든 선택이 목표 경로를 택하면 추론 3,612회, 최장 경로를 택할 경우 최대 3,708회다. metadata를 포함한 action은 3,740개다. 선택에 따라 여분 규칙 슬롯은 제외되며 미실행·HTTP 오류·잘못된 출력과 구분한다.

주평가는 **구조별 양방향 D 종단 차이〔two_stage_values−correct_values〕의 동일 가중치 평균**이다. 구조별 개선·악화·동일·미관측을 모두 남긴다. 전체 8개 구조의 쌍대조가 완료되지 않으면 전체 효과를 추정하지 않는다. 두 seed×네 표시를 독립 구조로 세거나 자동 p값을 계산하지 않는다. 기존 D/W 조합의 구조 재현 5개와 새로운 깊이 조합 3개의 효과도 별도로 집계한다.

양방향 성공에는 shallow/deep 두 요구에 대해 각각 올바른 비교·조회·유효 graph·실제 D가 필요하다. 단방향, 양방향, 네 표시 전체 성공은 분리한다. 평균 개선이 있어도 일부 표시가 무너지면 안정적 제어라고 쓰지 않는다. 종단 일부 실패가 전체 평균 개선을 지우지도 않는다. 현재 구조에서의 성과이며 A/M 독립성·hidden-layer 깊이·다른 모델 대비 우월성을 시험하지 않는다.

## 결과 보고의 보완

기본 `summary.json`, `summary.ko.md` 외에 **`diagnostics.json`, `diagnostics.ko.md`**를 evidence 안에 보존한다.

- 군·지표·단계별 요청 수와 seed 포함/제외 고유 요청 수. 같은 숫자 과제를 독립 산술 문제로 늘리지 않는다.
- 두 단계/oracle의 조회 요청 바이트 동일 여부. 같은 요청의 반복을 새 독립 문제로 합산하지 않는다.
- 같은 경로를 고른 기존 수치군/두 단계군의 최초 facts 요청 바이트와 생성 성패. `selection_original`의 공백/개행 차이를 제거하지 않는다.
- 입력에서 metric만 다른 D/W 조회 대조. 나머지 입력이 같을 때만 해당 비교에 포함한다.
- 생성 실패별 겹치는 graph 오류 코드와 실패 단계, D 본실험의 호출·토큰·duration 및 누락 수.

보조 집계는 선택/graph를 새로 채점하지 않는다. 생산과 독립 검산기가 각각 독립적으로 계산한 행에 같은 바이트 집계 함수를 적용한다. 의미 채점은 공유하지 않는다. 원응답 usage 합은 유일 토큰 수·API 청구액·벽시계 시간이 아니다.

## 실행

Windows 11 / 기존 Python 3.12 / Ollama / `qwen3:4b-instruct` 환경을 대상으로 한다. Python 3.10 이상과 표준 라이브러리만 사용한다. 모델 identity는 v085와 동일해야 한다. 다른 모델·서버 버전이면 진행하지 않는다.

Downloads에 `Run-v086-Auto-r2.ps1`을 저장하고 실행한다. 소스 ZIP은 PS1에 내장되어 있다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v086-Auto-r2.ps1"
```

모델 조회·추론 없이 설치·자체시험·측정기 점검·계획 생성만 하려면:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v086-Auto-r2.ps1" -CheckOnly -AllTests
```

`-AllTests`를 생략해도 전체 자체시험을 수행한다. `-CheckOnly`는 frozen batch를 시작하지 않는다. 실제 실행 전 Ollama는 이미 켜져 있어야 한다. 다운로드·업데이트·서버 시작·자동 재시도는 하지 않는다.

기준 evidence `v085_valuelink_20260915_160544_012189_evidence.zip`이 필요하다. `v085/results_llm`, 저장소의 `results_llm`, Downloads에서 해시가 맞는 파일만 찾는다. 자동 탐색이 되지 않으면 `-RepoRoot`, `-Baseline`, `-PythonPath`를 지정한다.

원본 v085 ZIP SHA-256:

```text
ef10ac69002c0c8015deb38ced44cb83d39b9ce34e1e5dfe5c9cbf21aef56589
```

소스 ZIP을 사용하는 경우 전체를 추출한 후 다음을 실행한다.

```text
python -X utf8 -B llm_experiments/v086/probe/launch.py --repo-root <저장소> --baseline <v085_evidence.zip> --check-only --all-tests
```

결과 위치:

```text
llm_experiments/v086/results_llm/
  v086_holdout_<timestamp>/
  v086_holdout_<timestamp>_evidence.zip
  v086_holdout_<timestamp>_independent.json
```

기존 v083~v085를 변경하지 않는다. 실행이 시작된 배치는 다른 RunName으로 우회 재실행하지 않는다. 중단된 증거·가드를 보존하고 읽기 전용 상태 확인을 사용한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v086-Auto-r2.ps1" -InspectOnly
```

수동 독립 검산:

```text
python -X utf8 -B llm_experiments/v086/probe/verify086.py <v086_evidence.zip>
```

## 개발 검증의 범위

합성 HTTP·오프라인 graph·v085 원응답 회귀시험은 연구 가설의 새 모델 표본이 아니다. `selftest086.py --out <json>`은 실제 시험 ID·결과·skip 이유·소스 해시·플랫폼·실제 Qwen 호출 0을 기록한다. 네이티브 PowerShell 파서가 없으면 그 시험을 skip으로 표시한다. 최종 수행 수치는 배포와 함께 전달한 `VALIDATION_RESULT_v086.json`을 기준으로 한다.

상세 사전등록은 `docs/PREREGISTRATION.ko.md`, 구현 검토는 `docs/IMPLEMENTATION_REVIEW.ko.md`에 있다.
