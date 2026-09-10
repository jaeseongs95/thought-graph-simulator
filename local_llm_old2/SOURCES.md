# 근거와 기준 소스 — v0.2.0

## 사용자 제공 실행 근거

`results_llm.zip`의 `smoke_01`과 `pilot_01`을 분석했다. ZIP SHA-256과 원본 manifest/run 해시는 배포본 `analysis/run_metrics.json`에 기록했다. 분석표는 외부 자료에서 가져온 수치가 아니라 사용자 실행 결과의 재집계다.

기존 `thought_graph_local_llm_source.zip`은 v0.1의 인터페이스와 판정 코드를 확인하는 기준이다. 수정본은 기존 `adm_minimal.py`를 바꾸지 않는다.

## 프로젝트 기준

- Repository: https://github.com/jaeseongs95/thought-graph-simulator
- Baseline commit: `254757486a987475d16541cf84b905d684c1c13d`
- Core Git blob: `b7aa0b58b9257fdb80882b48e4ecf1006ac4ff45`
- 사용자 실행 당시 core SHA-256: `24542551351225d4a2ed0e65c95cfca3d850e7bbd102439f1f3662d2eefcfad8`
- 참조 파일: `adm_minimal.py`, `docs/research_note.md`, 실행 manifest에 동결된 `examples/problems.json`.

기존 연구자료의 고정 결과·역할극·독립 재검사 범위를 따르며 새로운 논문 전체의 검증을 선언하지 않는다. 연구 방향과 고정 목표 선택은 사용자 제안이고, Horn 문제의 세부 스키마·런타임·진단은 AI 보조 구현이다.

## 공식 기술 자료

확인 기준일: 2026-09-10. 아래는 API·라이브러리의 설명이며 사용자의 서버 동작을 대신 측정한 근거가 아니다.

1. Ollama Structured outputs: https://docs.ollama.com/capabilities/structured-outputs
   - JSON Schema를 format으로 전달하고 원하는 구조를 설명하며 반환된 응답을 검증하는 사용 방식.
2. Ollama Chat API: https://docs.ollama.com/api/chat
   - chat 요청의 format/think/options와 응답 완료·토큰·시간 필드.
3. llama.cpp Grammars / JSON Schema 지원 설명: https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md
   - 스키마 지원 범위와 문법 변환의 한계. 사용자의 Ollama 버전에서 minProperties가 정확히 어떻게 처리됐는지는 이 일반 문서만으로 확정하지 않는다.

외부 문서는 새 코드의 Windows/Ollama 실행이나 정확도 개선을 입증하지 않는다. 실제 수행 범위는 BUILD_STATUS.json을 본다.
