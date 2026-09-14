# v076 동일 선택 공유 · 부모 수 제약 종단 대조

증거 구분: **live** / 실행 상태: **complete**

관측 추론: 332 / 최대 404. 조건부 생략: {'outside_selected_route': 72}

공유 선택: 20/24. 두 생성기 결과를 48개 독립 선택으로 세지 않는다.

|항목|base 성공/배정|parent_count 성공/배정|
|---|---:|---:|
|초기 사실 단계|36/36|36/36|
|선택 경로 구성 충실성|18/24|20/24|
|유효한 목표 D 구조|14/24|16/24|
|선택부터 종단까지|14/24|16/24|
|양방향 종단 쌍|2/12|4/12|
|별도 참조 구성|10/12|7/12|
base 규칙 진단: 부모 수 77/82, 규칙 단계 73/82, 수는 맞지만 단계 실패 4건. 단계 수는 독립 문제 수가 아니다.
parent_count 규칙 진단: 부모 수 82/82, 규칙 단계 72/82, 수는 맞지만 단계 실패 10건. 단계 수는 독립 문제 수가 아니다.

전체 공학적 기준: False / 결정: `close_batch_partial_no_automatic_followup`

base: 생성 기준 False, 종단 기준 False, 본실험 미측정 0, 참조 미측정 0
parent_count: 생성 기준 False, 종단 기준 False, 본실험 미측정 0, 참조 미측정 0

## 같은 선택에 대한 종단 짝비교

|둘 다 성공|base만 성공|parent_count만 성공|둘 다 실패|미측정|
|---:|---:|---:|---:|---:|
|14|0|2|8|0|

두 군 모두 사실 전용 스키마와 content-only 이력을 사용한다. 규칙 parents 길이 제한만 짝비교한다. atom·id·부모 정답을 제공하거나 보정하지 않는다.
참조 대조는 실험자가 경로를 지정했다. 선택 성공에 합산하지 않는다.
선택 오류 뒤 생성만 맞아도 종단 성공이 아니다. 실제 graph의 D와 단계 계약을 함께 확인한다.
공유 선택과 두 생성 경로는 독립 표본이 아니다. 3개 개발 문제이며 새 구조 일반화·A/M·비용 우월성은 미측정이다.
한 배치 후 종료한다. 결과에 따라 자동 재시도·문구/공백/seed 진단을 추가하지 않는다.

## 원문별 판정

|시행|군|문제|요구|선택|초기 사실|실제 D|종단/대조|
|---|---|---|---|---|---|---:|---|
|t000_base|reference|T02|shallow|route_0|True|1|True|
|t000_parent_count|reference|T02|shallow|route_0|True|1|True|
|t001_parent_count|reference|T02|deep|route_1|True|None|False|
|t001_base|reference|T02|deep|route_1|True|None|False|
|t002_base|model|T02|shallow|route_0|True|1|True|
|t002_parent_count|model|T02|shallow|route_0|True|1|True|
|t003_parent_count|model|T02|deep|route_1|True|4|True|
|t003_base|model|T02|deep|route_1|True|4|True|
|t004_base|model|T02|deep|route_0|True|4|True|
|t004_parent_count|model|T02|deep|route_0|True|4|True|
|t005_parent_count|model|T02|shallow|route_1|True|1|True|
|t005_base|model|T02|shallow|route_1|True|1|True|
|t006_base|model|T02|shallow|route_1|True|1|True|
|t006_parent_count|model|T02|shallow|route_1|True|1|True|
|t007_parent_count|model|T02|deep|route_0|True|None|False|
|t007_base|model|T02|deep|route_0|True|None|False|
|t008_base|model|T02|deep|route_1|True|None|False|
|t008_parent_count|model|T02|deep|route_1|True|None|False|
|t009_parent_count|model|T02|shallow|route_0|True|1|True|
|t009_base|model|T02|shallow|route_0|True|1|True|
|t010_parent_count|reference|T02|deep|route_0|True|None|False|
|t010_base|reference|T02|deep|route_0|True|4|True|
|t011_base|reference|T02|shallow|route_1|True|1|True|
|t011_parent_count|reference|T02|shallow|route_1|True|1|True|
|t012_parent_count|reference|E01_shared_fork|shallow|route_0|True|1|True|
|t012_base|reference|E01_shared_fork|shallow|route_0|True|1|True|
|t013_base|reference|E01_shared_fork|deep|route_1|True|None|False|
|t013_parent_count|reference|E01_shared_fork|deep|route_1|True|None|False|
|t014_parent_count|model|E01_shared_fork|shallow|route_0|True|1|True|
|t014_base|model|E01_shared_fork|shallow|route_0|True|1|True|
|t015_base|model|E01_shared_fork|deep|route_1|True|None|False|
|t015_parent_count|model|E01_shared_fork|deep|route_1|True|None|False|
|t016_parent_count|model|E01_shared_fork|deep|route_0|True|2|True|
|t016_base|model|E01_shared_fork|deep|route_0|True|None|False|
|t017_base|model|E01_shared_fork|shallow|route_1|True|1|True|
|t017_parent_count|model|E01_shared_fork|shallow|route_1|True|1|True|
|t018_parent_count|model|E01_shared_fork|shallow|route_1|True|1|True|
|t018_base|model|E01_shared_fork|shallow|route_1|True|1|True|
|t019_base|model|E01_shared_fork|deep|route_0|True|None|False|
|t019_parent_count|model|E01_shared_fork|deep|route_0|True|None|False|
|t020_parent_count|model|E01_shared_fork|deep|route_1|True|2|True|
|t020_base|model|E01_shared_fork|deep|route_1|True|None|False|
|t021_base|model|E01_shared_fork|shallow|route_0|True|1|True|
|t021_parent_count|model|E01_shared_fork|shallow|route_0|True|1|True|
|t022_base|reference|E01_shared_fork|deep|route_0|True|2|True|
|t022_parent_count|reference|E01_shared_fork|deep|route_0|True|None|False|
|t023_parent_count|reference|E01_shared_fork|shallow|route_1|True|1|True|
|t023_base|reference|E01_shared_fork|shallow|route_1|True|1|True|
|t024_base|reference|E02_two_vs_four|shallow|route_0|True|2|True|
|t024_parent_count|reference|E02_two_vs_four|shallow|route_0|True|2|True|
|t025_parent_count|reference|E02_two_vs_four|deep|route_1|True|None|False|
|t025_base|reference|E02_two_vs_four|deep|route_1|True|4|True|
|t026_base|model|E02_two_vs_four|shallow|route_0|True|2|True|
|t026_parent_count|model|E02_two_vs_four|shallow|route_0|True|2|True|
|t027_parent_count|model|E02_two_vs_four|deep|route_0|True|2|False|
|t027_base|model|E02_two_vs_four|deep|route_0|True|2|False|
|t028_base|model|E02_two_vs_four|deep|route_1|True|2|False|
|t028_parent_count|model|E02_two_vs_four|deep|route_1|True|2|False|
|t029_parent_count|model|E02_two_vs_four|shallow|route_1|True|2|True|
|t029_base|model|E02_two_vs_four|shallow|route_1|True|2|True|
|t030_base|model|E02_two_vs_four|shallow|route_1|True|2|True|
|t030_parent_count|model|E02_two_vs_four|shallow|route_1|True|2|True|
|t031_parent_count|model|E02_two_vs_four|deep|route_1|True|2|False|
|t031_base|model|E02_two_vs_four|deep|route_1|True|2|False|
|t032_base|model|E02_two_vs_four|deep|route_0|True|2|False|
|t032_parent_count|model|E02_two_vs_four|deep|route_0|True|2|False|
|t033_parent_count|model|E02_two_vs_four|shallow|route_0|True|2|True|
|t033_base|model|E02_two_vs_four|shallow|route_0|True|2|True|
|t034_parent_count|reference|E02_two_vs_four|deep|route_0|True|4|True|
|t034_base|reference|E02_two_vs_four|deep|route_0|True|4|True|
|t035_base|reference|E02_two_vs_four|shallow|route_1|True|2|True|
|t035_parent_count|reference|E02_two_vs_four|shallow|route_1|True|2|True|
