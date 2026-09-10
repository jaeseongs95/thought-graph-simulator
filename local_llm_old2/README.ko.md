# 고정 목표 A/D/M 로컬 LLM 검증 — v0.2.0

기존 `thought-graph-simulator/adm_minimal.py`를 그대로 사용하는 **교체용 `local_llm` 폴더**다. v0.1 실행 결과에서 드러난 노드 참조 혼동, 도식 출력 형식 문제, 실패 원인의 일괄 집계를 수정했다. 모델이 답·증명·도식·검토를 틀리면 그대로 실패로 남긴다.

**이 배포본에서는 모델 다운로드와 LLM 추론을 실행하지 않았다.** 오프라인 단위·회귀·모의 API 통합시험 63개, 자체 검사 21항목, 사용자가 보낸 기존 응답 45건의 재검사는 실행했다. 수정 프롬프트에 대한 실제 모델 반응은 사용자의 새 실행으로 확인한다. 모의 API 시험의 합격을 LLM 합격률로 사용하지 않는다.

## 1. 기존 설치에서 교체

Ollama와 `qwen3:4b`는 이미 설치했으므로 다시 설치하거나 모델을 다시 받을 필요가 없다. 모델 태그를 업데이트하면 다른 실험 조건이 되므로 이번 재실험에서는 기존 모델을 유지한다.

기존 실행 프로세스가 종료된 상태에서 저장소 루트의 `local_llm`을 `local_llm_v01_backup` 등으로 이름을 바꾸고, ZIP의 새 `local_llm` 폴더를 그 자리에 복사한다. `results_llm/smoke_01`, `results_llm/pilot_01`과 `adm_minimal.py`는 변경하지 않는다.

```text
thought-graph-simulator/
├─ adm_minimal.py                       # 기존 검증기 유지
├─ examples/problems.json             # 기존 문제 유지
├─ local_llm_v01_backup/               # 이전 소스 보관, 선택 사항
├─ local_llm/                          # 이 배포본의 폴더
└─ results_llm/
   ├─ smoke_01/                       # 기존 결과 유지
   └─ pilot_01/                       # 기존 결과 유지
```

명령은 **`adm_minimal.py`가 있는 저장소 루트에서 PowerShell로** 실행한다. Python 3.10 이상이며 Python 의존성은 표준 라이브러리뿐이다. 이 배포본의 오프라인 실행 환경은 Linux/Python 3.13이다. Windows PowerShell 및 실제 Ollama 연동은 이번 환경에서 실행하지 않았다.

## 2. 다시 실행하는 순서

Ollama 서버가 기존처럼 실행 중이면 그대로 사용한다. 서버가 꺼져 있으면 기존 방식으로 켜거나 다음 명령을 별도 창에서 실행한다. 이 스크립트는 이미 실행 중인 서버를 강제 종료하지 않는다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\local_llm\windows\serve-local.ps1
```

### 2.1 오프라인 자체 검사 — LLM 호출 0회

```powershell
py -3 -m local_llm selfcheck
```

`passed: true`, `model_called: false`를 확인한다. 이는 검증 코드와 예시의 검사 결과이지 모델 성능 결과가 아니다.

### 2.2 구성요소별 사전 진단 — LLM 호출 8회

```powershell
py -3 -m local_llm calibrate --out results_llm/v02_calibration_01
```

`results_llm/v02_calibration_01/summary.md`를 읽는다. 이 명령은 **모델을 학습하거나 보정하지 않는다.** 다음 과제를 별도 호출로 나눠 어느 부분에서 막히는지 관측한다.

| 과제 | 호출 수 | 모델이 생성·판정하는 것 |
| --- | ---: | --- |
| 증명만 생성 | 2 | 같은 목표에 대한 얕은/깊은 증명과 올바른 노드 참조 |
| 고정 증명의 도식화 | 1 | 호스트가 제공한 증명의 모든 노드별 보편 도식 |
| 고정 기록 검토 | 2 | 유효한 증명과 전제가 누락된 증명의 판정 |
| 수락 기준 비교 | 3 | 무근거 목표, 목표 아닌 사실, 주어진 목표 사실에 대한 두 기준의 차이 |

고정 증명을 입력으로 받은 과제에서 모델이 그 증명 자체를 생성했다고 집계하지 않는다. 이 8회를 본 A/D/M 실험의 성공률에 더하지 않는다. 각 과제는 새로운 요청이며 앞 과제 응답을 다음 과제에 붙이지 않는다.

### 2.3 통합 최소 실험 — LLM 호출 6회

```powershell
py -3 -m local_llm run --profile smoke --out results_llm/v02_smoke_01
```

동일 호출에서 증명·도식·검토를 작성하는 본 실험의 최소 구성이다. `results_llm/v02_smoke_01/summary.md`에서 여섯 조건의 상태를 확인한다. 실패가 남으면 `cases/` 원문과 함께 원인을 먼저 분석한다.

### 2.4 최소 실험이 통과하면 전체 조건 — LLM 호출 39회

```powershell
py -3 -m local_llm run --profile pilot --gate results_llm/v02_smoke_01 --out results_llm/v02_pilot_01
```

`--gate`는 요약 파일의 PASS 문구를 믿지 않고, 보존한 smoke 응답 여섯 건을 다시 검증한다. 소스·검증기·시드·설정·첫 문제·모델 digest·Ollama 버전이 같아야 한다. 실패나 변경이 있으면 pilot 추론을 시작하지 않는다.

실패 양상 자체를 수집할 목적이라면 다음과 같이 **명시적으로** 게이트 없이 실행할 수 있다. 이것은 진단 통과나 성공한 조건만의 평가가 아니다.

```powershell
py -3 -m local_llm run --profile pilot --ungated --out results_llm/v02_pilot_exploratory_01
```

기본 문제 파일 기준 `smoke=6`, `pilot=39`, `full=117`회다. full은 39조건을 세 시드로 반복한다. 새로운 문제 117개가 아니다. full에도 `--gate` 또는 `--ungated`가 필요하다. smoke 통과 후 진행한 실험과 실패를 포함해 진행한 탐색 실험은 보고할 때 구분한다.

## 3. 결과를 읽는 방법

먼저 `summary.md`, 그다음 `metrics.csv`, 개별 원인은 `cases/<case_id>/record.json`과 `response.raw.json`을 읽는다. A/D/M 대조는 `contrasts.json`에 저장한다.

| 구분 | 의미 |
| --- | --- |
| `accepted` | 전체 기록이 유효하고, 지정 역할이면 A/D/M 조건도 충족 |
| `role_mismatch` | 전체 기록은 유효하지만 요청 역할과 다름 |
| `invalid_trace` | JSON 전송 형식은 맞지만 증명·도식·검토의 의미 계약 위반 |
| `protocol_error` | 응답 봉투·엄격한 JSON·필드 형식 등의 위반 |
| `invalid_task` | 분리 진단 과제의 정답 또는 근거가 틀림 |
| `truncated` | 출력 길이 한도 종료. JSON이 완성되어 보여도 성공 처리하지 않음 |
| `transport_error` | HTTP/서버 응답 실패. 잠재적 중복 추론을 피하기 위해 중단 |
| `harness_error` | 모델 식별·실험 무결성·검증기 대조 등의 오류. 원인 확인 필요 |
| `interrupted_unknown` | 요청 흔적은 있으나 응답 없음. 성공도, 비용 0도 가정하지 않음 |

`final_reference_exists`와 `all_local_steps_valid`를 구분한다. **각 규칙 적용이 맞아도 최종 노드 지정과 전체 지지 연결성이 틀리면 전체 증명은 실패다.** 다중 오류 진단은 실패한 출력을 수리하는 절차가 아니다.

기본 증명 자체가 무효라면 `representation_valid`, `review_valid`는 `null`이고, 각각 `*_assessable`은 false다. 이는 해당 축이 독립적으로 실패했다는 의미가 아니라 그 증명 위에서 의미 검사를 완료할 수 없었다는 뜻이다. 원문 전송 형식 자체가 틀린 경우에도 다른 관측 가능한 문제는 `raw_diagnostics`에 남는다.

프로세스 종료 코드 0은 해당 명령 성공, 1은 **실험은 기록되었지만 실패 조건이 있음**, 2는 설정·통신·무결성 등 오류, 130은 사용자 중단이다. 코드 1만 보고 프로그램이 실행되지 않았다고 판단하지 않는다.

## 4. v0.1과 달라진 점

`id/parents/final`을 `node_id/parent_node_ids/selected_final_node_id`로 바꿔 명제 이름·규칙 이름·출력 노드 ID를 구분했다. 모델에는 `n0,n1,...` 형태의 노드 ID 사용을 설명하지만, 코드가 잘못된 참조를 찾아 바꿔 주지는 않는다.

HTTP 직렬화는 삽입 순서를 보존한다. 해시용 키 정렬 직렬화는 별개로 유지한다. 최상위 필드명 자체도 사전순으로 정렬하더라도 `nodes → selected_final_node_id → verification_reviews` 순서가 되도록 했다. 실제 요청 바이트를 `request.wire.json`과 SHA-256으로 저장한다. 순서 변경의 정확도 효과는 새 추론에서 확인해야 한다.

도식 바인딩은 동적 키 객체 `{"X":"p"}` 대신 `[{"variable":"X","atom":"p"}]` 배열로 받는다. 빈 목록·중복 변수·중복 원자·부분 증명에 없는 원자·틀린 전제는 거부한다. 변환은 필드명과 자료구조 위치만 바꾸고 도식 내용을 만들어 주지 않는다.

모든 역할에 같은 형식 예시 두 개를 제공한다. **예시의 원자·규칙 이름은 다르지만, 그 구조는 `chain_2`와 동형이다.** 따라서 v0.2는 공통 예시를 제공한 지시 수행 실험이며, 무예시 성능이나 낯선 구조로의 일반화 실험이 아니다. neutral도 같은 예시와 출력 계약을 보며 A/D/M 역할만 지정되지 않는다. v0.1과 v0.2는 프롬프트·전송 형식이 달라 같은 조건의 단순 반복으로 합산하지 않는다.

## 5. 재개·환경·비용

중단 후에는 **같은 버전 소스·모델·설정·출력 폴더**로 `--resume`을 붙인다. 완료된 실패 조건도 다시 추론하지 않는다. 요청만 남고 응답이 없는 조건은 미확인 실패 기록으로 남기며 자동 재호출하지 않는다. v0.1 결과 폴더를 v0.2로 이어 실행하지 않는다.

```powershell
py -3 -m local_llm run --profile pilot --gate results_llm/v02_smoke_01 --out results_llm/v02_pilot_01 --resume
```

서버가 계속 추론 중인지 확인한 뒤 재개한다. 강제 종료로 `.run.lock`만 남았을 때는 실제 실행 프로세스가 없는 것을 확인한 뒤 그 잠금 파일만 지운다.

기본값: `qwen3:4b`, `think=false`, 문맥 8192, 호출당 출력 한도 4096, temperature 0.2, top_p 0.9, top_k 20, repeat_penalty 1.0, CPU threads 6, batch 256, 요청 1개씩 순차 실행. 이번 수정에서는 모델·샘플링 기본값을 바꾸지 않았다.

실행 설정, 모델 digest, Ollama 버전, 검증기·런타임 소스의 해시와 소스 스냅샷을 저장한다. 토큰·시간은 Ollama의 실제 반환값을 사용한다. `/api/ps`의 `size_vram`은 모델 적재 정보이며 GPU 이용률이나 순간 최대 VRAM 측정치가 아니다. 별도 비용 절감이나 속도 개선을 주장하지 않는다.

## 6. 이전 응답 재분석 — LLM 호출 0회

```powershell
py -3 -m local_llm inspect-results --input results_llm/pilot_01 --out results_llm/v01_pilot_reanalysis
```

원본 폴더 밖의 빈 경로에 `reanalysis.json/md`를 만든다. 원본 결과의 해시·스냅샷을 검사하고 보존 응답을 현재 설치된 **동일한 기준 검증기**로 재검사한다. 첨부 결과의 `source_snapshot`을 실행하지 않는다. 원본 trace를 v0.2 성공 출력으로 변환하지 않는다. 현재 `inspect-results`는 통합 실험을 지원하며 `calibrate` 결과는 자체 요약으로 읽는다.

`inspect-results`의 핵심 검증기 바이트가 당시와 달라졌다면 분석을 중단한다. 줄바꿈 변경도 재분석 바이트 일치 검사에 영향을 줄 수 있으므로, 기존 결과를 생성한 로컬 검증기를 유지한다.

## 7. 오프라인 개발 시험

```powershell
py -3 -m unittest discover -s local_llm/tests -v
```

외부 모델·네트워크를 사용하지 않는다. 기존 39개 계약시험과 24개 신규 시험이다. 실제 실패 원문 네 건을 회귀 픽스처로 포함하고, 생성기 호출은 시험 픽스처를 만드는 경우에만 사용한다. 런타임 모델 경로는 기존 `simulate()`로 답을 대신 만들지 않는다.

`BUILD_STATUS.json`, `validation/offline_tests.txt`, `validation/selfcheck.json`, `MANIFEST.sha256`에서 작성·검사 범위를 확인할 수 있다. 검증기 기준 commit은 `254757486a987475d16541cf84b905d684c1c13d`이며, 의미 검증 코드 `adm_minimal.py`는 이번 수정 대상이 아니다.
