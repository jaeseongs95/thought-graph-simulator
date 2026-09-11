# 근거 및 구현 호환성 메모

작성일: 2026-09-11.

## 사용자가 제공한 자료

v046 성공 검증보고서 본문을 사용했다. 보고된 12개 새 응답, 교환식 4/4, NOT→AND 중간/최종 4/4, seed 1729, 원래 식의 과거 3/4, 원문 재생성·독립 파서·반례 검사는 이 제공 자료의 내용이다. 이번 작업에서 그 ZIP 원문을 새로 열어 재검사한 것으로 표시하지 않는다.

## 직접 읽은 연결 저장소 소스

저장소: `jaeseongs95/thought-graph-simulator`.
조회한 main tree 식별자: `3eaac78ad2ba7237f868c18a080794bda9e4f54c`.
이는 tree 식별자이며 commit ID라고 부르지 않는다.

- `local_llm/composition_probe.py`: 실제 부모 bool 바인딩, 교환식 생성, 부모·국소·최종 판정, 원문 보존 구조.
- `local_llm/operator_probe.py`: 원래 operator 표현, 한국어 system 문구, schema, 요청 키 순서, 16개 primitive 대조 계획.
- `local_llm/protocol.py`: `obj()`가 생성하는 schema 키와 순서.
- `local_llm/common.py`: canonical 해시와 wire 직렬화의 구분, 삽입 순서 보존, 소스 줄바꿈 정규화 정책.
- `local_llm/decision_probe.py`: `frozen.model.digest`, `show_sha256`, `frozen.ollama_server`의 런타임 동일성 대조.
- `docs/research_note.md`: A/D/M 정의, 고정 목표·역할극의 목적, 사용자 기여와 AI가 구체화한 명세의 구분.

이 패키지는 기존 모듈을 import하거나 수정하지 않는다. 위 형식의 저장된 요청과 manifest를 사용자의 로컬 결과 폴더에서 읽는 별도 실행기다. 과거 Python 객체나 pickle을 실행하지 않는다. 해당 계약과 맞지 않으면 원문을 고쳐 맞추지 않고 중단/제외 사유를 기록한다.

## 외부 1차 자료

[1] Ollama, Generate a chat message. https://docs.ollama.com/api/chat  
확인 사항: `/api/chat`, `messages`, `format`, `options`, `stream`, `think`, 완료 이유, 입력/출력 토큰 수, 캐시 토큰 수, 서버 처리 시간 필드.

[2] Ollama, List models. https://docs.ollama.com/api/tags  
확인 사항: 태그 이름, 모델 digest, parameter_size, quantization_level.

[3] Ollama, Modelfile Reference. https://docs.ollama.com/modelfile  
확인 사항: temperature, seed, num_ctx, num_predict, top_k, top_p 등 생성 설정. 이번 실행은 임의로 기본값을 다시 지정하지 않고 원본 옵션을 보존한다.

[4] Ollama, Structured Outputs. https://docs.ollama.com/capabilities/structured-outputs  
확인 사항: 자료형 기반 JSON schema 전달. schema 준수와 값의 의미적 정확성은 별도로 검사하도록 설계했다.

[5] Zhuo et al., ProSA: Assessing and Understanding the Prompt Sensitivity of LLMs (2024). https://arxiv.org/abs/2410.12405  
사용 범위: prompt 민감도를 별도의 평가 대상으로 연구한다는 배경. 이 사용자의 특정 실패의 내부 원인을 이 논문이 입증했다고 해석하지 않는다.

[6] Zhou et al., Least-to-Most Prompting Enables Complex Reasoning in Large Language Models (2022). https://arxiv.org/abs/2205.10625  
사용 범위: 복잡한 문제를 하위 문제로 나누고 앞선 답을 다음 단계에서 사용하는 선행 접근이 존재한다는 배경. A/D/M의 신규성·효과를 이 논문의 실험 결과로 대신 증명하지 않는다.

현재 v047의 반복 수·판정표·실행 순서·진행 경로는 이번에 제안한 연구 설계다. 외부 논문이 이 프로토콜이나 현재 모델의 성공률을 보증한다는 뜻이 아니다.
