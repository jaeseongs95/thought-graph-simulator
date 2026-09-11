# 모델/API 전제의 공식 근거

확인 기준일: 2026-09-10. 구현에 필요한 공개 계약만 정리했다. 실제 설치된 모델의 정체는 `/api/show`의 GGUF 메타데이터와 digest를 통해 별도로 확인한다.

1. Qwen 공식 Instruct 모델 카드
   https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507
   Instruct-2507은 non-thinking 전용. 권장 샘플링 temperature=0.7, top_p=0.8, top_k=20, min_p=0.

2. Qwen 공식 Thinking 모델 카드
   https://huggingface.co/Qwen/Qwen3-4B-Thinking-2507
   Thinking-2507은 thinking 전용. 권장 샘플링 temperature=0.6, top_p=0.95, top_k=20, min_p=0. 긴 출력 예산을 권장하지만 본 소스의 로컬 기본 예산은 그 벤치마크 예산을 재현하지 않는다.

3. Ollama Thinking API 문서
   https://docs.ollama.com/capabilities/thinking
   Chat 응답에서 `message.thinking`과 최종 `message.content`를 구분한다.

4. Ollama Chat API 문서
   https://docs.ollama.com/api/chat
   `think`, `format`, `options`, 비스트리밍 응답의 완료/시간/토큰 필드.

5. Ollama 구조화 출력 문서
   https://docs.ollama.com/capabilities/structured-outputs
   JSON Schema 형식 제약. 형식 적합성은 의미적 증명/도식/검토 정확성을 대체하지 않는다.

6. Ollama Instruct 태그
   https://ollama.com/library/qwen3:4b-instruct
   확인 시 Q4_K_M, 약 2.5GB. 태그는 변경될 수 있으므로 실행 시 digest/메타데이터를 보존하고 모드 정책을 재검사한다.

이 자료들은 사용자 실행의 단일 실패 원인을 입증하지 않는다. 이전 모드 요청의 적합성을 확인하지 않았다는 점과 새로운 모드 정책의 근거로 사용했다. 소스에서 확인되는 구조적 문제, 사용자 원문에서 관측한 실패, 아직 검증하지 않은 원인 가설은 분리했다.
