# v052 A/D/M 핵심 가설·실패 위치 분리 실험

## 목적

v051은 수집이 완료됐지만 역할 성공은 0/240이었다. 유효한 개별 규칙 적용과 유효한 전체 증명은 다르다. v052는 실패한 실험을 성공으로 재채점하지 않는다. 같은 문제·목표에서 실제 A/D/M 기록을 제어하는지, 단지 JSON 형식을 복사하거나 기본값을 반복하는지를 나눈다.

기존 v047~v051 코드를 교체하지 않는 추가 모듈이다. 모델 다운로드·변경, 샘플링 옵션 변경, 정답 보정, 실패 후 자동 재시도는 하지 않는다.

## 실행

Python 3.12 이상, 기존 로컬 Ollama 및 `results_llm/v051_adm_01_evidence.zip`이 필요하다. 외부 Python 패키지 설치는 필요 없다. 현재 배포 시험은 Linux에서 수행했으며 Windows 실행은 사용자의 selftest로 확인한다.

ZIP의 `v052_adm_diagnostic` 폴더를 저장소 루트 아래에 둔다.

```powershell
Set-Location C:\Users\sjs95\Desktop\thought-graph-simulator\v052_adm_diagnostic
powershell -NoProfile -ExecutionPolicy Bypass -File .\windows\Run-All.ps1
```

순서: selftest → prepare → run → audit → bundle. 어느 단계든 실패하면 중단한다. 파일을 덮어쓰지 않는다. 이전 시도 자료는 삭제하지 말고 다른 실행명을 사용한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\windows\Run-All.ps1 -RunName v052_adm_02
```

수동 실행:

```powershell
python -m adm_diagnostic_v052 selftest
python -m adm_diagnostic_v052 prepare --baseline-bundle ..\results_llm\v051_adm_01_evidence.zip --out ..\experiments_v052\v052_adm_01.plan.json
python -m adm_diagnostic_v052 run --plan ..\experiments_v052\v052_adm_01.plan.json --out ..\results_llm\v052_adm_01
python -m adm_diagnostic_v052 audit --plan ..\experiments_v052\v052_adm_01.plan.json --run ..\results_llm\v052_adm_01
python -m adm_diagnostic_v052 bundle --plan ..\experiments_v052\v052_adm_01.plan.json --run ..\results_llm\v052_adm_01 --out ..\results_llm\v052_adm_01_evidence.zip
```

prepare는 첨부 기준선을 재감사하고 계획만 고정한다. 네트워크/LLM 호출은 run에서만 한다. 모델 digest·서버 설정이 기존과 다르면 같은 조건으로 간주하지 않고 중단한다.

## 호출 구성: 440회

| 과제 | 호출 | 논문 핵심 가설의 직접 분모 |
|---|---:|---|
| v051 요청 그대로 재실행 | 120 | 구현 대응 대조 |
| 명시적 형식의 A 2 × D 2 × M 3, 두 문제 | 240 | **포함** |
| 같은 형식의 중립 대조 | 20 | 별도 중립 비교 |
| 정답을 제공한 JSON 복사 | 20 | **제외** |
| D만 요청하는 그래프 생성 | 40 | **제외: 구성요소 진단** |

모든 기존 seed 10개를 사용하고 이번에는 요청별 한 번만 실행한다. 새 실행의 반복 안정성은 추정하지 않는다. 같은 seed라도 서로 다른 요청은 서로 다른 조건이다.

## 무엇이 바뀌었는가

명시적 arm은 `final`을 `final_node_id`로 바꾸고, 동적 키를 쓰던 `views`와 `binding`을 `node_views`와 `bindings` 배열로 바꾼다. 노드를 먼저 선언하고 참조 필드를 뒤에 둔다. 대안 경로를 모두 나열하지 말고 하나를 선택하도록 계약을 명확히 한다.

이 변경은 필드명·직렬화·설명 명확화의 **묶음 대조**다. 결과가 개선돼도 어느 한 요소가 단독 원인이라고 단정하지 않는다. legacy arm은 이전 요청 바이트와 동일하게 유지한다.

배열을 기존 의미 구조로 투영하는 어댑터는 값·부모·최종 참조를 고치지 않는다. 중복 참조도 제거하지 않고 거부한다. 정답 증명을 모델 입력에 주는 것은 `copy_control`뿐이다.

## 결과 파일

`results_llm/v052_adm_01/summary.ko.md`는 핵심 가설, 중립 비교, 진단 결과를 나눠 보여 준다. 성공/실패/미측정을 분리한다. 전체 재검증용 파일은 `results_llm/v052_adm_01_evidence.zip`이다.

`summary.json`에는 모든 배정의 측정값·요청 상태·토큰·지연·대응 대조가 들어 있다. 복사 성공 20건은 본 가설 성공률에 들어가지 않는다. 중립 출력 하나를 12역할로 다시 평가하는 것은 12번의 새로운 추론이 아니다.

## 문서

- `docs/PROTOCOL.ko.md`: 사전 고정 실험 계약과 결과별 해석
- `docs/PAPER_CORE_MAPPING.ko.md`: 논문 핵심과 구현·반증 가능성의 대응
- `docs/REVIEW_AND_CHANGES.ko.md`: 다각도 심사와 실제 변경/시험 범위
- `validation/VALIDATION.ko.md`: 최종 실행 검증 결과
- `tools/independent_verify.py`: 생산 채점기를 import하지 않는 별도 원문 검사기

이 실험은 외부 생성 기록의 제어를 평가한다. 내부 hidden state, 범용 사고 차원, 모델 크기별 계산량 우월성은 측정하지 않는다.

## r2: 추론 0회 중단 진단 보강

`0.5.2-r2`는 실험 조건·요청·채점 기준을 바꾸지 않고 실행 실패의 위치를 명시한다. r1에서는 `run`이 첫 추론 전에 중단돼도 CLI가 `inference_calls: 0`만 표시하고 `status.json` 안의 실제 오류를 화면에 보여주지 않았다.

r2는 미완료 실행에서 다음을 함께 출력·보존한다.

- `failure_stage`: `preflight_metadata`, `preflight_identity`, `inference` 등 실제 중단 단계
- `failure_kind`: `runtime_metadata_error`, `runtime_identity_error`, `transport_error` 등 실행계층 분류
- `failure_slot_id`: 추론 중 실패한 경우 해당 슬롯 ID
- `run_error`: 원래 예외 메시지

자동 재시도, Ollama 자동 시작, 모델 자동 교체, identity 우회, 오답 보정은 추가하지 않았다. 따라서 실행환경이 기준선과 다르면 여전히 Exit 3으로 중단한다.

기존 r1의 `v052_adm_01` 실패 자료는 삭제하거나 덮어쓰지 않는다. r2의 기본 RunName은 `v052_adm_02`다. 기존 r1 plan은 source fingerprint가 다르므로 재사용하지 않고 r2에서 새 plan을 생성한다.

대표적인 판독:

- `preflight_metadata / runtime_metadata_error / Connection refused`: Ollama endpoint에 연결하지 못함. Ollama가 실행 중인지 먼저 확인한다.
- `preflight_identity / runtime_identity_error`: 서버는 응답했지만 모델 digest, `/api/show` 정보 또는 Ollama 서버 버전이 기준선과 다름. 이 검사를 우회하지 않는다.
- `inference / transport_error`: preflight는 통과했지만 실제 `/api/chat` 호출 중 통신 오류가 발생함. 원문을 보존하고 자동 재시도하지 않는다.

Windows에서 실행 전 확인 예시는 다음과 같다.

```powershell
ollama list
Invoke-RestMethod http://127.0.0.1:11434/api/version
```

그 뒤 패치본 폴더에서 그대로 실행한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\windows\Run-All.ps1
```
