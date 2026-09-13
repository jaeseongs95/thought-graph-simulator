# v061 최종 소스 독립 감사

## 감사 대상과 판정

`llm_experiments/v061/releases/v061_direction_choice_source_r1.zip`을 실제 추론 전 소스 배포본으로 감사했다. 파일 크기는 755,106바이트이며 SHA-256은 `ee0e877ec0dd80b2210c0530e50f12aad0d55af8fd6b83a3086f32b48167e760`이다.

최종 판정은 **PASS**다. 요청한 일곱 감사축이 모두 충족됐고 열린 차단 결함은 없다. 이 판정은 위 SHA-256의 ZIP에만 적용된다. ZIP 내부의 코드, 시험, README, 프로토콜 또는 manifest가 바뀌면 판정은 무효가 되며 새 다이제스트로 다시 감사해야 한다.

감사자는 v060 분석, v061 설계·구현, 생산자 검증에 참여하지 않은 fresh worker다. 감사를 재위임하지 않았고 봉인 ZIP이나 원소스를 수정하지 않았다. 이번 감사가 새로 쓴 파일은 이 문서와 `source_audit_r1.json`뿐이다.

감사 도중 저장소의 `AGENTS.md`가 감사 대상 밖에서 바뀌었다. 현재 파일을 다시 읽어 적용했으며 SHA-256은 `67a6973db5708b2d7daff01451fb0d2b80b96f1ca39e5cdb7b2382a313b55f58`이다. Git 추적 파일 수는 보존 근거로 쓰지 않았다.

## 확인한 근거

봉인 상태를 직접 계산했다. manifest에는 336개 파일이 있고 ZIP에는 `RELEASE_MANIFEST.json`을 포함해 337개 파일 항목이 있다. 대소문자를 접은 경로 중복, 안전하지 않은 경로, manifest 목록 불일치, 파일 해시 불일치는 모두 0건이었다. 동봉한 `tools/build_release.py --check`도 `release manifest: PASS (336 files)`를 출력했다.

fresh extraction에서 자체시험을 마친 뒤 파일 집합과 해시를 다시 확인했다. 337개 파일이 ZIP과 일치했고 336개 manifest 대상 파일의 불일치는 없었다. 새 v061 파일 24개와 `RELEASE_MANIFEST.json`은 모두 UTF-8, BOM 없음, LF 줄바꿈 조건을 충족했다. `fresh_selftest_r1.log`에는 33개 시험의 성공과 실행 시간 91.924초가 기록돼 있으며, 로그 SHA-256은 `10b8e08967d59e302be6ae849f6ebb12930147ba5bddcf46bbc1b1f9679477d7`이다. 생산 작업본의 최종 자체시험도 같은 33개 시험을 통과했다.

v060 source r2의 manifest 312개 파일을 새 ZIP과 이름·해시로 대조했으며 전부 같았다. 새 ZIP에는 v061 파일 24개만 추가됐다. 따라서 이전 312개 파일의 보존은 Git 상태가 아니라 두 ZIP의 manifest와 실제 바이트로 확인했다.

실제 v060 evidence ZIP의 SHA-256은 `5a2aeeaf28e9b445b61f3cf78ce87c11aeea1b57cc36ba74bd772fecc15c2c68`이다. 동봉된 독립 분석기를 다시 실행한 결과 40호출, metadata 20개, 비교 항목 882개, 차이 0건을 확인했다. `deep_first`는 `k17` 20/20, `shallow_first`는 `k03` 20/20이었다. 별도 역사 자료인 v059도 40호출, metadata 20개, 비교 항목 802개, 차이 0건이었다. 새로 계산한 전체 객체는 `v060_reanalysis_final.json`과 정확히 같았다. v059와 v060을 합친 효과량은 계산하지 않았고, 두 실행에서 공통으로 완전 일치한 사전 예측은 `first_terminal`뿐이다.

## 감사축별 판정

|감사축|판정|직접 확인한 내용|
|---|---|---|
|한 문제와 해석 범위|PASS|K01 한 문제, Gemma 후보, choice-only 범위가 코드와 문서에 고정돼 있다. 10개 seed와 40호출을 독립 문제 40개로 세지 않으며, 내부 기제·일반적 D 제어·다른 모델이나 문제로 확대하지 않는다.|
|조작과 wire 바이트 격리|PASS|두 조건의 rules는 모두 `[k03,k17,k10]`이다. 10개 seed 모두에서 같은 조건 반복 요청은 바이트가 같고, A/B 요청은 유일한 지시 어절 `작은`을 `큰`으로 바꾼 차이만 있었다. 재구성한 요청 해시는 계획의 `request_hashes`와 모두 같았다.|
|일정·이력·반복|PASS|`schedule_seed=6102026`, 10블록, ABBA 5블록, BAAB 5블록, shallow/deep 각 20호출, 총 40호출과 20개 metadata가 재구성됐다. 모든 40개 slot에서 `role_id == direction == variant`였고 반복 간격은 1 또는 3이었다. 이전 호출과 조건을 기록하되 reset이나 cache 통제를 주장하지 않는다.|
|측정·누락·공동 성공|PASS|`shallow_success`는 조건과 무관한 최소 깊이 선택이고, `instruction_fulfilled`는 shallow/min 또는 deep/max를 기준으로 한다. `role_match`는 후자와 같다. ID-only 응답의 `D`, `actual_D`, `proof_valid`, `strict_valid`는 null이다. 미실행·파싱 불가·미측정은 0으로 바꾸지 않으며, 양쪽 지시 성공과 ID 변화의 동시 충족을 별도 집계한다.|
|증거와 독립 재계산|PASS|생산 감사는 원요청·원응답·metadata·event chain·status·source snapshot·plan을 대조한다. 독립 검산기는 v061 생산 요청·채점·집계·실행 모듈을 import하지 않고 일정, 요청, 측정, 집계, JSON 보고서와 한국어 요약 바이트를 다시 만든다. 삭제·변조·누락·중복·추가 파일·재해시 위조 반례가 시험에 포함돼 있다.|
|실행기·manifest·fresh extraction|PASS|runner는 40호출 상한과 무재시도 정책을 고정하고 transport 또는 identity 오류에서 중단한다. 부분 실행과 실패 위치를 보존한다. ZIP manifest와 fresh extraction의 파일 집합·해시가 일치했고 별도 fresh 자체시험 33개가 통과했다. Windows PowerShell 5.1 `CheckOnly`는 `-SkipSelfTest`로 실행해 자체시험을 건너뛰고 실제 v060 재분석, v058 검증, 계획 prepare/show를 마쳤으며 Ollama를 시작하거나 추론하지 않았다.|
|기존 파일 보존과 문서 판본|PASS|v060 r2의 312개 파일이 바이트 단위로 보존됐다. 문서는 v060 r1 감사가 r2 전체에 자동 적용되지 않는 판본 공백, v061의 네 공동 프로필, 단일 문제, 대안 설명, 과도한 일반화 금지를 명시한다.|

동결된 CheckOnly 계획의 내부 `plan_sha256`은 `6ac771e951f25681ecc614230aaf8dfd14de371fe13d62c0bbe5609d4533d58d`이다. 계획 JSON 파일 자체의 SHA-256은 `d26b98bd30ca4c69f184bbb9b39cea2345591033a187eaab65877d8b576b99fd`로, 두 값의 대상이 다르다.

## 발견사항

`F01`은 당시 차단성이었으나 최종 ZIP에서는 해결됐다. 초기 자체시험은 독립 검산기가 slot을 재구성할 때 조건별 `role_id`를 반영하지 않아 3개 시험에서 `reconstructed schedule` 오류가 났다. 봉인된 [verify_v061.py](../validation/fresh_r1/llm_experiments/v061/probe/tools/verify_v061.py#L127)는 `direction`과 `role_id`를 모두 `variant`에 맞춰 재구성한다. 생산 작업본 33개 시험과 fresh extraction 33개 시험이 모두 통과했고, 별도 계획 재구성에서도 40개 slot 전부가 계약과 일치했다. 봉인본에는 추가 조치가 필요 없다.

`F02`는 비차단·미관측 사항이다. 이번 감사에서는 v061 실제 LLM 추론, Ollama 시작, 모델 다운로드와 현재 runtime identity 검사를 수행하지 않았다. `CheckOnly`와 자체시험은 소스 준비 상태를 검증하며 v061 과학 결과를 만들지 않는다. 실제 실행 때는 새 실행명과 동결 계획을 사용하고 40개 원호출, 20개 metadata, 생산 감사와 독립 evidence 검산이 모두 끝난 뒤 결과를 해석해야 한다.

`F03`은 비차단·열린 한계다. [verify_v061.py](../validation/fresh_r1/llm_experiments/v061/probe/tools/verify_v061.py#L20)는 v061 생산 모듈을 import하지 않지만 보존된 `verify_v058`, `independent_graph_forensic`, `independent_verify_v057`을 재사용한다. 생산 구현과는 분리됐으나 공유 사양이나 이전 독립 유틸리티의 공통 결함 가능성까지 없앤 것은 아니다. 더 강한 보증이 필요하면 미래 evidence를 별도 구현의 parser와 graph-depth 계산기로 다시 검산해야 한다.

`F04`는 비차단·미관측 사항이다. [V060_ANALYSIS.ko.md](../validation/fresh_r1/llm_experiments/v061/probe/docs/V060_ANALYSIS.ko.md#L92)에 적힌 검토 도구 worker의 실제 내부 모델 설정은 확인되지 않았다. 이 정보는 독립성이나 과학 결과의 근거로 쓰지 않았으며, 감사자 역할 분리와 직접 검사한 파일·로그·계산만 판정 근거로 삼았다.

## 보증 한계

이 PASS는 소스 배포본이 동결 계약을 구현하고 새 위치에서 오프라인·합성 시험을 통과했다는 뜻이다. 실제 v061 모델 응답이나 현재 서버 상태를 보증하지 않는다. v061 실행 경로 시험의 HTTP 서버와 응답은 합성 fixture이며, 실제 v058·v059·v060 evidence는 보존 기록을 대상으로 한 별도 오프라인 검산이다.

해시와 event chain은 기록의 내부 일관성을 보이지만 외부 실행을 인증하지 않는다. `implied_depth`는 선택한 규칙을 외부 규칙 그래프에 적용한 값이고 생성 증명의 실제 D가 아니다. metadata 경계는 모델 상태나 cache를 초기화하지 않으며 첫 호출에도 이전 서버 이력이 있을 수 있다. K01 한 문제의 반복 결과는 모집단 성능, 다른 문제·모델·지시 문구 또는 모델 내부 기제로 일반화할 수 없다.

봉인 대상에 차단 결함이 없으므로 source release gate는 PASS다. 이후 ZIP 바이트나 의미 있는 실행·측정·검산 계약이 바뀌면 영향받은 축을 다시 감사해야 한다.
