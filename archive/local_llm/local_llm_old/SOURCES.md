# 확인 자료와 출처

확인일: 2026-09-10. 소스 작성에 사용한 공개 기술 자료는 모델 공급자·엔진 개발사·제조사의 1차 자료다. 아래 자료 확인은 모델 실행이나 이 소스의 런타임 시험이 아니다.

## 저장소와 대화

기준 커밋: `254757486a987475d16541cf84b905d684c1c13d`

```text
https://github.com/jaeseongs95/thought-graph-simulator
```

연결된 GitHub 읽기를 통해 `README.md`, `adm_minimal.py`, `examples/problems.json`, `docs/research_note.md`의 관련 구간, `supplement/experiment_manifest.json`을 확인했다. ‘논문 기반 구현’ 대화의 회수 가능한 목적·정정 맥락도 확인했다. 현재 요청이 이전 단계에서 미뤄 둔 LLM 연결을 명시적으로 요청하므로 이 부분만 후속 구현했다.

기존 생성기의 테스트 픽스처 사용과 실제 모델 출력의 생성 경로는 분리했다. 기존 `results/`의 수치를 이번 모델의 결과로 복제하지 않았다. 저장소에 쓰기·커밋·푸시하지 않았다.

## 공식 기술 자료

**[S1] Ollama 모델 라이브러리 — qwen3:4b**  
확인 내용: 모델 태그, 약 4.02B 파라미터, Q4_K_M, 표시 파일 크기 약 2.5GB, thinking 지원.

```text
https://ollama.com/library/qwen3:4b
```

**[S2] Ollama Windows 안내**  
확인 내용: Windows 네이티브 실행, NVIDIA 지원, 기본 API 주소, 드라이버 및 설치 안내.

```text
https://docs.ollama.com/windows
https://ollama.com/download/windows
```

**[S3] Ollama 하드웨어 지원**  
확인 내용: RTX 4060은 지원 목록의 compute capability 8.9에 포함된다.

```text
https://docs.ollama.com/gpu
```

**[S4] NVIDIA RTX 4060 제품 정보**  
RTX 4060 제품군의 제조사 사양 출처. 사용자 스크린샷에 전용 VRAM 수치가 직접 표시된 것으로 해석하지 않았다.

```text
https://www.nvidia.com/en-us/geforce/graphics-cards/40-series/rtx-4060-4060ti/
```

**[S5] Ollama Chat·구조화 출력·Thinking API**  
확인 내용: `/api/chat`, JSON Schema `format`, `think=false`, `stream=false`, 완료 사유, 토큰·시간 필드. 구조화 출력은 의미 검증을 대신하지 않는다.

```text
https://docs.ollama.com/api/chat
https://docs.ollama.com/capabilities/structured-outputs
https://docs.ollama.com/capabilities/thinking
```

**[S6] Ollama FAQ·파라미터**  
확인 내용: 클라우드 기능 비활성, 서버 환경변수, 병렬 처리, 모델 적재 상태, 문맥·seed·출력 한도.

```text
https://docs.ollama.com/faq
https://docs.ollama.com/modelfile
```

**[S7] Ollama 모델 목록·상세 정보·적재 정보**  
확인 내용: 로컬 모델 digest, GGUF/양자화 정보, capability, `size_vram`, `context_length`.

```text
https://docs.ollama.com/api/tags
https://docs.ollama.com/api-reference/show-model-details
https://docs.ollama.com/api/ps
```

**설치 참고 — Python 공식 Windows 다운로드**

```text
https://www.python.org/downloads/windows/
```

README의 8,192 문맥·4,096 출력·6스레드·256배치·temperature 0.2는 이번 실험을 위해 선택한 설정값이다. 제조사가 이 실험에서 최적값이라고 검증한 수치가 아니다. 처리 속도·정답률·VRAM 실측값을 출처에서 가져와 사용자의 실제 결과처럼 표시하지 않았다.
