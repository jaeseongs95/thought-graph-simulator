# 논문 핵심이 코드에 남아 있는가

## 대조한 원문

연결 저장소의 `docs/research_note.md`, `adm_minimal.py`, `examples/problems.json`을 읽었다. 이 문서는 이번에 확인한 연구 명세와 대조한 것이며, 별도로 제공되지 않은 원 논문 전체의 모든 수식·가설을 검증했다고 주장하지 않는다.

연구 명세의 핵심은 결과 고정·역할 조작·실제 기록 측정·유효 경로 검사·손상 기록 거부다. A는 구체 사례/보편 도식, D는 실제 지지 깊이, M은 검토 대상 수준이다.

## 구현 대응

| 핵심 | 구현 | 반대 결과를 검출하는 장치 |
|---|---|---|
| 문제/목표 고정 | PROBLEMS와 계획·요청 해시 | 입력 변경, 다른 목표, source drift 거부 |
| 역할별 실제 구조 조작 | 2×2×3 factorial | 역할 무시 서버가 전체 제어 성공으로 통과하지 않음 |
| 요청 라벨과 관측 분리 | measure는 arm/task만 참조; role_match는 별도 | 동일 payload에서 role_id를 바꿔도 측정값 동일 |
| 실제 D | 규칙·부모·위상·목표 조상 검증 | 불필요한 노드, 양 경로 나열, 무근거 목표 거부 |
| 실제 A | 가정-규칙 접지 + 보편 진리표 | 목표 가정 주입, 바인딩 위조, 근거 삭제 거부 |
| 실제 M | 검토 대상 참조 + 실제 finding | M1 목표 원자 오용, M2 false/형식 오류 거부 |
| 축별 선택성 | 한 축 대응 및 비조작 구조 유지 | 상수 좌표 출력·다른 축 변경을 성공으로 세지 않음 |
| 우연한 기본값 대조 | neutral 동일 schema | 12역할로 재평가하되 독립 표본으로 증가시키지 않음 |
| v051 단일 과제 밖의 구조 전이 | 다전제/깊이4 T02 | K01 성공으로 T02 실패를 덮지 않음 |

## 성공으로 잘못 세지 않는 것

복사 진단의 정답은 호스트가 제공한다. 따라서 복사 성공은 형식 경계 진단일 뿐 논문 핵심의 성공이 아니다. D 단독 생성은 D에 관한 증거이며 A/D/M 통합 제어 성공이 아니다. 유효한 증명을 하나 만들었어도 역할에 따라 달라지지 않으면 선택적 제어 가설의 성공이 아니다.

## simulator와의 관계

기존 simulator는 가능한 증명 후보를 나열하고 shallow/deep에 따라 최소/최대 후보를 코드로 선택한다. A의 표현과 M 검토도 프로그램이 구성한다. 그것은 제한된 명세에서 역할별 경로를 만들고 검증할 수 있다는 구성적 증거다.

그 프로그램을 실제 LLM 생성기로 바꾼 뒤에도 같은 동작을 얻는지는 별도 경험적 질문이다. simulator의 성공이 LLM 성공을 자동으로 보장하지 않고, LLM의 한 구성 실패가 그 명세 자체의 논리 모순을 자동으로 보이지도 않는다.

## 이론에서 아직 연결되지 않은 부분

외부 증명/도식/검토 기록을 좌표화하는 것과 모델 내부 hidden layer의 실제 사고 상태를 좌표화하는 것은 같은 관측이 아니다. 이 코드의 정당한 성과는 전자다. 내부 메커니즘 주장에는 그에 맞는 별도 계측과 개입이 필요하다.

따라서 v052를 '실행되기만 하는 코드'로 만들지 않았다. 생성 결과가 유효한지, 요청된 축 조작이 실제로 나타나는지, 중립 대조와 구별되는지, 다른 구조에서도 유지되는지를 모두 실패 가능하게 만들었다. 동시에 이를 이론 전체·신규성·성능 우월성의 단독 입증으로 포장하지 않는다.

## 참고 1차 자료

- 연구 명세: https://github.com/jaeseongs95/thought-graph-simulator/blob/main/docs/research_note.md
- 원래 simulator: https://github.com/jaeseongs95/thought-graph-simulator/blob/main/adm_minimal.py
- 원래 문제 집합: https://github.com/jaeseongs95/thought-graph-simulator/blob/main/examples/problems.json
- Ollama structured outputs: https://docs.ollama.com/capabilities/structured-outputs
- llama.cpp JSON Schema→GBNF 지원 범위: https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md
- Turpin et al., Language Models Don't Always Say What They Think (2023): https://arxiv.org/abs/2305.04388

외부 생성 trace와 내부 원인을 구분하는 이유는 출력 설명의 충실성이 별도 연구 대상이기 때문이다. 위 논문에서 관측한 모델/과제를 현재 Qwen의 직접 실험 결과로 바꾸어 인용하지 않는다.
