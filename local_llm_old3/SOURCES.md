# 근거와 기준 소스 — v0.3.0

## 이번 분석에 직접 사용한 자료

- 사용자 제공 `results_llm (2).zip`: v0.2 calibration 8건, smoke 6건의 manifest·요청/응답 원문·기록·소스 스냅샷.
- 이전 배포 `thought_graph_local_llm_v02_source.zip`: 기존 구현과 v0.2 승인 소스 해시의 기준.
- 이전 실행 `results_llm.zip`: 기본 세 문제의 동결 사본을 오프라인 시험에 사용. 새 저장소 파일을 덮어쓰지 않는다.

입력 ZIP/manifest/core의 해시는 배포본 `analysis/run_metrics.json`, 원문 재검사는 `analysis/v02_calibration_01/reanalysis.json` 및 `analysis/v02_smoke_01/reanalysis.json`에 있다. 수치는 사용자 실행 결과를 재계산한 것이며 외부 벤치마크 수치가 아니다.

## 기존 프로젝트 기준

기준 저장소는 GitHub `jaeseongs95/thought-graph-simulator`다. 이번 수정은 저장소의 최신 커밋 조회나 원격 커밋/푸시를 수행한 작업이 아니다. 사용자 실행 당시 동결한 파일과 이전 배포 소스를 사용했다.

기준 commit: `254757486a987475d16541cf84b905d684c1c13d`

core Git blob: `b7aa0b58b9257fdb80882b48e4ecf1006ac4ff45`

core SHA-256: `24542551351225d4a2ed0e65c95cfca3d850e7bbd102439f1f3662d2eefcfad8`

연구 방향과 고정 목표 비교는 사용자의 제안이고, 이 런타임의 Horn 과제 세부 계약·구현·게이트·보고는 AI 보조 구현이다. 기존 A/D/M 의미를 바꾸거나 논문 전체를 검증했다고 주장하지 않는다.

## 기술 인터페이스의 확인 수준

기존 Ollama `/api/chat`, `/api/tags`, `/api/show`, `/api/ps`, `/api/version` 사용 코드를 유지했다. 사용자 로그의 실제 서버 버전은 0.34.0이다. 이번 수정에서 새 서버 호출, 새 공식 문서 조회, 설치/다운로드는 하지 않았다. 저장 응답의 재판정과 mock API 시험만으로 새 버전 Ollama의 동작이나 Windows 실행을 보증하지 않는다.

수행 범위: `BUILD_STATUS.json` 및 `validation/`.
