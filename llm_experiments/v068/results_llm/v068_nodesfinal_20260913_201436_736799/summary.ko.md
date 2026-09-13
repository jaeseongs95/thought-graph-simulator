# v068 전체 graph vs nodes→final 참조 재구성 대조

상태: complete / 관측 36/36 / provenance: live
정답 규칙 경로를 제공한 양성 대조다. D 자율 제어·A/M 성공이 아니다. v067은 4/12 그대로 보존한다.
staged는 첫 모델의 nodes와 둘째 모델의 final_node_id를 그대로 결합한다. 노드/부모/ID 수정·후보 추출·사후 가지치기 없음.

|문제|참조|구조|성공/배정|측정|strict|순서 이행|
|---|---|---|---:|---:|---:|---:|
|T02|reference_short|direct|2/2|2|2|2|
|T02|reference_short|staged|2/2|2|2|2|
|T02|reference_long|direct|0/2|2|0|2|
|T02|reference_long|staged|2/2|2|2|2|
|E01_shared_fork|reference_short|direct|2/2|2|2|2|
|E01_shared_fork|reference_short|staged|0/2|2|0|0|
|E01_shared_fork|reference_long|direct|0/2|2|0|0|
|E01_shared_fork|reference_long|staged|2/2|2|2|2|
|E02_two_vs_four|reference_short|direct|0/2|2|0|2|
|E02_two_vs_four|reference_short|staged|2/2|2|2|2|
|E02_two_vs_four|reference_long|direct|0/2|2|0|0|
|E02_two_vs_four|reference_long|staged|0/2|2|0|0|

## 전체 판정
direct: 4/12, 미측정 0, 기준선 불통과.
staged: 8/12, 미측정 0, 기준선 불통과.

짝지은 결과: {'both_success': 2, 'staged_only': 6, 'direct_only': 2, 'both_failure': 2, 'unmeasured': 0}
다음 결정: partial_scope_preserved_close_diagnostic
이번 한정 진단은 이 배치에서 종료한다. 부분 성공의 문제/경로/seed 범위를 보존하고 문구 변경·새 seed로 자동 재실행하지 않는다.
미실행/파싱 실패/예산 초과를 논리 오답이나 D=0으로 채우지 않는다. 중단 배치의 전체 gate는 미판정이다.
staged는 2회 호출하므로 동일 예산 대조가 아니다. 차이는 출력 계약+호출 분리의 결과이며 JSON 키 순서나 내부 원인을 단독 입증하지 않는다.

단계별 원응답 비용 계수: {'direct': {'prompt_eval_count': 8332, 'eval_count': 2494, 'total_duration': 35263544100, 'prompt_eval_cached_count': 7016}, 'nodes': {'prompt_eval_count': 6784, 'eval_count': 2516, 'total_duration': 32936182500, 'prompt_eval_cached_count': 5748}, 'final': {'prompt_eval_count': 9249, 'eval_count': 112, 'total_duration': 4032536200, 'prompt_eval_cached_count': 4251}}
계획 SHA-256: 5a60829231d11c8bb06be661346dada4ff6aa20e38ee594c59c8ebcc12d0f8c4
