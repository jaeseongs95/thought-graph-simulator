# 개발 중 발견·교정 기록

이 기록은 새 개발 도구의 결함과 검사 환경 문제다. 이전 실험 계약·원문·공식 판정은 수정하지 않았다. 테스트 수와 합성 정답은 연구 가설의 증거가 아니다.

|항목|직접 관측한 수정 전 근거|교정·검증|
|---|---|---|
|임시 v058 원문 집계 필드|raw_crosscheck.json에서 rule_id로 읽어 KeyError를 실패로 잘못 분류|판본별 rule 필드로 raw_crosscheck_corrected.json 생성. Qwen T02 graph20/20 D1 복원. 이전 생산 채점 결함 아님|
|부분 자료 분모|partial_before_fix.json: 미관측 쌍 False, 문제 비율 0.0|미측정 None, 전체 비율 None. 미관측·파싱 불가 및 뒤 실패/앞 성공 보존 회귀|
|runner→report 입력 계약|첫 MAIN 통합 실행 RuntimeTests setUpClass에서 record must refer to one planned call slot 오류를 직접 관측(별도 로그 파일 없음)|finalize에서 kind 제거한 계약 필드만 전달. integration_round1.log 11개 통과|
|위상 순서|topological_before_fix.json: 원문 노드만 역순으로 바꿔도 strict=True D1|논리 유효성과 요청 준수 구분. non_topological_order로 strict=False/actual_D=null. reverse_nodes 합성 전배치 및 수동 사례|
|음수 사용량|소스 검사로 음수 수용 가능성을 발견. 수정 전 음수 실패 실행 로그는 없음|음수·불리언·비정수·누락은 null, 유효 0은 보존. 생산·독립 parity와 회귀|
|숫자 지수 overflow|nonfinite_before_fix.json: 1e999가 inf로 파싱됨|finite_float에서 비유한 수 거부. 양·음 overflow/NaN/중복 JSON 회귀|
|PowerShell 검사 실행 정책|integration_round2.log native stdout 누락; native_before_fix.json에 스크립트 실행 정책 차단과 함수 미정의 오류|테스트 프로세스만 기존 launcher와 같은 -ExecutionPolicy Bypass 적용, ErrorActionPreference Stop. 전역 정책 미변경. native_regression.log 통과|
|중첩 PowerShell 진행 출력|windows_checkonly_r1.log의 native stderr UTF-8 decode 오류. native_nested_before_fix.json에서 child stderr와 PowerShell CLIXML 진행 메시지 혼합 직접 관측. 재현 실행의 문구는 영어로 decode 오류 자체는 재발하지 않음|테스트 child를 NonInteractive/OutputFormat Text/ProgressPreference SilentlyContinue로 설정. 실제 stdout/stderr와 exit0/7 검사는 유지. 다음 CheckOnly 판본에서 재확인|
|프로토콜 직렬화|protocol_serialization_correction.json|CRLF→LF를 실제 모델 실행 전에 교정. JSON 값은 design_decision.json과 동일. 원 결정 기록 보존|

worker의 중간 통합 중 plan source fingerprint mismatch도 보고되었다. 이때 MAIN이 테스트·공통 IO·문서를 수정 중이었다. 해당 판본을 완료 증거로 사용하지 않는다. 최종 일반 검증은 모든 source writer가 멈춘 뒤 수행하고, 새 계획·새 실행·새 ZIP에 결속한다.

과거 단계형 코드의 실제 반례는 staged_adversarial.json이다. 잘못된 NOT 값을 그대로 전달하면 뒤 AND 국소 결과와 우연한 최종 공식 정답이 true여도 전체 valid_completion은 false다. 이번 직접 생성 실행기에 단계형 정답 보정 경로를 추가하지 않았다.
