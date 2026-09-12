# 고정 목표 A/D/M — 로컬 LLM 검증 소스

**버전:** 0.1.0 · **대상:** Windows / Ryzen 5 5600X / RAM 32GB / RTX 4060  
**형태:** 기존 `thought-graph-simulator`에 추가하는 `../local_llm_0441` 폴더  
**배포 상태:** 소스 작성 및 정적 구문 검사. 모델 다운로드, 추론, 단위시험, Windows 실행은 작성자가 수행하지 않았다.

## 1. 이번에 실제로 바뀌는 부분

기존의 `simulate()`가 정해진 규칙으로 만들어 주던 증명 경로·표현 도식·검토 기록을 **로컬 LLM이 직접 생성**한다. 기존 `adm_minimal.py`의 `verify()`가 원문 문제를 별도로 받아 다시 판정한다. 기존 파일·논문·결과를 교체하지 않는다.

```text
기존 examples/problems.json의 사실·규칙·목표
  → 조건 공통 출력 규약 + A/D/M 역할 지시
  → Ollama / qwen3:4b가 JSON 증명 기록 생성
  → 필드 위치만 변환하고 문제 식별자·해시 부착
  → 기존 verify()로 증명·표현·검토 재검사
  → 실제 관측값과 요청 역할 비교
  → 실패를 포함한 결과·축별 대조·토큰·시간 저장
```

A는 `instance / schema`, D는 실제 지지 DAG의 최장 의존 깊이, M은 검토 대상 0/1/2다. A를 논문의 A0~A4 전체 분류로 확장하거나, D를 문장 수·토큰 수로 바꾸지 않았다. 모델 출력이 잘못되면 코드가 정답 경로·도식·검토를 대신 채워 주지 않는다.

이 실험의 목표는 **동일한 문제와 고정 목표에서 작은 모델이 지정한 A/D/M 역할을 수행하는지 확인하는 것**이다. 논문 부록의 H7b 라우터·B0~B3 실험 전체는 별도이며, 이번 추가 파일이 그 구현이라고 표시하지 않는다. 자세한 판정 계약은 `PROTOCOL.ko.md`에 있다.

## 2. 모델과 기본 설정

| 항목 | 기본값 |
| --- | --- |
| 모델 | `qwen3:4b` |
| 실행 엔진 | Windows용 Ollama |
| 모델 파일 형식 | GGUF / 라이브러리 기본 Q4_K_M |
| 모델 파일 크기 | 공식 라이브러리 표시 약 2.5GB |
| 문맥 길이 | 8,192 토큰 |
| 호출당 최대 출력 | 4,096 토큰 |
| Thinking | `false` |
| 동시 모델 요청 | 이 프로그램은 항상 1개씩 순차 실행 |
| CPU 스레드 / 배치 | 6 / 256 |
| temperature / top_p / top_k | 0.2 / 0.9 / 20 |
| 추가 Python 패키지 | 없음. 표준 라이브러리만 사용 |

Ollama는 Windows에서 NVIDIA GPU를 지원하고 RTX 4060을 지원 목록에 명시한다. 위 모델은 크기와 출력 형식 지원을 고려해 선택한 시작점이다. **2.5GB는 모델 파일 크기이지 전체 VRAM 사용량이 아니다.** 화면에는 전용 VRAM 총량이 보이지 않았으므로 `doctor`가 사용자 PC에서 드라이버·VRAM 정보를 조회하게 했다. 처리 속도와 실제 적재 메모리는 아직 측정하지 않았다. [S1–S4]

Python에 PyTorch, Transformers, CUDA Toolkit, `ollama` Python 패키지를 설치할 필요가 없다. GPU 추론은 별도로 설치하는 Ollama가 담당한다. Python 소스는 3.10 이상 문법으로 작성했다. [S2, S5]

## 3. 파일을 놓을 위치

ZIP을 풀어 나온 **`local_llm` 폴더만 기존 프로젝트 최상위에 복사**한다. `adm_minimal.py`와 같은 위치다. 기존 README나 결과 파일을 덮어쓰지 않는다.

```text
thought-graph-simulator/
├─ adm_minimal.py                 기존 파일 그대로
├─ examples/problems.json         기존 문제 그대로
├─ results/                       기존 결정론적 실행 결과 그대로
├─ paper/                         기존 논문 그대로
├─ supplement/                    기존 논문 부록 그대로
└─ local_llm/                     이번 추가 폴더
   ├─ __main__.py                 명령행 진입점
   ├─ client.py                   로컬 Ollama 통신
   ├─ protocol.py                 조건 공통 스키마·무보정 변환
   ├─ prompts.py                  한국어 과제·역할 지시
   ├─ design.py                   조건표·참조 깊이
   ├─ audit.py                    기존 검증기 연결·층위별 진단
   ├─ runner.py                   순차 실행·기록·중단 복구
   ├─ report.py                   집계·CSV·축별 대조
   ├─ common.py                   JSON·해시·파일 저장
   ├─ tests/test_local_llm.py      사용자가 실행할 오프라인 시험
   ├─ windows/serve-local.ps1      로컬 전용 서버 시작
   ├─ README.ko.md
   ├─ PROTOCOL.ko.md
   ├─ SOURCES.md
   └─ BUILD_STATUS.json
```

ZIP에는 모델 가중치와 기존 `adm_minimal.py`가 들어 있지 않다. 확인한 기준 커밋은 `254757486a987475d16541cf84b905d684c1c13d`다. 기존 핵심 파일의 Git blob은 `b7aa0b58b9257fdb80882b48e4ecf1006ac4ff45`다. Windows 체크아웃의 CRLF/LF 차이는 허용한다.

## 4. 최초 준비

### 4.1 Python·Ollama 확인

PowerShell의 현재 경로를 **기존 프로젝트 루트**로 바꾼 뒤 확인한다. `C:\Windows\System32`에서 실행하지 않는다.

```powershell
# 탐색기에서 프로젝트 폴더를 연 뒤 주소 표시줄에 powershell을 입력해도 된다.
py -3 --version
ollama --version
```

Python이나 Ollama가 없으면 각각 공식 설치 프로그램으로 설치하고 새 PowerShell 창을 연다. 설치 주소는 `SOURCES.md`의 코드 블록에 있다. NVIDIA 드라이버가 너무 오래되었으면 Ollama의 Windows 요구 조건도 확인한다. 이 패키지는 설치 프로그램·드라이버를 자동 설치하지 않는다. [S2]

### 4.2 로컬 전용 서버 실행

Ollama 설치 직후에는 트레이 앱이 서버를 이미 실행할 수 있다. 트레이의 Ollama를 **Quit**하여 정상 종료한 후, 프로젝트 루트에서 아래 명령을 실행한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\local_llm\windows\serve-local.ps1
```

이 PowerShell 창은 열어 둔다. 스크립트는 해당 프로세스에만 로컬 주소·클라우드 비활성·동시 요청 1개를 설정한다. 기존 프로세스 강제 종료나 사용자 전체 환경변수 변경은 하지 않는다. `ExecutionPolicy Bypass`도 이 자식 PowerShell 실행에만 지정한 것이며 전역 설정 변경 명령이 아니다.

스크립트를 사용하지 않고 같은 설정으로 직접 실행하려면 기존 Ollama를 종료한 PowerShell에서 다음과 같이 한다.

```powershell
$env:OLLAMA_HOST = "127.0.0.1:11434"
$env:OLLAMA_NO_CLOUD = "1"
$env:OLLAMA_NUM_PARALLEL = "1"
$env:OLLAMA_MAX_LOADED_MODELS = "1"
$env:OLLAMA_CONTEXT_LENGTH = "8192"
$env:OLLAMA_KV_CACHE_TYPE = "f16"
ollama serve
```

`OLLAMA_NO_CLOUD`와 병렬 처리 설정은 서버 프로세스가 읽는 값이다. 다른 터미널에서 이미 실행 중인 서버에 뒤늦게 설정해도 반영되지 않는다. [S6]

### 4.3 모델은 사용자가 직접 다운로드

**두 번째 PowerShell 창**을 프로젝트 루트에서 열어 실행한다.

```powershell
ollama pull qwen3:4b
```

이 명령은 최초 모델 다운로드다. Python 확장은 `/api/pull`을 호출하지 않으며, 모델이 없으면 멈춘다. 다운로드 이후의 이 실험은 로컬 루프백 서버를 사용한다. API 키나 OpenAI 계정 설정은 필요하지 않다. [S1, S5]

## 5. 먼저 확인하고 작게 실행

### 5.1 오프라인 코드 시험

```powershell
py -3 -m unittest discover -s local_llm/tests -v
```

시험 코드가 기존 결정론적 생성기로 테스트용 기록을 만들 수는 있지만, **LLM·네트워크·GPU는 호출하지 않는다.** 이 시험은 소프트웨어 점검이며 LLM 성능 결과가 아니다. 작성자가 실행한 테스트 결과는 동봉하지 않았다.

### 5.2 설치와 모델 정보 확인 — 추론하지 않음

```powershell
py -3 -m local_llm doctor
```

기존 검증기 기준 파일, Python/운영체제, `nvidia-smi`의 GPU·VRAM·드라이버, Ollama 버전, 로컬 모델 digest, capability를 출력한다. 모델을 로드해 JSON을 생성한 결과는 아니다.

### 5.3 조건표 확인 — Ollama에 접속하지 않음

```powershell
py -3 -m local_llm plan --profile smoke
py -3 -m local_llm plan --profile pilot
```

### 5.4 첫 실제 추론 — 6회

```powershell
py -3 -m local_llm run --profile smoke --out results_llm/smoke_01
```

기본 첫 문제 `chain_2`에서 중립 조건과 다섯 가지 역할 조건을 실행한다. 최초 실행은 모델 적재 시간이 포함될 수 있다. 진행 상황과 각 실패 이유가 터미널에 출력된다. 동시에 다른 LLM 추론을 실행하지 않는 편이 실험 비교에 적합하다.

다른 PowerShell 창에서 다음 명령으로 모델 적재 위치를 확인할 수 있다.

```powershell
ollama ps
```

`PROCESSOR`의 `100% GPU`, `CPU/GPU` 혼합, `100% CPU`를 구분한다. 작업 관리자의 일반 3D 사용률 하나만으로 추론 여부를 판정하지 않는다. [S6]

## 6. 본 실험 규모

| 프로필 | 문제 | 조건 | 반복 | 배정 호출 | 축별 대조 |
| --- | ---: | ---: | ---: | ---: | ---: |
| smoke | 첫 문제 1개 | 중립 1 + 지정 5 | 1 | 6 | 4 |
| pilot | 기본 3개 | 중립 1 + A2×D2×M3 | 1 | 39 | 60 |
| full | 기본 3개 | 중립 1 + A2×D2×M3 | 3 | 117 | 180 |

위 숫자는 기본 문제 파일을 사용하는 **계획 수**이지 이미 실행한 결과가 아니다. 같은 반복 블록에서는 같은 seed를 사용하고 조건 순서를 섞는다. 모든 조건의 출력 스키마·모델·샘플링 설정·호출당 토큰 한도는 같다.

```powershell
py -3 -m local_llm run --profile pilot --out results_llm/pilot_01
py -3 -m local_llm run --profile full --out results_llm/full_01
```

`smoke`는 연결·형식과 최소 대조를 확인하는 용도다. `pilot`은 기존 36개 지정 조건 전체를 한 번씩 본다. `full`은 같은 세 문제를 세 시드로 반복하는 것이며 독립된 117개 문제를 푼다는 뜻이 아니다.

문제 하나만 정해서 전체 조건을 실행할 수도 있다.

```powershell
py -3 -m local_llm run --profile pilot --problem conjunction_4 --out results_llm/conjunction_01
```

같은 조건을 5번 반복하려면 `--repeats 5`를 명시한다. 문제를 바꿀 때는 `--problems 다른문제.json`을 사용한다. 도달 불가능하거나 깊이 차이가 없는 문제도 조용히 제외하지 않고 경고와 실패를 남긴다.

## 7. 결과 파일 읽는 순서

먼저 `results_llm/실험명/summary.md`를 연다. 상세 수치는 `metrics.csv`, 전체 설정은 `manifest.json`, 축별 비교는 `contrasts.json`에 저장된다.

```text
results_llm/pilot_01/
├─ manifest.json                 문제·조건·시드·모델 digest·소스·환경 동결
├─ summary.md                    한국어 요약
├─ summary.json                  기계 판독용 집계
├─ metrics.csv                   조건별 지표, UTF-8 BOM
├─ contrasts.json                A/D/M별 대조 결과
├─ source_snapshot/              실행 당시 확장 소스와 기존 검증기 사본
└─ cases/<case_id>/
   ├─ request.json               실제 요청 본문·문제/역할 지시
   ├─ response.raw.json          수신한 Ollama API JSON 원문
   ├─ trace.json                 필드 위치만 옮긴 기존 검증기 형식
   ├─ timing.json                호출 경과 시간
   ├─ gpu.json                   응답 후 모델 적재 정보
   └─ record.json                판정·실패 사유·비용·파일 해시
```

`proof_valid`가 실패하면 목표까지의 근거 자체가 잘못된 것이다. 증명은 통과하지만 `representation_valid`가 실패하면 도식의 바인딩·가정·양화 등을 확인한다. `review_valid`가 실패하면 검토 대상·근거 목록·판정값을 확인한다. 전체 증명 기록이 유효해도 요청한 깊이나 A/M 역할을 따르지 않으면 `role_mismatch`다.

A/D/M 준수율은 **처음 배정한 모든 지정 조건**을 분모로 한다. 성공한 출력만 골라서 비율을 계산하지 않는다. 중립 조건은 역할을 지정하지 않았으므로 역할 준수율에서만 제외한다. 토큰 누락은 `null/unknown`이며 0으로 채우지 않는다.

`record.json`의 진단 사본은 원문 실패를 설명하기 위한 것이다. 원본의 전체 검사 실패를 뒤집지 않는다. `/api/ps`의 `size_vram`은 적재 메모리 정보이며 최고 VRAM 사용량이나 GPU 이용률 측정이 아니다. [S7]

기존 CLI로 변환된 기록을 한 번 더 검사할 수 있다. `<case_id>`는 실제 생성된 폴더명으로 바꾼다.

```powershell
py -3 adm_minimal.py verify --trace results_llm/pilot_01/cases/<case_id>/trace.json
```

이 기존 CLI는 기존 trace 계약을 검사한다. 이번 확장의 추가 실험 정책인 역할 일치와 단순 지지 경로 제한은 `record.json`에서 함께 확인해야 한다. 원본 문제 파일을 바꿨다면 당시 manifest의 문제와 현재 파일이 일치하는지도 확인한다.

## 8. 중단과 이어서 실행

같은 설정으로 미시작 조건만 이어서 실행한다.

```powershell
py -3 -m local_llm run --profile full --out results_llm/full_01 --resume
```

완료한 실패 조건을 다시 뽑아 성공으로 바꾸지 않는다. 요청만 저장되고 응답이 없는 조건은 `interrupted_unknown`으로 종결하며 재호출하지 않는다. 응답이 이미 파일로 보존된 조건은 새 추론 없이 판정할 수 있다. 통신 오류가 발생하면 서버에 기존 작업이 남아 있을 수 있으므로 다음 호출을 바로 보내지 않고 실행을 멈춘다.

강제 종료로 `.run.lock`만 남으면 같은 실험이 실행 중이지 않은지 확인한 후 **그 잠금 파일만** 삭제한다. 그 다음 `--resume`을 사용한다. 프로그램은 잠금을 자동으로 깨지 않는다.

모델 digest, Ollama 버전, Python/운영체제·드라이버 정보, 소스, 문제, 시드, 예산 등이 바뀌면 이어서 실행을 거부한다. 변경한 조건은 새 결과 폴더를 사용한다. GitHub의 기존 코드 자체가 바뀌었다면 내용을 확인한 뒤 `--allow-core-change`를 명시할 수 있지만, 원래 검증기와 동일하다고 표시하지 않는다.

저장된 판정 결과만 다시 집계하려면 다음을 실행한다. 이 명령은 모델을 호출하지 않으며, 원문에서 모든 판정을 새로 수행하는 별도 재감사 명령은 아니다.

```powershell
py -3 -m local_llm summarize --out results_llm/full_01
```

## 9. 흔한 상황

**`No module named local_llm`**: 프로젝트 루트가 아니라 다른 폴더에서 실행했거나 `../local_llm_0441`처럼 한 단계 깊게 복사했는지 확인한다.

**`adm_minimal.py` 기준 파일 불일치**: 이번 소스가 확인한 커밋 이후 핵심 파일이 바뀌었는지 확인한다. 자동으로 옛 파일을 덮어쓰지 않는다.

**모델이 없다**: `ollama list`로 이름을 확인한다. `qwen3:4b`와 다른 태그를 쓴다면 다운로드 명령과 `--model`을 함께 맞춘다. 자동 대체 모델은 없다.

**11434 포트 사용 중**: 기존 Ollama 트레이 앱이나 서버가 떠 있다. 정상 종료 후 로컬 전용 시작 스크립트를 다시 실행한다.

**`truncated`가 많다**: API가 출력 한도 종료를 보고한 것이다. 기존 결과를 보존하고 새 폴더에서 `--num-ctx 12288 --num-predict 6144` 같은 더 큰 예산을 별도 시험할 수 있다. 문맥을 늘리면 메모리 사용도 증가하므로 `ollama ps`를 확인한다. 두 실험의 예산은 다르다고 구분한다.

**증명은 맞지만 schema·M 검토가 실패한다**: JSON 형식 부담과 해당 의미 계약의 수행 실패를 분리해 `record.json`과 원문을 본다. 프로그램이 자동으로 보완하거나 재질문하지 않으므로 실패 기록 자체가 관측 결과다.

**CPU에 적재된다**: 드라이버와 다른 GPU 프로그램의 메모리 사용을 확인하고 `doctor`, `ollama ps`의 출력을 본다. 소스에서 GPU 사용 성공을 추정해 기록하지 않는다.

**호출이 느리거나 timeout**: 로그에 최초 로딩 시간을 구분해서 저장한다. `--timeout 600`을 사용하는 새 실험을 만들 수 있다. 이 값은 소켓 대기 제한이며 엄밀한 서버 계산 시간 상한이나 서버 작업 취소 명령이 아니다.

실행 종료 코드는 `run` 기준 0=전체 배정 조건과 대조 통과, 1=실험 완료했지만 미준수/실패 존재, 2=통신·환경·하네스 오류, 130=사용자 중단이다. `doctor/plan/summarize`의 0은 해당 명령의 완료만 뜻한다.

## 10. 남겨 둔 연구 경계

이 버전은 외부로 작성된 형식 증명 기록을 검사한다. 모델 내부 레이어의 A/D/M 좌표를 관측하거나 바꾸는 코드는 아니다. 모델에게 목표를 알려주는 것은 고정 목표 역할 수행이라는 과제 조건이며, 증명 경로와 참조 깊이는 프롬프트에 제공하지 않는다.

기본 세 문제는 작고 규칙 이름에도 경로 힌트가 있다. 동일 문제의 A/D/M 조작 여부를 확인하는 시작점이지 폭넓은 일반화 시험은 아니다. A 도식·M 검토는 출력량을 늘릴 수 있어, 토큰과 시간을 저장했다는 사실만으로 계산량 절감이나 성능 향상을 선언하지 않는다.

확인한 공식 API와 모델 자료는 `SOURCES.md`, 작성·미실행 상태는 `BUILD_STATUS.json`에 기록했다.
