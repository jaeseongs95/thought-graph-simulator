# v064 최종 검증서

**완료: 연구 복귀 설계·실행 소스·오프라인/합성 검증·독립 소스 감사. 실제 v064 모델 실험은 미실행이다.** 실제 전달 파일은 `releases/v064_direct_D_source_r3.zip`이며 r1/r2는 교정 전 감사 기록이다.

## 결정과 연구 범위

[연구 복귀 결정서](../probe/docs/RESEARCH_RETURN.ko.md)에서 세 독립 초기 관점과 교차검토, 남은 반론, 세 후보 비교를 확인할 수 있다. Qwen의 v058 유효 얕은 구성20/20을 출발점으로, 같은 문제의 shallow/deep 지시가 실제 유효 증명의 최소/최대 D에 대응하는지 확인하는 18호출을 선택했다. Gemma/K01 진단 분기는 이어가지 않는다. 지정 구성 선행 게이트가 필요하다는 측정 관점의 반론은 보존했다.

논문 TTS v1.0과 제한 simulator 코드북을 구분했고, 이번 A/M은 미측정이다. 이번 설계는 원 질문 중 선택적 D 제어에 직접 연결되지만, 소스 검사·합성 정답은 모델의 제어 성공 증거가 아니다. E01/E02는 설계자 선정의 사전 모델 응답 미관측 구조이며 외부 독립 holdout이 아니다. T02는 개발 회귀다. 일반화·비용 절감·큰 모델 동등 성능·내부 hidden layer 제어는 미검증이다.

## 증거 종류별 결과

|종류|실제로 확인한 것|근거|
|---|---|---|
|원자료|v058 Qwen graph20/20 D1, choice15/20; v061 k03 40/40; v062 graph0/40 및 문자열39/40; v063 조상 밖 오류진단은 재채점 아님|[원자료 대조](EVIDENCE_MAP.ko.md), [교정 집계](raw_crosscheck_corrected.json)|
|이전 단계형|NOT 실제 값→AND 전달4/4 대조. 틀린 중간값·국소 정합·우연한 최종 정답과 전체 실패 분리|[전달 검사](staged_transfer_check.json), [반례](staged_adversarial.json)|
|실행·측정 소스|계획 동결, 원문·metadata·event 보존, 무보정 proof/D, 중단·충돌 처리, 한국어 보고, 별도 의미 계산의 독립 검산, Windows 자동화|[소스 안내](../probe/README.md), [동결 프로토콜](../probe/docs/PROTOCOL.ko.md)|
|코드·합성 검증|최종19 tests 통과. 선택적 정답 승인, 고정/반대 D 거부, 잘못된 부모·순서·미관측, 재해시 변조, 중단자료 보존, 실제12,674,642-byte 중첩 입력·한글·공백·native stderr/exit 확인|[통합 로그](integration_r3.log)|
|최종 ZIP 실행|새 빈 폴더 추출 후 Windows CheckOnly19 tests 및 무추론 plan 생성 exit0|[새 폴더 로그](fresh_source_r3.log), [검증 기록](fresh_validation_r3.json)|
|실제 모델|이번 개발의 실제 추론0회. 모델 다운로드·갱신·서버 시작 없음|계약 및 실행 로그; 합성 provenance와 구분|
|연구 가설|v064의 실제 D 결과, A/M·통합 성과는 미관측|사용자 별도 실행 후 판정|

r1의 합성 정상18호출과 r2의 정상/중단 재현, r3의 pending 재현은 가짜 로컬 HTTP 실행이다. 자체시험 재실행과 원자료 재집계를 독립 연구 표본이나 실제 모델 비용으로 더하지 않았다.

## 발견·교정과 독립 감사

초기 임시 집계의 필드 오류, 부분 자료 분모, runner/report 필드, 위상순서·비유한 수·native 검사 환경 문제는 [개발 교정 기록](CORRECTIONS.ko.md)에 보존했다. 실행하지 않은 수정 전 재현을 실행했다고 기재하지 않았다.

|감사 finding|교정과 최종 상태|
|---|---|
|r1 F001: 조기 오류 후 계속된 재서명 실행 승인|모든 action의 첫 중단 사유와 후속 시작 부재 검사. r2에서 resolved, r3 무변경 영역 재사용|
|r1 F002: 생성 상한 초과의 정상 stopped 검산 실패|초과 관측을 보존하고 중단·후속 부재로 검산. r2에서 resolved, r3 무변경 영역 재사용|
|r1 F003: event 전 원문 보존 실패|한 pending action의 제한된 미확정 자료 보존·미채점. r3에서 resolved|
|r2 F001: response 없는 후행 record 허용|완전 request/response 쌍 뒤에서만 pending record 허용. r3에서 resolved|

[첫 감사](SOURCE_AUDIT.ko.md), [r2 재감사](SOURCE_AUDIT_R2.ko.md), [최종 r3 감사](SOURCE_AUDIT_R3.ko.md)의 판정과 반례를 보존했다. 최종 감사는 설계·구현에 참여하지 않은 `/root/v064_source_audit`가 수행했다. requested model/effort는 gpt-5.6-sol/high이며 도구 반환이 실제 설정을 확인하지 않아 적용 상태는 unverified다. 역할·독립성과 검토 내용의 실제 호출/자료 근거로 판단했다.

보증은 cooperative-sealed / sealed-artifact-v1이다. 감사자는 최종 전체19검사·Windows 검사를 반복한 것이 아니라 결속 로그를 대조하고 변경 반례를 직접 검사했다. 이전 무변경 검토를 재사용했다. 외부 실행 인증이나 같은 OS 사용자 권한의 악의적 writer 방어를 주장하지 않는다.

## 최종 동일성과 실행

- source ZIP SHA256: `238b4997ceaa4191fb79498cc12647010bd02056cf7ac96a0ca0752712ff4553`
- source16개: ZIP member·현재 probe·새 폴더가 바이트 단위로 일치한다.
- 결정적 rebuild가 동일하며 감사 전후·최종 전달 hash가 일치한다. 감사 결과를 넣기 위해 ZIP을 다시 만들지 않았다.
- 보호 입력153개 해시가 모두 동일하다. 기존 v063 사용자 작업을 보존했다. tracked git diff 검사는 통과했다.

실제 실행은 [Run-v064.cmd](../probe/windows/Run-v064.cmd)를 더블클릭한다. 무추론 검사는 README의 `-CheckOnly -NoPause` 명령을 사용한다. 별도 폴더에서는 `-Baseline`으로 보존된 v058 입력을 지정한다. 사용자 실행의 최대 추론은 **18회**, 생성 설정 합계는 **73,728 tokens**이며 실제 사용량 보장은 아니다. metadata12묶음은 추론과 별도로 기록한다. 자동 재시도·모델 변경·다운로드는 없다.

여섯 directed 쌍 모두 유효 최소/최대 D면 D-only 검사를 끝내고 제한된 A 또는 M 대조 설계로 이동한다. 유효한 같은/반대 D이면 선택적 대응 불충족이다. 깊은 유효 구성이 전혀 관측되지 않으면 구성/선택 원인을 미분리로 남기고 별도 최소 구성 질문의 필요성을 판단한다. 미완료·파싱 불가이면 전체 진입 판정을 보류한다. 어떤 경우에도 이 배치에서 문구 튜닝·추가 호출을 자동 실행하지 않는다.

미확정 원문은 의미 채점을 하지 않으며, not_observed는 완료 관측 레코드가 없다는 뜻이다. 손상된 committed JSON/torn event를 임의 복구하는 도구는 아니다. 모든 가능한 물리적 중단 바이트 위치와 실제 제공자 장애는 열거 검증하지 않았다.
