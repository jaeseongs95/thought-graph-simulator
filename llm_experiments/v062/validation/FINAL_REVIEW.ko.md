# v061 분석과 v062 소스 제작 최종 결과

v061 원자료 검증, 연구 방향의 독립 관점 검토와 교차검토, v062 소스 작성, 오프라인 통합 검증, 최종 배포본의 독립 소스 감사를 완료했다. 실제 v062 모델 추론은 실행하지 않았다.

## 연구 결과와 방향

v061은 40회 모두 `k03`를 출력했다. shallow 지시 이행은 20/20, deep은 0/20, 양 조건의 선택 ID 변화는 0/20이다. 독립 검산은 882개 필드와 기준선 1,649개 필드를 대조해 불일치를 찾지 못했다. 이것은 기록의 내부 일관성을 확인한 결과다. 실제 증명 깊이와 A/M은 v061 choice 과제에서 측정하지 않았다.

지금까지의 실험은 선택 오류를 좁히는 진단으로 의미가 있었다. 같은 K01에서 규칙 ID만 고르는 대조를 계속 늘리는 것은 원래의 실제 증명 깊이 연구에서 멀어질 수 있다. 따라서 v062는 마지막 규칙을 지정한 작은 증명 DAG 생성으로 전환했다. 이 선택에 반대하는 ‘같은 choice 형식의 ID 복사 대조 우선’ 의견도 분석 문서에 보존했다.

v062는 지정된 규칙까지 유효한 풀이를 구성하는지 확인한다. 성공해도 모델이 자유롭게 깊이를 선택했다는 결론은 내리지 않는다. 40회 모두 strict 유효·지정 규칙 일치·기대 실제 D를 충족하고 10개 seed가 반복 안정적일 때만, 별도의 자유 깊이 지시 실험을 준비할 수 있다. 부분 실행의 판정은 null로 남긴다.

## 산출물

- 분석·경쟁 의견·교차검토: `../probe/docs/V061_ANALYSIS.ko.md`
- v062 사전 질문·측정·종료 기준: `../probe/docs/V062_PROTOCOL.ko.md`
- 실행 안내: `../probe/README.md`
- Windows 실행: `../probe/windows/Run-v062.cmd`
- 배포 소스: `../releases/v062_construction_source_r1.zip`
- 독립 소스 감사 원문: `SOURCE_AUDIT.ko.md`, `source_audit_result.json`

실행 파일을 일반 모드로 실행하면 실제 모델을 40회 호출한다. 준비만 검사하려면 `-CheckOnly -NoPause`를 사용한다. 배포 ZIP에는 v057~v062 상대 경로를 유지한 소스를 포함하고, 연구 evidence ZIP과 모델 가중치는 포함하지 않는다.

## 확인한 검사

|검사|결과|근거|
|---|---|---|
|v061 원문·계획·측정 재검산|40 calls / 20 metadata, differences=[]|`v061_reanalysis.json`|
|실제 기준 요청 격리|10 seed의 A/B 요청 20개에서 생산/독립 바이트 일치, target ID 한 곳만 다름|`request_isolation_real.json`|
|재분석기 반례|네 패턴, 미관측 null, 미완료 비율 null, 중복 거부: 7/7|`analyzer_regression.json`|
|원본 소스 전체 검사|27 tests, exit 0, 72.967초|`producer_integration_selftest.log`|
|Windows 준비 전용 실행|실제 v058/v061 입력의 재분석·prepare/show 통과, 실제 추론 없음|`windows_checkonly.log`|
|배포 manifest·보존|360파일, 기존 336개 바이트 보존, 신규 v062 24개|`release_validation.json`|
|새 빈 폴더에서 최종 ZIP 자체시험|27 tests, exit 0, 73.175초|`fresh_source_selftest.log`|
|새 감사자의 추가 검사|생산 DFS/독립 Kahn 무작위 DAG 5,000개 불일치 0, 분석기 7개 재현|`source_audit_result.json`|
|소스·입력 범위|기존 evidence 불변, manifest와 현재 소스 일치, CheckOnly 계획 지문과 최종 소스 일치|`scope_check.json`|

27개 시험에는 정상 40회 합성 실행→감사→증거 ZIP→독립 검산, 부분 실행, 형식·파싱·논리 오류, 부모·규칙·순환 반례, 요청·event·snapshot·측정·요약문 재해시 변조 거부가 포함된다. 합성 E2E의 v058 receipt는 fixture로 대체했고, 실제 v058 evidence의 독립 검증은 별도의 Windows CheckOnly 및 실제 요청 검사에서 확인했다. 합성 실행은 로컬 fake HTTP를 사용했으며 실제 모델 결과로 집계하지 않는다.

## 최종 감사와 남긴 한계

일반 검증과 ZIP 고정 뒤, 앞선 분석·구현·통합에 참여하지 않은 새 감사자가 C1~C8을 확인했다. `audit_state=completed`, `candidate_completion=complete`, blocking 0건, diagnostic 1건이다. 보증 범위는 `cooperative-sealed` / `sealed-artifact-v1`이며 외부 서명 인증이나 같은 OS 사용자 권한의 의도적 조작 방어를 주장하지 않는다.

**V062-SA-D01은 채택하되 비차단 잔여 항목으로 남겼다.** 독립 검산기는 `invalid_response`/`invalid_payload_schema`의 사람이 읽는 `parse_error` 설명 문자열을 정확히 재구성하지 않는다. 감사자는 설명을 바꾸고 manifest를 재해시한 합성 ZIP이 수용되는 반례를 재현했다. 원응답에서 계산하는 상태·형식·증명 유효성·D·집계·진입 판정에는 영향이 없지만, 오류 설명 문구까지 독립적으로 검증됐다고 주장해서는 안 된다. 오류 원인을 조사할 때 원응답과 재감사를 기준으로 삼는다. 다음 소스 개정에서 안정된 파싱 오류 분류를 결속하는 보강을 권고하며, 현재 r1을 수정해 감사 결과를 다른 후보에 옮기지 않는다.

독립 관점 패널과 최종 감사에 요청한 모델·추론 설정의 실제 적용값은 도구에서 반환하지 않아 미확인이다. 최종 감사자는 통합 문서의 경쟁 논거와 원자료를 검토했고, 패널 원시 대화의 출처까지 별도로 인증하지는 않았다.

## 판본 결속

최종 소스 ZIP SHA256:

`33830e414b93174b2fbc36ec46d4675ab8e15321abd5608db301a487d8561da4`

감사 입력 SHA256:

`68cb9d0d67dfbdb3bf0c55805d55b57401b1a0bb677fba317cd0d010e5ab185b`

감사 결과 JSON SHA256:

`bd05242f7bd5a6afbecd00b74bb96eb899d73ce2f67a8b5909acd58a005c3fe4`

감사 이후 최종 ZIP·현재 소스·기존 입력의 재확인과 진단 항목 처리 기록은 `completion.json`에 결속한다. 실제 v062 모델의 과제 수행 결과는 아직 미측정이다.
