# v070 D 지시 기반 후보 경로 선택

상태: complete / 관측 40/40 / provenance: live
v069의 지정 append-only 구성 12/12는 그대로 보존한다. 이번에는 경로 선택만 측정하며 generator를 호출하지 않는다.
두 정상 후보를 주지만 short/long 정답 라벨이나 기대 D는 모델에게 주지 않는다. shallow/deep 요구와 후보 순서를 교차한다.
C01은 규칙 개수가 같고 D가 다르다. C02는 얕은 후보의 규칙이 더 많다. 두 문제는 직접 만든 진단 대조이며 독립 holdout이 아니다.

|문제|D 요구|성공/배정|측정|유효 경로|
|---|---|---:|---:|---:|
|T02|shallow|4/4|4|4|
|T02|deep|0/4|4|4|
|E01_shared_fork|shallow|4/4|4|4|
|E01_shared_fork|deep|0/4|4|4|
|E02_two_vs_four|shallow|2/4|4|4|
|E02_two_vs_four|deep|2/4|4|4|
|C01_equal_count|shallow|2/4|4|4|
|C01_equal_count|deep|2/4|4|4|
|C02_count_reversal|shallow|2/4|4|4|
|C02_count_reversal|deep|2/4|4|4|

## 전체 판정
선택 성공 20/40, 선택적 pair 0/20, 미측정 0, gate 불통과.
다음 결정: selector_failed_preserve_ranges_close_formulation
40/40 및 20/20이어도 후보 목록 내 D 선택 기준선이다. 자유 계획 생성·전체 graph D 제어·A/M 성공으로 바꾸지 않는다.
실패/부분 성공은 원범위를 보존하고 이 선택 계약을 종료한다. 자동 재시도·seed 변경·다음 단계 자동 실행은 없다.
형식 오류·미실행·중단·길이 종료는 논리 오답 또는 D=0으로 채우지 않는다. 미완료/미측정이면 전체 gate는 null이다.
규칙 목록의 D는 입력 규칙 의존 관계에서 검산한 값이며 모델이 작성한 parent ID를 검증한 graph D가 아니다.

원응답 사용량 계수: {'prompt_eval_count': 18328, 'eval_count': 694, 'total_duration': 15837066900, 'prompt_eval_cached_count': 16382}
계획 SHA-256: 6a7ce8c31c36a9da2677299a7b36bbb1f7f8e5ef9dbbc011494b082b247aa060
