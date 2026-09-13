# v058 구조 이전 검증

이 기록은 `llm_experiments/vNNN/` 구조로 옮긴 뒤 수행한 오프라인 검증 결과다. 실제 Ollama 추론, 모델 다운로드·갱신, 서버·캐시 초기화는 수행하지 않았다.

## 결과

- v047~v057 동결 자료 11,994파일을 이전 전 inventory와 대조했다. 누락, 크기 차이, SHA-256 불일치는 모두 0건이다.
- v057 입력 다섯 자료의 바이트 결합, preflight identity, 생산 재감사와 독립 재계산이 통과했다. 결과는 `input_validation_layout.json`에 있다.
- v057 원문 480호출의 별도 서술 분석을 새 경로에서 다시 생성했다. 결과는 `v057_analysis_layout.json`에 있다.
- v058 전체 selftest 44개가 통과했다. 새 물리 경로, 기존 논리 fingerprint 키와 split input 배치를 확인하는 시험 5개가 포함된다.
- 최종 계획 `../experiments/v058_order_layout.plan.json`의 `plan_sha256`은 `3f36e4871f3a2de5d1b03c78e28669051154e498e3d40d36b97956eca97bd28c`다. 함께 생성된 baseline ZIP은 v057 evidence ZIP과 같은 SHA-256 `1949d10375a1848982c427a79f3b2cd5c751e44cdc7045945d2b2ff7be3a083e`다.
- release `../releases/v058_order_replay_source_layout.zip`은 `v058-source-release-r2` 계약으로 260개 파일을 포함한다. ZIP SHA-256은 `c50b64c3420867ded5164727d3dc5e6ffe0226bd350dbbcaaa891ec0b6bfecdb`이며 manifest 검사가 통과했다.
- release를 새 임시 폴더에 풀어 `llm_experiments/v058/probe`에서 다시 실행한 selftest 44개도 통과했다. 원 저장소의 `PYTHONPATH`에 기대지 않았다.

## 현재 저장소용 최종 배포본 재확인

- 실행 안내에서 v057 입력 다섯 자료 중 잘못 적힌 `run 디렉터리`를 실제 필수 입력인 `독립 검산 JSON`으로 바로잡았다.
- 기존 구조 이전 배포본은 보존하고 `../releases/v058_order_replay_source_repo.zip`을 새로 만들었다.
- 새 ZIP은 `v058-source-release-r2` 계약의 260개 파일을 포함하며 SHA-256은 `e9079af13ef21cc9d96e063c21bacdae7dc16f73cf78a60997437cf4f7169a86`이다.
- manifest 검사와 현재 `v057` 입력 다섯 자료의 생산·독립 재감사가 통과했다.
- 새 ZIP을 빈 임시 폴더에 풀고 원 저장소의 `PYTHONPATH` 없이 실행한 selftest 44개가 모두 통과했다.
- 동결 계획 `../experiments/v058_order_layout.plan.json`은 현재 Python 소스 지문과 일치하며 `show` 검사가 통과했다. 실제 Ollama 추론은 실행하지 않았다.

## 완료 버전 evidence 재검산

v049~v057의 주 evidence ZIP 9개를 새 위치에서 검사했다. v049, v050, v053~v057은 각 버전 독립 검산기가 통과했고, v052는 이후 버전의 강건한 검사기로 4,400필드 차이 0을 확인했다. v051의 기존 독립 검사기는 기록된 무효 graph를 처리하다 `KeyError`로 종료했지만, ZIP manifest와 생산 read-only 재감사는 완결·무결 상태로 통과했다. 따라서 v051은 ZIP 손상으로 판정하지 않되 독립 의미 검산 근거는 부족한 것으로 남긴다.

## 경로 호환성

각 버전의 Python 모듈 selftest는 새 `probe/` 위치에서 실행된다. v047~v057의 `probe/windows/*.ps1`은 옛 공용 `results_llm/`과 `experiments_vNNN/` 경로를 계산하는 동결 자료이므로 새 구조에서 직접 사용하지 않는다. 현재 경로를 명시해 Python CLI를 실행하는 방법은 `../../README.md`에 기록했다.
