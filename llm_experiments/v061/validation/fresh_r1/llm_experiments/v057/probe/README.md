# v057: 전체 증명 생성과 마지막 규칙 선택의 분리

v056 실제 결과는 메시지를 합쳐도 D 제어가 생기지 않았다는 것이다. 다음 진단은 동일한 문제에서 **전체 증명 DAG를 작성하는 과제(graph)**와 **요구한 경로의 마지막 규칙 ID 하나를 선택하는 과제(choice)**를 비교한다. choice 성공을 증명 생성이나 A/D/M 핵심 제어 성공으로 보고하지 않는다.

## 휴대폰 원격 실행

별도로 제공한 `Run-v057-Auto.ps1` 한 파일을 PC 다운로드 폴더에 저장한 후 실행한다. 검증된 소스 ZIP이 내장되어 있어 따로 압축을 풀 필요가 없다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v057-Auto.ps1"
```

기본 저장소는 바탕화면의 `thought-graph-simulator`, 기준선은 `results_llm\v056_layout_01_evidence.zip`이다. 추가로 제출한 v056 `.plan.baseline.zip`은 해당 evidence ZIP 내부에도 동일하게 들어 있으므로 새 자동화의 별도 입력은 아니다.

수동 설치는 이 `v057_selection_probe` 폴더를 기존 저장소 밑에 추가하고 `windows\Run-All.ps1`을 실행한다. 기존 v056 폴더와 결과는 수정하지 않는다.

## 수행 흐름

소스 실제 파일·해시 확인 → 신규 설치 또는 동일 바이트 재사용 → 빠른 자체시험 → v056 전체 기준선 재감사 → 새 계획 동결/재읽기 → Ollama 상태 확인 → 기존 두 모델 identity 확인 → 480회 실행 → 원문 감사 → 증거 ZIP → 독립 검산.

모델은 다운로드하거나 갱신하지 않는다. 없는 모델/변경된 identity면 추론 전에 중단한다. 서버만 꺼져 있으면 기존 Ollama를 시작할 수 있다. 결과 실패 후 모델 재요청·다른 RunName으로 자동 재실행·답안 보정은 하지 않는다. 사용자가 재실행할 때만 새 빈 이름을 선택하고 기존 자료를 보존한다.

## 실험 구성

2모델 × 2과제 × 2문제 × 2규칙순서 × 3방향 × 10seed = **480회**. graph 240회와 choice 240회 각각을 새로 실행하며, 방향 지정은 총 320회, 중립은 총 160회다. 두 모델 모두 v056의 merged 배치를 공통 사용한다.

**보존:** 모델 digest/show/template, 옵션, 전체 seed, facts/rules/goal, 규칙 제시 순서, 원래 경로 지시. graph 요청 240개는 실제 v056 merged 요청 바이트를 그대로 쓴다.

**변경:** choice는 전체 증명 작성 설명과 schema를 마지막 규칙 ID 하나의 선택 과제로 바꾼다. 원래 문제와 경로 지시는 그대로다. 정답 그래프·깊이·규칙을 제공하지 않으며 선택 가능한 정답 ID enum도 사용하지 않는다.

## 성공 기준

각 모델/과제/문제/순서/seed에서 shallow와 deep을 모두 올바르게 이행해야 선택적 성공이다. 한쪽만 우연히 맞거나 규칙 순서만 따라 달라진 것은 선택적 성공이 아니다.

- graph: 모든 사실·규칙·부모 연결이 맞는 단일 유효 증명의 실제 깊이 D를 계산한다.
- choice: 반환한 마지막 규칙이 goal에 도달하는 유효 경로에 해당하는지, 그 경로의 깊이가 요구에 맞는지 검사한다. 이는 선택 진단이며 `proof_valid`, `strict_valid`, `D`는 null이다. 별도의 `implied_depth`는 문제 명세에서 도출한 대응값이지 생성된 증명이 아니다.

현재 K01/T02는 마지막 규칙으로 깊이를 식별할 수 있다. 그렇지 않은 문제로 확장되면 채점기가 승인하지 않는다. 이 진단의 성공만으로 다른 그래프나 모델 내부 사고를 제어했다고 주장하지 않는다.

## 출력

기본 빈 이름은 `v057_selection_01`이다.

```text
results_llm/v057_selection_01.plan.json
results_llm/v057_selection_01.plan.baseline.zip
results_llm/v057_selection_01.preflight.json
results_llm/v057_selection_01/summary.ko.md
results_llm/v057_selection_01_evidence.zip
results_llm/v057_selection_01_independent.json
results_llm/automation_logs/
```

기존 실행명이 있으면 다음 빈 번호를 사용한다. 실제 추론 시작 후 오류가 나면 멈추며 새 번호로 자동 재시도하지 않는다.

## 시험

```powershell
python -m selection_probe_v057 selftest --quick
python -m selection_probe_v057 selftest
python -m selection_probe_v057 selftest --all
```

자동화 기본은 빠른 시험이다. 전체 누적 시험도 실행하려면 자동화 명령 끝에 `-AllTests`를 붙인다. 시험의 가짜 HTTP 서버 응답을 실제 Qwen/Gemma 연구 성과로 합산하지 않는다. 배포본의 실제 시험 결과와 실행 로그는 별도 분석·검증 ZIP에 있다.

## 해석 경계

이는 출력 과제 묶음을 비교하는 진단이다. 문자 수 한 요소의 효과, 내부 이해도, 학습 우선순위, 같은 호출 안에서 계획을 잊었는지를 단독 측정하지 않는다. 기존 원문 전체와 실패를 보존하고, 다음 결정을 결과에 따라 내린다.
