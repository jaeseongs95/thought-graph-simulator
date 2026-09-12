# v051 — 고정 문제·목표 A/D/M 조작 예비실험

기존 `local_llm`, v047~v050 폴더를 교체하지 않는 추가 모듈이다. Python 표준 라이브러리만 사용한다.

**v050을 성공 기준선으로 삼지 않는다.** v050은 네 경로 모두 핵심 양성 조건을 놓쳤다. 이번에는 같은 문제에서 축별 지시가 실제 유효한 증명·표현·검토의 차이를 만드는지 직접 검사한다. A/D가 유효하고 M2가 잘못된 결과를 따로 관측하되 전체 성공으로 세지 않는다.

## 실행 전 조건

Python과 기존 Ollama 서버가 필요하다. 모델·Ollama 식별 정보와 생성 옵션은 v050 증거에서 수입하며 변경되면 중단한다. 새 모델을 다운로드하지 않는다. 이전에 만든 `results_llm/v050_criterion_01_evidence.zip`을 보존한다.

ZIP을 저장소 아래에 풀면 다음 구조다.

```text
thought-graph-simulator/
├─ results_llm/v050_criterion_01_evidence.zip
├─ v050_criterion_probe/                 기존 그대로
└─ v051_adm_pilot/                       이번 추가
   ├─ adm_pilot_v051/
   ├─ tests_v051/
   ├─ windows/Run-All.ps1
   ├─ docs/
   └─ validation/
```

## 한 번에 실행 — PowerShell

현재 폴더가 어디이든 먼저 아래 위치로 이동한다. 기존 Ollama 서버를 켜 둔다.

```powershell
Set-Location C:\Users\sjs95\Desktop\thought-graph-simulator\v051_adm_pilot
powershell -NoProfile -ExecutionPolicy Bypass -File .\windows\Run-All.ps1
```

스크립트는 `selftest → prepare → run → audit → bundle` 순서로 실행한다. 실패하면 다음 단계로 넘어가지 않고 원문을 보존한다. 모델 오답은 자료 수집 실패와 다르므로 정상적으로 수집된 오답도 보고서와 ZIP에 포함한다.

이미 같은 이름의 파일이 있으면 덮어쓰지 않는다. 원본을 삭제하지 말고 다른 이름을 사용한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\windows\Run-All.ps1 -RunName v051_adm_02
```

기준선 ZIP 경로가 다르면 `-BaselineBundle "C:\경로\v050_criterion_01_evidence.zip"`을 추가한다. 다른 경로를 쓸 때도 그 파일을 감사하므로 임의 결과를 기준선으로 우회하지 않는다.

## 수동 단계

아래 명령은 모두 `v051_adm_pilot` 폴더에서 실행한다. 각 명령 후 `$LASTEXITCODE`가 0인지 확인한다. `selftest`와 `prepare`는 실제 모델 추론을 하지 않는다. selftest에는 외부 모델이 아닌 로컬 합성 HTTP 서버 시험이 포함된다.

```powershell
python -m adm_pilot_v051 selftest
python -m adm_pilot_v051 prepare --baseline-bundle ..\results_llm\v050_criterion_01_evidence.zip --out ..\experiments_v051\v051_adm_01.plan.json
python -m adm_pilot_v051 run --plan ..\experiments_v051\v051_adm_01.plan.json --out ..\results_llm\v051_adm_01
python -m adm_pilot_v051 audit --plan ..\experiments_v051\v051_adm_01.plan.json --run ..\results_llm\v051_adm_01
python -m adm_pilot_v051 bundle --plan ..\experiments_v051\v051_adm_01.plan.json --run ..\results_llm\v051_adm_01 --out ..\results_llm\v051_adm_01_evidence.zip
Get-Content ..\results_llm\v051_adm_01\summary.ko.md -Encoding UTF8
```

증거 ZIP에는 외부 동결 계획도 묶인다. `summary.ko.md`만으로 원문·해시·부모값·채점을 재검사할 수는 없으므로 결과 분석에는 `results_llm/v051_adm_01_evidence.zip`을 사용한다.

## 실험과 주요 판정

K01 한 문제, 목표 Cc, A=instance/schema, D=shallow/deep, M=0/1/2이다. 기존 seed 10개 × 12조건 × 2반복 = **240회 실제 추론**이다. 한 역할 한 호출이며 모든 역할에 같은 출력 schema를 준다.

`data_integrity`는 자료의 일관성, `strict_valid`는 전체 기록의 의미상 유효성, `role_match`는 유효한 기록이 요청 역할에도 부합하는지를 뜻한다. `coordinate_change_observed`는 증명·표현·검토 대상의 조작 관측이며, M finding까지 옳다는 뜻이 아니다. `clean_requested_axis_change`는 대응하는 두 기록의 전체 판정까지 유효해야 인정된다.

한 문제의 실험이며 잠재 사고 좌표·범용 축 독립성·큰 모델과의 동급 성능을 측정하지 않는다. v050과는 다른 작업이므로 점수를 직접 개선율로 비교하지 않는다.

## 검증 자료

전체 시험 417개(기존 322개 + 신규 95개)가 실행됐다. 합성 HTTP 정상 사례와 M2 오류 주입 사례를 각 240회 실행했다. 이들은 테스트 서버 실행이며 실제 Qwen의 새 성공 표본이 아니다. 자세한 수행·환경·배포 검증 결과는 `validation/VALIDATION.ko.md`를 참고한다.

`validation/perfect_evidence.zip`과 `wrong_m2_evidence.zip`은 **synthetic_fixture**로 표시된 테스트 자료다. 사용자 실행용 기준선으로 쓰면 실제 실행이라고 분류되지 않는다.

`docs/PROTOCOL.ko.md`: 실험 계약 및 해석. `docs/REVIEW_AND_FIXES.ko.md`: 반론·반례·수정. `docs/NEXT_DECISIONS.ko.md`: 실제 결과별 다음 단계.
