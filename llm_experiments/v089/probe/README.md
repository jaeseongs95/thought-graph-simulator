# v089 — 초기 ID × 후속 ID 전환 교차 실험

v088 결과에서 분리하지 못한 초기 원자–ID 대응과 후속 ID 방식의 조합을 같은 구조에서 4×4로 비교한다. 상세 연구 계약은 `docs/PREREGISTRATION.ko.md`, 기계 계약은 `data/protocol.json`에 있다.

## 사용

Windows에서는 배포된 `Run-v089-Auto.ps1` 하나에 소스 ZIP이 내장되어 있다. Python이나 모델을 설치하지 않는다. 기존 Python 3.10 이상을 사용하며 Python 3.12 문법을 대상으로 확인한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v089-Auto.ps1" -CheckOnly -AllTests
```

CheckOnly는 설치, 실제 설치 소스 자체시험, calibration, v088 기준선 무결성/독립 검산, plan 생성까지만 한다. 실제 Ollama 조회/추론은 하지 않는다. 시험의 합성 HTTP는 격리된 임시 loopback 서버로서 Ollama가 아니다. 설치 출처는 로그 폴더의 `installation.json`에 기록된다.

검사가 정상 완료된 후 실제 실험을 시작한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v089-Auto.ps1"
```

실제 실행도 자체시험 및 calibration을 먼저 한다. `-AllTests`는 이전 자동화와의 명령 호환을 위해 받아들이며 모든 검사를 생략 없이 수행한다. CheckOnly의 RunName을 다시 지정하지 않는다. 자동 실행은 새 v089_idcross_<timestamp> 이름을 만든다.

기본 탐색이 실패하면 다음 옵션을 붙인다. 경로는 기존 사용자 환경의 예시다.

```powershell
-RepoRoot 'D:\codex\AI논문\thought-graph-simulator'
-Baseline 'D:\codex\AI논문\thought-graph-simulator\llm_experiments\v088\results_llm\v088_r2_idcontinuity_20260916_093741_268466_evidence.zip'
-PythonPath 'C:\Users\sjs95\AppData\Local\Programs\Python\Python312\python.exe'
```

기준선 SHA-256은 `2d9c2324aa9a9a64d97beb74cc158b24f1e7cf4f59df599a4a154ff110fcfbff`다. 서버는 사용자가 이미 실행한 Ollama 0.34.1이어야 한다. 모델 digest/template/parameters/runtime metadata가 다르면 추론 전 중단한다. 업데이트·모델 다운로드·서버 시작을 자동으로 하지 않는다.

## 설치 경계

새 소스: `llm_experiments/v089/probe`.
설치 manifest: `llm_experiments/v089/RELEASE_MANIFEST_v089.json`.
실행 guard: `llm_experiments/v089/results_llm/frozen_batch.started.json`.

이미 설치된 같은 소스는 교체하지 않는다. 소스가 다르거나 실행 흔적이 있으면 덮어쓰지 않는다. v088의 이전 manifest 충돌을 피하도록 v089 전용 manifest를 먼저 검증하며 잘못된 전용 manifest를 다른 상위 manifest로 우회하지 않는다. 기존 결과나 guard를 삭제해서 재실행하지 않는다.

## 산출물

`results_llm/v089_idcross_<timestamp>_evidence.zip`과 `_independent.json`을 결과 분석에 사용한다. evidence에는 원문 요청/응답, event hash chain, 소스 snapshot, 기준선, protocol, summary 및 최초 오류·risk-set 진단이 들어 있다. 독립 검산은 요청 재구성 및 의미 판정을 별도 구현한다. 바이트 보존·원응답 미보정이 기본이며, 집계/한국어 렌더링/진단의 공통 루틴은 공유한다고 표시한다.

## 오프라인 재현

설치 probe에서 다음을 실행한다. 결과 경로는 새 폴더여야 한다.

```text
python -X utf8 -B reproduce_synthetic.py --baseline <v088_evidence.zip> --out <새_검증_폴더>
```

이는 전체 실행·중단·검산 경로용 합성 응답이지 실제 Qwen의 연구 결과가 아니다. 최종 배포 검증 내역 및 수행하지 않은 항목은 배포 ZIP의 `VALIDATION_RESULT_v089.json`과 `validation/`에 기록한다.
