# v091 구현 변경 경계

## 보존

frozen090 아래178파일은 v090 실제 evidence/source와 바이트 단위로 보존한다. design091은 원형/재명명/신규의 현재problem과논리ID view만 만든 뒤 보존된 design090.request_for를 호출한다. 기존모델지시문·schema·ID지원·sampling·직접전제검증·D재계산은바꾸지않는다. 대규모 엔진리팩터링은하지않는다.

## 추가 파일

- build_corpus091.py / topology091.py: 모델 없는 문제 생성, canonical topology 및 역재명명.
- audit_corpus091.py: 생산 canonical 구현을 import하지 않는 독립 동형성·D/W·변환·배정 검사.
- data/corpus.json / protocol.json / protocol_v090_snapshot.json: 사전선정 문제와 배정, 보존계약.
- design091 / audit091: 물리슬롯과 모델논리ID를 구별한 새배정; 생산/독립 요청재구성.
- tables091 / audit_metrics091: cohort별 결과, 신규주평가, original/R1 대응. 핵심집계는 별도 계산대조.
- diagnostics091: 이전부모·조상선택·빈첫parents·해시동일성 진단. 채점/원응답은수정하지않는다.
- tests/test_topology_trace091.py: 재명명복원, 비동형성, cohort혼입방지, 신규주평가, 진단양성/음성/무변경 검사.

## 실행 및 포맷

v091은 알려진구조/R1/신규를 한동결배치에서 수행한다. 지원변경을 섞지 않으려고 v090 renderer를그대로재사용하며 모델에 전달할논리 ID는 원형/R1에서 대응시킨다. 과거의deepcopy한모델응답을정답으로넣지않고 각자새facts부터생성한다.

3배규모의event/summary/diagnostics를보존하기 위해 번들한도512MiB,해제합계2GiB,파일120,000개,일반JSON32MiB로늘렸다. 이는 보존/검산 컨테이너 한도이며 실제 모델request byte budget·context·num_predict·HTTP응답한도는바꾸지않는다. ZIP 경로이탈/중복/심볼릭링크/의도하지않은추가파일은계속거부한다.

독립 verifier는 요청과의미판정은 별도 구현,group/pair/bundle/주평가/재명명핵심집계는 audit_metrics091에서별도검사한다. 한국어출력과diagnostics 일부코드는공유한다. 공유를숨기지않고 independent receipt에기록한다. 내부번들일관성검산은외부실행인증이아니다.

PowerShell템플릿은 Python발견/내장ZIP해시/압축해제/전용manifest설치/UTF-8/오류보존 흐름을유지한다. --all-tests는호환인자이며기본도전체자체시험을수행한다. 네이티브Windows시험수행여부는검증영수증에별도로기록한다.
