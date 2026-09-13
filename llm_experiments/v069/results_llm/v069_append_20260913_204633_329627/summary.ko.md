# v069 지정 규칙 append-only 참조 구성 검사

상태: complete / 관측 54/54 / provenance: live
정답 참조 경로와 단계별 적용 규칙을 제공한 양성 대조다. 자율 D 제어·A/M 성공이 아니다.
v068 direct 4/12, staged 8/12와 두 arm의 전체 기준선 미달 판정을 그대로 보존한다.
사실 nodes → 규칙별 node 하나 → final_node_id를 모델이 작성한다. 원응답 전달·무보정 연결만 허용한다.

|문제|참조|성공/배정|측정|strict|단계 계약|
|---|---|---:|---:|---:|---:|
|T02|reference_short|2/2|2|2|2|
|T02|reference_long|2/2|2|2|2|
|E01_shared_fork|reference_short|2/2|2|2|2|
|E01_shared_fork|reference_long|2/2|2|2|2|
|E02_two_vs_four|reference_short|2/2|2|2|2|
|E02_two_vs_four|reference_long|2/2|2|2|2|

## 전체 판정
append_only: 12/12, 미측정 0, 기준선 통과.
다음 결정: append_reference_constructor_available_stop
12/12인 경우에도 이 지정 경로·단계별 지시 계약과 이미 본 문제·seed의 구성 기준선만 확보된다.
일부 또는 전부 실패하면 이 배치는 종료한다. 문구·seed 변경, 자동 재시도나 다음 실험 자동 실행은 없다.
형식 오류·길이 종료·미실행은 논리 오답이나 D=0으로 채우지 않는다. 미완료/미측정이 있으면 전체 gate는 null이다.
v068과 동시 대조하지 않은 단일 조건 실험이다. 성공률 차이를 인과 효과·동일 비용 우월성으로 해석하지 않는다.

단계별 원응답 비용 계수: {'facts': {'prompt_eval_count': 6784, 'eval_count': 886, 'total_duration': 17044427000, 'prompt_eval_cached_count': 5665}, 'rule': {'prompt_eval_count': 29309, 'eval_count': 1448, 'total_duration': 28414384400, 'prompt_eval_cached_count': 18229}, 'final': {'prompt_eval_count': 11923, 'eval_count': 124, 'total_duration': 6039355900, 'prompt_eval_cached_count': 4825}}
계획 SHA-256: 6d247f4a6a6ada3b927a83d9ba2e381458a32a252b855b50d47b924c5db5d35e
