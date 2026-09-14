# v075 동일 선택 공유 · 초기 사실 스키마 종단 대조

증거 구분: **live** / 실행 상태: **complete**

관측 추론: 332 / 최대 404. 조건부 생략: {'outside_selected_route': 72}

공유 선택: 20/24. 두 생성기 결과를 48개 독립 선택으로 세지 않는다.

|항목|legacy 성공/배정|fact_only 성공/배정|
|---|---:|---:|
|초기 사실 단계|19/36|36/36|
|선택 경로 구성 충실성|10/24|21/24|
|유효한 목표 D 구조|10/24|17/24|
|선택부터 종단까지|10/24|17/24|
|양방향 종단 쌍|2/12|5/12|
|별도 참조 구성|4/12|9/12|

전체 공학적 기준: False / 결정: `close_batch_partial_no_automatic_followup`

legacy: 생성 기준 False, 종단 기준 False, 본실험 미측정 0, 참조 미측정 0
fact_only: 생성 기준 False, 종단 기준 False, 본실험 미측정 0, 참조 미측정 0

## 같은 선택에 대한 종단 짝비교

|둘 다 성공|legacy만 성공|fact_only만 성공|둘 다 실패|미측정|
|---:|---:|---:|---:|---:|
|10|0|7|7|0|

첫 사실 스키마만 실험 처치다. atom·id·부모 정답을 호스트가 작성하거나 원응답을 보정하지 않는다.
참조 대조는 실험자가 경로를 지정했다. 선택 성공에 합산하지 않는다.
선택 오류 뒤 생성만 맞아도 종단 성공이 아니다. 실제 graph의 D와 단계 계약을 함께 확인한다.
공유 선택과 두 생성 경로는 독립 표본이 아니다. 3개 개발 문제이며 새 구조 일반화·A/M·비용 우월성은 미측정이다.
한 배치 후 종료한다. 결과에 따라 자동 재시도·문구/공백/seed 진단을 추가하지 않는다.

## 원문별 판정

|시행|군|문제|요구|선택|초기 사실|실제 D|종단/대조|
|---|---|---|---|---|---|---:|---|
|t000_legacy|reference|T02|shallow|route_0|False|None|False|
|t000_fact_only|reference|T02|shallow|route_0|True|1|True|
|t001_fact_only|reference|T02|deep|route_1|True|4|True|
|t001_legacy|reference|T02|deep|route_1|True|4|True|
|t002_legacy|model|T02|shallow|route_0|True|1|True|
|t002_fact_only|model|T02|shallow|route_0|True|1|True|
|t003_fact_only|model|T02|deep|route_1|True|4|True|
|t003_legacy|model|T02|deep|route_1|False|None|False|
|t004_legacy|model|T02|deep|route_0|True|4|True|
|t004_fact_only|model|T02|deep|route_0|True|4|True|
|t005_fact_only|model|T02|shallow|route_1|True|1|True|
|t005_legacy|model|T02|shallow|route_1|True|1|True|
|t006_legacy|model|T02|shallow|route_1|True|1|True|
|t006_fact_only|model|T02|shallow|route_1|True|1|True|
|t007_fact_only|model|T02|deep|route_0|True|4|True|
|t007_legacy|model|T02|deep|route_0|True|4|True|
|t008_legacy|model|T02|deep|route_1|False|None|False|
|t008_fact_only|model|T02|deep|route_1|True|4|True|
|t009_fact_only|model|T02|shallow|route_0|True|1|True|
|t009_legacy|model|T02|shallow|route_0|True|1|True|
|t010_fact_only|reference|T02|deep|route_0|True|4|True|
|t010_legacy|reference|T02|deep|route_0|True|None|False|
|t011_legacy|reference|T02|shallow|route_1|False|None|False|
|t011_fact_only|reference|T02|shallow|route_1|True|1|True|
|t012_fact_only|reference|E01_shared_fork|shallow|route_0|True|1|True|
|t012_legacy|reference|E01_shared_fork|shallow|route_0|True|1|True|
|t013_legacy|reference|E01_shared_fork|deep|route_1|True|None|False|
|t013_fact_only|reference|E01_shared_fork|deep|route_1|True|None|False|
|t014_fact_only|model|E01_shared_fork|shallow|route_0|True|1|True|
|t014_legacy|model|E01_shared_fork|shallow|route_0|True|1|True|
|t015_legacy|model|E01_shared_fork|deep|route_1|True|None|False|
|t015_fact_only|model|E01_shared_fork|deep|route_1|True|None|False|
|t016_fact_only|model|E01_shared_fork|deep|route_0|True|None|False|
|t016_legacy|model|E01_shared_fork|deep|route_0|True|None|False|
|t017_legacy|model|E01_shared_fork|shallow|route_1|True|1|True|
|t017_fact_only|model|E01_shared_fork|shallow|route_1|True|1|True|
|t018_fact_only|model|E01_shared_fork|shallow|route_1|True|1|True|
|t018_legacy|model|E01_shared_fork|shallow|route_1|True|1|True|
|t019_legacy|model|E01_shared_fork|deep|route_0|True|None|False|
|t019_fact_only|model|E01_shared_fork|deep|route_0|True|None|False|
|t020_fact_only|model|E01_shared_fork|deep|route_1|True|2|True|
|t020_legacy|model|E01_shared_fork|deep|route_1|False|None|False|
|t021_legacy|model|E01_shared_fork|shallow|route_0|True|1|True|
|t021_fact_only|model|E01_shared_fork|shallow|route_0|True|1|True|
|t022_legacy|reference|E01_shared_fork|deep|route_0|True|2|True|
|t022_fact_only|reference|E01_shared_fork|deep|route_0|True|None|False|
|t023_fact_only|reference|E01_shared_fork|shallow|route_1|True|1|True|
|t023_legacy|reference|E01_shared_fork|shallow|route_1|True|1|True|
|t024_legacy|reference|E02_two_vs_four|shallow|route_0|False|None|False|
|t024_fact_only|reference|E02_two_vs_four|shallow|route_0|True|2|True|
|t025_fact_only|reference|E02_two_vs_four|deep|route_1|True|None|False|
|t025_legacy|reference|E02_two_vs_four|deep|route_1|False|None|False|
|t026_legacy|model|E02_two_vs_four|shallow|route_0|False|None|False|
|t026_fact_only|model|E02_two_vs_four|shallow|route_0|True|2|True|
|t027_fact_only|model|E02_two_vs_four|deep|route_0|True|2|False|
|t027_legacy|model|E02_two_vs_four|deep|route_0|False|None|False|
|t028_legacy|model|E02_two_vs_four|deep|route_1|False|None|False|
|t028_fact_only|model|E02_two_vs_four|deep|route_1|True|2|False|
|t029_fact_only|model|E02_two_vs_four|shallow|route_1|True|2|True|
|t029_legacy|model|E02_two_vs_four|shallow|route_1|False|None|False|
|t030_legacy|model|E02_two_vs_four|shallow|route_1|False|None|False|
|t030_fact_only|model|E02_two_vs_four|shallow|route_1|True|2|True|
|t031_fact_only|model|E02_two_vs_four|deep|route_1|True|2|False|
|t031_legacy|model|E02_two_vs_four|deep|route_1|False|None|False|
|t032_legacy|model|E02_two_vs_four|deep|route_0|False|None|False|
|t032_fact_only|model|E02_two_vs_four|deep|route_0|True|2|False|
|t033_fact_only|model|E02_two_vs_four|shallow|route_0|True|2|True|
|t033_legacy|model|E02_two_vs_four|shallow|route_0|False|None|False|
|t034_fact_only|reference|E02_two_vs_four|deep|route_0|True|4|True|
|t034_legacy|reference|E02_two_vs_four|deep|route_0|False|None|False|
|t035_legacy|reference|E02_two_vs_four|shallow|route_1|False|None|False|
|t035_fact_only|reference|E02_two_vs_four|shallow|route_1|True|2|True|
