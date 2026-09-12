# v0.4.3 변경

기본 모델·기존 프롬프트·원샷 채점·core는 변경하지 않았다. 실제 v042 응답 8건의 전체 판정은 유지한다.

- `criterion_witness`를 누락하던 최종 패턴 집계 수정. 입력/기본 비교/최종 판정/자기 모순/평가 불가를 따로 표시.
- response content의 필드 순서를 관측값으로 저장. 이를 내부 생성 또는 사고 순서라고 해석하지 않음.
- `decision_probe`: 원본 v042 스냅샷 27개, core, 요청 wire, 응답 해시, 기존 판정을 검증한 뒤 네 기준 조건을 전부 재사용.
- `format_json`: 실제 원문 요청에서 format만 변경. 원래 검사 기준은 유지.
- `staged`: 앞선 모델의 observed/primitives만 그대로 후속 호출에 전달. 잘못된 finding을 다음 입력에서 제외하는 변경은 명시하고 원본 실패를 보존. 정답을 덮어쓰거나 중간값을 교정하지 않음.
- 틀린 원본 중간값이 있으면 최종값만 맞아도 end-to-end 성공으로 세지 않음.
- source model digest/show hash/server/core/config 고정. 실패 포함 모두 집계, 자동 재추론 없음.
- 신규 오프라인 시험 32개. 전체 204개와 자체 검사 21항목 통과. 실제 추론 효과는 미측정.

확인된 reporting 결함의 수정과 미확인 원인을 구별하는 대조 경로를 분리한다. 기존 FAIL을 새 PASS로 재해석하지 않는다.

---

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
