# v058: 같은 seed에서 graph/choice 순서를 뒤집어 재실행

v057 원문 분석에서 seed와 과제 선후의 교락이 발견됐다. v058은 Qwen의 `T02/original/shallow`와 Gemma의 `K01/original/shallow`에서 같은 seed를 두 실행 순서에 모두 배정하는 **80회 탐색적 진단**이다. [분석 보고서](docs/V057_ANALYSIS.ko.md)와 [사전 프로토콜](docs/V058_PROTOCOL.ko.md)에 관점 도출, 독립 반론, 설계 선택 근거를 기록했다.

각 모델의 10개 seed마다 graph→choice와 choice→graph를 새로 실행한다. 요청·옵션·모델 identity는 v057과 같고, 호출 순서만 정해진 일정으로 바꾼다. 두 모델의 문제가 다르므로 일반적인 모델 성능 비교로 해석하지 않는다. shallow만 검사하므로 shallow/deep 제어 성공률도 계산하지 않는다.

## Windows 원클릭 실행

파일 탐색기에서 `llm_experiments/v058/probe/windows/Run-v058.cmd`를 더블클릭한다. 이 실행기는 시스템 실행 정책을 바꾸지 않고 해당 PowerShell 프로세스에만 `ExecutionPolicy Bypass`를 적용해 `Run-v058.ps1`을 시작한다. 스크립트가 저장소 위치를 자동으로 찾고, 새 실행명을 선택한 뒤 자체시험, v057 입력 검증, 계획 동결, Ollama 확인, 80회 추론, 감사, 증거 ZIP 생성, 독립 검산을 차례로 수행한다. 모델을 다운로드하거나 실패한 추론을 재시도하거나 기존 실행을 덮어쓰지 않는다.

PowerShell 터미널에서 직접 시작할 때도 `./Run-v058.ps1` 대신 다음 명령을 사용한다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Run-v058.ps1
```

Ollama와 모델을 건드리지 않고 실행기·입력·기준 계획만 점검하려면 저장소 루트에서 다음을 실행한다.

```powershell
powershell -ExecutionPolicy Bypass -File .\llm_experiments\v058\probe\windows\Run-v058.ps1 -CheckOnly -NoPause
```

선택 매개변수로 `-RunName v058_order_02`, `-BaselineBundle <경로>`, `-SkipSelfTest`, `-NoOpen`, `-NoPause`를 사용할 수 있다.

## 설치와 오프라인 확인

Python 3.10 이상과 표준 라이브러리가 필요하다. 소스 ZIP은 **새 빈 폴더**에 푼다. 안에 들어 있는 `llm_experiments/v057/probe`와 `llm_experiments/v058/probe`의 상대 위치를 유지한다. v057은 변경하지 않은 감사·채점 의존성이다. ZIP에는 원래 실험 결과나 모델 가중치를 넣지 않는다.

`llm_experiments/v058/probe`에서 다음을 실행한다.

```powershell
python -B -m order_replay_v058 selftest
python -B tools/validate_inputs.py --directory ../../v057/results_llm --out ../validation/input_validation_layout.json
python -B tools/analyze_v057.py ../../v057/results_llm/v057_selection_01_evidence.zip --out ../validation/v057_analysis_layout.json
python -B -m order_replay_v058 prepare --baseline-bundle ../../v057/results_llm/v057_selection_01_evidence.zip --out ../experiments/v058_order_layout.plan.json
python -B -m order_replay_v058 show --plan ../experiments/v058_order_layout.plan.json
```

`validate_inputs.py`에는 v057 계획, baseline ZIP, preflight JSON, evidence ZIP, 독립 검산 JSON의 다섯 자료가 필요하다. 기본 위치는 `llm_experiments/v057/results_llm/`이며, 계획·baseline·preflight가 `llm_experiments/v057/experiments/`에 분리된 현재 구조도 자동으로 확인한다. `prepare`에는 evidence ZIP 하나가 필요하다. 오프라인 명령은 실제 모델을 호출하지 않는다. 자체시험의 로컬 가짜 HTTP 서버는 모델 추론이 아니며 연구 성과로 합산하지 않는다.

계획과 기준선 파일은 기존 경로를 덮어쓰지 않는다. 소스가 바뀌면 계획 검사가 거부하므로 최종 소스에서 새 계획을 준비해야 한다. 제공된 검증용 계획은 검증 당시의 해시를 보여 주는 자료이고 설치 위치의 모델·서버 상태를 미리 보증하지 않는다.

## 실제 실행 명령

아래 `run`은 실제 Ollama 추론 80회를 수행한다. 이번 소스 제작·검증 과정에서는 실행하지 않았다. 사용자가 실제 실험을 수행할 때 사용한다.

```powershell
python -B -m order_replay_v058 run --plan ../experiments/v058_order_layout.plan.json --out ../results_llm/v058_order_01
python -B -m order_replay_v058 audit --plan ../experiments/v058_order_layout.plan.json --run ../results_llm/v058_order_01
python -B -m order_replay_v058 bundle --plan ../experiments/v058_order_layout.plan.json --run ../results_llm/v058_order_01 --out ../results_llm/v058_order_01_evidence.zip
python -B tools/verify_v058.py ../results_llm/v058_order_01_evidence.zip --out ../results_llm/v058_order_01_independent.json
```

동결된 서버·모델 identity가 다르거나 HTTP 요청이 실패하면 즉시 멈춘다. Ollama 0.34가 같은 `parameters` 항목을 다른 줄 순서로 반환할 수 있으므로 줄의 순서만 정규화한다. 각 줄의 값과 중복·누락 여부, 모델 digest, 서버 버전, details, template, model_info는 그대로 비교한다. 모델 다운로드, 자동 재시도, 중단된 추론의 자동 재개는 없다. 정상 HTTP로 받은 형식·논리 오류는 실패 또는 미측정으로 기록하고 예정된 다음 호출을 진행한다. metadata 검사는 상태를 읽을 뿐 모델이나 캐시를 초기화하지 않는다.

## 결과를 읽는 방법

`summary.json`과 `summary.ko.md`에서 같은 seed의 choice 선택 ID 변화와 방향 이행 변화를 확인한다. `first`와 `second`는 전체 실행의 첫 번째·두 번째 반복이 아니라 **각 두 과제 묶음 안에서의 위치**다. choice의 first는 choice→graph, second는 graph→choice다. 직전 호출 ID·과제, 원문 cache 수치와 종료 필드도 남긴다.

choice의 `implied_depth`는 규칙에 대응하는 깊이이고 실제 증명의 D는 아니다. 실제 D는 유효한 graph에서만 계산한다. 미실행과 미측정은 별도로 두며 전체 미완료에서는 비교율이 null이다. 순서 차이가 나더라도 캐시나 내부 사고의 구체적인 원인이 확정되는 것은 아니다.

## 배포본 검사

```powershell
python -B tools/build_release.py --out ../releases/v058_order_replay_source_repo.zip
python -B tools/build_release.py --check ../releases/v058_order_replay_source_repo.zip
```

ZIP은 소스 폴더 밖 경로에 저장한다. 배포 manifest는 모든 소스·문서·의존성의 바이트 해시를 기록한다. 기존 v057 파일은 재작성하지 않는다. 검증 결과와 시험의 적용 범위는 [검증 기록](docs/VALIDATION.ko.md)에 기록한다.
