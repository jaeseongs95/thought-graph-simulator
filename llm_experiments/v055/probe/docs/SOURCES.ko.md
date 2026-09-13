# 자료 출처와 범위

## 사용자 자료

`v054_order_01_evidence.zip`: SHA-256 `46bd0c8abeb074c7ed218a6b3b3ce83eaa7ad042ad00c9ab939d495aa70c6f40`. 이번 결과의 직접 근거다. 원문120개, manifest333개 파일, 계획/metadata/event/소스 snapshot을 다시 검사했다.

`current_session_full_chat.md`: 원문 재계산, 독립 채점, 제3자 심사 관점, 다음 코드 작성 뒤 재검증, '동작시키기'가 아니라 논문의 핵심 검증, 기존 성공과 실패를 함께 보존하라는 기준을 확인했다.

`thought_graph_v054_order_probe.zip`: 생산 코드와 전체 회귀시험의 직접 기준이다. 기존 Python152개는 바이트 보존했으며 `PRESERVED_SOURCE_MANIFEST.json`에 기록했다.

`v053_depth_01_evidence.zip`: original 요청60개의 바이트와 독립 측정값이 v054 original60개와 같은지 반복 실행 비교에 사용했다. 새로운 실험 표본으로 중복 합산하지 않았다.

## 확인한 공식 공개 자료 (2026-09-12 조회)

1. Ollama Gemma3 4B: https://ollama.com/library/gemma3:4b
   공개 패키지는 4.3B, Q4_K_M, 약3.3GB로 표시된다. 실제 다운로드 digest는 로컬 capture 값으로 동결한다. 후보의 우월성 근거로 일반 벤치마크 수치를 가져오지 않았다.
2. Qwen 공식 Qwen3-4B-Instruct-2507: https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507
   모델 계열/체크포인트 설명. 사용자가 실행한 모델의 직접 identity 증거는 첨부 ZIP의 metadata다.
3. Ollama show API: https://docs.ollama.com/api-reference/show-model-details
   모델 세부 정보와 template/parameters/model_info 기록 방식의 근거다.

외부 문서의 설명을 사용자 모델 실행 결과로 취급하지 않는다. 실험 제약과 비교 해석은 위 원문 및 고정된 설계에서 도출했다.
