# v084 — 신규 구조에서 D 양방향 종단 재현

v083 결과를 근거로 **선택·생성 계약은 유지하고 문제 구조를 교체**한 후속 실험이다.
직접 선택 `candidate_id`와 정확한 수치 지원 `correct_values`를 비교한다.
기존 v083 코드/결과/가드는 변경하지 않는다. 소스만으로 연구 성공을 주장하지 않는다.

## 실행

단일 파일 `Run-v084-Auto.ps1`에는 이 소스 ZIP이 내장되어 있다. 별도 압축 해제가 필요 없다.
기존 v083 evidence ZIP은 `llm_experiments/v083/results_llm` 또는 Downloads에 보존한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v084-Auto.ps1"
```

실제 모델 호출 없이 먼저 검사하려면 다음과 같이 실행한다. 자체시험에는 Ollama가 아닌 loopback 합성 HTTP 서버 시험이 포함된다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v084-Auto.ps1" -CheckOnly -AllTests
```

`-AllTests`는 기존 호출 호환성을 위한 옵션이며, 이 버전은 생략해도 전체 자체시험을 수행한다.
저장소·기준선 경로가 자동 탐색되지 않을 때만 명시한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v084-Auto.ps1" `
  -RepoRoot 'D:\codex\AI논문\thought-graph-simulator' `
  -Baseline "$env:USERPROFILE\Downloads\v083_controlcross_20260915_131258_306803_evidence.zip"
```

Python은 기존 설치본을 사용한다. `py` 명령을 요구하지 않는다. 자동 탐색 실패 시 `-PythonPath`에 기존 python.exe를 지정한다.
모델 다운로드/업데이트, Ollama 시작, 자동 재시도는 하지 않는다. 실제 실행은 기존 로컬 서버가 실행 중인 상태에서만 가능하다.
v083의 서버 버전·모델 digest·native 설정을 확인하고 불일치하면 추론 전에 중단한다.

## 변경과 유지

| 구분 | 내용 |
|---|---|
| 새 주제 | 기존 네 문제의 표현 조정이 아니라 신규 구조쌍 8개에서의 재현 |
| 선택기 | v083의 `candidate_id` / `correct_values` 그대로 |
| 생성기 | `explicit_rule`, `fact_only` 초기 사실 제약 그대로 |
| 고정 | 헤더·스키마·API 옵션·두 seed·모델 identity·무보정 채점 |
| 미실행 군 | `correct_full`, `swapped_values`는 v084 배정에서 제외 |
| 보조 대조 | W는 규칙 수가 다른 4개 문제에서 선택만 실행 |
| 공통 참조 | 문제·seed·방향별 지정 경로 생성 32건; 군에 중복 합산하지 않음 |

숫자 지원 헤더의 “참고 자료의 정확성은 보장되지 않는다”라는 표현까지 v083에서 그대로 유지했다.
이번에는 지원값이 모두 정확하지만, 헤더까지 고쳐 효과를 유리하게 만들지 않는다.
기존 요청과 같은 문제·이력을 주었을 때 v083의 실제 1,020개 요청 바이트가 일치하는 회귀시험이 포함된다.

## 신규 문제와 배정

| 구조 | shallow D/W | deep D/W | 비교 유형 |
|---|---:|---:|---|
| T01 | 2 / 4 | 3 / 4 | 같은 규칙 수 |
| T02 | 3 / 4 | 4 / 4 | 같은 규칙 수 |
| T03 | 3 / 5 | 4 / 5 | 같은 규칙 수 |
| T04 | 3 / 5 | 4 / 5 | 같은 규칙 수 |
| T05 | 2 / 4 | 3 / 3 | 규칙 수 역전 |
| T06 | 3 / 5 | 4 / 4 | 규칙 수 역전 |
| T07 | 3 / 5 | 4 / 4 | 규칙 수 역전 |
| T08 | 3 / 5 | 4 / 4 | 규칙 수 역전 |

각 구조에서 2 seed × 후보 위치 2종 × ID 배정 2종 × shallow/deep를 고정한다.
한 군당 D 선택 128건, D 생성 128건, D 양방향 pair 64개다. 한 군당 W 선택은 64건이다.
전체 선택 384회, graph 288건(본실험 256+참조 32), 진행 슬롯 2,316개다.
모든 선택이 목표 경로를 고르면 2,220회, 최대 2,284회 추론한다. 모든 선택이 매핑될 때 최단 경로 기준 최소는 2,156회다.
선택 JSON이 매핑되지 않으면 해당 graph는 요청하지 않으므로 실제 호출 수는 이 최소보다 작아질 수 있다.
metadata 32회는 모델 추론으로 세지 않는다.

## 성공과 주장 범위

주평가는 **구조별 양방향 D 종단 성공률 차이(지원−직접)의 동일 가중치 평균**이다.
구조 하나는 8개의 pair(2 seed × 4 표시)를 포함한다. 64개 pair를 64개의 독립 구조로 취급하지 않는다.
한 구조에서 미관측 pair가 있으면 해당 구조 효과는 미판정이고 전체 8구조 평균도 미판정이다.
완료 구조·가족별 관측과 미관측은 별도 보고된다. p-value를 자동 산출하지 않는다.

구조는 응답을 보기 전에 정한 8개 새 문제쌍이다. 기호 재명명 여부를 두 별도 구현으로 검사한다.
부분 가지나 모티프는 겹칠 수 있으므로 IID 무작위 표본, 모든 개별 경로가 전혀 새롭다는 뜻은 아니다.
지원군 성공을 모델의 자력 D 계산 성공으로 바꾸지 않는다.

모델 자기보고 대신 실제 proof graph의 전체 전제/부모/규칙/최종 ancestry를 검사한다.
초기 사실 D=0, 규칙 결과 D=1+max(전제 D), 최종 목표의 D_DAG를 측정한다.
선택, 생성, 유효 graph, 요구 D 종단, 양방향, 네 표시 강건성을 분리한다.
실패·미관측·사전 미배정을 구분하고 rule/parent/final을 사후 보정하지 않는다.

## 산출물

실제 실행 완료 또는 중단 후 가능한 범위에서 다음 파일을 생성한다.

```text
llm_experiments/v084/results_llm/
  v084_holdout_<timestamp>/
    plan.json
    status.json
    summary.json
    summary.ko.md
    source/
    baseline/v083_evidence.zip
    wire/...
    records/...
  v084_holdout_<timestamp>_evidence.zip
  v084_holdout_<timestamp>_independent.json
```

분석에는 evidence ZIP과 independent JSON을 함께 사용한다. independent는 번들 내부 일관성 검산이지 외부 실행 인증이 아니다.
부분 실행도 원응답과 dispatch 표지를 보존한다. 검산 반복은 새 모델 실험 표본이 아니다.
가드가 있으면 새 RunName으로 우회하지 않는다. 상태만 보려면 다음 명령을 사용한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v084-Auto.ps1" -InspectOnly
```

중단이 발생하면 가드를 지우거나 재실행하지 말고 해당 evidence/로그를 분석한다.

## 소스 구조

- `cases084.py`, `data/protocol.json`: 사전 고정 구조·배정·지원값. `cases084.py --check`로 재구성 일치를 검사한다.
- `design084.py`, `run084.py`: 요청과 기록. 모델 응답을 보정하지 않는다.
- `report084.py`: 생산 채점·집계.
- `audit084.py`, `verify084.py`: 생산 요청/채점 모듈을 import하지 않는 독립 재구성·검산.
- `legacy/`: v083에서 사용한 의미 채점기·스키마 처리 등을 바이트 그대로 보존.
- `calibrate084.py`: 원자 재명명·규칙 나열·합법적 위상 나열·무효 증명에 대한 오프라인 교정.
- `selftest084.py`, `tests/`: 전체 합성 실행, 요청 회귀, 변조·중단·Windows 경로·HTTP 시험.
- `launch.py`, `windows/Auto.template.ps1`: 로컬 설치/검사/실행 자동화.
- `prior/v083_source.zip`, `previous084.py`: 고정 v083 결과의 원래 독립 검산기 재실행.

필수 외부 Python 패키지는 없다. Python 표준 라이브러리만 사용한다. 지원 최소 Python 버전은 3.10이며 사용자 환경은 3.12다.
실제 이 개발 환경에서의 플랫폼별 실행 여부·검사 수는 배포와 함께 제공하는 별도 검증 결과에 기재한다.

## 기준 evidence

파일: `v083_controlcross_20260915_131258_306803_evidence.zip`

SHA-256: `6132c1db632afd8e1bd8d5c98bc2a0639252ddcedd21a44423ff876b1d239a5e`

Plan SHA-256: `1e9ad6f1be311d3c8e5de34eed786f4234f0f94e3b6e05cc0e444e5262f3ed8e`
