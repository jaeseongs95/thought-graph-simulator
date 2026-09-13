# v061 K01 지시 방향 민감도

무결성: True / 완료: True / 호출: 40/40 / 출처: live_source_artifacts

10개 seed 블록에서 각 조건을 두 번 관측한다. 40호출은 독립 문제 40개가 아니다.
선택 규칙의 implied_depth는 실제 생성 증명의 D가 아니다. 선택 ID·위치·terminal 순위·goal 도달성·shallow 선택·방향별 지시 이행을 분리한다.
두 조건의 rules는 모두 [k03,k17,k10]이다. shallow/deep 지시 한 단어만 바뀌므로 이 배열의 좁은 지시 민감도만 검사한다.
사전 판정은 k03/k17=direction-sensitive, k03/k03=first-terminal 또는 fixed-shallow, k17/k17=fixed-deep, k17/k03=역방향이며 기타·누락·반복 불일치는 별도 패턴이다.

|조건|관측|형식 유효|goal 도달 선택|shallow 선택|지시 이행|미측정|
|---|---:|---:|---:|---:|---:|---:|
|shallow|20/20|20|20|20|20|0|
|deep|20/20|20|20|20|0|0|

선택 위치 shallow: {'0': 20} / terminal 순위: {'0': 20}

선택 위치 deep: {'0': 20} / terminal 순위: {'0': 20}

seed별 평균 B−A: -1.0
조건 간 선택 ID 변화: 0/20 대응 비교
양쪽 지시 이행과 ID 변화 동시 충족: 0/20 대응 비교
B−A만으로 양쪽 이행과 양쪽 불이행을 구분할 수 없으므로 paired outcome과 ID 변화를 함께 본다.
위 20개 비교는 seed 10개에 중첩된다. 조건별 반복 불일치와 sequence/period/직전 조건/반복 간격별 표는 summary.json에서 함께 확인한다.
미완료이거나 해당 비교에 미측정이 있으면 전체 비율은 null이다. metadata는 캐시 초기화가 아니며 첫 호출도 과거 이력을 가질 수 있다.

계획 SHA-256: 0af48276d0ff65b3bbccc5d4f1967fe6738c430110b7e62cae98a8a6c36302bc
event tip: 5d9e5c0aecee016c4869de0a52ae876c2c270994cf0914ca601375ca41d25e08
