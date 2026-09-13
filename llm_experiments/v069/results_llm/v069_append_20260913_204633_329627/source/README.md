# v069 — 지정 규칙 append-only 참조 구성 양성 대조

v068의 direct 4/12 / nodes→final 8/12와 두 방식의 12/12 gate 불통과를 보존하고, 그 진단 분기를 종료한다. 이 코드는 다른 계약인 `초기 사실 → 지정 규칙별 노드 하나 → 최종 ID`의 구성 가능성을 검사한다. **참조 경로와 단계별 rule ID를 실험자가 제공하므로 자율 D 제어 실험이 아니다.**

## 가장 간단한 실행

배포된 `Run-v069-Auto.ps1` 하나를 다운로드 폴더에 저장한다. 실제 v068 evidence ZIP은 기존 `llm_experiments/v068/results_llm` 또는 다운로드 폴더에 둔다. 파일명에 `(1)`이 붙어도 지정 SHA-256의 내용이 같으면 찾는다. 기존 Ollama와 `qwen3:4b-instruct`가 실행 가능한 상태여야 한다. 자동 다운로드·업데이트·서버 시작은 없다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v069-Auto.ps1"
```

소스 무결성 → 새 버전 설치 → 무추론 자체시험 → v068 원문 전체 재감사 → 동결 계획 저장 → 기존 모델 identity 확인 → 최대 54회 추론 → evidence ZIP → 독립 JSON 순서다. 실패 시 재시도하거나 새 RunName으로 자동 반복하지 않는다. 이전 버전과 결과를 덮어쓰지 않는다.

저장소 자동 탐색이 되지 않을 때에는 명령에 기존 경로를 명시한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v069-Auto.ps1" -RepoRoot "D:\codex\AI논문\thought-graph-simulator"
```

`-Baseline`으로 v068 evidence의 정확한 경로, `-PythonPath`로 기존 python.exe 경로를 지정할 수 있다. 필요한 Python은 3.10 이상이며 표준 라이브러리만 사용한다.

## 무추론 확인만 하기

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v069-Auto.ps1" -CheckOnly
```

`-CheckOnly`는 Ollama 조회나 모델 추론을 하지 않는다. 소스 설치·오프라인 시험·이전 evidence 감사·계획 저장만 한다. 해당 검사 계획을 재사용해 자동 실행하지 않으며, 실제 실행은 사용자가 위 기본 명령으로 따로 요청한다. `-AllTests`는 로컬 합성 HTTP를 사용하는 전체 시험까지 수행한다. 합성 시험 결과는 모델 성능 결과가 아니다.

## 배정과 결과

3문제 × 2seed × 2참조 = 12개 trial. facts 12회 + rule 30회 + final 12회, 최대 54회 추론이다. 각 block 전후 metadata 12묶음까지 합쳐 66개 action이다. 정상 참조 D는 T02 1/4, E01 1/2, E02 2/4다.

모든 초기 사실·노드 ID·규칙 적용·부모 연결·최종 ID는 모델이 쓴다. 호스트는 고정 순서와 현재 규칙을 제공하고 원문을 운반한다. 잘못된 응답도 전달할 수 있는 문자열이면 그대로 전달한다. 채점 시 노드를 순서대로 연결하되 수정·가지치기·fact 보충·ID 추측은 하지 않는다.

모든 단계가 측정되고 12/12면 이 계약의 제한된 구성 기준선, 0/12면 종료, 부분 성공이면 범위를 보존하고 종료다. 미측정·미완료가 있으면 gate는 null이다. 결과에 따라 다음 실험을 자동 생성하거나 실행하지 않는다.

결과 경로:

```text
llm_experiments/v069/results_llm/v069_append_<시각>_evidence.zip
llm_experiments/v069/results_llm/v069_append_<시각>_independent.json
```

두 파일이 다음 분석의 입력이다. 중단된 경우에도 만들어진 증거·로그를 보존한다. 완료하지 않은 run을 새 이름으로 자동 반복하지 않는다.

## 소스 ZIP을 직접 사용하는 경우

ZIP의 디렉터리 구조를 그대로 푼 뒤 `llm_experiments/v069/probe`에서 실행한다. 다음 명령의 경로와 RunName은 실제 값으로 지정한다.

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8'
$env:V069_BASELINE='C:\Users\사용자\Downloads\v068_nodesfinal_20260913_201436_736799_evidence.zip'
python -X utf8 -B -m unittest discover -s tests -v
python -X utf8 -B run.py prepare --baseline "$env:V069_BASELINE" --run-name v069_append_manual --out ..\experiments\v069_append_manual.plan.json
python -X utf8 -B run.py execute --plan ..\experiments\v069_append_manual.plan.json --baseline "$env:V069_BASELINE" --out ..\results_llm\v069_append_manual --endpoint http://127.0.0.1:11434
```

기존 계획·결과가 있으면 덮어쓰기 없이 중단한다. 실행은 `prepare`와 별개이며 자동 재시도하지 않는다.

## 재현성과 검산

`data/protocol.json`과 `docs/PROTOCOL.ko.md`가 사전 계약이다. `measure.py`는 v068과 바이트 동일하다. `verify.py`는 본 버전의 생산 design/measure/report/run/stages를 import하지 않고 요청·단계·graph·summary·한국어 보고서를 별도로 재계산한다. 이전 버전의 고정 소스는 검산용으로만 포함한다.

Hash/manifest는 evidence의 내부 일관성 검사이며 실제 외부 모델 실행을 서명 인증하지 않는다. 새 소스의 합성 시험을 실제 Qwen 실험 성공으로 세지 않는다. v068과 동시 대조하지 않으므로 성공률 차이를 인과 효과나 동일 비용 우월성으로 해석하지 않는다.
