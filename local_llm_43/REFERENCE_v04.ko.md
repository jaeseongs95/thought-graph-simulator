# 로컬 LLM 고정 목표 A/D/M 실험 — v0.4.0

## 교체 범위

기존 `local_llm` 폴더를 다른 이름으로 보관한 뒤 이 폴더로 교체한다. `adm_minimal.py`, `examples/problems.json`, 기존 `results_llm`은 변경하지 않는다. 덮어쓰기보다 폴더 교체가 적절하다. 예전 파일이 섞이지 않게 하기 위해서다.

Python 3.10 이상, 로컬 Ollama를 사용한다. Python 코드는 표준 라이브러리만 필요하다. 작성 시 Python 3.13에서 오프라인 시험을 실행했고 Python 3.10 문법 검사도 별도로 수행했다. Windows/Ollama/모델 추론을 작성 환경에서 실행한 것은 아니다.

```text
thought-graph-simulator/
├─ adm_minimal.py              기존 검증기 그대로
├─ examples/problems.json     기존 문제 그대로
├─ results_llm/               과거 결과 그대로
└─ local_llm/                 이번 버전으로 교체
```

## 기본 실행: 새로운 기준선

Ollama 서버가 실행 중인 상태에서 프로젝트 루트 PowerShell에 입력한다.

```powershell
# 최초 한 번: 명시적인 Instruct 체크포인트를 사용자가 직접 다운로드
ollama pull qwen3:4b-instruct

# 코드 자체 검사: 추론/네트워크 없음
py -3 -m local_llm selfcheck

# 모델 메타데이터/모드 확인: 추론 없음
py -3 -m local_llm doctor

# 분리 진단: 24회 (학습/파인튜닝 아님)
py -3 -m local_llm calibrate --out results_llm/v04_calibration_01

# 통합 최소 실험: 6회
py -3 -m local_llm run --profile smoke --out results_llm/v04_smoke_01

# 같은 조건의 통합 본 실험: 39회
py -3 -m local_llm run --profile pilot --gate results_llm/v04_smoke_01 --out results_llm/v04_pilot_01
```

**예전 `v02_smoke_01`/`v03_pilot_01`을 새 기본 실행의 게이트나 이어하기 대상으로 사용하지 않는다.** 모델 체크포인트·프롬프트·문제 구성이 달라졌다. 예전 결과는 그 조건의 결과로 보존한다. 위 전체 순서는 진단 24회 + smoke 6회 + pilot 39회, 합계 69회 계획이다. 모델 오류로 호출이 시작되지 않거나 중단되면 실제 호출 수는 줄어든다. 세 묶음을 독립된 69문제 표본으로 합산하지 않는다.

`accepted` 이외의 의미적 실패가 나와도 다음 조건을 진행한다. `role_mismatch`, `invalid_trace`, `invalid_task`, 정상 응답의 JSON 형식 실패는 측정 대상이다. calibration의 전부 성공을 pilot의 전제조건으로 삼지 않는다.

`mode_error`, 통신/하네스 오류는 별개다. 모델 채널 불일치 등이 발견되면 중단한다. smoke가 길이 제한으로 잘렸다면 준비 게이트를 통과시키지 않는다. 이미 기록한 실패를 성공으로 고치거나 자동 재호출하지 않는다.

## 실제로 바뀐 전제

| 항목 | v0.4 기본값/동작 |
| --- | --- |
| 모델 | `qwen3:4b-instruct` |
| 모드 | `--mode auto`: 실제 GGUF 메타데이터를 확인. Instruct-2507에는 `think` 필드 생략 |
| Thinking | Thinking-2507에는 `think:true`; 별도 `message.thinking`과 최종 `message.content` 확인 |
| 불일치 | Thinking-2507 + non-thinking, Instruct-2507 + thinking 요청을 추론 전에 거부 |
| 모드 지원 범위 | 메타데이터로 식별 가능한 Qwen3 Instruct/Thinking-2507. 다른 계열/불명확한 메타데이터는 자동 추정하지 않음 |
| 프롬프트 | `factorized-v4`: 증명, 표현, 검토 예시를 분리 |
| 기본 통합 문제 | `transfer-v4`: 추가 구조 3개. 기존 문제 파일은 수정하지 않음 |
| 성공 기준 | 기존 전체 증명·도식·검토 검증 유지 |
| 진단 | 전체 실패, 축 불일치, 전제 실패로 인한 평가 불가(null)를 분리 |

모델 태그에 `instruct`라는 글자가 있다고 믿는 방식이 아니다. `general.architecture`, `general.finetune`, `general.version`, 공식 체크포인트 URI, capability를 검사한다. 모델 digest·메타데이터·설정·요청 바이트는 실행마다 동결한다. 실행 중 태그 digest가 바뀌면 중단한다.

`doctor`는 메타데이터의 일관성만 확인한다. 실제 채널은 첫 추론에서 별도로 검사한다. API가 HTTP 200을 반환했다는 이유만으로 Thinking 모드가 정상이라고 판단하지 않는다. thinking 문자열에서 JSON을 찾아 최종 답으로 사용하는 복구도 하지 않는다.

## 모델별 기본 예산

| 항목 | Instruct-2507 | Thinking-2507 |
| --- | ---: | ---: |
| temperature | 0.7 | 0.6 |
| top_p | 0.8 | 0.95 |
| top_k / min_p | 20 / 0 | 20 / 0 |
| num_ctx | 8192 | 16384 |
| num_predict | 4096 | 8192 |
| num_thread / num_batch | 6 / 256 | 6 / 256 |
| 동시 추론 | 1 | 1 |

샘플링 기본값은 각 모델 공식 권장값에 맞추고, context/출력 예산은 사용자 로컬 환경에서 시작하기 위한 제한된 설정으로 잡았다. **공식 벤치마크의 긴 출력 예산을 재현한 설정이 아니다.** 메모리 사용량/속도/성공률을 미리 보증하지 않는다. `num_predict`는 Thinking 모드에서 사고와 최종 응답에 사용되는 생성 예산이다. API `eval_count`를 최종 JSON 토큰 수로 부르지 않는다.

`--temperature`, `--top-p`, `--num-ctx`, `--num-predict`, `--threads`, `--batch-size`, `--timeout`으로 명시할 수 있다. 설정을 바꾸면 새 결과 폴더와 새 smoke를 사용한다.

## 분리 진단 24회의 구성

| 과제 | 호출 | 측정 범위 |
| --- | ---: | --- |
| 증명만 생성 | 6 | 3문제 × shallow/deep. 표현/검토는 미측정 |
| 고정 증명 전체 노드의 도식화 | 3 | 제공한 증명의 전체 도식 작성 |
| 같은 증명의 최종 노드만 도식화 | 3 | 최종 도식 하나의 의미 검사. 중간 표현은 호스트의 진단용 instance |
| 고정 기록 검토 | 6 | 유효/무효 지지, 목표/비목표, 불필요한 노드 등 |
| 기준 비교 | 6 | 서로 다른 정답 패턴 3종을 2회씩. 단독 사실 probe로 정의 |

전체 도식과 최종 도식 단독 과제는 같은 고정 증명에 대해 짝지어 저장한다. 최종 도식만 성공한 경우 그것을 전체 A 성공이라고 세지 않는다. 이는 의미를 이해하지 못한 것인지, 누적 도식을 반복 작성하며 오류가 생기는지 구분하기 위한 관측이다. 한 번의 쌍 비교로 단독 원인을 단정하지 않는다.

기준 비교 과제는 true/false 패턴을 서로 다르게 해야 통과한다. `task_comparisons.json`에는 **모델 실제값 / 기대값 / 일치 여부**를 별도로 저장한다. `component_diagnostics.json`에는 과제군별 결과, 정답 패턴별 결과, 상수 응답 관측, 도식 범위별 쌍 비교가 있다. 고정된 증명을 주는 과제에서 모델이 그 증명 자체를 생성했다고 주장하지 않는다.

## 통합 문제/예시 대조

기본 `transfer-v4`에는 분기 후 합류, 공유 지지 조상, 순환 후보/무관한 규칙이 있는 추가 문제 3개를 넣었다. 원자명과 규칙명/배열 순서는 고정 시드로 재배치하며 동일 문제의 모든 역할에는 같은 입력을 보낸다. 가능한 증명 깊이는 각각 `[2,4]`, `[2,3]`, `[3,4]`다. 참조 깊이/정답 경로를 모델 프롬프트에 주지 않는다. 이 세 문제만으로 광범위한 일반화를 입증하는 것은 아니다.

기존 3문제를 다시 사용할 때에는 두 명령 모두 `--suite legacy`를 지정한다.

```powershell
py -3 -m local_llm run --profile smoke --suite legacy --out results_llm/v04_legacy_smoke_01
py -3 -m local_llm run --profile pilot --suite legacy --gate results_llm/v04_legacy_smoke_01 --out results_llm/v04_legacy_pilot_01
```

`--problems <파일>`을 지정하면 `--suite`보다 우선한다. `--problem <id>`로 문제를 선택할 수 있다. `full`은 3반복, 기본 117회다. 같은 문제의 반복을 별개 문제로 세지 않는다.

### 예시 유무만 바꾸는 대조

`definitions-v4`는 `factorized-v4`와 의미 지시/출력 스키마/역할 지시는 같고, 공통 예시만 제거한다. 서로 다른 출력 폴더로 실행한다.

```powershell
py -3 -m local_llm run --profile smoke --prompt-profile definitions-v4 --out results_llm/v04_no_examples_smoke_01
py -3 -m local_llm run --profile pilot --prompt-profile definitions-v4 --gate results_llm/v04_no_examples_smoke_01 --out results_llm/v04_no_examples_pilot_01
```

예시 제거로 입력 길이도 달라진다. 결과 차이는 예시 조건의 효과이며, 한 측정으로 내부 원인을 특정하지 않는다. `legacy-v2`/`explicit-v3`는 과거 형식의 재검사/별도 대조용으로 남겼다. **새 추론에서는 이 프로필을 선택해도 모델 모드 검사를 우회하지 못한다.** 예전 8회 진단에는 `--calibration-suite legacy-v2`를 명시한다.

## 현재 Thinking 모델을 별도 조건으로 사용할 때

사용자 기존 `qwen3:4b`의 기록은 Thinking-2507이었다. 그대로 설치돼 있으면 다음처럼 명시할 수 있다. alias가 다른 체크포인트로 바뀌었으면 실제 메타데이터 검사가 이를 드러낸다.

```powershell
py -3 -m local_llm doctor --model qwen3:4b --mode thinking
py -3 -m local_llm calibrate --model qwen3:4b --mode thinking --out results_llm/v04_thinking_calibration_01
```

Ollama/템플릿/구조화 출력 조합에서 별도 thinking과 최종 JSON이 정상 반환되는지는 실제 실행이 필요하다. 모드 오류가 나면 설정을 확인해야지 검사를 끄고 대량 실행하지 않는다. 더 긴 예산이 필요하면 예산을 명시하고 새 폴더를 쓴다. Instruct와 Thinking은 다른 체크포인트이므로 같은 가중치의 단순 on/off 실험으로 합산하지 않는다.

## 결과 파일과 종료 코드

우선 `summary.md`를 읽는다. 통합 실험은 `metrics.csv`, 분리 진단은 `component_diagnostics.json`/`task_comparisons.json`을 함께 본다. `cases/`에 요청 원문·응답 원문·판정·시간·모델 적재 정보가 보존된다.

축별 표의 일치 + 불일치 + 평가 불가/미완료 = 배정된 지시 조건 수다. 선택된 연결 부분의 깊이는 별도 진단이다. 전체 기록에서 불필요한 노드를 제거하지 않는다. `M_target_observed`는 검토 종류 관측이지 내용이 정확하다는 뜻이 아니다.

**본 실험의 M2는 원래 고정 목표 반례 계약을 유지하므로 기본 3문제에서 판정 정답 패턴이 같다.** 보고서에 이 한계를 표시한다. 다양한 기준 판정 능력은 별도 6회 진단에서 확인하며, 그 성공을 본 실험의 성공률에 합산하지 않는다.

종료 코드 0은 실험이 처리됐다는 뜻이지 모델 성능 PASS가 아니다. `execution_completed`와 `performance_passed`를 분리한다. 코드 2는 환경/모드/통신/하네스/미완료, 130은 사용자 중단이다. 모델 성능 실패도 코드 1로 받고 싶을 때는 `--fail-on-model-failure`를 쓴다. `--gate-mode strict`만 모든 smoke 과제의 성공도 요구하며 기본은 `readiness`다.

## 재개와 오프라인 검사

환경·모델·서버·소스·문제·시드·설정이 모두 동일할 때만 기존 명령 뒤에 `--resume`을 붙인다. 완료된 실패를 다시 시도하지 않는다. 응답이 유실돼 성공 여부를 모르는 요청도 자동 재호출하지 않는다. 새 소스 설치 뒤 이전 실험을 이어하지 않는다. 강제 종료 뒤 남은 `.run.lock`은 관련 프로세스가 모두 종료됐음을 확인한 경우에만 제거한다.

```powershell
# 계획만 조회
py -3 -m local_llm plan --profile pilot

# 오프라인 시험 전체
py -3 -m unittest discover -s local_llm/tests -v

# 과거 응답 재검사: 원본은 변경하지 않음
py -3 -m local_llm inspect-results --input results_llm/v03_pilot_01 --out analysis_v04/v03_replay

# 새 smoke의 실행 준비를 파일만으로 확인
py -3 -m local_llm check-gate --gate results_llm/v04_smoke_01
```

서버가 꺼졌다면 기존 Ollama 앱을 시작하거나 `windows/serve-local.ps1`을 별도 창에서 실행한다. 스크립트는 이미 실행 중인 서버를 강제 종료하지 않는다. 로컬 API 호출만 허용하며 자동 모델 다운로드·원격 클라우드 전환·의미 오류 재시도·외부 도구 실행은 구현하지 않았다.

검사 범위는 `BUILD_STATUS.json`, 연구 해석은 `PROTOCOL.ko.md`, 공식 근거는 `SOURCES.md`에 있다.
