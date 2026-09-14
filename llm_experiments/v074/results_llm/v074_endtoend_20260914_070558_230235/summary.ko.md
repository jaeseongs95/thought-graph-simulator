# v074 후보 선택 → 증명 생성 종단 결과

증거 구분: **live** / 실행 상태: **complete**

관측 추론: 178 / 최대 214. 조건부 생략: {'outside_selected_route': 36}

|항목|성공|측정|배정|미측정|
|---|---:|---:|---:|---:|
|모델 경로 선택|20|24|24|0|
|선택 경로 구성 충실성|8|24|24|0|
|유효한 목표 D 구조|8|24|24|0|
|선택부터 종단까지|8|24|24|0|
|양방향 종단 쌍|3|12|12|0|
|별도 참조 구성 대조|3|12|12|0|

전체 공학적 기준: False / 결정: `close_batch_control_contract_not_ready`

참조 대조는 실험자가 경로를 지정했다. 모델의 경로 선택 성공에 합산하지 않는다.
graph가 목표 D를 충족해도 선택 또는 앞 단계가 틀렸으면 종단 trace 성공이 아니다.
정확한 깊이 숫자를 출력하는 과제는 없다. 출력 graph D만 재측정한다.
현재 배치는 3개 개발 문제의 고정 후보 6개다. A/M, 내부 상태, 독립 holdout, 비용 우월성은 측정하지 않았다.
한 배치로 종료한다. 미측정/실패를 자동 재시도하거나 문구·seed를 바꾸지 않는다.

## 원문별 종단 판정

|시행|군|문제|요구|선택|실제 D|종단/대조|
|---|---|---|---|---|---:|---|
|t000|reference|T02|shallow|route_0|None|False|
|t001|reference|T02|deep|route_1|4|True|
|t002|model|T02|shallow|route_0|1|True|
|t003|model|T02|deep|route_1|None|False|
|t004|model|T02|deep|route_0|4|True|
|t005|model|T02|shallow|route_1|1|True|
|t006|model|T02|shallow|route_1|1|True|
|t007|model|T02|deep|route_0|4|True|
|t008|model|T02|deep|route_1|4|True|
|t009|model|T02|shallow|route_0|1|True|
|t010|reference|T02|deep|route_0|4|True|
|t011|reference|T02|shallow|route_1|None|False|
|t012|reference|E01_shared_fork|shallow|route_0|1|True|
|t013|reference|E01_shared_fork|deep|route_1|None|False|
|t014|model|E01_shared_fork|shallow|route_0|None|False|
|t015|model|E01_shared_fork|deep|route_1|None|False|
|t016|model|E01_shared_fork|deep|route_0|None|False|
|t017|model|E01_shared_fork|shallow|route_1|1|True|
|t018|model|E01_shared_fork|shallow|route_1|None|False|
|t019|model|E01_shared_fork|deep|route_0|None|False|
|t020|model|E01_shared_fork|deep|route_1|None|False|
|t021|model|E01_shared_fork|shallow|route_0|None|False|
|t022|reference|E01_shared_fork|deep|route_0|None|False|
|t023|reference|E01_shared_fork|shallow|route_1|None|False|
|t024|reference|E02_two_vs_four|shallow|route_0|None|False|
|t025|reference|E02_two_vs_four|deep|route_1|None|False|
|t026|model|E02_two_vs_four|shallow|route_0|None|False|
|t027|model|E02_two_vs_four|deep|route_0|None|False|
|t028|model|E02_two_vs_four|deep|route_1|None|False|
|t029|model|E02_two_vs_four|shallow|route_1|None|False|
|t030|model|E02_two_vs_four|shallow|route_1|None|False|
|t031|model|E02_two_vs_four|deep|route_1|None|False|
|t032|model|E02_two_vs_four|deep|route_0|None|False|
|t033|model|E02_two_vs_four|shallow|route_0|None|False|
|t034|reference|E02_two_vs_four|deep|route_0|None|False|
|t035|reference|E02_two_vs_four|shallow|route_1|None|False|
