# v050: 원래 기준 판정 과제로 성공 경로 재통합

기존 local_llm/v047/v048/v049 폴더와 결과를 변경하지 않는 추가 모듈이다. Python 3.10 이상, 표준 라이브러리와 기존 로컬 Ollama를 사용한다. 모델 다운로드·외부 API 호출·pip 설치는 없다.

## 무엇을 실행하는가

원래 단독 사실 주장 과제에서 입력 읽기, 목표 동일성/초기 사실 소속 판단, 세 최종 판정을 검증한다. oneshot 원식·oneshot 교환식·실제 추출→교환식·실제 추출→NOT→AND 네 경로다. 두 staged 경로는 추출과 proof AND를 공유한다.

v049의 seed 10개 전체 × 네 입력 × 두 반복, 최대 **560회** 새 추론이다. 준비와 감사는 오프라인이며 run 단계에서만 기존 로컬 모델을 호출한다. 정답 보정·실패 자동 재시도·성공 seed 선별은 없다.

## 압축 해제 후 한 번에 실행

저장소 바로 아래에 `v050_criterion_probe`가 있어야 한다.

```text
thought-graph-simulator/
├─ results_llm/v049_expression_01_evidence.zip
├─ v049_expression_probe/          기존 보존
└─ v050_criterion_probe/           이번 추가 폴더
```

Ollama 서버를 기존 모델/버전/설정으로 켜 둔 뒤 PowerShell에서 실행한다.

```powershell
Set-Location C:\Users\sjs95\Desktop\thought-graph-simulator\v050_criterion_probe
powershell -NoProfile -ExecutionPolicy Bypass -File .\windows\Run-All.ps1
```

순서는 selftest → prepare → run → audit → bundle이다. 어느 단계든 오류가 나면 다음 단계로 넘어가지 않는다. 기존 계획이나 결과는 덮어쓰지 않는다.

완료 후 분석에 필요한 파일은 다음이다.

```text
C:\Users\sjs95\Desktop\thought-graph-simulator\results_llm\v050_criterion_01_evidence.zip
```

요약은 `results_llm/v050_criterion_01/summary.ko.md`다. ZIP에는 원문·외부 계획·감사 결과·실행 소스 snapshot을 함께 넣는다.

## 단계별 명령

같은 `v050_criterion_probe` 폴더에서 실행한다. Run-All과 별도로 같은 명령을 중복 실행하지 않는다.

```powershell
python -X utf8 -m criterion_probe_v050 selftest
python -X utf8 -m criterion_probe_v050 prepare --baseline-bundle ..\results_llm\v049_expression_01_evidence.zip --out ..\experiments_v050\v050_criterion_01.plan.json
python -X utf8 -m criterion_probe_v050 run --plan ..\experiments_v050\v050_criterion_01.plan.json --out ..\results_llm\v050_criterion_01
python -X utf8 -m criterion_probe_v050 audit --plan ..\experiments_v050\v050_criterion_01.plan.json --run ..\results_llm\v050_criterion_01
python -X utf8 -m criterion_probe_v050 bundle --plan ..\experiments_v050\v050_criterion_01.plan.json --run ..\results_llm\v050_criterion_01 --out ..\results_llm\v050_criterion_01_evidence.zip
```

단계별 실행에서는 오류가 난 단계 이후로 진행하지 않는다. `bundle`은 미완료 원문도 그 상태 그대로 보존할 수 있다. 완료가 아닌 증거를 분석 가능한 완결 실험으로 표시하지 않는다.

## 중단·기존 결과

실패한 결과 폴더를 지우지 않는다. 별도 새 실행이 필요할 때에는 다음처럼 새로운 이름을 지정한다. 동일 실행을 이어 붙이는 resume 기능은 없다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\windows\Run-All.ps1 -RunName v050_criterion_02
```

모델 digest·Ollama 버전이 기준선과 다르면 중단한다. v049 ZIP을 다른 곳에 보관했다면 `-BaselineBundle "실제 경로"`로 지정한다. 환경 차이를 무시하는 우회 옵션은 제공하지 않는다.

## 시험과 검증

`selftest`는 기존 243개와 신규 79개, 총 **322개**를 실행한다. 새 코드만 검사하려면 `selftest --new-only`를 사용한다. 초기/수정 전후/최종 로그는 validation 폴더에 있다.

실제로 확인한 환경은 Linux / Python 3.13.5다. Windows/PowerShell 실기 실행을 했다고 주장하지 않는다. 이전 CP949/UTF-8 subprocess 수정은 바꾸지 않고 재시험했으며, 한글 계획 파일명을 사용하는 실제 자식 Python CLI 호출도 시험했다.

`validation/SYNTHETIC_560_EVIDENCE.zip`은 실제 사용자 LLM 결과가 아니라 합성 HTTP 서버 시험 자료다. 원식만 일부러 틀리게 한 결과를 그대로 실패로 기록한 증거다. 이를 사용자 결과 폴더에 덮어쓰지 않는다.

## 문서

- docs/V049_ANALYSIS.ko.md: 첨부한 실제 v049 원문 분석.
- docs/PROTOCOL.ko.md: 다음 실험의 고정 조건·대조·판정·후속 방향.
- docs/REVIEW_AND_FIXES.ko.md: 다각도 검토 및 실제 수정 전후 반례.
- validation/VALIDATION.ko.md: 최종 실제 검증 범위와 로그.

현재 실험은 원래 criterion_witness 구성요소의 재통합이다. 증명 그래프 전체나 A/D/M 축별 효과를 이번 점수로 대체하지 않는다.
