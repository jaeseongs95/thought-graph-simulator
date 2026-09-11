# v0.4.4 → v0.4.4.1

## 수정한 결함

Windows working tree의 `adm_minimal.py`가 CRLF이고 과거 실행 스냅샷이 LF일 때,
실제 Git 소스는 동일해도 raw SHA-256만 비교하여 `현재 core와 기록된 core가 다릅니다.`로
중단하던 provenance 결함을 수정했습니다.

- `common.py`: raw SHA-256, raw Git blob, BOM/줄바꿈 정규화 SHA-256, 정규화 Git blob을 분리.
- `decision_source.py`, `decision_probe.py`: 기록된 스냅샷의 raw 무결성은 유지하고 현재 core와의
  동일성만 정규화 Git blob으로 판정.
- `gate.py`, `diagnostics.py`, `compare_runs.py`: 같은 core 동일성 정책 적용.
- 실제 문자/공백/코드 변경은 정규화 후 blob이 달라져 계속 거부.
- `adm_minimal.py`, 모델/프롬프트/채점식은 수정하지 않음.

## 회귀검사

- LF ↔ CRLF: 동일 소스로 수락.
- UTF-8 BOM 유무: 동일 소스로 수락.
- 실제 소스 한 줄 추가: 거부.
- 사용자 로컬에서 보고된 CRLF raw SHA-256 `60b5c75d...44fad`를 재현하여
  실제 `v043_decision_01` 8건 `decision_audit` 재검사 완료.
- `factor_probe --plan-only`도 같은 CRLF core에서 통과.

---

# v0.4.3 → v0.4.4

## 바꾸지 않은 것

`adm_minimal.py`, 기존 모델/모드/샘플링, 이전 요청과 기존 응답의 채점 기준을 변경하지 않았습니다.
v043 8건은 여전히 5건 accepted, 3건 invalid_task입니다. v042 기준선의 8건도 기존 판정을 유지합니다.
소스 변경이 모델의 내부 오류를 해결했다는 결과는 없습니다.

## 확인한 누락과 보완

v043 `task_diagnostics`에는 새 `decision_stage`에 대한 의미 진단 분기가 없었습니다.
기존 `audit.details`와 총 성공 수는 이미 맞았고 generic pattern 집계에도 staged는 포함되어 있었습니다.
따라서 기존 총계가 잘못됐다고 주장하지 않습니다. 상세 증거 경로와 군별 필요조건/민감도 표를 추가합니다.

- `task_evidence.py`: 단계형의 실제 이전 출력과 현재 finding을 출처를 나누어 검사.
- `decision_table.py`: 독립 고정 진리표, 필요조건 위반, 거짓 수락, 핵심 b 대응쌍, 평가불가/반복 구분.
- `component_report.py`, `report.py`: 군별 `decision_contract_by_arm`, `decision_tables.json`, summary 추가.
- `decision_source.py`, `approved_v043.py`: 승인 소스 지문과 원문 요청/응답/채점 재검사. 스냅샷 코드는 실행하지 않음.
- `decision_audit.py`: 이전 결과를 읽기 전용으로 재검사.
- `factor_probe.py`, `runner.py`: replay/json/b_last/neutral_keys 4군 각 4입력. 선택형 temperature_zero.
- `model_integrity.py`: 실제 가중치 파일 전체 SHA-256과 기록된 blob 이름 대조. 모드·성능 검증과 분리.

## 검증

기존 204개 시험에 새 31개 시험을 추가했습니다.
각 새 대조 요청의 허용 변경, 잘못된 이전 값의 성공 차단, 정답 누출 차단, 128 출력 조합,
원문 tamper 감지, 모의 16회 API 실행과 재개 시 0회 재호출, 합성 GGUF 헤더/체크섬 등을 포함합니다.
최종 실행 횟수와 결과는 BUILD_STATUS.json 및 패키지 검증 파일을 확인하세요.
