# v052 r2 실행 실패 진단 교정

## 확인된 r1 문제

r1 runner는 `runtime.before` metadata/identity 검사에서 실패하면 예외를 잡아 `status.json.error`에 저장하고 `audit_run()`을 호출했다. 감사 결과에는 `run_error`가 들어 있었지만 CLI는 이를 출력하지 않았다. 따라서 사용자는 `data_complete=false`, `inference_calls=0`, Exit 3만 보고 실제 중단 원인을 알 수 없었다.

이 결함은 연구 결과의 오답이 아니라 실행 진단 정보의 은폐 문제다. r1의 fail-closed 중단 자체는 의도에 맞았다.

## r2 변경

1. runner가 현재 실행 단계를 `active_stage`로 기록한다.
2. 실패 시 `failure_stage`, `failure_kind`, `failure_slot_id`를 고정한다.
3. audit가 이 진단 필드의 자료형과 단계/종류 조합, 전송 오류 이벤트와의 일관성을 검사한다.
4. CLI와 `summary.ko.md`가 `run_error`를 포함한 중단 원인을 출력한다.
5. PowerShell wrapper도 `status.json`을 읽어 마지막 throw에 원인을 포함한다.
6. 기존 실패 폴더를 덮어쓰지 않도록 r2 기본 RunName을 `v052_adm_02`로 바꾼다.

## 바꾸지 않은 것

- 440개 슬롯과 task 배분
- K01/T02
- seed 10개
- 모델/샘플링 옵션 상속
- A/D/M 정의와 role-match 계산
- neutral/copy_control/graph_only의 분모 구분
- 잘못된 모델 출력을 호스트가 교정하지 않는 정책
- 통신 오류 자동 재시도 금지
- 모델 digest/show/server version identity gate

따라서 r2는 실패를 통과시키는 수정이 아니라, 같은 실패를 더 정확히 분류하는 수정이다.

## 현재 사용자 로그에 대해 말할 수 있는 범위

`inference_calls=0`이므로 첫 정상 추론 이전에 중단된 것은 확인된다. r1 로그만으로는 Ollama 미접속과 runtime identity 불일치를 구분할 수 없다. 실제 r1 `results_llm/v052_adm_01/status.json`의 `error`를 보면 당시 원인을 바로 확인할 수 있다.
