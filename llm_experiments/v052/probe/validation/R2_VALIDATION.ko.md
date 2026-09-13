# v052 r2 검증 기록

## 완료된 검사

- 새 실행 진단 단위시험 4/4 통과.
- `tests_v052.test_measure` + `tests_v052.test_review_regressions` + 새 진단 시험: 총 29/29 통과.
- 닫힌 Ollama endpoint 재현: Exit 3, `inference_calls=0`, `preflight_metadata/runtime_metadata_error`, Connection refused 원문 노출 확인.
- 서버는 응답하지만 model digest가 다른 재현: Exit 3, `inference_calls=0`, `preflight_identity/runtime_identity_error` 확인.
- preflight identity 통과 후 첫 `/api/chat`이 HTTP 503인 재현: Exit 3, `inference_calls=1`, `inference/transport_error`, 실패 slot ID 확인.
- 위 세 경우 모두 자동 재시도 없이 원문/status 보존.

## 전체 selftest에 대한 정직한 범위

r2에서 `selftest --new-only` 전체 실행을 두 번 시도했으나 이 환경의 단일 명령 실행 제한(각 120초/180초)에 도달해 완료 상태를 얻지 못했다. 두 번째 시도는 로그상 29개 기존 v052 시험까지 연속 통과한 뒤 제한시간에 중단됐다. 따라서 r2에 대해 "전체 480+ 시험 통과"라고 주장하지 않는다.

r1 배포본은 기존에 480/480 통과 기록이 있으며, r2에서 연구 의미를 담당하는 `design.py`, `requests.py`, `schema.py`, `measure.py`, `calibration.py`, `plan.py`, `evidence.py`는 수정하지 않았다. r2 변경은 버전, runner 실행 진단, audit 진단 일관성 검사, CLI/reporting 출력, Windows wrapper, 새 회귀시험과 문서에 한정한다.

## 판정

수정은 A/D/M 성공률을 올리는 방향이 아니다. 인프라 실패와 모델 오답/미측정을 구분해, 실제 추론이 시작되지 않은 상태를 연구 실패로 오독하지 않게 한다. 모델 identity gate와 no-retry 정책은 유지한다.
