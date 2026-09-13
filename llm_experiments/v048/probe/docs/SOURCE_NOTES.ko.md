# 출처와 구현 범위

## 사용자 제공 자료

`thought_graph_v047_next_step.zip`: 기존 실행·감사 코드 및 시험.
`v047_paired_01.zip`: 96회 실제 요청·응답과 계획 snapshot.
앞선 분석 결과: 원식 18/24, 교환식 24/24, 연결식 최종/전체 경로 24/24.

기존 `paired_probe_v047/*.py`와 `tests_v047`는 감사 호환성과 회귀 검사를 위해 변경하지 않고 동봉했다. 새 코드는 `paired_probe_v048`에 있다. 기존 저장소를 직접 수정하거나 GitHub에 커밋하지 않았다.

사용자 원문에 대한 이번 오프라인 호환 검사 범위는 `validation/ACTUAL_BASELINE_COMPATIBILITY.json`에 기재했다. 업로드에 별도 외부 v047 계획은 없었으므로 패키지 제작 환경에서는 `snapshot_only`로 표시했다. 사용자의 로컬 실행에서는 이미 보관 중인 `experiments_v047/v047_paired_01.plan.json`을 우선 사용하도록 안내한다.

## 공식 API 문서 확인

확인일: 2026-09-11. 아래 자료는 API 필드와 생성 옵션 의미를 확인하는 데 사용했다. 현재 문서에 맞추려고 사용자의 기존 모델이나 서버를 업데이트하지 않는다.

1. Ollama Modelfile Reference — `seed`, `temperature` 생성 설정.
   https://docs.ollama.com/modelfile
2. Ollama Generate a chat message — 요청 `options`, `format`, `stream`, `think`, 응답의 토큰·시간·캐시 필드.
   https://docs.ollama.com/api/chat
3. Ollama List models — 모델 태그와 digest 및 모델 세부 정보.
   https://docs.ollama.com/api/tags
4. Ollama Usage — 처리 시간의 나노초 단위와 로딩/입력/출력 처리 필드의 구분.
   https://docs.ollama.com/api/usage

공식 문서의 seed 설명과 별개로, 실제 응답 반복의 동일성은 실행 원문으로도 검사한다. API가 보고한 토큰과 시간은 실제 모델 간 동일 FLOPs의 측정치가 아니다.

## 합성 검증 자료

`validation/SYNTHETIC_960_EVIDENCE.zip`는 테스트 서버가 정해진 행동을 반환한 코드 검증 자료다. 패키지 안의 높은 정답률이나 960회 호출을 실제 새 LLM 표본으로 사용하면 안 된다. 새 LLM 호출은 사용자의 로컬 `run` 명령에서 수행된다.
