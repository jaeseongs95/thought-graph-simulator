# v078 P03 동결 계약 r1

## 범위

분석 대상은 외부 경로 선택과 무보정 단계형 graph 출력이다. 모델 내부 사고 깊이가 아니다. 입력 problem의 facts/rules/goal을 고정하고 selector의 requested_depth만 작은/큰 D로 교체한다. 고정 경로 카드 중 선택한 원응답을 그대로 생성기로 운반한다.

## 시행

본실험: H01~H04 × seed64001001/64001002 × 후보순서0/1 × shallow/deep =32. 쌍은 동일 문제/seed/후보순서의 두 요구로16개다. 각 문제/seed에서 별도 경로지정 참조2개를 추가해 참조16개, 전체 생성48개다. 후보선택32회는 각 본조건마다1회이며 참조는 선택하지 않는다. 블록 내 순서는 design.py에 동결했고 별도 audit_model.py에서 재구성한다.

## 입력·출력 계약

모델/서버/native identity와 API 기본값은 첨부 v077의 base와 동일하다. 초기 사실은 원자 수만큼의 nodes, rule=null, parents=[]인 형식을 제한한다. atom/id는 모델이 쓴다. 규칙 단계는 해당 operation의 node 하나, 종료 단계는 final_node_id 하나다. 부모 배열 길이를 정답 전제 수로 제한하지 않고 정답 ID enum도 제공하지 않는다. bindings는 사용하지 않는다.

각 history 항목의 content는 보존한 모델 message.content 문자열과 동일하다. 공백/개행/오류 중간값을 재직렬화·치환·보정하지 않는다. HTTP 응답의 시각/SHA는 evidence에만 남기며 모델 입력에 넣지 않는다. 모델의 선택이 틀려도 호스트가 정답 경로로 바꾸지 않는다. 선택 ID를 사전 후보에 매핑할 수 없으면 종속 단계는 unmappable_selection으로 건너뛰고 재질문하지 않는다.

## 판정

- selection_success: 정상 선택 응답이며 실제 선택 경로의 D가 요구한 최소/최대 D와 일치하는가.
- generator_success: 정상 단계 응답에서 초기 사실/매 단계 계약/전체 strict graph/선택 경로 순서/선택 경로의 D가 모두 맞는가.
- actual_D: 최종 goal ancestry의 사실0, 규칙1+max 전제 깊이. strict graph 불가/미측정이면 null.
- actual_goal_support_rule_count: strict graph의 goal ancestry 규칙 노드 수. D와 별도 측정하며 미측정이면 null.
- trace_success: 본실험의 selection_success, generator_success, target_structure_success가 모두 참인가. 필요한 값이 미측정이면 null.
- control_success: 실험자 경로지정 참조의 생성과 요구 D 성공. 자율 선택 성공으로 합산하지 않는다.
- pair.success: 동일 문제/seed/후보순서의 shallow/deep trace_success가 모두 참인가. 전체·문제별·규칙 수 관계별 pair 모두 이 기준이다.

논리적으로 틀린 정상 응답은 false, 생성 숫자를 측정할 수 없는 응답은 null과 구체 상태를 함께 보존한다. invalid_json/invalid_schema/length/HTTP/transport/identity/미실행을 하나의 D값으로 대체하지 않는다. summary의 성공/배정 표는 미측정을 분모에서 숨기지 않으며 실패·미측정을 별도로 제시한다.

## 예산과 중단

최대316 추론, 목표경로 전부 선택 시308. 진행332슬롯 중16은 metadata다. 한 metadata 슬롯은 version/tags/show 조회3개를 포함한다. 출력 상한은 요청당4096 토큰, 요청 bytes 상한262144다. 상한 초과 요청을 잘라 보내지 않는다. HTTP/transport/identity/생성 예산 초과는 배치 중단이다. 자동 재시도나 재개는 없다. source/plan/baseline 일치 확인 뒤 첫 모델 호출 전에 started guard를 기록하므로 guard 자체는 추론 증거가 아니다.

## 근거와 검산

evidence는 원 요청/HTTP 응답/record/event hash chain/metadata/source/plan/summary를 포함한다. 별도 verify는 동일 소스 스냅샷, 고정 일정, 조건부 skip, 요청 원문, 실제 그래프와 단계, D/규칙 수, 집계와 한글 보고를 검산한다. preflight는 생산 graph 판정으로 후보를 검사하고 audit_design은 별도 역방향 의존 탐색으로 검사한다. 이들 소프트웨어 검증은 모델의 실험 성공이나 신규 독립 표본이 아니다.
