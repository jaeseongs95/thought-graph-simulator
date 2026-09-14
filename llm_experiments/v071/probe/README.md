# v071 — 모델 깊이 계산 원문 → 수치 선택 / 정답 깊이 양성 대조

v070 evidence를 재검산하면 유효한 후보 경로 40/40, 올바른 D 선택 20/40, 선택적 쌍 0/20이다. v070의 단일 호출 후보 선택 계약은 종료한다. v069의 지정 append-only graph 구성 12/12는 그대로 보존한다.

v071은 v070의 문구만 바꾸어 재실행하지 않는다. 계산과 비교를 분리한 새 출력 계약을 한 배치로 시험한다.

## 실험

5문제 × 2seed × 2후보 순서 = 20개 단위다. 각 단위에서 다음 다섯 호출을 수행한다.

- 깊이 계산 1회: 문제·규칙·후보 두 개를 보고 `{"depths":[d0,d1]}`를 출력한다. D 요구 방향이나 정답 깊이는 주지 않는다.
- 모델 원문 선택 2회: 위 `message.content` 원문을 그대로 전달하고 작은 D/큰 D 인덱스를 각각 출력하게 한다.
- 정답 깊이 선택 2회: 별도 양성 대조로 실험자가 미리 계산한 정확한 깊이 두 개를 주고 작은 값/큰 값 인덱스를 선택하게 한다.

최대 **100회 추론, 140개 action**이다. 40개 모델 선택은 깊이 계산 20개를 두 번씩 공유한다. 각 선택 결과는 `{"candidate_index":0}` 또는 `{"candidate_index":1}`이며, 인덱스와 원래 후보의 대응은 사전 고정이다. 호스트가 더 작거나 큰 후보를 대신 고르는 작업은 없다.

초기 사실 D=0, 규칙 결과 D=1+max(전제 D). 규칙 수 동률 C01과 규칙 수 역전 C02를 유지한다. 정답입력군의 성공은 모델이 깊이를 계산한 성과가 아니다. 모델 단계의 깊이가 틀리면 뒤의 선택이 우연히 맞아도 전체 성공이 아니다. 두 경우의 경로 선택 자체 성공률은 별도로 보존한다.

## 실행

배포된 `Run-v071-Auto.ps1` 하나를 다운로드 폴더에 저장하고 기존 Ollama가 켜져 있는 상태에서 실행한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v071-Auto.ps1"
```

필요 입력은 실제 v070 ZIP이다. 파일명 변경이나 `(1)` 접미사는 허용하지만 바이트 SHA-256은 고정이다.

```text
v070_select_20260913_213212_243277_evidence.zip
SHA-256 b91117c7b65bd60d5dc187251f9880e272d1224d3bf615e32354a382df98ebc6
```

자동 탐색 위치는 기존 저장소의 `llm_experiments/v070/results_llm`, 저장소 `results_llm`, 다운로드 폴더다. 탐색 실패 시 명시 경로를 사용할 수 있다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v071-Auto.ps1" -RepoRoot "D:\codex\AI논문\thought-graph-simulator" -Baseline "C:\경로\v070_select_20260913_213212_243277_evidence.zip"
```

기존 버전은 덮어쓰지 않는다. 소스는 `llm_experiments/v071/probe`에 설치된다. 기본 자체시험은 오프라인 논리 시험이다. `-CheckOnly`는 실제 모델 요청을 하지 않으며, `-AllTests`는 합성 HTTP 대역 시험도 포함한다. `-AllTests` 역시 실제 Qwen을 시험한 결과는 아니다.

실제 실행을 시작한 배치는 `results_llm/frozen_batch.started.json`으로 잠그며 다른 RunName으로 자동 반복하지 않는다. 모델 다운로드·갱신·Ollama 시작은 하지 않는다. HTTP/transport/identity 오류와 예산 초과 시 중단한다. 형식 오류에는 재시도·보정을 하지 않는다.

## 결과 파일

```text
llm_experiments/v071/results_llm/v071_depthcompare_<시각>_evidence.zip
llm_experiments/v071/results_llm/v071_depthcompare_<시각>_independent.json
```

분석에는 위 두 파일을 전달한다. 자동화 로그도 같은 버전의 `results_llm/automation_logs`에 남긴다.

## 성공 및 종료

완료·측정 가능한 상태에서 깊이 계산 20/20, 정답 깊이 선택 40/40 및 20/20쌍, 모델 계산→선택 40/40 및 20/20쌍이 모두 맞아야 이번 기준선을 확보한다. 미완료·미측정은 전체 gate `null`이다. 부분 성공은 그대로 남기고 한 배치 이후 계약을 종료한다. 다음 실험은 자동으로 실행하지 않는다.

생성기 호출은 0회다. 성공해도 후보 목록 내 계산·선택 기준선이며, 실제 graph 종단 D 제어가 아니다. v070과 동시 대조한 설계가 아니고 동일 비용 비교도 아니다. C01/C02까지 이미 사용한 문제이며 독립 holdout이 아니다.

## 검산

`verify.py`는 생산 `design`, `depths`, `measure`, `reference`, `report`, `run`을 불러오지 않는다. 요청·스케줄·수치·경로 깊이·단계/쌍 성공·한국어 보고서를 별도로 재구성한다. 공통 바이트 계약과 동결 명세는 공유한다. 번들 일관성 검산은 외부 장비에서 실제 실행했다는 사실의 외부 인증이 아니다.

개발 검증에서 실제 Qwen 추론은 수행하지 않았다. Windows PowerShell 네이티브 시험은 Windows에서만 실행된다. 상세 연구 조건은 `docs/PROTOCOL.ko.md`, 이전 결과는 `docs/REVIEW_AND_CHANGES.ko.md`에 있다.
