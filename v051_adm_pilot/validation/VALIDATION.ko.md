# 실제 수행한 검증 기록

## 환경과 구분

시험 환경은 Linux, Python 3.13.5다. 사용자 Windows·PowerShell에서 새 코드의 실제 실행을 수행하지 않았다. 기존 CP949/UTF-8 subprocess 처리 및 관련 회귀시험을 보존했다. 실제 Qwen 모델에 새 추론 요청을 보내지 않았다.

아래 합성 HTTP 시험은 실제 HTTP 요청·응답과 파일 보존·감사를 수행한 테스트 서버 실행이다. 응답은 테스트 fixture가 생성하며 모든 증거에 `synthetic_fixture` 출처가 들어간다. 실제 모델의 성공 표본으로 사용하지 않는다.

## 사용자 v050 원문

사용자의 v050 ZIP에서 manifest 파일1,169개, HTTP560건, 부모 연결400개를 검사했다. 기존 v050 감사기의 전체 report 재계산이 저장된 report와 일치했고, 별도 정답 계산과 층별 원문 분석이 일치했다. 관련 소스·로그는 별도 v050 분석 ZIP에 있다.

최종 v051 코드로 사용자 v050 ZIP을 수입해 `prepare`를 실제 실행했다. `REAL_BASELINE_PREPARE.log`와 `.exit`에 결과가 있다. 최대240호출, 12역할, 기존10seed, 같은 모델·옵션을 가진 계획이 만들어졌으며 종료0이다. 이 단계는 실제 모델 추론을 하지 않는다. 해당 환경에서 만든 계획 파일 자체는 사용자용으로 배포하지 않는다. 사용자의 환경에서 다시 동결하도록 한다.

## 전체 시험

`FULL_SELFTEST.log`: **417개, 126.645초, OK, 종료0**.

구성은 기존 v047~v050 회귀322개와 신규 v051 시험95개다. 시험 개수는 실제 실행 로그에서 집계했다. 서로 다른 논리 문제417개를 실제 LLM이 풀었다는 뜻이 아니다.

`INITIAL_NEW_SELFTEST.log`는 초기 신규64개 시험 통과 기록이다. 그 뒤 경계·CLI 시험31개를 추가했다. `INTERRUPTED_NEW_SELFTEST.log`는 도구 실행 시간 제한 때문에 종료 기록이 없는 중간 실행이며 완료된 성공 시험으로 세지 않는다. 이후의 완료된 전체417개 시험이 최종 기준이다.

## 수정 전후 같은 반례

`REVIEW_BEFORE_FIX.log`: 네 반례 중 assertion failure3개, missing-field error1개, 종료1.

`REVIEW_AFTER_FIX.log`: 같은 네 반례 모두 통과, 종료0.

문제는 뒤쪽 형식 오류가 앞 단계의 유효한 측정을 지우는 경로와, 전체 의미 유효성에만 의존하는 비교 보고였다. 부분 측정을 유지하되 전체 성공 요건을 유지하도록 고쳤다. 자세한 내용은 `docs/REVIEW_AND_FIXES.ko.md`에 있다.

## 전체 규모 합성 HTTP 실행

정상 생성 시나리오: 실제 HTTP240건. 12조건 모두20/20 유효·역할 부합, 총240/240.

M2 오류 주입 시나리오: 별도 실제 HTTP240건. 유효한 증명과 표현240/240은 유지되지만 M2 finding이 틀린80건은 전체 성공으로 승인하지 않아 총160/240이다. 네 M2 역할은 각각0/20이다. A의 구조·대상 조작 관측은120쌍이지만 전체 의미까지 유효한 A 조작은80쌍이다. 부분 관측과 전체 성공을 혼동하지 않는지 확인했다.

`SYNTHETIC_REPRODUCTION.log`, `SYNTHETIC_VALIDATION.exit`(0), `perfect_evidence.zip`, `wrong_m2_evidence.zip`를 동봉한다. 두 ZIP은 모두 합성 증거다.

## 서버 종료 후 재검사

테스트 서버를 종료한 뒤 별도 Python CLI 프로세스로 정상 실행 원문을 오프라인 재감사했다. 실행 직후 report 전체와 일치했다. 로그는 `OFFLINE_AFTER_SERVER_EXIT.log`다.

생산 코드·생산 정답표를 import하지 않는 `independent_check.py`로 두 합성 ZIP을 각각 재검사했다. 각 manifest537개 파일, HTTP240개, 외부 문제 고정, event chain, 요청·응답 해시, 실제 proof DAG, schema 치환·가정·진리값 검사, M target 및 finding을 계산했다. `INDEPENDENT_PERFECT.json`은240/240, `INDEPENDENT_WRONG_M2.json`은160/240이며 생산 보고서와 일치했다. 같은 작성자가 만든 분리된 검사기이지, 외부 학술 심사자의 독립 구현을 확보한 것은 아니다.

## 기존 파일 보존

`COMPATIBILITY.json`: v047/v048/v049/v050 코어 및 test_support의 Python 파일37개가 기존 v050 배포 ZIP과 바이트 단위로 같았다. 핵심 과거 성공·실패 채점기를 수정해 새 결과에 맞춘 것이 아니다. 신규 코드는 `adm_pilot_v051`에 추가했다.

## 배포 ZIP 검사

배포 ZIP을 별도 새 폴더에 푼 뒤 **417개, 125.252초, OK, 종료0**으로 재시험했다. 새 폴더의 코드로 두 합성 증거 ZIP도 각각 오프라인 재감사해 240/240 및160/240 역할 성공이 재현됐다. `RELEASE_SELFTEST.log`, `RELEASE_SELFTEST.exit`, `RELEASE_CHECK.json`에 기록했다. 시험한 Python·PowerShell 파일은 최종 소스와 전부 바이트가 같았다. 마지막 재패키징에서는 로그·문서만 추가하며 프로그램 코드는 변경하지 않았다.

해시 manifest는 배포 파일 일관성 점검용이다. 모든 파일과 hash를 함께 바꿀 수 있는 공격자를 막는 서명 체계는 아니다.
