# v055 — 같은 문제에서 Qwen/Gemma의 선택적 D 제어 비교

v054 원문 분석을 바탕으로 추가한 별도 실험 모듈이다. 기존 `v054_order_probe`를 교체하지 않는다.

**질문:** 동일한 두 문제·두 규칙 순서에서, 비슷한 크기의 다른 계열 모델도 shallow/deep 지시와 무관하게 같은 경로를 선택하는가?

v054에서는 K01의 규칙 순서 변경에 따라 유효 깊이가 2→1로 바뀌었지만 선택적 D 제어는 없었다. T02의 순서 변경 조건에서는 최종 규칙의 전제가 잘못 연결되어 30개 증명이 모두 무효였다. 이 어려운 조건을 제외하거나 보정하지 않고 두 모델에 똑같이 제시한다.


## v055-r2 실행 계획 크기 수정

실제 Gemma metadata를 포함한 v055 계획 파일은 `capture` 원문·identity·v054 기준선 영수증을 함께 보존하면서 공용 8 MiB JSON 한도를 넘을 수 있다. r1에서는 `prepare`가 큰 계획을 기록한 뒤 `run`이 그 계획을 다시 읽는 순간 `ContractError: JSON 크기 한도를 넘었습니다.`로 추론 전에 중단될 수 있었다.

r2는 **모델 응답/metadata의 기존 8 MiB 제한은 그대로 유지**하고, 이미 로컬에 동결된 `v055 plan`과 `plan.snapshot`에만 32 MiB 상한의 동일한 엄격 JSON 파서를 사용한다. 중복 키·비유한 숫자 검사도 유지한다. 연구 문제·요청 바이트·모델·seed·채점·실행 순서·무재시도 정책은 바꾸지 않았다. `prepare` 단계에서 저장한 계획을 새 파서로 즉시 재읽어 round-trip까지 확인한다.

## 실행

ZIP 안의 `v055_model_probe` 폴더를 기존 저장소 바로 아래에 추가한다.

먼저 새 비교 모델만 준비한다. 이미 같은 모델이 설치돼 있다면 다시 다운로드할 필요가 없다.

```powershell
ollama pull gemma3:4b
```

기존 Qwen 태그를 새로 만들거나 다른 가중치로 바꾸지 않는다. 기준선과 Qwen digest·show metadata·Ollama 서버 버전이 다르면 시작 전에 중단한다. 실행 중 모델이나 서버를 업데이트하지 않는다.

```powershell
Set-Location C:\Users\sjs95\Desktop\thought-graph-simulator\v055_model_probe
powershell -NoProfile -ExecutionPolicy Bypass -File .\windows\Run-All.ps1
```

기본 기준선은 `..\results_llm\v054_order_01_evidence.zip`이다. 다른 위치라면 다음과 같이 명시한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\windows\Run-All.ps1 -BaselineBundle "C:\경로\v054_order_01_evidence.zip"
```

이전 실행 자료가 이미 존재하면 새 이름을 사용한다. 실패한 원문은 지우지 않는다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\windows\Run-All.ps1 -RunName v055_model_02
```

기본 스크립트는 새 v055 시험을 실행한다. 기존 v047~v054까지 포함해 전체 시험을 다시 실행하려면 `-AllTests`를 추가한다. 시험은 임시 로컬 합성 서버를 사용하며 실제 Qwen/Gemma 추론을 실행하지 않는다.

## 실행 단계와 파일

```text
배포 파일 해시 확인
→ capture: 실제 v054 원문 재감사 + 두 로컬 모델 metadata 조회, 추론 0회
→ selftest: 코드 시험, 실제 모델 호출 없음
→ prepare: capture를 검증해 계획 동결, 네트워크 없음
→ run: 사전 배정된 240회 추론, 블록 앞뒤 metadata 검사
→ audit: 원문으로 오프라인 재계산
→ bundle: 실제 묶을 바이트를 다시 감사한 증거 ZIP
```

```text
results_llm\v055_model_01.capture\capture.json
results_llm\v055_model_01.plan.json
results_llm\v055_model_01\summary.ko.md
results_llm\v055_model_01\summary.json
results_llm\v055_model_01_evidence.zip
```

모델이 없거나 접속이 안 되는 경우 긴 시험 전에 `capture`가 중단하며 raw metadata와 오류가 남는다. `capture`는 서버를 켜거나 모델을 내려받지 않는다. `run` 오류는 status에 단계·종류·실패 슬롯을 남기고 자동 재시도하지 않는다. PowerShell의 마지막 오류보다 바로 앞 Python 오류와 `status.json.error`를 먼저 본다.

## 설계

| 요소 | 고정 내용 |
|---|---|
| 모델 | 기준선의 `qwen3:4b-instruct`와 `gemma3:4b` |
| 조건 | 2문제 × 2규칙 순서 × 3방향 × 10seed × 2모델 = 240회 |
| 방향 | shallow / deep / neutral |
| 요청 | 기존 Qwen 요청 120개를 바이트 단위 보존. 후보 요청은 `model` 값만 변경 |
| 언어 | 실제 기존 한국어 지시문 유지. 영문 번역/모델별 프롬프트 튜닝 없음 |
| 출력 | 동일 JSON schema. 호스트의 정답 경로 선택·응답 보정 없음 |
| 샘플링 | 기준선의 같은 수치 옵션과 전체 10seed 유지 |
| 실행 순서 | seed별 모델당 12회 블록. 먼저 실행하는 모델을 5:5로 교차 배정 |
| 모델 확인 | 시작 전 및 20개 블록 각각의 전후, 총 40개 metadata 기록 |
| 중단 | HTTP/identity 오류면 그대로 중단. 잘못된 증명은 실패로 기록하고 다음 배정 진행 |

모델당 120회 중 방향 지정 80회, 중립 40회다. 주 지표는 같은 문제·순서·seed에서 **shallow/deep 두 지시 모두 이행한 40쌍**이다. 두 규칙 순서 모두에서 성공한 20묶음도 별도로 집계한다. 동일 응답의 재집계를 새로운 독립 표본으로 더하지 않는다.

완료된 실험의 무효 응답은 배정 분모에서 제외하지 않는다. 응답을 파싱하지 못하면 증명 진위는 `null`이며, 최종 참조가 존재하지만 논리가 틀리면 `final_ref_valid=true`, `proof_valid=false`, `D=null`이다. 미실행 모델 간 대응쌍은 두 모델 모두 실패로 세지 않고 `unobserved_pairs`에 둔다.

## 수동 명령

```powershell
python tools\validate_release.py
python -m model_probe_v055 selftest
python -m model_probe_v055 selftest --all
python -m model_probe_v055 capture --baseline-bundle ..\results_llm\v054_order_01_evidence.zip --out ..\results_llm\v055_model_01.capture
python -m model_probe_v055 prepare --baseline-bundle ..\results_llm\v054_order_01_evidence.zip --capture ..\results_llm\v055_model_01.capture\capture.json --out ..\results_llm\v055_model_01.plan.json
python -m model_probe_v055 run --plan ..\results_llm\v055_model_01.plan.json --out ..\results_llm\v055_model_01
python -m model_probe_v055 audit --plan ..\results_llm\v055_model_01.plan.json --run ..\results_llm\v055_model_01
python -m model_probe_v055 bundle --plan ..\results_llm\v055_model_01.plan.json --run ..\results_llm\v055_model_01 --out ..\results_llm\v055_model_01_evidence.zip
python tools\independent_verify_v055.py ..\results_llm\v055_model_01_evidence.zip --out ..\results_llm\v055_model_01_independent.json
```

`bundle`은 원문이 무결하면 미완료 실행도 보존할 수 있다. 기본 Run-All은 오류 때 중단하므로 미완료 ZIP이 필요하면 마지막 `bundle` 명령만 수동 실행한다. `run`을 같은 결과 폴더에서 재시작하거나 기존 계획을 수정하지 않는다.

## 검증 범위

Python 3.13.5 / Linux에서 코드 시험·합성 HTTP·오프라인 재감사를 실행했다. Windows PowerShell의 실제 실행과 실제 두 모델의 새로운 240회 추론은 이 배포 검증에 포함되지 않는다. 요구 런타임은 Python 3.10 이상이며 외부 Python 패키지 의존성은 없다.

동일 API 옵션 숫자·seed라도 tokenizer/native template/가중치와 내부 난수 경로는 모델마다 다르다. 이 실험은 **이 실행 계약에서의 모델 패키지 차이**를 비교한다. 학습 우선순위나 내부 사고 메커니즘 하나를 분리해 입증하는 실험, 모든 모델/언어에서의 성능 순위, A/M 통합 성공 판정은 아니다.

관련 문서: `docs/PROTOCOL.ko.md`, `docs/REVIEW_AND_CHANGES.ko.md`, `docs/VALIDATION.ko.md`, `docs/SOURCES.ko.md`.
