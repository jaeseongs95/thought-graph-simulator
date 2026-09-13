# v056: 입력 메시지 배치 대조

v055의 실제 240회 자료를 변경하지 않고 새 480회 실험을 추가한다. 현재 Qwen/Gemma, 한국어 지시 내용, 문제·규칙·두 규칙 순서, 샘플링 옵션, seed, JSON Schema 및 증명 채점 기준을 그대로 유지한다.

## 질문

기존 system/user 두 메시지를 **내용을 추가하지 않고 한 user 메시지로 연결**하면, (1) 증명 유효성과 (2) shallow/deep 선택적 제어가 각각 어떻게 달라지는가?

Gemma가 실패한 원인을 미리 확정하지 않는다. 기록된 모델 template의 역할 변환과 Google의 첫 user 메시지 내 지시 배치 안내를 근거로, 메시지 배치라는 실행 조건을 대조한다. 배치 변경은 역할·턴 경계·구분자 위치를 묶어서 바꾸므로 각각의 내부 효과를 분리 입증하지 않는다.

## 실행

휴대폰 원격 작업은 별도로 제공한 **Run-v056-Auto.ps1 하나**를 Windows 다운로드 폴더에 저장한 후 실행한다. 이 파일에는 검증된 소스 ZIP이 내장되어 있으므로 소스 ZIP을 별도로 받지 않아도 된다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v056-Auto.ps1"
```

수동으로 이 ZIP을 풀었다면 `v056_layout_probe`를 기존 `thought-graph-simulator` 아래에 추가하고 실행한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\windows\Run-All.ps1
```

기준선: `..\results_llm\v055_model_02_evidence.zip`. 자동화는 존재하는 두 모델을 확인하며 모델을 다운로드·업데이트하지 않는다. 기존 v055 폴더 및 모든 결과는 그대로 둔다. v056 설치본도 실제 파일 전체가 같을 때만 재사용하며, 다르면 이름을 붙여 보존 백업한다.

## 자동 처리 순서

배포 무결성 검사 → 안전한 새 설치 또는 전 파일 확인 후 재사용 → 빠른 로컬 회귀시험 → 실제 v055 전체 재감사·계획 준비·재읽기 → Ollama 확인/필요 시 서버만 시작 → **두 모델 식별값 선확인** → 480회 실행 → 원문 재감사 → 증거 ZIP → 별도 그래프 계산기에 의한 독립 검산 → 요약 및 결과 파일 표시.

어떤 하위 단계든 실패하면 중단한다. 다른 RunName을 만들어 자동으로 실험을 다시 시작하지 않는다. 모델·증명·참조·응답 문법의 자동 보정도 하지 않는다. 자동화 재실행은 사용자가 직접 시작할 때만 가능하며 이전 자료는 보존된다.

기본 자체시험은 빠른 네트워크 없는 검사다. Windows에서도 누적 전체 시험을 실행하려면 `-AllTests`를 추가한다. 누적 시험의 HTTP 호출은 합성 시험 서버에 대한 것이며 실제 Qwen/Gemma 추론과 구분한다.

## 구성과 성공 기준

2모델 × 2배치(split/merged) × 2문제 × 2규칙 순서 × 3방향 × 10seed = **480회**. 방향 지정 320회, 중립 160회. split 240요청은 실제 v055 요청과 바이트 동일. merged는 같은 원문 두 개를 줄바꿈 두 개로 연결한 단일 user 메시지만 다르다.

같은 모델·배치·문제·규칙 순서·seed에서 shallow와 deep 증명이 둘 다 유효하고 각각 가능한 최소/최대 깊이를 가져야 D 선택적 성공이다. 둘 중 하나만 우연히 맞은 것은 대응쌍 성공이 아니다. 순서 영향, 중립 대비 변화, 두 순서에 걸친 제어, 증명 유효성 개선을 서로 분리한다.

계획은 과거 계획 JSON을 재귀적으로 복제하지 않는다. 기준선 ZIP을 별도 파일로 보존하고 전체 재감사로 요청은행과 식별자를 대조한다. 계획 JSON 한도 32 MiB, 일반 응답 JSON 한도 8 MiB이며 중복 key·비유한 수·파일 추가·삭제·변조는 계속 거부한다.

## 산출물

기본 빈 이름은 `v056_layout_01`이며, 이미 자료가 있으면 다음 빈 번호를 사용한다.

- `results_llm/v056_layout_01.plan.json` 및 `.plan.baseline.zip`: 외부 동결 계획과 원 v055 ZIP
- `results_llm/v056_layout_01.preflight.json`: 추론 전에 확인한 두 모델의 metadata 원문
- `results_llm/v056_layout_01/`: 상태·이벤트·요청·응답·source snapshot·summary
- `results_llm/v056_layout_01_evidence.zip`: 이후 재감사 가능한 증거
- `results_llm/v056_layout_01_independent.json`: 생산 모듈을 import하지 않는 검산 결과
- `results_llm/automation_logs/`: 단계 로그 및 완료 영수증

## 보장 경계

모델 내부 hidden state나 학습 우선순위를 계측하지 않는다. metadata template은 기록하지만 서버 내부의 최종 토큰 스트림을 기록했다고 주장하지 않는다. 해시는 동봉 자료와 계획의 일관성을 검사하며, 전체 자료를 함께 조작한 공격을 막는 외부 전자서명은 아니다.

Windows PowerShell 5.1을 대상으로 작성했다. 이 배포에 대한 실제 실행 환경과 시험 결과는 별도 분석·검증 ZIP의 VALIDATION_RESULT.json 및 실행 로그에 기록한다. Windows 실기 실행과 합성 Linux 실행을 혼동하지 않는다.
