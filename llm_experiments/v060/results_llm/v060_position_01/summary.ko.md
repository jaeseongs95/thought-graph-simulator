# v060 K01 terminal 위치 진단

무결성: True / 완료: True / 호출: 40/40 / 출처: live_source_artifacts

10개 seed 블록에서 각 조건을 두 번 관측한다. 40호출은 독립 문제 40개가 아니다.
선택 규칙의 implied_depth는 실제 생성 증명의 D가 아니다. 선택 ID·전체 위치·terminal 순위·goal 도달성·shallow 지시 이행을 분리한다.
두 배열은 first-terminal과 absolute-second 가설에 반대 예측을 주지만 k10 후치, 캐시와 더 넓은 위치 기제는 식별하지 못한다.

|조건|관측|형식 유효|goal 도달 선택|지시 이행|미측정|
|---|---:|---:|---:|---:|---:|
|deep_first|20/20|20|20|0|0|
|shallow_first|20/20|20|20|20|0|

선택 위치 deep_first: {'0': 20} / terminal 순위: {'0': 20}

선택 위치 shallow_first: {'0': 20} / terminal 순위: {'0': 20}

seed별 평균 B−A: 1.0
조건 간 선택 ID 변화: 20/20 대응 비교
위 20개 비교는 seed 10개에 중첩된다. 조건별 반복 불일치와 sequence/period/직전 조건/반복 간격별 표는 summary.json에서 함께 확인한다.
미완료이거나 해당 비교에 미측정이 있으면 전체 비율은 null이다. metadata는 캐시 초기화가 아니며 첫 호출도 과거 이력을 가질 수 있다.

계획 SHA-256: 2174a90657dd37cc2574fd56484e65119e5b353f9831888c699554f7aea81259
event tip: 9308c64e80b97247b17fe9ff420ff9a02b5e03c85b97d72765bb5dcb08a92fad
