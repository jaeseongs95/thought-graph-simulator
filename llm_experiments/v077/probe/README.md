# v077 — 동일 선택·모델 작성 전제 대응표 종단 비교

v076은 부모 수를 맞춰도 존재하는 다른 전제 노드를 선택하는 실패를 보였다. 이번에는 base를 유지하고 다른 군만 규칙 노드와 전제→부모 ID 대응표를 모델이 같이 작성한다. 부모 수 강제는 채택하지 않는다. 표로 node를 보정하거나 정답 부모 ID를 제공하지 않는다. 효과는 실제 모델 실행 후 판단한다.

## 실행

`Run-v077-Auto.ps1`을 다운로드 폴더에 저장한다. 기존 Ollama와 Qwen은 사용자가 켜 둔다. 이번 v076 evidence ZIP을 Downloads 또는 기존 `v076/results_llm`에 보관한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v077-Auto.ps1"
```

Ollama 조회·실제 추론 없이 설치·자체시험·이전 증거 재감사·계획 생성만 하는 명령:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v077-Auto.ps1" -CheckOnly
```

경로 검색 실패 시 `-RepoRoot "기존 저장소 경로" -Baseline "v076 evidence ZIP 경로" -PythonPath "기존 python.exe 경로"`를 지정한다. Python 3.10 이상과 표준 라이브러리만 사용한다. `-AllTests`는 합성 HTTP·변조 검사를 포함한다. 자동 모델 다운로드·갱신·서버 시작·기존 버전 덮어쓰기·실패 재시도는 없다.

## 설계와 출력

공유 선택24회, 두 군에 각각 본실험24건·실험자 지정 참조12건. 최대404회 추론, 모든 선택이 목표 경로면348회. 추가 대응표는 별도 호출이 아니라 기존 규칙 호출 안에서 생성한다. 토큰량은 달라질 수 있다.

`bindings`의 premise와 parent_id는 모델이 직접 작성한다. node는 기존 스키마 그대로다. 전체 graph에는 모델의 node를 그대로 연결하고, 표의 전제·실제 원자·부모 ID 일치를 별도로 검사한다. node가 맞고 표만 틀린 경우 graph-only 성과는 보존하지만 새 계약 전체는 실패다. 모델 출력에 있는 표와 공백·개행은 다음 호출에 그대로 전달된다.

```text
llm_experiments/v077/results_llm/v077_bindingpair_<시각>_evidence.zip
llm_experiments/v077/results_llm/v077_bindingpair_<시각>_independent.json
```

## 주요 파일

`docs/PLAN_LEDGER.ko.md`는 r5 계획장부, `data/protocol.json`은 실행 전 동결 계약이다. `design.py`/`run.py`는 무보정 실행, `report.py`/`bindings.py`는 오프라인 채점이다. 기존 `measure.py`/`stages.py`는 바이트 동일하게 보존했다. `audit_model.py`/`audit_bindings.py`/`audit_graph.py`/`verify.py`는 생산 채점 모듈을 import하지 않는 별도 검산이다.

직접 명령은 probe 디렉터리에서 실행한다.

```text
python -X utf8 -B run.py prepare --baseline <v076 evidence.zip> --run-name v077_bindingpair_<고유시각> --out <plan.json>
python -X utf8 -B run.py execute --plan <plan.json> --baseline <v076 evidence.zip> --out <실행이름과 같은 폴더> --endpoint http://127.0.0.1:11434
python -X utf8 -B verify.py <생성한 evidence.zip>
```

`--synthetic`는 합성 실행 표시다. 실제 모델 성과로 보고하지 않는다. 한 배치 후 종료하며 P03·다른 모델·추가 진단은 자동 실행하지 않는다.
