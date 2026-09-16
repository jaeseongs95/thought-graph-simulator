# v089 사전 실험 계획 — 초기 ID와 후속 ID의 완전 교차

작성일: 2026-09-16. 버전: v089 r1. 이 문서는 새 실제 Qwen 추론 전에 소스 및 protocol과 함께 동결한다.

## 1. 근거와 새 질문

v088 r2의 B에서는 초기 facts가 원자명=ID인 경로에서 이후 별도 ID를 부여할 때 참조 오류가 집중됐다. 그러나 당시 초기 명명 유형은 구조/경로에 묶여 있었다. v089는 같은 구조·경로·seed에서 초기 ID와 후속 ID를 교차해 그 혼재를 제거한다. 이는 v088에 이미 실행된 결과가 아니라 이번 후속 설계다.

핵심 질문: 동일한 의미의 초기 facts, 목표, primitive rules, 선택 경로에서 초기 원자–ID 대응 방식과 후속 대응 방식의 조합에 따라 유효한 연속 proof 및 양방향 D 실현이 달라지는가?

D는 최종 goal의 실제 proof DAG 의존 깊이(D_DAG)다. 초기 facts는 깊이 0, 규칙 노드는 1+max(부모 깊이)로 재계산한다. 설명 길이, 규칙 수, hidden-state 깊이를 대신 측정하지 않는다.

## 2. A: 초기 ID 4 × 후속 ID 4

| 방식 | 초기 facts | 후속 규칙의 지정 ID |
|---|---|---|
| atom_alias | ID=atom | ID=이미 제시된 규칙의 결론 atom |
| short | n0001, n0002, n0003 | n0004부터 동일 sequence |
| long | v087_node_0001 등 | v087_node_0004부터 동일 sequence |
| atom_tagged | node_<atom> | node_<이미 제시된 결론 atom> |

16조합 각각 U01~U08 × shallow/deep × seed 2개로 32개 연속 graph 및 16개 양방향 pair를 배정한다. 합계 512 graph, 규칙+final 요청 2,752회다. 모두 같은 기존 구조이며 새 holdout은 없다.

초기 facts는 v088 C baseline의 첫 규칙 요청에서 얻는다. 각 구조/경로에서 trial ID 사전순으로 첫 유효 초기 facts를 선정한다. 선정 함수는 plan과 요청만 읽고 대상 응답·후속 응답·summary를 읽지 않는다. 원문 요청과 선정 provenance를 소스에 보존한다. 입력 초기 facts ID는 4방식 각각으로 한 번만 전단사 치환한다.

모든 조합에 같은 allocated-ID header, 같은 singleton ID enum을 적용한다. 부모·원자·규칙 schema는 기존과 같다. 같은 후속 방식에는 초기형이 달라도 새 ID sequence가 같다. 충돌 확인은 모든 초기형의 ID 합집합에 대해 한다. 의미 ID에서 충돌하면 이름을 임의 수정하지 않고 설계를 거부한다. 현재 16개 경로는 원자 결론 재정의가 없어 이 조건을 만족한다.

atom_alias/atom_tagged는 의미 단서를 포함한다. 이들의 성과를 문자열 길이 단독 효과나 지원 없는 모델 능력으로 해석하지 않는다. enum 준수는 지원 계약 준수이고 자율 ID 생성 능력과 다르다.

16개 문제×seed block마다 각 방향에서 16조합의 순서를 순환 배정한다. 각 조합은 방향별로 각 실행 순서를 한 번씩 차지한다. 각 요청은 stateless /api/chat이며 history를 명시적으로 제공한다. 순환 배정은 구조별 모든 시간효과를 제거한다는 주장이 아니다.

새 응답이 잘못되어도 그 content 문자열을 다음 history에 그대로 전달한다. 초기 이외의 재명명, parent 보충, rule 교체, final 수정, 잘못된 응답 재시도는 하지 않는다.

## 3. 주평가와 보조평가

q_p(i,o)는 구조 p에서 초기형 i/후속형 o의 shallow와 deep이 모두 유효하게 성공한 seed 비율이다(구조당 2 seed pair).

주평가:

    mean_p 0.5 × [(q_p(short,short) − q_p(atom_alias,short))
                +(q_p(long,long) − q_p(atom_alias,long))]

즉 후속 중립 ID 계열을 고정하고 초기형을 atom_alias에서 같은 계열 중립 ID로 바꾼 효과를 short/long 동일 가중 및 8구조 동일 가중으로 합산한다. 양수는 해당 중립 초기형이 유리하다는 뜻이다. 이 주평가 자체는 일반적 통일 효과와 의미 대응 전환의 내부 원인을 완전히 분리하지 않는다.

보조 대비는 protocol.secondary_comparisons에 순서까지 고정한다. short→long, long→short 등의 중립 계열 교차를 포함하여, 단순 계열 혼용과 원자명=ID 관계 변화가 같은 패턴을 보이는지 살핀다. atom_alias→atom_alias는 지원받은 연속 생성에서 국소 alias 효과가 이어지는지의 평가이며 새 facts 종단 성과가 아니다. atom_tagged 관련 대비는 의미 단서와 문자 동일성의 탐색 대조다.

단일 graph, 양방향 pair, 구조별 성공, 양쪽/한쪽/양쪽실패 분포, 대응 경로의 최초 오류 전이, 한 구조씩 제외한 민감도를 따로 보고한다. leave-one-structure-out 범위는 신뢰구간이 아니다. 자동 p-value 또는 IID 일반화 추정은 하지 않는다.

## 4. B: 기존 D 종단 기준선

C라는 v088 phase 이름을 코드의 end_to_end로 유지하며, 문서에서는 이번 두 번째 평가로 표시한다. 기존 correct external D values → compare → ID lookup을 새로 실행한다. 128개 선택에서 비교/조회 총 256회이며 한 번만 센다. baseline 생성기만 각자 새 facts부터 128개 proof를 생성한다. 64 양방향 pair, 16 네 표시 묶음을 보고한다.

v088에서 실패한 allocated_id를 기본안으로 승격하지 않는다. atom_alias의 새 선택·새 facts 전체 종단도 이번 배정에 추가하지 않는다. A와 시작 조건·분모가 달라 직접 우열 또는 합산을 하지 않는다.

기존 문제·seed·D 후보/표시·프롬프트·sampling·JSON schema·채점 계약은 유지한다. baseline의 요청은 v088 실제 원응답 history를 넣어 1,072건 byte regression으로 검증할 수 있다.

## 5. 분모·자원·실행 제어

- 전체 trial 640개: 지원 연속 graph 512 + 새 baseline graph 128.
- 정상 목표 경로 선택 시 추론 3,824회: A 2,752 + B 선택/생성 1,072.
- 최대 inference slot 3,856개. 경로별 최대 규칙 슬롯을 두므로 짧은 경로의 남는 32개는 정상 조건부 skip이다(목표 경로가 선택된 경우).
- metadata 32개 action, 최대 action slot 3,888개.
- 모델 qwen3:4b-instruct, digest 0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0, Ollama 0.34.1.
- seeds 64001001/64001002, temperature 0.7, top_p 0.8, top_k 20, num_ctx 8192, num_predict 4096. 실제 값은 protocol과 대조한다.

요청 바이트 제한은 절단 없이 검사한다. 네트워크/identity/길이종료/미실행/조건부 skip을 논리 오답과 분리한다. 부분 배치에서 전체 주평가를 산출하지 않는다.

## 6. 사전 진단

원응답 기준 missing_parent, 잘못된 전제 multiset, 중복 ID, 지원 계약 실패를 구분한다. 최초 실패와 실패 이후의 후속 오류를 분리한다. 각 규칙 위치의 risk set은 직전까지 의미·지원 계약이 모두 유효한 경로다. 전제 수 및 조상인 직접 전제의 중첩을 기록한다. 모든 규칙 오류를 독립 graph 실패로 합산하지 않는다.

서버 응답의 token/duration 합과 미제공 값을 함께 기록한다. 누적 입력은 반복 history를 포함한다. 이 값은 GPU 전기료, 청구액, 전체 wall-clock 또는 대형 모델 대비 비용 우월성이 아니다.

## 7. 근거 보존과 다음 단계

v088의 실제 소스 115파일을 frozen088에 바이트 보존하고 v088 evidence ZIP 자체를 SHA-256으로 고정한다. 새 실행은 llm_experiments/v089에 설치한다. 기존 v088 소스·manifest·guard·로그·evidence는 읽기만 한다.

v089 결과가 나온 뒤에만 생성기 승격 또는 다음 설계를 판단한다. 현재 단계에서 추가 holdout과 전체 alias 종단이 성공했다고 기록하지 않는다. 자체시험·calibration·합성 전체 실행은 새 연구 표본이 아니다.
