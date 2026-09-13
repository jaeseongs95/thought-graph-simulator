# v060 소스 검증

분석과 v060 소스 제작·검증을 완료했다. 구현에 참여하지 않은 별도 감사자의 최종 판정은 **PASS**이며, 일곱 관점 모두 통과했고 차단·비차단 발견사항은 없다. 감사 후 ZIP 해시도 다시 확인했다. 실제 v060 모델 실험은 실행하지 않았다.

## 대상과 변경

후속 소스는 [v060_terminal_position_source_r1.zip](../releases/v060_terminal_position_source_r1.zip)이다. SHA-256은 `4fed2f1cd053bc6679246a7ad94649b811e8b549ef930d8e033aa39a405567c5`이며, manifest에 소스 파일 312개를 기록했다. 보존된 v057/v058/v059 의존성과 새 v060 코드를 포함한다.

새 v060은 `k10`을 마지막에 두고 `[k17,k03,k10]`과 `[k03,k17,k10]`을 비교한다. 기존 10개 seed, 조건별 두 반복, 40회 호출과 20개 metadata 수집 계획을 실행 전에 고정한다. 규칙 배열 밖의 원요청 바이트를 유지하며, 자동 재시도·재개·응답 교정·모델 다운로드는 하지 않는다.

선택의 유효성과 지시 이행을 분리하기 위해 `task_valid` 대신 `goal_reachable_choice`와 `instruction_fulfilled`를 기록한다. 전체 배열 위치와 `terminal_rank`를 함께 집계하고, 실제 증명의 D와 proof 유효성은 null로 유지한다. 구현과 별도 독립 계산기는 한국어 요약을 포함한 결과를 원자료에서 재계산한다.

## 분석 관점을 소스에 적용한 결과

|관점|검증한 소스 조건|직접 근거|일반 검증 판정|
|---|---|---|---|
|측정 정의|선택 ID의 implied_depth와 생성 증명의 D를 구분|`test_choice_depth_is_not_proof_depth`, 독립 채점 16경우|통과. actual_D/D/proof_valid/strict_valid=null|
|과제 이행|형식·도달 가능 선택·shallow 지시 이행을 분리|형식 오류/unknown/k10/k17/k03 반례, 새 측정 필드 변조 검사|통과. 파싱 불가 null, 유효하지만 지시 위반은 false|
|경쟁 설명|기존 두 예측은 동치, 새 두 배열에서는 반대|`test_v059_analysis_predictions_separate_only_in_new_arrays`, `test_frozen_hypotheses_make_opposite_joint_predictions`|통과. 내부 기제 확정은 하지 않음|
|인과·이력|균형 일정·반복·직전 호출·간격을 기록하고 순서 해석을 제한|`test_balanced_full_schedule_and_history`, 고정 일정 변조 거부, 프로토콜|통과. 캐시·고차 이력 제거는 미검증|
|표본·일반화|seed 10개·호출 40개·문제 하나와 누락 분모를 분리|`test_partial_summary_has_null_rates`, 반복과 조건 차이 구분 시험, 보고서|통과. 모델 전체 능력의 검증은 아님|
|증거·재현성|요청/응답·계획·소스·event 연결과 생산/독립 집계를 대조|정상/부분 fake HTTP 번들 검산, manifest 재해시 후 변조 거부, 새 ZIP 검사|통과. 공통 명세와 독립 유틸리티 의존, 외부 인증 부재는 남음|
|설계·구현 계약|배열 밖 바이트 보존, 생성기와 채점 분리, 중단·무재시도|바이트 변환 시험, AST import 검사, transport/identity 중단 시험, Windows CheckOnly|통과. 실제 v060 모델 호출은 미실행|

`instruction_fulfilled`, `goal_reachable_choice`, `terminal_rank`를 각각 그럴듯한 값으로 바꾸고 manifest 해시까지 갱신한 반례도 거부했다. 한국어 요약만 바꾼 경우, 요청·상태·파일을 누락하거나 잘못 연결한 경우도 시험했다. 실패한 감사를 기록할 때 report symlink를 따라 쓰지 않는 시험을 포함한다.

## 실제 실행한 검사

|검사|결과|근거|
|---|---|---|
|v059 원자료 재분석|v059 802필드, 기준선 1,649필드 비교, 차이 0|[v059_reanalysis.json](v059_reanalysis.json)|
|새 독립 채점기의 수동 기대값 대조|정상·오류 16경우 통과|[independent_measure_checks.json](independent_measure_checks.json)|
|원본 v060 자체시험|31개 통과, 구현 담당자 실행|작업 내 구현 담당자 결과 및 [task_record.json](task_record.json)|
|ZIP 생성·manifest 검사|312개 파일, 종료 코드 0|[release_build.log](release_build.log), [release_check.log](release_check.log)|
|새 폴더에 압축을 푼 v060 자체시험|31개 통과, 시험 출력 기준 74.545초|[extracted_r1_selftest.log](extracted_r1_selftest.log)|
|Windows 실행기의 CheckOnly|v059 재분석→v058 기준선 감사→현재 소스 계획 준비/검증 통과, 종료 코드 0|[windows_checkonly.log](windows_checkonly.log)|
|원자료 보존·후보 일치 검사|초기 입력 해시 유지, ZIP 312개 파일이 작업 소스와 일치|[scope_and_candidate_check.json](scope_and_candidate_check.json)|

Windows CheckOnly에는 `-SkipSelfTest`를 지정했다. 자체시험은 앞서 원본과 새 추출본에서 별도로 실행했다. CheckOnly에서 Ollama를 시작하거나 실제 추론을 수행하지 않았다. 개발 중 생산/독립 코드의 동시 변경으로 발생한 지문·구필드 불일치는 동기화 후 해소됐고, 최종 무수정 후보의 31개 시험은 모두 통과했다.

모의 HTTP 시험과 독립 채점 반례는 소프트웨어 검증이다. v059의 실제 관측이나 새 v060 연구 결과에 합산하지 않는다. 실제 v060 LLM 실험 및 그 실험의 실제 evidence ZIP 검산은 아직 수행하지 않았다.

## 독립 감사와 봉인

분석·설계·구현에 참여하지 않은 `final_source_audit`를 별도 컨텍스트에서 생성했다. 감사자는 봉인 ZIP, 새 추출본, 원자료와 위 검증 로그를 읽고 일곱 관점 및 필수 수용 기준을 대조했다. 소스와 ZIP은 감사 중 수정하지 않았다.

보증 범위는 `cooperative-sealed`다. 협력하는 실행자 사이의 후보 혼동을 줄이기 위해 같은 ZIP digest를 사용하고 감사 후 다시 확인한다. 별도 principal의 서명이나 host의 원자적 쓰기 차단을 제공하는 보증은 아니다. 모델·추론 설정은 `gpt-5.6-sol`·`high`로 요청했지만 도구 응답이 작업 식별자만 반환해 실제 적용 상태는 `unverified`로 기록한다.

독립 감사 결과는 [source_audit_r1.json](source_audit_r1.json)에 기록했다. 감사자는 원응답 40개, 새 일정과 요청 해시, 허용한 바이트 변화, 측정 진리표 및 거부 경계를 직접 확인했다. 추출본의 동일한 31개 시험도 다시 실행해 통과했다(80.451초). 같은 시험의 재실행이므로 시험 수를 더해 계산하지 않는다.

감사 기록 SHA-256은 `5d1393518873715975b8ef62e6741cd9a417470adcea25defb9c5b12bc86577b`다. 메인이 이 감사 기록의 바이트와 PASS·발견사항 없음·7축 PASS를 확인했고, 최종 ZIP digest가 감사 대상과 같은 `4fed2f1cd053bc6679246a7ad94649b811e8b549ef930d8e033aa39a405567c5`임을 재확인했다. 수정이나 재감사가 필요한 finding은 없었다.

## 남은 해석과 실행 범위

v059의 순열 민감성은 확인됐지만 첫 terminal·절대 두 번째·다른 배열 반응 중 내부 원인을 특정하지 못했다. v060은 `k10` 후치 배열에서 사전 예측을 비교한다. 첫 전체 항목, 마지막 terminal, 한 번의 순방향 읽기 등과의 동치가 남으며 v059의 기제를 그대로 재현했다는 뜻도 아니다.

한 문제의 choice 결과이므로 A/D/M 전체 제어 능력, 실제 증명 생성 깊이, 다른 모델이나 문제로 일반화하지 않는다. source fingerprint는 Python 소스의 바이트 보존을 검사한다. Python/Ollama 실행파일·하드웨어·backend·캐시를 모두 봉인하거나 외부 실행을 인증하지는 않는다.
