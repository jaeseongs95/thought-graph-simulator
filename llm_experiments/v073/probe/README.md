# v073 — 공백 × 후보 순서 인터페이스 양성 대조

v072를 종료·보존한 뒤, 같은 숫자에 대한 공백 한 글자와 후보 순서의 효과를 별도로 검사한다. **실제 모델 추론은 배포 시점에 아직 실행하지 않았다.**

## 문서

- `docs/PLAN_LEDGER.ko.md`: 전체 계획장부, 종료·복귀 기준, 실제 결과의 빈 기록 칸.
- `docs/V072_FROZEN.ko.md`: v072 결과 동결.
- `docs/PROTOCOL.ko.md`, `data/protocol.json`: 사람용/기계용 실험 계약.

## 단일 파일 자동화

`Run-v073-Auto.ps1`을 Downloads에 저장하고, 기존 Ollama가 켜진 상태에서 실행한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v073-Auto.ps1"
```

실행 없이 설치·검산·계획 생성만 하려면 `-CheckOnly`를 붙인다. 이것은 모델이나 Ollama에 HTTP 요청을 보내지 않는다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v073-Auto.ps1" -CheckOnly
```

기존 evidence ZIP을 이름이 아니라 내용 해시로 찾는다. `(1)` 같은 이름 변경은 허용한다. 자동으로 못 찾을 때는 `-RepoRoot`와 `-Baseline`에 기존 실제 경로를 지정한다. 이전 버전은 덮어쓰지 않는다.

## 수동 CLI

소스 ZIP 전체를 추출한 후 `llm_experiments/v073/probe` 폴더에서 실행한다. 아래 `$baseline`에는 원본 v072 ZIP의 실제 경로를 설정한다.

```powershell
$baseline = "$env:USERPROFILE\Downloads\v072_gemma_20260913_225125_604451_evidence.zip"
$env:V073_BASELINE = $baseline
python -X utf8 -B -m unittest discover -s tests -p "test_*.py" -v
python -X utf8 -B run.py prepare --baseline $baseline --run-name v073_interface_manual --out ..\experiments\v073_interface_manual.plan.json
python -X utf8 -B run.py execute --baseline $baseline --plan ..\experiments\v073_interface_manual.plan.json --out ..\results_llm\v073_interface_manual
```

`--synthetic`는 시험용 provenance 표기이며 실제 배포 실행 명령에는 사용하지 않는다. 시험 서버는 test fixture에서만 작동하고 실제 모델 실행 경로에는 정답 생성기를 넣지 않았다.

## 산출물

```text
llm_experiments/v073/results_llm/v073_interface_<시각>_evidence.zip
llm_experiments/v073/results_llm/v073_interface_<시각>_independent.json
```

원응답·모델 식별·고정 계획·직전 evidence·현재 소스·실제 호출 순서·usage·한국어 보고서를 보존한다. 64회 추론, 96개 action이며 형식별 32개 선택/16개 방향 쌍을 기록한다. 성공 여부와 관계없이 다음 실험을 자동 실행하지 않는다.

이번 비교에서 주는 숫자는 명시적인 양성 대조다. 성공해도 D 계산/자율 경로 선택/최종 graph 생성/A·M/내부 구조 제어를 입증한 것은 아니다. 본실험의 정확한 숫자 보고라는 추가 관문을 만드는 목적도 아니다.

장부를 진행 기록으로 갱신할 때는 별도로 제공한 MD 복사본에 새 revision을 만든다. 실행·검산에 사용하는 `probe/docs` 내부의 동결 장부나 소스를 실행 도중 수정하지 않는다.
