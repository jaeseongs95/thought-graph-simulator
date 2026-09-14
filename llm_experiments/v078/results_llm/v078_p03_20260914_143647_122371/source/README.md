# v078 / P03 — 규칙 수와 D를 분리한 새 구조 확인

v077은 완료된 배치다. premise_binding을 승격하지 않고 **base 계약을 유지**한다. v078은 새 문제의 동일 목표에서 shallow/deep 요구만 교체했을 때 실제 유효한 goal 지지 DAG의 D가 바뀌는지를 검사한다. 이번 소스 작성/시험 중 실제 Qwen 호출은 하지 않았다.

## 실행

`Run-v078-Auto.ps1` 하나를 다운로드 폴더에 저장한다. v077 원 evidence ZIP은 기존 v077/results_llm 또는 Downloads에 둔다. 이름에 `(1)`이 붙어도 내용 SHA-256으로 찾는다. Ollama와 `qwen3:4b-instruct`는 사용자가 기존 환경에서 켜 둔다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v078-Auto.ps1"
```

이 명령은 v078 소스 설치 → 자체시험 → v077 evidence 재감사 → 새 계획 동결 → **실제 추론 한 배치** → 보고서/독립 검산/evidence 생성까지 수행한다. 기존 v077 파일을 고치거나 다시 실행하지 않는다. 모델 다운로드·업데이트·서버 시작은 하지 않는다.

실제 추론이나 Ollama 조회 없이 먼저 점검하려면:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v078-Auto.ps1" -CheckOnly
```

`-CheckOnly`는 설치·시험·계획만 작성하며 started guard는 만들지 않는다. 그 뒤 위의 기본 명령을 실행하면 별도 고유 RunName으로 첫 실제 배치를 시작한다. `-AllTests`는 합성 HTTP·중단·변조까지 검사하며 실제 모델은 호출하지 않는다.

기존 v078 실행 상태만 읽으려면:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v078-Auto.ps1" -InspectOnly
```

저장소 자동 검색 우선 경로는 `D:\codex\AI논문\thought-graph-simulator`다. 검색 실패 시 `-RepoRoot`, `-Baseline`, `-PythonPath`를 명시한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v078-Auto.ps1" -RepoRoot "D:\codex\AI논문\thought-graph-simulator" -Baseline "$env:USERPROFILE\Downloads\v077_bindingpair_20260914_101310_397759_evidence(1).zip"
```

Python 3.10 이상, 표준 라이브러리만 필요하다. 기존 근거와 같은 모델 digest·Ollama 0.34.0·native template·옵션인지 검사하고 다르면 중단한다. 불일치를 자동 업데이트로 해소하지 않는다. Windows 전용 구문 검사를 제외한 실행/검산은 이 소스의 오프라인 시험 대상으로 포함된다.

## 배정과 문제

|문제|작은 D|해당 규칙 수|큰 D|해당 규칙 수|설계층|
|---|---:|---:|---:|---:|---|
|H01|2|3|3|3|규칙 수 동일|
|H02|3|4|4|4|규칙 수 동일|
|H03|2|4|3|3|규칙 수-D 역전|
|H04|3|5|4|4|규칙 수-D 역전|

본실험은 4문제 × 2seed × 2후보순서 × 2D요구 = **32조건/16쌍**이다. 실험자 경로 지정 참조는 16조건이며 선택 성공에 합산하지 않는다. 전체 생성 48개, 선택 요청32회, 최대 추론316회, 모든 선택이 목표 경로면308회, 진행332슬롯(메타데이터16슬롯 포함)이다. 메타데이터 슬롯 하나는 3개 HTTP 조회를 수행할 수 있으므로 진행슬롯 수를 전체 HTTP 요청 수로 부르지 않는다.

각 문제의 facts/rules/goal과 각 비교 쌍의 seed·후보순서는 같다. 선택 요청에서는 작은/큰 D 요구만 달라진다. 문제·후보에는 규칙 자체만 보이며 정답 D/규칙 수 표나 family 이름을 넣지 않는다. 새로운 원자명·규칙 ID·전체 규칙 나열을 고정했으며 이름/순서의 개별 효과를 추정하는 교차 실험은 아니다.

## 무엇을 유지했는가

v077의 base 프롬프트, API 옵션, seed, fact-only 형식, content-only history, 전체 graph/단계 검증을 유지했다. `measure.py`, `stages.py`, `audit_graph.py`, `audit_io.py`는 첨부 소스와 바이트 동일하다. premise_binding·부모 개수 강제·정답 parent ID 제공·사후 보정은 없다. 잘못된 경로를 골라도 그 선택을 그대로 생성한다.

D는 초기 사실0, 규칙 결과 `1 + max(전제 깊이)`다. 실제 goal 지지 DAG에서 다시 측정하며 규칙 수와 별도 필드로 기록한다. 길이 종료·미실행·HTTP·identity·파싱/스키마·논리 실패를 분리한다. 미측정 D는 `null`이고 0으로 채우지 않는다. 최종 graph가 맞아도 요청된 단계/경로를 어겼으면 종단 성공이 아니다.

## 결과

```text
llm_experiments/v078/results_llm/v078_p03_<시각>_evidence.zip
llm_experiments/v078/results_llm/v078_p03_<시각>_independent.json
llm_experiments/v078/results_llm/v078_p03_<시각>/summary.ko.md
llm_experiments/v078/results_llm/automation_logs/v078_p03_<시각>/run.log
```

보고서의 종단과 pair는 **같은 graph/단계/D 기준**이다. 대응표 계약 지표를 섞지 않는다. 전체·문제별·규칙 수 관계별 선택/생성/종단/쌍/참조를 분리한다. 전수 공학 기준(32/32·16/16쌍·참조16/16)은 별도 표시하며 일부 실제 성공을 지우지 않는다. 기존 개발 문제를 holdout으로 재명명하지 않았으며 새 구조4개도 외부 독립 표집 benchmark라고 주장하지 않는다.

## 중단되었을 때

가드 파일이 있으면 RunName을 바꿔도 자동화는 새 배치를 시작하지 않는다. 가드·응답·로그를 삭제하지 말고 `-InspectOnly`로 상태를 확인한다. guard는 첫 추론 전에도 생성될 수 있다. `run.py finalize --run <기존 결과 폴더>`는 보존된 파일을 묶고 검산하는 오프라인 명령이며 모델을 다시 호출하지 않는다. 실행 재개 명령은 없다.

## 소스와 재현

`data/protocol.json`: 동결 계약. `docs/PLAN_LEDGER.ko.md`: 계획장부. `preflight.py`/`audit_design.py`: 문제 구조 이중 검증. `design.py`/`run.py`: 실행. `report.py`: 생산 채점. `audit_model.py`/`audit_graph.py`/`verify.py`: 생산 채점 모듈을 import하지 않는 검산. `tests/fixtures.py`: 시험 전용 합성 모델이다.

직접 소스를 실행할 때 probe 디렉터리에서:

```powershell
$env:V078_BASELINE = "<v077 evidence ZIP의 실제 경로>"
python -X utf8 -B -m unittest discover -s tests -p "test_*.py" -v
python -X utf8 -B run.py prepare --baseline "$env:V078_BASELINE" --run-name v078_p03_manual --out ..\experiments\v078_p03_manual.plan.json
python -X utf8 -B run.py execute --plan ..\experiments\v078_p03_manual.plan.json --baseline "$env:V078_BASELINE" --out ..\results_llm\v078_p03_manual --endpoint http://127.0.0.1:11434
python -X utf8 -B verify.py ..\results_llm\v078_p03_manual_evidence.zip
```

시험의 `synthetic` 결과는 실제 LLM 성공 증거가 아니다. 검산 PASS는 같은 배치의 일관성 검증이며 새 독립 표본도 외부 실행 인증도 아니다.
