# v053 — D 깊이 정의 명시 대조 실험

v052_adm_02의 D 단독에서는 40개 모두 유효한 증명이었지만 shallow/deep 선택적 제어는 0/20 대응쌍이었다. 이 모듈은 **기존 지시를 그대로 다시 측정하는 조건과 깊이 계산 정의만 추가한 조건**을 동일 모델·옵션·문제·seed에서 비교한다.

원래 v052를 교체하지 않는 추가 모듈이다. 예전 증거와 코어는 변경하지 않는다. 기준선의 모델 성적을 수입 게이트로 쓰지 않는다. 정상 수집된 실패 자료도 받아야 하기 때문이다.

## 구성

`original/defined × shallow/deep/neutral × K01/T02 × 10seed = 120회`다. 방향 지정 80회와 중립 40회는 별도 분모다. original의 지정 방향 요청 40개는 실제 v052 원문 요청과 바이트 단위로 같다. defined는 일반적인 깊이 정의 문단 하나만 더한다. 목표 깊이 숫자·규칙 정답·정답 증명은 제공하지 않는다.

유효 증명 생성, 요청 깊이 이행, 같은 seed에서 양방향 모두 성공한 대응쌍을 각각 보고한다. 같은 경로를 두 번 제시하면 두 증명이 맞아도 선택적 제어 성공은 아니다.

## Windows 실행

압축 안의 `v053_depth_probe` 폴더를 기존 저장소 바로 아래에 추가한다.

```text
thought-graph-simulator/
├─ v052_adm_diagnostic/          기존 폴더 유지
├─ v053_depth_probe/            이번 폴더 추가
│  ├─ depth_probe_v053/
│  ├─ tests_v053/
│  └─ windows/Run-All.ps1
├─ experiments_v053/            실행 시 생성
└─ results_llm/
   └─ v052_adm_02_evidence.zip  기존 실제 증거
```

Ollama 서버와 기존 모델을 켠 뒤 실행한다. 이 패키지는 모델을 다운로드하거나 임의로 서버를 실행하지 않는다.

```powershell
Set-Location C:\Users\sjs95\Desktop\thought-graph-simulator\v053_depth_probe
powershell -NoProfile -ExecutionPolicy Bypass -File .\windows\Run-All.ps1
```

스크립트는 위 트리의 위치, 저장소 루트, 현재 모듈 폴더에서 `v052_adm_02_evidence.zip`을 찾는다. 파일이 없거나 여러 군데 있으면 자동으로 고르지 않고 경로 지정을 요구한다. 경로가 다른 경우:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\windows\Run-All.ps1 -BaselineBundle "C:\Users\sjs95\Downloads\v052_adm_02_evidence.zip"
```

기본 실행 이름은 `v053_depth_01`이다. 기존 계획·실행 폴더·증거 ZIP이 있으면 덮어쓰지 않는다. 새 실행은 `-RunName v053_depth_02`처럼 다른 이름을 명시한다. 실패했던 원문은 삭제하지 않는다.

프로세스는 `selftest → prepare → show → run → audit → bundle`이다. selftest는 가짜 서버를 쓰는 코드 시험이며 사용자의 Qwen 추론이 아니다. `run`에서만 사용자 모델의 120회 실험을 시작한다. 실패하면 자동 재시도하지 않고 상태와 원문을 보존한다.

결과:

```text
results_llm/v053_depth_01/summary.ko.md
results_llm/v053_depth_01/summary.json
results_llm/v053_depth_01/status.json
results_llm/v053_depth_01_evidence.zip
experiments_v053/v053_depth_01.plan.json
```

결과 폴더와 별도 외부 계획을 함께 보존한다. 최종 증거 ZIP에 재감사에 필요한 바이트가 묶인다.

## 수동 CLI

모듈 폴더에서 실행한다. `selftest`는 신규 시험, `selftest --all`은 기존 v047~v052까지 포함한 전체 회귀다.

```powershell
python -m depth_probe_v053 selftest
python -m depth_probe_v053 selftest --all
python -m depth_probe_v053 prepare --baseline-bundle ..\results_llm\v052_adm_02_evidence.zip --out ..\experiments_v053\v053_depth_01.plan.json
python -m depth_probe_v053 show --plan ..\experiments_v053\v053_depth_01.plan.json
python -m depth_probe_v053 run --plan ..\experiments_v053\v053_depth_01.plan.json --out ..\results_llm\v053_depth_01
python -m depth_probe_v053 audit --plan ..\experiments_v053\v053_depth_01.plan.json --run ..\results_llm\v053_depth_01
python -m depth_probe_v053 bundle --plan ..\experiments_v053\v053_depth_01.plan.json --run ..\results_llm\v053_depth_01 --out ..\results_llm\v053_depth_01_evidence.zip
```

`audit`와 `bundle`은 원문만 재검사하며 모델에 새로 묻지 않는다. 불완전 실행도 원문 보존용 bundle을 만들 수 있지만, 완료 실험의 성공률로 판정하지 않는다. CLI 종료 코드 0은 해당 명령의 정상 완료, 3은 수집 미완료, 2는 계약·자료 오류다. selftest 실패는 1이다.

## 별도 구현으로 재검사

완료·정상 전송된 v053 120회에 대한 독립 의미 검증:

```powershell
python .\tools\independent_verify_v053.py ..\results_llm\v053_depth_01_evidence.zip --out ..\results_llm\v053_depth_01_independent.json
```

원래 사용자 v052 증거의 독립 재분석:

```powershell
python .\tools\independent_review_v052.py ..\results_llm\v052_adm_02_evidence.zip --out ..\results_llm\v052_adm_02_independent.json
```

독립 검증기는 source/runtime/request 재생성 검사를 대체하지 않는다. 생산 감사기와 함께 비교한다. 첨부 source_snapshot은 검사 대상이지 실행 대상이 아니다.

## 진단 교정

`final_ref_valid`는 “최종 노드 ID가 정확히 하나 존재하는가”로 검사한다. 그 노드의 논리적 유효성은 `proof_valid`다. 원래 v052에는 둘을 혼동한 진단 오류가 있었으며, 교정표는 `docs/ANALYSIS_v052_02.ko.md`에 있다. 기존 v052 소스는 역사적 재현용으로 보존했고 새 v053 측정 및 독립 재분석에서 교정했다.

## 문서와 검증

- `docs/ANALYSIS_v052_02.ko.md`: 실제 자료 분석, 다각도 심사와 합의.
- `docs/PROTOCOL.ko.md`: 배정·성공 조건·고정 변수·결과별 후속 방향.
- `docs/REVIEW_AND_FIXES.ko.md`: 결함 재현, 수정 경계, 반론과 검사.
- `validation/VALIDATION.ko.md`: 실제 실행한 시험과 한계.
- `validation/synthetic_*.zip`: **가짜 모델 응답**을 사용한 시험 증거. 실제 연구 성과가 아니다.

실제 검증 환경은 Linux/Python 3.13이다. Python 표준 라이브러리만 사용한다. Windows PowerShell 스크립트는 UTF-8 BOM/CRLF로 제공했으나 Windows에서 직접 실행 검증하지 않았다. 이 배포본에 실제 Qwen의 새 v053 결과는 없다.
