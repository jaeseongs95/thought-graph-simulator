# v055-r2 계획 JSON 크기 오류 교정

## 관측

Windows 실제 실행에서 `capture`와 `prepare`는 완료됐지만 `run` 시작 직후 `ContractError: JSON 크기 한도를 넘었습니다.`가 발생했다. PowerShell은 run 폴더의 `status.json`을 찾지 못하고 마지막 정상 자료인 `capture.json`을 표시했다. 이는 추론 전 `execute()`의 첫 `read_json(plan_path)`에서 중단되는 형태와 일치한다.

## 원인

공용 `paired_probe_v049.contracts.strict_json()`은 네트워크/응답 방어용으로 JSON 하나당 8 MiB 상한을 둔다. v055 계획은 모델 metadata capture 원문, compact identity, 이전 v054 기준선 계획/요청 영수증을 한 파일에 함께 동결하므로 실제 모델 metadata에서 8 MiB를 넘을 수 있다. `prepare`의 `write_json()`에는 이 상한이 없어 큰 계획을 쓸 수 있지만, `run`의 `read_json()`이 같은 파일을 다시 읽으면서 거부했다.

## 교정

- 기존 공용 8 MiB `strict_json`/`read_json`은 변경하지 않는다.
- v055의 **로컬 plan/snapshot 전용** 엄격 파서 `strict_plan_json`/`read_plan_json`을 추가한다. 상한은 32 MiB다.
- 중복 키, 비유한 숫자, JSON 문법 오류 검사는 기존과 동일하게 유지한다.
- runner/audit/show의 v055 plan 읽기에만 새 파서를 사용한다.
- prepare가 파일을 기록한 직후 새 파서로 재읽어 canonical equality를 확인한다.

## 바뀌지 않은 것

문제, 규칙, 규칙 순서, shallow/deep/neutral 지시, 10개 seed, 두 모델, sampling option, 240회 배정, 요청 생성, 증명 채점, 모델 비교 지표, metadata identity gate, HTTP fail-closed, 자동 재시도 금지 정책은 변경하지 않았다. 모델 응답 JSON은 계속 기존 8 MiB 제한을 적용받는다.
