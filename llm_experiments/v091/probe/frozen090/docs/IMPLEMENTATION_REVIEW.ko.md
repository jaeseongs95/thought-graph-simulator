# v090 구현 검토 기록

## 연구 설계

이 버전은 v089에서 선택된 의미 ID 후보를 새 facts부터 평가하는 별도의 사전 계약이다. 기존 8구조를 재사용한다. 신규 구조 일반화나 생성기 승격은 이 소스를 작성하는 시점에 판단하지 않는다.

baseline 요청은 v089 실제 baseline에서 1,072건을 대조하도록 시험했다. baseline 이외 세 군은 동일 수준의 ID 지원을 받고 부모는 자유롭게 출력한다. ID 지원이 없는 baseline과의 차이는 전체 절차 효과이며, 의미 ID만의 차이는 short_uniform과의 보조 비교로 분리한다.

## 응답 보존 및 채점

새 facts가 틀려도 과거의 정답 facts로 바꾸지 않는다. facts ID가 예정된 다음 규칙 ID와 충돌해도 규칙 ID를 새 번호로 변경하지 않는다. 모델 원문의 공백을 포함한 content를 그대로 history에 보낸다.

facts 의미, facts ID 계약, 현재 규칙 ID 계약, 규칙 전제 multiset, 전체 graph·goal ancestry·D, 비교→조회→생성 전체 성공을 별도 필드로 둔다. 의미적으로 유효한 graph라도 해당 군의 사전 ID 계약을 어겼으면 엄격 종단 성공은 아니다. 전송·length 종료·pending은 논리 오답과 구분한다.

## 검산 독립성

생산 요청은 design090/frozen design086, 독립 요청은 audit090/frozen audit086로 재구성한다. 규칙/graph 의미 판정 구현도 각각 rows087+measure, audit_rows087+audit_graph로 분리한다. 핵심 집계는 audit_metrics090이 별도로 계산한다. 한국어 렌더링과 일부 상세 diagnostics는 공유된 코드이며 이를 독립적으로 새 구현했다고 표현하지 않는다.

## 개발 중 반례 시험의 수정

초기 개발 시험 하나는 호출 수의 최솟값을 검사할 때 가장 작은 D를 선택했다. 현재 구조에는 얕은 경로의 규칙 수가 더 많은 경우가 있어 이 기대값이 맞지 않았다. 실제 배정/생성 코드를 바꾸지 않고, 해당 반례 시험을 공개된 후보 rule_count의 최솟값/최댓값을 선택하도록 수정했다. 수정 후 3,392~3,648회의 호출 범위를 검증한다. D와 규칙 수를 동일시하지 않는다.

## 설치·runtime

v090 전용 manifest를 먼저 확인하고, 전용 manifest가 잘못됐으면 무관한 상위 manifest로 우회하지 않는다. 임의로 수정된 소스와 기존 결과를 덮어쓰지 않는다. 시작 guard·record·dispatch·response·hash chain을 보존하며, 오류가 난 뒤 새 이름으로 자동 재실행하지 않는다. CheckOnly는 metadata 조회도 하지 않는다.

검증 결과 숫자와 환경 한계는 배포 묶음의 VALIDATION_RESULT_v090.json에 별도 기록한다. 합성 시험을 실제 모델 결과로 세지 않는다.
