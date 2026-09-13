# v064 직접 D 대조 결과

실행 상태: stopped / 관측 호출: 1/18 / 완결 분모: False
기록 성격(provenance): synthetic
주판정(여섯 directed 대응쌍 모두 strict·최소/최대 실제 D): 미판정

|문제|directed 쌍|strict 최소/최대 쌍|모든 directed 규칙·부모 경로 동일|
|---|---:|---:|---:|
|T02|2|None|None|
|E01_shared_fork|2|None|None|
|E02_two_vs_four|2|None|None|

neutral 조건은 진단용이며 주 성공 지표에 포함하지 않는다.
파싱·envelope 실패와 논리적 증명 실패는 별도로 기록한다. 미관측 또는 비완결 실행에서는 전체 비율을 제시하지 않는다.
T02는 개발 기준선이고 E01_shared_fork·E02_two_vs_four는 설계자가 정한 사전 미관측 구조다. 구조적 평가문제 두 개이지만 무작위 모집단이나 외부 독립 holdout은 아니다.
A와 M은 이번 D-only 대조에서 측정하지 않는다. 실제 D는 모든 노드가 유효하고 최종 조상 closure를 만족할 때만 기록한다.
