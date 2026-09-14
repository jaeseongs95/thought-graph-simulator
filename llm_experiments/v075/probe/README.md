# v075 — 같은 선택 원값을 공유하는 두 종단 생성기

실제 Qwen의 v075 추론은 아직 실행 전이다. v074 결과(선택20/24, 종단8/24, 양방향3/12, 참조3/12)를 보존한다. 첫 facts 단계에서 규칙 노드를 미리 쓰는 관찰을 근거로 **기존 스키마와 사실 전용 스키마**를 한 배치 안에서 비교한다. 숫자·공백 진단은 재개하지 않는다.

세부 계약: `docs/PROTOCOL.ko.md` / 새 장부: `docs/PLAN_LEDGER.ko.md` / 이전 동결 장부: `docs/PLAN_LEDGER_v074_frozen.ko.md`.

## 실행

Python3.10 이상과 표준 라이브러리만 사용한다. 기존 Ollama와 `qwen3:4b-instruct`를 켜 두어야 한다. 모델·서버를 시작/설치/다운로드/갱신하지 않는다.

`Run-v075-Auto.ps1`을 다운로드 폴더에 저장하고 이번 v074 evidence ZIP을 다운로드 폴더 또는 기존 v074/results_llm에 보관한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v075-Auto.ps1"
```

설치·오프라인 자체시험·v074 감사·계획 생성만 수행(실제 Ollama 조회/추론 없음):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v075-Auto.ps1" -CheckOnly
```

자동으로 경로를 못 찾을 때만 명시한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v075-Auto.ps1" -RepoRoot "D:\codex\AI논문\thought-graph-simulator" -Baseline "$env:USERPROFILE\Downloads\v074_endtoend_20260914_070558_230235_evidence.zip"
```

`-PythonPath`는 설치된 python.exe를 직접 지정한다. `-AllTests`는 합성/변조를 포함한 전체 시험이며 기본은 오프라인 핵심·짝비교 시험이다. 파일명에 `(1)`이 붙어도 evidence 내용 해시로 검사한다. 기존 소스·계획·실행 결과를 덮어쓰지 않는다.

## 규모와 결과

공유 선택24회, 본실험 생성24건×2군, 참조12건×2군. 최대404회이며 모두 요구 경로를 선택하면348회다. 모델 상태 조회와 생략 슬롯을 포함한416 진행 슬롯을 추론404회와 혼동하지 않는다.

```text
llm_experiments/v075/results_llm/v075_factpair_<시각>_evidence.zip
llm_experiments/v075/results_llm/v075_factpair_<시각>_independent.json
```

각 군의 최초 사실 단계/구성 충실/목표D구조/종단/양방향/참조와 같은 선택을 공유하는 짝비교를 별도로 기록한다. 선택 하나를 두 생성기가 썼다고 성공 선택 표본을 두 배로 세지 않는다.

## 오류 처리와 증거

잘못된 선택/노드/부모/사실/최종ID를 고치지 않는다. facts 스키마 제한도 atom/id 정답을 제공하지 않는다. 틀린 원문은 그대로 후속 단계로 가며 해당 단계의 실패를 보존한다. 파싱·length·미실행과 의미상 오류를 구분하고 HTTP/transport/identity/생성예산 초과는 중단한다. 자동 재시도·새 RunName 반복·다음 버전 실행은 없다.

중단 뒤 증거만 다시 묶는 명령은 추론하지 않는다. 반드시 해당 실행의 동결 소스를 사용한다.

```powershell
python -X utf8 -B .\llm_experiments\v075\probe\run.py finalize --run ".\llm_experiments\v075\results_llm\v075_factpair_실제실행이름"
```

source ZIP 내 파일을 수정하면 동결 소스 검산이 거부되므로 계획 수정은 별도 revision으로 보존한다. 원본 evidence와 과거 결과를 고치지 않는다.

## 검증 경계

measure.py/stages.py는 이전 v074/v069 바이트를 그대로 보존했다. 독립 검산은 생산 design/report/measure/stages를 import하지 않고 실제 요청과 raw history, 선택 공유, 스키마 처치, graph, 단계, 집계·한국어 보고서를 재계산한다. source archive 해시는 변경 검출용이며 외부 실행 사실 인증이 아니다.

합성 시험을 실제 모델 성능으로 보고하지 않는다. Windows PowerShell 네이티브 실행 여부와 수행한 시험 수는 별도 배포 검증 결과에 기록한다.
