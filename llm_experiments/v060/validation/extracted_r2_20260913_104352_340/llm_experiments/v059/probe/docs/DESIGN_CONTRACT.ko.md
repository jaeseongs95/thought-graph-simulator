# v059 구현 계약

목표는 Gemma K01 choice의 규칙 배열 순열에 대한 탐색적 민감도를 조사하는 것이다. 기존 증거는 수정하지 않는다.

- 입력: v058_order_02_evidence.zip 전체를 설치된 v058 생산 감사기와 독립 계산기로 다시 검산한다. 동봉 source_snapshot을 실행하지 않는다.
- 대상: candidate(gemma3:4b), K01/original/shallow/choice, 기존 10개 seed 전체. v058 graph_choice의 choice 요청을 seed마다 하나 선택하고, 반대 sequence의 요청 바이트가 동일한지 확인한다. 과거 응답은 새 결과로 합산하지 않는다.
- A=original [k10,k17,k03], B=terminal_swap [k10,k03,k17]. rules 배열 외 요청 바이트는 그대로 유지한다. facts, goal, rule 내용과 ID, 문구, schema, 옵션, seed, 모델 identity 고정. 요청 생성기는 채점기/정답을 import하지 않는다.
- seed당 4회, 10블록, 총 40 inference. ABBA/BAAB를 각 5블록에 배정한다. schedule_seed=5902026으로 블록 순서와 5:5 배정을 결과 전에 고정한다. 최초 조건 반복을 repeat=0, 두번째를 repeat=1로 표시한다.
- 각 블록 전후 metadata 20개. metadata는 캐시 초기화가 아니다. 직전 호출 ID/조건, 절대 위치, block 내 period, repeat와 원문 시간/cache/종료 필드 보존.
- 형식, choice_valid, selected_rule_id, selected_rule_position(0기준), implied_depth, shallow_success를 분리한다. actual_D, proof_valid, strict_valid는 null이다. 선택 실패를 호스트가 교정하지 않는다.
- seed별 A0/B0, A1/B1 비교와 A0/A1, B0/B1 반복 비교를 따로 기록한다. seed 10개를 분석 단위로 삼는다. 교차조건 변화가 있어도 순수 위치 인과효과, cache나 내부 heuristic은 확정하지 않는다.
- 미실행·파싱불가·측정불가는 null. 알려지지 않은 rule ID는 형식성공/choice실패로 기록. 정상 HTTP의 잘못된 payload는 기록 후 진행, transport/identity 오류는 즉시 중단. retry/resume/download 없음.
- 계획, 요청, 원문, 사건 해시체인, metadata, 소스 snapshot, 상태, summary의 상호검증과 독립 계산기를 제공한다. 오프라인 mock/fixture는 synthetic_fixture로 표시한다.
- 로컬 소스 ZIP을 새 위치에 풀어 manifest와 selftest를 검사한다. 실제 Ollama 추론은 이번 작업 범위에 없다.

분석 근거와 관점 간 상충 의견은 V058_ANALYSIS.ko.md에, 실행 명령은 README.md에 기록한다.
