# v073 공백 × 후보 순서 인터페이스 양성 대조

상태: complete / 관측 64/64 / provenance: live
실험자가 제공한 숫자쌍 4개 × 공백 형식 2개 × 후보 순서 2개 × 방향 2개 × seed 2개다.
값·지시·모델·출력 스키마·생성 옵션은 고정했다. 비교 형식은 쉼표 뒤 공백 한 글자만 다르다.
기존 v072의 응답과 점수는 변경하지 않았다. 이 검사는 깊이 계산이나 최종 graph의 D 제어를 측정하지 않는다.

|형식|후보 순서|수치 선택 성공/배정|측정|인덱스 0 / 1|
|---|---|---:|---:|---:|
|compact|작은 값 먼저|8/16|16|16 / 0|
|compact|큰 값 먼저|8/16|16|16 / 0|
|comma_space|작은 값 먼저|16/16|16|8 / 8|
|comma_space|큰 값 먼저|8/16|16|16 / 0|

## 형식별 공학적 기준
|형식|선택|양방향 비교 쌍|판정|
|---|---:|---:|---|
|compact|16/32|0/16|미달|
|comma_space|24/32|8/16|미달|

전체 선택 40/64, 양방향 쌍 8/32, 미측정 0.
인터페이스 gate: 기준 미달. 후속 결정: no_interface_qualified_close_diagnostic_branch
충족 형식: []; 새 계약 설계 시 우선 형식: None
한 형식만 통과하면 그 형식에 한정한 결과다. 양쪽 통과도 이 4개 숫자쌍·2개 seed 범위의 기준이지 보편적 능력 인증이 아니다.
통과하면 다음 작업은 종단 D 실험 설계다. 정밀한 숫자 보고를 본실험의 새로운 필수조건으로 추가하지 않는다.
실패하면 이 제한 진단을 닫는다. 형식/seed/숫자쌍 추가 탐색이나 새 모델 호출을 자동 실행하지 않는다.
미완료·파싱·스키마·생성 예산 문제는 전체 gate null로 남긴다. 미측정을 오답이나 0으로 채우지 않는다.

## 공백만 다른 요청의 짝비교
{'both_correct': 16, 'both_wrong': 8, 'compact_only': 0, 'spaced_only': 8, 'unmeasured': 0}
짝비교와 개별 성공 수는 같은 원응답의 서로 다른 집계다. 독립 실험 표본으로 중복 계산하지 않는다.

## 요청 반복 및 사용량
{'assigned_conditions_without_seed': 32, 'observed': 64, 'observed_conditions_without_seed': 32, 'unique_numeric_pairs': 4, 'unique_request_bytes': 64}
{'eval_count': 520, 'prompt_eval_cached_count': 0, 'prompt_eval_count': 14752, 'total_duration': 24089774200}
seed 반복과 같은 숫자쌍을 새로운 독립 과제로 세지 않는다. 누락된 사용량은 0으로 대체하지 않는다.

v072 결과 동결: {'depth_assigned': 20, 'depth_correct': 2, 'model_pipeline_correct': 4, 'model_pipeline_pairs': 2, 'model_selection_correct': 26, 'oracle_assigned': 40, 'oracle_correct': 20, 'oracle_pairs': 0, 'overall_gate': False}
종단 graph 생성, A/M, 모델 내부 원인, 출력 스키마의 효과는 이번 검사로 확인하지 않는다.
계획 SHA-256: b97dc2182f7120b93a87b4736e66a2b405de5bcd8a4849caa5c7584890ace8c5
