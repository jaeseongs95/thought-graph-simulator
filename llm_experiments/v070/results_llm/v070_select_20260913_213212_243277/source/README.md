# v070 — D 지시 기반 후보 경로 선택

v069 지정 append-only 생성기 12/12를 보존하고, **두 정상 후보 중 D 요구에 맞는 경로를 모델이 선택하는가**를 검사한다. 전체 graph를 생성하지 않는 선택 전용 실험이다.

## 기본 실행
배포받은 `Run-v070-Auto.ps1`을 Downloads에 저장하고 기존 Ollama가 켜져 있는 상태에서 실행한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v070-Auto.ps1"
```

이번 v069 evidence ZIP을 기존 `llm_experiments/v069/results_llm` 또는 Downloads에 둔다. 파일명보다 SHA-256을 확인하므로 `(1)` 접미사가 있어도 된다. 기존 저장소를 찾지 못하면 자동화의 `-RepoRoot` 인자로 지정한다. `-Baseline`으로 evidence를 직접 지정할 수도 있다. Windows 시스템 구성이나 모델을 변경하지 않는다.

## 작업 범위
5문제 × 2seed × 2후보 순서 × 2D = 최대 40회 추론, 60개 action이다. 기존 3문제 24회와 규칙 개수/깊이를 구분하는 새 진단 대조 16회를 모두 실행한다. 원응답의 ID/순서는 바꾸지 않는다. D 지시/후보 순서만 고정 배정하며 실패에 따라 새 문구·seed를 선택하지 않는다.

출력:

```text
llm_experiments/v070/results_llm/v070_select_<시각>_evidence.zip
llm_experiments/v070/results_llm/v070_select_<시각>_independent.json
```

40/40 + 20/20짝이면 이 후보 선택 인터페이스 기준선이다. 부분/전부 실패는 범위를 보존하고 이 분기를 종료한다. 미완료·미측정이면 gate=null이다. 결과가 나와도 다음 실험은 자동 실행하지 않는다. batch가 한 번 시작되면 새 RunName으로 재실행하지 않는다.

## 오프라인 검사와 수동 실행

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v070-Auto.ps1" -CheckOnly
```

소스 폴더에서:

```powershell
$env:V070_BASELINE = "실제 v069 evidence ZIP의 전체 경로"
python -X utf8 -B -m unittest discover -s tests -p "test_*.py" -v
python -X utf8 -B run.py prepare --baseline "$env:V070_BASELINE" --run-name v070_manual --out v070_manual.plan.json
python -X utf8 -B run.py execute --plan v070_manual.plan.json --baseline "$env:V070_BASELINE" --out v070_manual
python -X utf8 -B verify.py v070_manual_evidence.zip
```

수동 execute도 같은 계획/결과를 덮어쓰지 않는다. 사용자가 명시적으로 판단하기 전 새 RunName을 만드는 방식으로 실패 배치를 반복해서는 안 된다. interrupted run의 offline export는 `python -X utf8 -B run.py finalize --run <기존 실행 폴더>`다. 이미 evidence/summary가 있는 결과는 덮어쓰지 않는다.

## 소스 구성
`design.py`는 고정 배정/요청, `selection.py`는 원값 평가, `report.py`는 생산 집계, `verify.py`는 별도 재계산 및 원문 감사다. `previous.py`는 SHA로 고정한 v069 배포본 검산기로 실제 baseline을 확인한다. 임의의 evidence 내부 코드를 실행하지 않는다. `measure.py`는 v069와 동일하게 유지해 기존 parser/증명 깊이 열거를 사용하며, 이번 모델 출력에 전체 증명 평가를 호출하지 않는다.

연구 범위·반례 대조·종료 기준은 `docs/PROTOCOL.ko.md`에 있다. 합성 정답 생성은 tests에만 있으며 실험 실행의 답안 생성기로 사용하지 않는다. 테스트의 `synthetic` 결과는 Qwen의 성능 증거가 아니다.
