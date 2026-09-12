# v0.4.2 변경

## 반례로 확인한 수정

`component_report.py`: 같은 problem/view_scope에 여러 schema 조건이 있으면 마지막 결과로 덮어쓰던 결함 수정. 모든 조건과 비교 모호성을 보존한다. 원래 총점/causal_probe 세 조건은 바뀌지 않는다.

`task_evidence.py`: 기존 평가기와 별도로 형식 오류 경로, 원문 규칙·부모 대조, 누락 사실절과 진리값 반례, criterion 입력/기대값을 추출한다. 비정규 bindings 객체는 관측으로만 읽고 자동 수리하지 않는다.

`runner.py`, `diagnostics.py`, `report.py`: 실패 응답도 과제별 증거를 남긴다. `final_is_goal_atom`의 의미를 명시하고 실제 목표 명제 일치 수를 별도 표시한다. 기존12건의 status/error/audit 및 요청을 유지한다.

## 선택형 새 계약

`micro_probe.py`: 입력복사/문자열 대조4건, criterion 중간값4건, 전체증명/부모연결2건, 도식 사실절 지시2건. 그룹 선택으로 최소8건부터 실행한다. 전체 스키마를 메시지에 명시하고 format만 대조 가능하다. 호스트 보조 과제는 명확히 구분한다.

`compare_runs.py`: format/temperature/seed/model/server 중 허용한 변경 외 core·하네스·문제·실제 요청 차이를 검사한다. 다수결/평균으로 원인을 고르지 않는다.

## 바꾸지 않은 것

`adm_minimal.py`, 기본 모델과 샘플링, 과거 causal/통합 실험 메시지, 엄격한 수락 기준. 실패 출력을 자동 보충하는 코드, 새 모델 다운로드, 실제 LLM 추론 실행은 없다.

## 검사

신규33개 포함 총172개 오프라인 시험.21개 selfcheck. 별도 분석에서 원래12건/과거39건 재검사,1,088개 유한 core 대조,20개 출력 복사본 변경 검사. LLM 표본으로 세지 않는다.
