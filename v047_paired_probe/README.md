# v047: 원식·교환식·실제 NOT→AND의 동일 배치 대조

**버전:** 0.4.7-r1  
**구현 목적:** v046 성공을 유지하면서, 과거 실패한 원식도 같은 실행 배치에서 다시 비교한다.  
**범위:** 작은 모델의 한 불리언 식에 대한 구성요소 실험. A/D/M 본 가설의 성공을 판정하지 않는다.

## 설치 형태

이 폴더 전체를 기존 저장소 바로 아래에 둔다. 기존 `local_llm`, `adm_minimal.py`, 이전 `results_llm`의 파일은 교체하지 않는다.

```text
thought-graph-simulator/
├─ local_llm/                 # 변경하지 않음
├─ adm_minimal.py             # 변경하지 않음
├─ results_llm/               # 기존 결과 보존, v047 결과만 새 하위 폴더에 추가
├─ experiments_v047/          # 실행 전 동결한 별도 계획
└─ v047_paired_probe/         # 이번 ZIP에 들어 있는 폴더
   ├─ paired_probe_v047/
   ├─ tests_v047/
   ├─ windows/
   ├─ docs/
   └─ validation/
```

Python 3.10 이상과 이미 사용 중인 로컬 Ollama를 사용한다. 외부 Python 패키지 설치, 새 모델 다운로드, Git 변경 명령은 없다. 사용자 환경의 Python 3.12를 그대로 사용하면 된다.

## 먼저 할 일: 오프라인 시험과 계획 동결

PowerShell에서 다음을 실행한다.

```powershell
Set-Location "$env:USERPROFILE\Desktop\thought-graph-simulator\v047_paired_probe"

python -m paired_probe_v047 selftest
if ($LASTEXITCODE -ne 0) { throw "오프라인 시험 실패" }

python -m paired_probe_v047 prepare --source-root ..\results_llm --out ..\experiments_v047\v047_paired_01.plan.json
if ($LASTEXITCODE -ne 0) { throw "계획 생성 실패" }

python -m paired_probe_v047 show --plan ..\experiments_v047\v047_paired_01.plan.json
if ($LASTEXITCODE -ne 0) { throw "계획 확인 실패" }
```

이 명령들은 실제 LLM 추론을 하지 않는다. `selftest`의 HTTP 통합 시험은 가짜 서버를 사용한다. `prepare`는 기존 저장된 원문에서 설정을 읽고 순서를 동결할 뿐 Ollama 서버에 접속하지 않는다.

출력에서 원본 경로가 보존한 v046 실행인지, 모델·endpoint·options가 기존 실험과 일치하는지 확인한다. 기본 계획은 원래 seed 그대로, 6회 반복, 24개 입력 블록, 최대 96회 추론 요청이다. v046 기록이 없으면 적합한 v045 원문을 사용할 수 있으며 선택 경로가 출력된다. 응답이 정답이었는지는 원본 선택 기준으로 사용하지 않는다.

## 실제 LLM 실행

기존 로컬 Ollama 서버를 실행 중인 상태에서 다음을 실행한다. 기존 `local_llm/windows/serve-local.ps1`을 사용하던 환경은 그대로 유지한다.

```powershell
python -m paired_probe_v047 run --plan ..\experiments_v047\v047_paired_01.plan.json --out ..\results_llm\v047_paired_01
if ($LASTEXITCODE -ne 0) { throw "수집 미완료 또는 계약 오류. 기존 결과를 삭제하거나 자동 재시도하지 마세요." }

python -m paired_probe_v047 audit --plan ..\experiments_v047\v047_paired_01.plan.json --run ..\results_llm\v047_paired_01
if ($LASTEXITCODE -ne 0) { throw "오프라인 감사 실패" }

Get-Content ..\results_llm\v047_paired_01\summary.ko.md -Encoding UTF8
```

`run`만 실제 추론을 호출한다. 최대 96회이며 형식 오류가 있는 NOT 응답의 AND 자식은 생략하므로 실제 호출은 적을 수 있다. 이 경우 해당 파이프라인은 실패로 남고 할당된 비교 조건에서 빠지지 않는다. HTTP 오류나 통신 중단은 재시도하지 않고 미완료 결과를 보존한다.

종료 코드 0은 수집·감사 완료이지 모델 100% 정답이라는 뜻이 아니다. 종료 코드 1은 시험 실패, 2는 계약/파일 오류, 3은 수집 미완료다.

## 한 번에 실행하는 PowerShell 스크립트

위 단계별 명령과 같은 작업을 다음 한 줄로 실행할 수도 있다. `-Execute`가 있어야 실제 추론을 시작한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\windows\Run-NextStep.ps1 -Execute
```

이미 같은 이름의 계획이나 결과가 있으면 중단한다. 두 번째 독립 실행은 `-RunName v047_paired_02`처럼 새 이름을 쓴다. 기존 결과를 지우거나 `-Force`로 덮어쓰지 않는다. `-Execute` 없이 생성한 계획을 실행할 때는 표시된 `python ... run` 명령을 사용한다. 같은 계획을 새로 생성하려고 스크립트를 다시 실행하면 보존 규칙 때문에 중단한다.

## 실행 후 보존·공유할 파일

핵심 결과는 `results_llm/v047_paired_01/summary.ko.md`, 기계 판독 지표는 `summary.json`, 입력별 표는 `trials.csv`다. 판정 재검사에는 결과 폴더 전체와 **별도 위치의 `experiments_v047/v047_paired_01.plan.json`**이 모두 필요하다.

```powershell
Compress-Archive -Path ..\results_llm\v047_paired_01, ..\experiments_v047\v047_paired_01.plan.json -DestinationPath ..\v047_paired_01_results.zip
```

이 패키지의 `validation/demo_*`는 **가짜 HTTP 서버의 합성 자료**다. 사용자 모델의 새 성공 사례에 합산하면 안 된다.

## 추가 옵션

원본 실행 폴더를 정확히 지정하려면 `prepare --source-run "기존 v046 phase_one 실행 폴더"`를 사용한다. 재귀 자동 탐색에서 제외한 후보와 이유는 계획의 `skipped_sources`에 남는다.

다중 seed 기능도 구현되어 있다. 예를 들어 `--seeds 1729,2718,3141 --cycles 6`은 288회가 상한이다. **첫 96회 결과를 보기 전에 이 확장부터 시작할 필요는 없다.** 원래 temperature가 0이면 그 설정을 그대로 보존하며, seed 변경을 곧바로 독립 표본 증가나 실질적인 생성 다양성으로 해석하지 않는다.

## 보존·감사 계약

원래 한국어 system 문구, 자료형 전용 JSON schema, 모델, endpoint, sampling options, thinking 요청의 생략 여부를 기존 HTTP 원문에서 가져온다. 원식/교환식의 허용 변경은 expression 문자열이다. 파이프라인은 NOT 응답의 실제 bool을 AND의 b 입력으로 전달한다. 틀린 bool도 전달하며 정답표로 고치지 않는다. 평가기는 모든 요청이 끝난 뒤에만 실행 경로에 불러온다.

실행 전·후 모델 digest, 모델 정보/템플릿 해시, Ollama 버전을 기존 기록과 대조한다. 불일치하면 결과를 동등 조건 비교로 확정하지 않는다. 모든 요청/응답 바이트, 부모 ID와 응답 해시, 계획·실행 소스 스냅샷을 보존한다. 같은 저장소의 모든 자료와 해시를 동시에 위조하는 공격이나 원격 실행 사실을 외부적으로 증명하는 전자서명까지 제공하는 것은 아니다.

## 문서

- `docs/REVIEW_AND_CONSENSUS.ko.md`: 다각도 심사와 합의
- `docs/PROTOCOL.ko.md`: 이번 실험의 질문·처치·측정·판정
- `docs/NEXT_STEPS.ko.md`: 결과별 후속 경로 및 A/D/M 본 실험 복귀
- `docs/SOURCE_NOTES.ko.md`: 확인한 저장소 소스와 외부 1차 자료
- `validation/VALIDATION.ko.md`: 실제 수행한 검증과 미수행 범위
