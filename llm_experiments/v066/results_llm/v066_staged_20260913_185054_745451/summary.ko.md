# v066 직접 생성 대 모델 원계획 전달 비교

실행 상태: complete / 관측 호출: 36/36 / provenance: live
이전 v065의 지정 규칙 단일 호출 분기는 종료했다. 이번에는 정답 규칙을 알려주지 않는 다른 실행 구조를 비교한다.
staged 성공에는 모델의 계획이 유효·요구 깊이 이행, 원계획 그대로 전달, 그래프 규칙 순서 일치, 전체 strict 증명·요구 D 이행이 모두 필요하다.

|방식|호출 관측/배정|최종 strict 증명|최종 D만 일치|종단 이행|선택적 D쌍|6쌍 진입 기준|
|---|---:|---:|---:|---:|---:|---|
|direct|12/12|4|2|2|0/6|False|
|staged|24/24|0|0|0|0/6|False|

## 계획과 최종 증명의 분리
계획 관측 12/12, 유효 경로 계획 0, 방향 이행 0.
planned_D는 규칙 목록의 사후 진단값이다. actual_D는 모델이 작성한 최종 유효 DAG에서만 계산한다. 잘못된 계획 뒤의 우연한 정답은 종단 성공이 아니다.

|문제|seed|방식|방향|계획 방향 성공|최종 그래프 방향 성공|계획 준수|종단 성공|실제 D|
|---|---:|---|---|---|---|---|---|---:|
|T02|64001001|direct|shallow|None|True|None|True|1|
|T02|64001001|direct|deep|None|False|None|False|1|
|T02|64001001|staged|shallow|False|False|False|False|None|
|T02|64001001|staged|deep|False|False|True|False|None|
|T02|64001002|direct|shallow|None|True|None|True|1|
|T02|64001002|direct|deep|None|False|None|False|1|
|T02|64001002|staged|shallow|False|False|True|False|None|
|T02|64001002|staged|deep|False|False|False|False|None|
|E01_shared_fork|64001001|direct|shallow|None|False|None|False|None|
|E01_shared_fork|64001001|direct|deep|None|False|None|False|None|
|E01_shared_fork|64001001|staged|shallow|False|False|True|False|None|
|E01_shared_fork|64001001|staged|deep|False|False|True|False|None|
|E01_shared_fork|64001002|direct|shallow|None|False|None|False|None|
|E01_shared_fork|64001002|direct|deep|None|False|None|False|None|
|E01_shared_fork|64001002|staged|shallow|False|False|True|False|None|
|E01_shared_fork|64001002|staged|deep|False|False|True|False|None|
|E02_two_vs_four|64001001|direct|shallow|None|False|None|False|None|
|E02_two_vs_four|64001001|direct|deep|None|False|None|False|None|
|E02_two_vs_four|64001001|staged|shallow|False|False|False|False|None|
|E02_two_vs_four|64001001|staged|deep|False|False|True|False|None|
|E02_two_vs_four|64001002|direct|shallow|None|False|None|False|None|
|E02_two_vs_four|64001002|direct|deep|None|False|None|False|None|
|E02_two_vs_four|64001002|staged|shallow|False|False|False|False|None|
|E02_two_vs_four|64001002|staged|deep|False|False|True|False|None|

## 비용과 범위
direct는 12호출, staged는 24호출이다. 동일 계산량 비교 또는 토큰 절약 검증이 아니다. 같은 원문 재집계를 독립 표본이나 비용으로 중복 합산하지 않는다.
direct 원응답 사용량: {'prompt_eval_count': 6520, 'eval_count': 2767, 'total_duration': 39216240100, 'prompt_eval_cached_count': 5664}
staged 원응답 사용량: {'prompt_eval_count': 13748, 'eval_count': 3189, 'total_duration': 45753215100, 'prompt_eval_cached_count': 8304}

## 다음 판단
staged가 6/6쌍을 충족하면 이 제한된 외부 실행 구조의 D 기준선만 확보한다. 이전 단일 호출 실패를 취소하거나 내부 사고/A/M 성과로 확대하지 않는다.
일부만 성공하면 해당 문제와 방향 범위를 보존한다. staged 종단 성공이 없다면 이 2단계 구조도 종료하며 같은 문구 변형을 자동 반복하지 않는다.
미완료/파싱 불가이면 전체 진입 기준은 미판정이다. 모든 원응답과 중간값을 보존하고 자동 보정·자동 재시도는 하지 않는다.
계획 SHA-256: 1031d4d6af330b34c609dc83ac0789547f88bded8abde4c558b84d4e84caec49
