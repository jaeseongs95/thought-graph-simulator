# v049 — 표현 2×2 대조

기존 v047/v048 폴더를 교체하지 않는 추가 모듈이다. v048의 전체 10개 seed와 모델 설정을 보존하고, 피연산자 순서와 바깥 괄호만 비교한다. 네 직접식과 기존 NOT→AND 연결식을 사용하며 최대 480회 실제 추론이다. 자연어 추출·새 논리 문제·A/D/M 조작·큰 모델 비교는 이번 단계에 포함되지 않는다.

필요 환경은 Python 3.10 이상, 기존 Ollama 서버 및 원래 모델, `results_llm/v048_seed_01_evidence.zip`이다. 추가 pip 패키지는 필요 없다. 기존 인코딩 수정과 171개 회귀시험을 포함한다. `selftest`는 합성 로컬 HTTP 서버만 사용하고 실제 Ollama에는 접근하지 않는다.

## 폴더 위치

다운로드한 `thought_graph_v049_expression_probe.zip`을 `C:\Users\sjs95\Desktop\thought-graph-simulator`에 풀면 다음 구조가 되어야 한다. 기존 파일은 덮어쓰지 않는다.

```text
thought-graph-simulator/
├─ v047_paired_probe/                  기존 유지
├─ v048_seed_probe/                    기존 유지
├─ results_llm/
│  ├─ v048_seed_01/                    기존 유지
│  └─ v048_seed_01_evidence.zip         이번 prepare 입력
└─ v049_expression_probe/              새 폴더
   ├─ paired_probe_v049/
   ├─ tests_v049/
   └─ windows/Run-All.ps1
```

## 권장 실행: 전체 순서를 한 번에

기존 Ollama 서버를 켜 두고 아래 두 줄을 실행한다. 이 명령은 selftest→prepare→실제 run→audit→bundle을 순서대로 실행한다. 단계가 실패하면 다음 단계로 넘어가지 않는다. Windows 실기에서는 직접 시험하지 않았으므로 로컬 selftest를 생략하지 않는다.

```powershell
Set-Location C:\Users\sjs95\Desktop\thought-graph-simulator\v049_expression_probe
powershell -NoProfile -ExecutionPolicy Bypass -File .\windows\Run-All.ps1
```

이 스크립트는 로컬 파일 하나의 실행에 대해서만 정책을 지정한다. 시스템 정책을 영구 변경하지 않는다. 계획·결과·ZIP이 이미 있으면 덮어쓰지 않고 중단한다. 새 시도는 기존 파일을 삭제하지 말고 다음처럼 다른 이름을 사용한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\windows\Run-All.ps1 -RunName v049_expression_02
```

중단된 실행은 자동 resume/retry하지 않는다. 먼저 보존된 status/summary를 확인한다. 단지 모델 오답이 기록된 완결 실행은 인프라 실패가 아니므로 계속 감사·묶음 생성이 가능하다.

## 단계별 실행

전체 스크립트를 실행한 뒤 이 절차를 또 실행할 필요는 없다. 각각 실행하려는 경우 아래 블록을 통째로 사용한다. PowerShell 백틱 줄바꿈은 사용하지 않았다.

```powershell
Set-Location C:\Users\sjs95\Desktop\thought-graph-simulator\v049_expression_probe
python -m paired_probe_v049 selftest
if ($LASTEXITCODE -ne 0) { throw "selftest 실패" }
python -m paired_probe_v049 prepare --baseline-bundle ..\results_llm\v048_seed_01_evidence.zip --out ..\experiments_v049\v049_expression_01.plan.json
if ($LASTEXITCODE -ne 0) { throw "prepare 실패" }
python -m paired_probe_v049 run --plan ..\experiments_v049\v049_expression_01.plan.json --out ..\results_llm\v049_expression_01
if ($LASTEXITCODE -ne 0) { throw "수집 미완료/계약 오류. 결과를 보존하세요." }
python -m paired_probe_v049 audit --plan ..\experiments_v049\v049_expression_01.plan.json --run ..\results_llm\v049_expression_01
if ($LASTEXITCODE -ne 0) { throw "audit 실패" }
python -m paired_probe_v049 bundle --plan ..\experiments_v049\v049_expression_01.plan.json --run ..\results_llm\v049_expression_01 --out ..\results_llm\v049_expression_01_evidence.zip
if ($LASTEXITCODE -ne 0) { throw "bundle 실패" }
Get-Content ..\results_llm\v049_expression_01\summary.ko.md -Encoding UTF8
```

prepare/show는 실제 추론을 실행하지 않는다. prepare는 v048 ZIP에 동봉된 외부 계획과 원문을 재감사한다. 따라서 이전처럼 외부 계획 경로와 snapshot 대체 옵션을 따로 선택하지 않는다. ZIP이 없으면 먼저 기존 v048 모듈의 bundle 명령으로 생성해야 한다.

## 전달할 결과

```text
C:\Users\sjs95\Desktop\thought-graph-simulator\results_llm\v049_expression_01_evidence.zip
```

ZIP에는 실제 요청·응답, 별도 동결 계획, 집계, 실행 코드 snapshot이 들어간다. summary만 전달하는 것보다 원문 재검증이 가능하다.

## 해석

`original`/`commuted`는 v048과 같은 식이다. `_open` 두 조건은 식 전체를 감싼 바깥 괄호만 제거했다. NOT b의 괄호는 남아 있다. 각각 전입력 4개를 모든 seed에서 두 번 평가한다. 결과는 seed별·입력별로 모두 보존하고 사후 최고 표현을 선택해 하나의 점수를 만들지 않는다.

자료 무결성 PASS와 모델 정답률은 다르다. 잘못된 bool은 오답으로 기록하고, 중간 NOT 값이 틀리면 최종값이 맞아도 전체 pipeline 성공은 아니다. 무결성 감사 실패 시 기존 PASS 요약은 실패 요약으로 갱신한다.

비용은 실패 포함 실측 호출·토큰·캐시·로딩·요청 시간으로 기록한다. 같은 토큰 수는 같은 FLOPs의 증거가 아니다. pipeline 비용은 두 호출을 합산한다.

## 소스와 문서

- `paired_probe_v049/plan.py`: 고정 2×2 조건과 균형 순서, 원문 템플릿 수입.
- `runner.py`: 원문 보존, 무보정 부모값 전달, 식별 검사.
- `audit.py`, `oracle.py`: 원문 재채점, 독립 식 계산과 수동 진리표.
- `reporting.py`: seed별 결과, 차이의 차이, 공정한 비용 비교.
- `evidence.py`: 안전한 ZIP 수입, 실제 묶을 바이트의 재감사.
- `docs/V048_ANALYSIS.ko.md`: 사용자 v048 결과 분석.
- `docs/PROTOCOL.ko.md`: 다음 단계 실험 계약.
- `docs/REVIEW_AND_FIXES.ko.md`: 다각도 검토와 실제 수정 전/후 기록.
- `validation/VALIDATION.ko.md`: 실제 실행한 코드 시험의 범위와 한계.

동봉한 v047/v048 코어는 호환성·기준선 감사를 위한 고정 의존성이다. 기존 저장소 폴더를 덮어쓰거나 GitHub에 자동으로 커밋하지 않는다.
