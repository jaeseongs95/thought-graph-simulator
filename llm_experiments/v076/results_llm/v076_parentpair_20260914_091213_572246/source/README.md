# v076 — 동일 선택·부모 수 제약 종단 비교

v075 분석을 근거로 한 새 실행 전 계약이다. 사실 전용 스키마를 두 군에서 유지하고, 한 군만 규칙의 부모 수를 제한한다. 응답 해시는 evidence에 보존하되 모델 프롬프트에서는 두 군 모두 제외한다. 정확한 부모 ID는 모델이 직접 고른다. 기존 점수의 수정이나 오답의 사후 복구는 하지 않는다.

## Windows 실행

단일 배포 파일 `Run-v076-Auto.ps1`을 다운로드 폴더에 저장한다. 기존 Ollama 서버와 Qwen 모델을 사용한다. 이전 v075 evidence ZIP을 다운로드 폴더 또는 기존 v075/results_llm에 보관한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v076-Auto.ps1"
```

무추론 검사(설치·자체시험·v075 재감사·계획 생성, Ollama 조회조차 없음):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v076-Auto.ps1" -CheckOnly
```

자동 경로 검색이 실패할 때는 `-RepoRoot "기존 저장소 경로" -Baseline "v075 evidence ZIP 경로" -PythonPath "기존 python.exe 경로"`를 지정한다. 일반 실행은 logic/paired_contract 자체시험을 한다. `-AllTests`는 합성 HTTP·무결성 시험까지 포함한다. 자동 다운로드·설치·모델 갱신·Ollama 시작은 하지 않는다.

## 파일

- `data/protocol.json`: 동결 입력·모델 identity·호출 상한.
- `docs/PLAN_LEDGER.ko.md`: r4 연구 계획장부. 기존 r3와 결과는 frozen 문서에 보존.
- `design.py` / `run.py`: 요청 구성·로컬 실행. 과제 content를 고치지 않는다.
- `report.py`, `measure.py`, `stages.py`: 실제 증명·단계·D 채점. 기존 의미 채점기를 유지한다.
- `verify.py`, `audit_model.py`, `audit_graph.py`, `audit_io.py`: 생산 계산 모듈을 import하지 않는 별도 검산.
- `previous.py`, `prior/v075_source.zip`: 해시가 고정된 v075 증거를 직전 검산기로 확인.

최대404회, 모든 선택이 목표 경로이면348회. 실제 호출 수는 선택 경로에 따라 달라진다. 각 군 본실험24건·참조12건, 선택은 공유24회다.

```text
llm_experiments/v076/results_llm/v076_parentpair_<시각>_evidence.zip
llm_experiments/v076/results_llm/v076_parentpair_<시각>_independent.json
```

## 직접 명령

저장소에서 이 probe 디렉터리로 이동한 뒤 사용한다. Windows에서는 같은 Python 실행 파일로 실행한다.

```text
python -X utf8 -B run.py prepare --baseline <v075 evidence.zip> --run-name v076_parentpair_<고유시각> --out <plan.json>
python -X utf8 -B run.py execute --plan <plan.json> --baseline <v075 evidence.zip> --out <실행이름과 같은 폴더> --endpoint http://127.0.0.1:11434
python -X utf8 -B verify.py <생성한 evidence.zip>
```

`--synthetic`는 시험 응답 출처를 명시하는 개발용 표지다. 실제 모델 결과로 사용하지 않는다. 중단 후 수동 finalize는 기존 원문을 읽는 오프라인 기능이며 추론을 재개하지 않는다. 동일 배치 재실행은 차단한다.

## 성공 판정의 범위

부모 수만 맞는 것은 충분하지 않다. 실제 전제, 부모 ID, 단계 계약, 전체 graph, 목표 D, 공유 선택 정오를 각각 확인한다. 선택 오류는 생성 성공으로 숨기지 않는다. P03·A/M·새 구조 일반화·비용 비교는 자동으로 실행하지 않는다. 세부 오류·통과·종료 기준은 계획장부에 있다.
