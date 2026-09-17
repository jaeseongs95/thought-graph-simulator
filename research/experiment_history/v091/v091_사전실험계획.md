# v091 사전 계획 — 신규 구조 일반화와 표면형 민감성의 분리

작성일: 2026-09-16 KST. 이 문서는 실험 실행 전 동결되는 계획이다. 실제 모델 결과를 보고 적격 구조나 주평가를 선택하지 않았다.

## 1. 연구 질문과 범위

v090에서 새 선택·새 facts 종단의 의미 ID 효과가 관측되었다. 이 버전은 생성 절차를 더 고치지 않고 다음을 구분한다.

(1) 기존 생성기 대비 의미 ID의 효과가 새 proof topology에서도 관측되는가?
(2) 동일한 topology를 일관되게 재명명하면 성과와 실패 유형이 얼마나 달라지는가?
(3) 실패한 직접 전제 연결에서 이전 parents와의 일치, 필요한 전제의 조상 선택, 첫 규칙의 빈 parents가 관측되는가?

첫 질문만 주평가다. 두 번째는 표면형 민감성의 대응 평가, 세 번째는 관측 진단이며 내부 복사·attention 기제를 입증하는 개입 실험이 아니다. 정확한 외부 D를 사용하는 선택과 공개된 규칙을 실행하는 기존 지원 범위를 유지한다. D는 실제 최종 proof DAG의 inferential dependency depth이고 hidden-state 깊이가 아니다.

## 2. 동결 환경과 네 생성군

Ollama0.34.1, qwen3:4b-instruct, digest `0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0`.
seed64001001·64001002, temperature0.7, top_p0.8, top_k20, min_p0.0, repeat_penalty1, num_ctx8192, num_predict4096. protocol_v090_snapshot와 identity·headers·schemas·allocation·sampling을 직접 대조한다.

baseline은 자유 ID, short_uniform은 n0001계열, atom_alias는 ID=atom, atom_tagged는 node_+atom이다. 세 지정군은 동일한 형식의 facts ID 표와 현재 규칙 ID 지정을 받는다. 현재 결론·규칙·부모·final을 모델이 출력하며 정답 부모 목록을 추가하지 않는다. 동일한 원자가 다시 도출되지 않는 reference path 범위를 유지한다.

## 3. 문제은행 생성과 신규성 검사

`build_corpus091.py`의 생성seed9101601과 재명명seed9101602를 고정한다. 모델은 호출하지 않는다. 각 기존 U문제의 shallow/deep별 D와 규칙수 W를 맞춘 새 경로를 만든다. facts3개, 전제1~3개, 선행 노드만 참조, 모든 규칙 노드가 goal을 지지, 경로 내 원자 유일성, 모든 초기 사실의 사용을 검사한다. 규칙마다 전제 수를 기존과 똑같이 맞추지는 않는다. 새 구조의 전제 결합·분기 패턴은 달라지는 대상이다.

사전 순서에서 위 조건과 비동형성 조건을 처음 충족한 후보를 채택한다. 후보별 탐색 상한200,000회이며, 결과를 보고 후보를 버리거나 재생성하지 않는다. 두 경로는 facts와goal만 공유하고 내부 도출 원자는 분리한다. 제시 규칙순서는 동결난수로 배정한다. V01~V08은 대응U문제와 D쌍·W쌍을 같게 유지하며 최대D5,최대규칙5다.

보존된 v090 source 및 그 안의 읽을 수 있는 protocol/reference_plans(최대5규칙)를 재귀 조회해 과거39개 고유 경로 topology 은행을 구성한다. 새16경로는 그39개 및 서로 간 모두 비동형이다. 생산 정규형은 facts·추론·goal의 색을 구분한 전단사 정규화, 독립 검사기는 색·차수 후보와 간선 보존 backtracking을 사용한다. 새 경로 대 과거 및 새 경로 상호 비교744회를 수행한다. 이 범위는 보존 자료의 구조 비중복 검사이며 모델 사전학습에서의 미노출을 뜻하지 않는다.

## 4. 원형과 R1 재명명

U01~U08 각각에 사전 고정 R1 한 개를 만든다. 원자명·규칙명은 각각 전단사로 바꾸되 기존 prefix와문자길이(문자1+숫자2)는 유지하고 기존 이름과 겹치지 않게 한다. facts순서·규칙제시순서·각premise순서·goal관계·D·W를 보존한다. 역변환이 원문 problem과 reference path를 정확히 복원하는지 검사한다.

R1은 신규 topology가 아니다. 이름을 한 종류씩만 바꾼 순수 원자명 효과나 토큰화 단독 효과도 아니다. 모델 학습/토큰 경계는 통제하지 않았으며, 한 R1에서의 효과를 임의 재명명 분포 전체로 일반화하지 않는다.

## 5. 배정과 모델 입력 경계

기존16개 구조×seed block 순서를 유지하고, 각 기존unit 위치에서 원형·R1·신규 cohort를 순환 배치한다. 네 arm순서는 block과기존unit에 따라 순환하며, 대응 cohort는 같은 arm rank를 가진다. 2seed·4표시·2방향은 v090과 같다. 전체 각 cohort512graph,128공유선택,256pair,64bundle이며 각군/cohort는128graph·64pair·16bundle이다.

물리 실행 ID에는 o_/r_/n_ prefix로 서로 다른 호출·로그를 구분한다. 모델 입력의 원형과 R1에는 동일한 v090 논리 unit/source ID 및 Uproblem ID를 쓴다. 원자명·규칙명 처치에 추적용 ID 차이가 추가되지 않도록 한 사전 배정이다. 새 V에는 별도 논리 h계열을 쓴다. execution_id,topology_id,renaming_id,presentation_id,sampling_seed,replicate_id는 감사 자료에서만 구분하며 새로운 지시문으로 주입하지 않는다.

원형의 모델 요청은 이전 원응답을 회귀 입력으로 넣을 때 v090 실제3,520요청과 byte-identical이어야 한다. 실제 새 실험에서는 새선택·새facts를 생성한다. 과거 응답을 복사해 결과를 만드는 것이 아니다. 실행 순서·시점은 v090과 다르므로 새 모델 응답이 반드시 동일하다고 가정하지 않는다.

## 6. 주평가·보조평가·미관측

주평가 = new_topology의 각 V구조에서 `(alias 양방향 성공률 − baseline 양방향 성공률)`을 계산한 뒤8구조 동일가중. 각 구조·군에는2seed×4표시=8pair가 있다. 양방향은 동일구조·seed·표시에서 shallow와deep이 모두 엄격종단성공해야 한다. 주평가만을 위해 알려진구조나 R1을 합산하지 않는다.

tagged−baseline,short−baseline,alias−short,tagged−short,tagged−alias는 사전보조대조다. known_original/known_renamed에서도 각각 같은 지표를 기술하되 신규주효과를 대체하지 않는다. R1−original의 군별 대응차이·획득/소실·최초오류전이도 별도 보고한다. baseline 대비는 지원 포함 절차효과, short대비는 같은지원에서 명명계약 대조다.

공유선택·facts의미·facts ID계약·graph의미·전체지원계약·D·종단·pair·네표시bundle을 구분한다. HTTP오류/JSON오류/길이종료/identity오류/미실행/조건부skip/중단을 논리오답과 구분한다. 불완전배치에서 주평가를 완전관측값처럼 계산하지 않는다. 같은원응답의 반복검산·표시·seed는 독립문제 수가 아니다. 사전선정한8개 신규구조의 기술적 비교이며 IID모집단 p값을 주장하지 않는다.

## 7. 추가 진단

`parents_equal_previous_rule`, `parents_equal_any_prior_rule`, `current_rule_correct_but_parents_stale`, `wrong_parents_are_ancestors_of_required_parent`, `first_rule_empty_after_facts`를 기록한다. 배열 일치만으로 실패라고 하지 않는다. 현재 규칙의 직접전제에 맞지 않는 parents일 때만 오류재사용 플래그를 세며, duplicate ID같은 다른이유로 실패했지만 parents는 맞으면 stale오류로 분류하지 않는다.

각 flag는 누적관측과 직전까지 유효했던 prefix에서의 관측을 분리한다. 한graph의 최초실패와이후오류를 더해 새실패graph 수를 만들지 않는다. 조상선택과이전배열일치는 동시에 성립할수있으며 원인기제의 단독식별로 보고하지 않는다. 기존 graph·D 채점기는 바꾸지 않는다.

원래 wire_request_sha256과 source ID만 정규화한 감사용해시를 함께 기록한다. 정규화는 비교용 사본에만 적용하고 모델이 쓴 content공백·표현이나실제history는 수정하지 않는다. 동일wire와다른실행·동일topology와다른표면형을구분한다.

## 8. 이번에 하지 않는 변경

history 순서 개입, 추적용 metadata 제거/고정 ablation, 새프롬프트 강화, 부모 자동복구, 문제별arm분기, alias/tagged 이중실행후정답선택,중복원자 허용은 하지 않는다. 이들은 별도 사전계약이 필요한 후속실험이다. 이번 주생성기를 몰래 고치거나 알려진 U03/U07만 통과하도록 규칙을 추가하지 않는다.

## 9. 실패 보존과 검증

새 버전 전용 manifest/guard 및 고유run이름을 사용한다. 중단실행을 삭제하거나 새이름으로자동재시도하지 않는다. 원문·해시·기준선·모델identity·source snapshot을 보존한다. 배포검증은 최종ZIP설치본에서 자체시험/calibration/CheckOnly/전체합성실행/독립검산으로 수행하고 실제수치는 배포외부 검증영수증에 남긴다. 합성성공은 모델연구결과가 아니다.
