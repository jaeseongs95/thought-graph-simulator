# v088 r2 — ID 표현·명명 일관성·연속 참조 (runtime identity refreeze)

r2는 v088 r1의 연구 설계를 변경하지 않고 Ollama 0.34.1 runtime/API metadata identity만 재동결한 배포 revision이다. r1은 `v088_idcontinuity_20260916_081431_746223`에서 첫 metadata action에 fail-closed되어 추론 0회·관측 0회였고 기존 evidence/guard를 보존한다. 상세 provenance는 `data/runtime_provenance_r2.json`에 기록한다.

v087에서 새 node ID 출력은 맞았지만 후속 부모 참조가 크게 실패했다. 본 버전은 기존 생성기를 바꾸지 않고 원인을 구분하기 위한 사전 고정 진단을 수행한다. 상세 조건·주평가·주장 범위는 `docs/PREREGISTRATION.ko.md`를 읽는다.

## 평가 구성

| 평가 | 새 모델 호출/단위 | 의미 |
|---|---:|---|
| A. 같은 유효 prefix의 ID 재명명 | 560호출 | observed / atom_alias / short / legacy_long. 출력 ID 제약은 추가하지 않음 |
| B. 초기 이름 유지/통일 × short/long 연속 생성 | 128 continuation, 688호출 | 과거 유효 사실에서 시작해 모든 규칙·final을 새로 생성. 전체 자율 종단이 아님 |
| C. 기존 D 종단의 기준군·v087 ID 대조 | 256 신규 graph + 공통 선택256호출 | 새 비교/조회/facts부터 실행. 군당128graph·64양방향 |

목표 경로 선택 시 총 3,136추론, 사전 최대3,200추론. metadata 포함3,232action. 과거 anchor와 합성 검증은 새 모델 표본이 아니다.

## Windows 자동 실행

`Run-v088-Auto-r2-fix1.ps1`에 소스 ZIP이 내장돼 있다. Python 3.12, 기존 Ollama와 qwen3:4b-instruct를 사용한다. 아래 원본 ZIP이 Downloads 또는 `llm_experiments/v087/results_llm`에 있어야 한다.

```text
v087_genfactor_20260915_221007_079036_evidence.zip
SHA-256 9286d135fe3f0feb7bfaf35ee371d776f3746e0ea214e4b1816de2130835b702
```

무추론 점검:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v088-Auto-r2-fix1.ps1" -CheckOnly -AllTests
```

실제 모델 실행:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v088-Auto-r2-fix1.ps1"
```

자동 탐색이 되지 않으면 `-RepoRoot`, `-Baseline`, `-PythonPath`를 명시한다. PowerShell 5.1 이상이 필요하다. CheckOnly도 모든 자체시험을 실행한다(`-AllTests`는 기존 명령과의 호환용). 자체시험 HTTP는 loopback 합성 서버이며 실제 Ollama를 호출하지 않는다. 별도 `-InspectOnly`는 기존 실행 상태만 읽는다.

이전 소스·evidence·가드는 건드리지 않는다. 수정된 v088 설치본은 덮어쓰지 않고 차단한다. 이미 시작한 배치는 새 RunName으로 우회하지 않는다. 실제 중단은 로그·가드를 보존하고 검토한다. 완결된 기존 결과를 덮어쓰지 않는다.

결과:

```text
llm_experiments/v088/results_llm/v088_r2_idcontinuity_<timestamp>_evidence.zip
llm_experiments/v088/results_llm/v088_r2_idcontinuity_<timestamp>_independent.json
```

evidence의 summary는 A/B/C를 분리한다. diagnostics는 변환된 prefix, 새 응답 이력, 누락 parent 문자열, 고유 요청·usage를 제공한다. 원자 이름을 올바른 부모 ID로 바꿔 채점하지 않는다.

## 수동 실행/검증

probe 디렉터리에서:

```text
python -X utf8 -B selftest088.py --out <새 selftest.json>
python -X utf8 -B calibrate088.py --out <새 calibration.json>
python -X utf8 -B run088.py prepare --baseline <v087 evidence.zip> --run-name v088_r2_manual --out <새 plan.json>
python -X utf8 -B run088.py execute --baseline <v087 evidence.zip> --plan <plan.json> --out <새 결과폴더/v088_r2_manual>
python -X utf8 -B verify088.py <v088 evidence.zip>
```

selftest는 `V088_BASELINE` 환경변수 또는 Downloads의 사전 이름을 사용한다. 결과 경로는 새 경로여야 한다. live CLI는 synthetic plan으로 실행할 수 없다. 전체 합성 검증은 `reproduce_synthetic.py --baseline <v087 evidence.zip> --out <새 검증폴더>`로 수행한다. 소스/자동 실행 파일 재빌드는 `build_release.py --out <새 배포폴더>`다.

## 주요 모듈

`baseline088.py`: 결과를 보지 않는 prefix 선정. `design088.py`: 배정·사전 변환·무보정 요청. `rows088.py`: 생산 채점. `audit088.py`, `audit_rows088.py`: 별도 재구성/의미 검산. `tables088.py`: 명시된 주평가. `run088.py`, `verify088.py`: 이벤트·원문·중단·증거. `frozen087/`: v087 소스77개 원문 보존.

## 주장 범위

B의 성공은 과거의 유효 사실을 지원받은 연속 생성의 성공이다. 새 선택 제어나 새 facts 생성으로 세지 않는다. atom_alias 조건은 의미 단서가 있는 진단이지 중립 ID 길이 대조가 아니다. long/short 차이는 이름 계열 차이이며 길이만의 원인으로 표현하지 않는다. 이번 구조는 새 holdout이 아니다. 실제 Qwen 결과는 사용자가 실행한 evidence로 판단한다.


## r2 release fix1 (2026-09-16)

연구 protocol은 변경하지 않았다. 최초 r2 배포본은 설치된 `probe_r2`에서 manifest를 찾을 때 보존된 r1 `RELEASE_MANIFEST.json`을 먼저 읽는 배포 결함이 있었다. fix1은 설치본에서 `RELEASE_MANIFEST_r2.json`을 우선한다. 알려진 결함판 r2가 이미 설치된 경우, 결함판 manifest fingerprint와 전체 파일 hash가 모두 일치하고 실제 r2 실행 guard가 없을 때만 기존 소스를 `probe_r2_release_bug_20260916`으로 보존한 뒤 교체한다.
