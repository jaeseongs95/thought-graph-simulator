# 로컬 LLM 고정 목표 A/D/M 검증 — v0.3.0

## 이번 버전의 핵심

실험 실행 준비와 모델 성능을 분리했다. v0.2는 smoke 6건 모두 `accepted`여야 pilot으로 진행했지만, 역할 준수를 측정하는 연구에서는 역할 미준수도 결과다. v0.3의 기본 게이트는 정상 API 종료·기록 완결성·요청/모델/검증기 일관성을 검사하고 의미·역할 실패는 보존한다.

기본 프롬프트는 `legacy-v2`다. 이전 결과와 조건이 섞이지 않도록 모델, 출력 스키마, 프롬프트 원문, 샘플링을 그대로 유지했다. **기본 경로에서 통과율을 올리기 위해 정답이나 목표 깊이를 프롬프트에 주입하지 않는다.** 기존 `adm_minimal.py`도 변경하지 않는다.

## 설치된 프로젝트에 적용

Python 3.10 이상과 실행 중인 로컬 Ollama를 사용한다. Python 의존성은 표준 라이브러리뿐이다. 기존 `local_llm` 폴더를 보관한 후 이번 폴더로 교체한다.

```text
thought-graph-simulator/
├─ adm_minimal.py              기존 파일 유지
├─ examples/problems.json     기존 파일 유지
├─ results_llm/               기존 결과 유지
└─ local_llm/                 이번 폴더로 교체
```

## 현재 사용자에게 필요한 실행

프로젝트 루트 PowerShell에서:

```powershell
py -3 -m local_llm selfcheck
py -3 -m local_llm run --profile pilot --gate results_llm/v02_smoke_01 --out results_llm/v03_pilot_01
```

기존 calibration과 smoke를 다시 실행할 필요가 없다. 기본 문제가 그대로라면 새 호출은 39회다. 기존 smoke는 파일에서 재검사할 뿐 다시 호출하지 않는다. 기존 6건과 새 39건을 45개의 독립 표본으로 합산하지 않는다.

준비 게이트만 먼저 재검사하는 오프라인 명령:

```powershell
py -3 -m local_llm check-gate --gate results_llm/v02_smoke_01
```

`passed=true`는 실행 준비를 통과했다는 뜻이다. 이번 결과에서는 `model_failures_retained=5`도 함께 나온다. 소스 변경 없이 `--ungated`로 우회하는 대신 승인된 v0.2 소스와 요청 바이트를 재검사한다.

## 실행과 성능의 종료 코드

기본 종료 코드 0: 배정한 모든 호출을 처리하고 결과를 기록했다. **모델 성능 PASS를 뜻하지 않는다.** `summary.json`의 `execution_completed`와 `performance_passed`를 따로 본다.

종료 코드 2: 입력/파일/환경/통신/하네스 오류 또는 미완료. 130: 사용자 중단. 모델 성능 FAIL도 종료 코드 1로 취급할 CI 용도에는 `--fail-on-model-failure`를 추가한다.

별도 `--gate-mode strict`는 이전처럼 smoke의 모든 의미/역할 성공을 요구한다. 연구용 기본값은 `readiness`이며 strict의 성능 성공 조건을 기본 실행 준비 검사에 혼합하지 않는다.

## 출력 파일 읽는 순서

| 파일 | 내용 |
| --- | --- |
| `summary.md`, `summary.json` | 실행 완료, 증명 유효성, 전체 역할 성공, 축별 진단 |
| `metrics.csv` | 조건별 관측 A/D/M, 목표 D, 각 축의 일치 여부, 실패·토큰·시간 |
| `contrasts.json` | 양쪽 모두 요청 역할을 충족하는 엄격 대조 |
| `descriptive_contrasts.json` | 전체 역할 성공과 별도로 관측된 축의 변화 |
| `task_comparisons.json` | calibration 전용: 모델 실제값·기대값·일치 여부 |
| `cases/` | 실제 HTTP 요청, 원문 응답, 검증 기록, 시간, 적재 정보 |
| `manifest.json` | 문제·설정·모델 digest·소스 해시·사전 게이트 결과 |

`task_checks`의 불리언은 “정답과 일치했는가”이고, 모델이 출력한 불리언 자체가 아니다. 예를 들어 모델과 정답이 모두 false면 일치 여부는 true다. v0.3은 `task_comparisons`에서 실제값과 기대값을 따로 표시한다.

`descriptive_contrasts`는 실패를 성공으로 바꾸는 집계가 아니다. 예를 들어 두 조건이 모두 요청 D=1을 어기고 D=2를 냈더라도, 관측 D=2가 유지된 상태에서 A만 달라졌는지는 별도 관측할 수 있다. 엄격 대조와 이 관측을 합산하지 않는다.

## 선택형 새 프롬프트 실험

`explicit-v3`는 증명 선택, 표현 도식, 검토 예시를 구성요소별로 분리하고, 단독 probe의 판정 정의를 명시한 별도 프롬프트다. 원문 자동 복구, 정답 경로 생성, 역할별 출력 스키마 강제는 하지 않는다. **실제 LLM 개선 여부는 아직 실행되지 않았다.**

기본 pilot 결과를 먼저 확보하고 별도 조건으로 비교할 때 사용한다:

```powershell
py -3 -m local_llm run --profile smoke --prompt-profile explicit-v3 --out results_llm/v03_explicit_smoke_01
py -3 -m local_llm run --profile pilot --prompt-profile explicit-v3 --gate results_llm/v03_explicit_smoke_01 --out results_llm/v03_explicit_pilot_01
```

새 smoke도 의미·역할 실패만으로 pilot을 차단하지 않는다. 단, 프롬프트가 다르므로 **v0.2 smoke를 explicit-v3의 게이트로 재사용할 수 없다.** 새 프롬프트에서 calibration을 실행하려면:

```powershell
py -3 -m local_llm calibrate --prompt-profile explicit-v3 --out results_llm/v03_explicit_calibration_01
```

calibration은 학습이나 파인튜닝이 아닌 8개 분리 진단 과제다. 예시와 작업 범위가 다르므로 통합 실험과 단순히 “더 쉬움/더 어려움”으로 비교하지 않는다. 기본 `legacy-v2`와 새 프로필의 결과를 하나의 성공률로 섞지 않는다. 새 프로필은 여러 설명을 함께 바꾸므로 개선되더라도 특정 변경 하나가 원인이라고 단정하지 않는다.

## 설정·재개·오프라인 검사

기본값: `qwen3:4b`, `think=false`, temperature 0.2, top_p 0.9, top_k 20, context 8192, 출력 한도 4096, CPU 스레드 6, 배치 256, 동시 호출 1, localhost Ollama.

환경·모델·프롬프트·문제·시드·소스가 동일할 때만 미시작 조건을 이어간다:

```powershell
py -3 -m local_llm run --profile pilot --gate results_llm/v02_smoke_01 --out results_llm/v03_pilot_01 --resume
```

완료된 실패를 다시 뽑지 않는다. 요청만 보존되고 응답이 없는 조건도 자동 재호출하지 않는다. 강제 종료로 잠금이 남았을 때만 실행 중인 프로세스가 없음을 확인하고 해당 결과 폴더의 `.run.lock`을 제거한다. 모델/서버/소스 변경 후에는 새 결과 폴더를 사용한다.

```powershell
# 계획만 조회. 네트워크 없음
py -3 -m local_llm plan --profile pilot

# 전체 오프라인 시험. 모델·네트워크 호출 없음
py -3 -m unittest discover -s local_llm/tests -v

# 기존 응답 재검사. 원본 밖의 새 분석 폴더를 사용
py -3 -m local_llm inspect-results --input results_llm/v02_calibration_01 --out analysis_v03/calibration
py -3 -m local_llm inspect-results --input results_llm/v02_smoke_01 --out analysis_v03/smoke
```

`--think`나 모델·예산을 바꾸는 것은 별도 조건이다. 기존 게이트는 설정이 달라지면 재사용하지 않는다. 모델이나 서버를 바꾸라는 전제를 이번 수정에 추가하지 않았다.

작성·검사 범위는 `BUILD_STATUS.json`, 실험 해석 범위는 `PROTOCOL.ko.md`에 기록했다.
