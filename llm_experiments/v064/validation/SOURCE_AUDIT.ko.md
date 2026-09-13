# v064 소스 독립 감사 r1

판정은 **감사 완료 / 후보 미완료**다. 감사 대상은 `v064_direct_D_source_r1.zip` SHA-256 `5cd7a8d755dc60bf90afe90ff26fca451944deb72480d074acff2499114c84e6`이며, 감사 전후 digest가 같다. `audit_input_r1.json`도 전후 `e9ae5bd08c2604f73963e7aa681f397132c88a4b0bd73c30d4ebac19150ff018`로 같다. `cooperative-sealed` / `sealed-artifact-v1` 범위의 감사이며 외부 실행 인증은 주장하지 않는다.

후보 manifest의 source 16개, 작업 트리 `probe`, `fresh_source_r1`, 결정적 rebuild의 바이트가 모두 일치했다. 원 요청·AGENTS·구조 문서·결정서·프로토콜·검증 자료의 지정 hash도 모두 일치했다. 별도 고정점 계산으로 세 문제의 가능한 실제 D는 T02 `[1,4]`, E01 `[1,2]`, E02 `[2,4]`였고, 여섯 조건열은 서로 다른 여섯 순열이었다. 실행기는 문제·seed·direction만 계획대로 바꾸며, 측정기는 실제 rule, parents, 전제 multiset, goal, cycle, 전체 조상 폐쇄, 원응답 위상순서와 D를 검사한다. A/M 미측정, neutral 진단 전용, T02 개발 문제, E01/E02 외부 holdout 아님이라는 한계도 문서와 코드에서 일치했다.

다만 필수 계약을 막는 finding 세 개가 있다.

1. `V064-SA-R1-F001` — **blocking**. `verify.py`는 마지막 action의 stop reason만 검사한다. 첫 call의 응답 `model`을 `different:4b`로 바꾸고 response hash, record, 이후 전체 event chain, summary, 한국어 보고서, manifest를 모두 다시 계산한 반례에서도 첫 row를 `identity_error`로 재계산하면서 `state=complete`, `observed_calls=18`, `verified=true`를 반환했다. 실제 runner는 첫 identity 오류에서 중단하므로 이 순서는 생성할 수 없다. 원 요청의 모델 식별자 변조 거부와 즉시 중단 결속을 위반한다. 모든 완료 action을 순서대로 검사해 첫 stop reason이 마지막 완료 action 및 stopped status와 일치하도록 고치고, 조기 identity/metadata/HTTP 오류를 완전 재서명한 반례로 회귀해야 한다.

2. `V064-SA-R1-F002` — **blocking**. runner와 verifier의 stopped reason 목록은 `generation_budget_exceeded`를 허용하지만 verifier는 `eval_count > num_predict`인 record를 상태와 무관하게 거부한다. 봉인 뒤 별도 합성 관측 `v064_repro_provider_over_budget_r1_evidence.zip` SHA-256 `6be0fbb0f0adcbbab02e053bf7a94b6d18d1db6edf52f6d250e527d52ed5192d`은 `stopped/generation_budget_exceeded`, 호출 1회로 올바르게 중단했지만 `generation budget per call`로 exit 2이고 independent receipt가 없다. terminal stopped 위반 관측은 보존·승인하되 complete 또는 후속 action이 있으면 거부하도록 상태별 계약을 분리해야 한다.

3. `V064-SA-R1-F003` — **blocking**. `capture_call`은 request/response wire를 record/event보다 먼저 저장한다. 응답 저장 직후 중단된 `v064_repro_pending_wire_r1_evidence.zip` SHA-256 `a09b3131e1906c868e22c22f065cd9dae0f2d8ab3ae0862fd1059e7b77ee7dc9`은 `crashed/interrupted_action`, 완료 1/시작 2/추론 시작 1을 보존하지만 verifier가 pending action의 wire 두 개를 layout extras로 거부해 independent receipt를 만들지 못한다. 정확히 한 started-but-uncompleted action의 제한된 partial wire를 재구성·크기·바이트 검사와 함께 결속하고 성과 관측으로는 올리지 않아야 한다.

`fresh_source_r1`에서 지정 Python 3.12로 16개 단위·합성 검사를 다시 실행해 exit 0/OK를 확인했고, source release check와 기존 synthetic evidence 독립 검산도 exit 0이었다. 이 시험 수와 합성 정답은 연구 가설의 근거로 사용하지 않았다. 반례 결과가 정상 suite의 공백을 직접 드러냈으므로 r1 후보를 사용자 실행 완료본으로 승인할 수 없다.

실제 Ollama 추론·다운로드·서버 시작은 수행하지 않았다. 실제 v064 모델 결과와 A/M 결과, 패널 참가자의 실제 모델 설정, 외부 실행 사실은 확인하지 않았다. 수정 후 관련 반례와 정상·부분 실행 회귀를 수행하고 새 source ZIP을 봉인한 뒤, 이 세 finding을 새 digest에 다시 결속해 재감사해야 한다.
