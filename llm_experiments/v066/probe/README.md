# v066 — 직접 증명 생성 대 모델 원계획 전달

v065 지정 규칙 단일 호출 구성은 0/12였다. 그 분기를 종료하고, 원래 shallow/deep 지시만으로 **직접 생성**과 **모델 경로 계획→그 원문을 받은 모델의 증명 작성**을 비교하는 새 실행 계약이다. 모델이 택할 규칙을 호스트가 지정하지 않는다.

## 휴대폰 원격 실행

배포된 `Run-v066-Auto.ps1` 한 파일을 PC 다운로드 폴더에 저장하고 실행한다. 소스 ZIP이 내장돼 있어 별도 ZIP 다운로드/압축 해제가 필요 없다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v066-Auto.ps1"
```

자동화는 현재 경로, `D:\codex\AI논문\thought-graph-simulator`, 바탕화면 저장소를 확인한다. 기준선은 **v065_construct_20260913_181003_418911_evidence.zip**, SHA-256 `5fdba7ace2bfe29dc9b5d4f30d75bf32d7963ed82943afe77f5de6e087a6ff09`다. 저장소의 `llm_experiments/v065/results_llm`, `results_llm`, 다운로드 폴더에서 해시까지 같은 자료를 찾는다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Run-v066-Auto.ps1 -RepoRoot 'D:\내 저장소\thought-graph-simulator' -Baseline 'D:\결과\v065_construct_20260913_181003_418911_evidence.zip'
```

`-CheckOnly`는 실제 Ollama 조회·추론 없이 자체시험과 원문 감사·계획 준비만 한다. 기본 자체시험은 `test_logic.py`이며 `-AllTests`는 합성 HTTP/중단/변조/설치 시험까지 포함한다. 실제 모델을 다운로드·갱신하거나 서버를 시작하지 않는다. 기존처럼 Ollama가 켜져 있어야 한다.

## 36회의 뜻

3문제 × 2seed × 2방향 = 12개 조건이다.

|방식|조건당 호출|전체 호출|
|---|---:|---:|
|direct|기존 D 지시로 전체 증명 생성 1회|12|
|staged|규칙 목록 계획 1회 + 그 원문을 전달받은 증명 생성 1회|24|
|합계|—|36|

총 **36회**다. 같은 문제·목표·규칙 순서·모델·옵션·seed를 유지한다. direct 요청은 실제 v064의 해당 방향 요청과 바이트 동일하다. staged는 추가 프롬프트와 한 번 더 호출하는 **시스템 비교**다. 동일 계산 예산이나 토큰 절감 검증이라고 해석하지 않는다.

첫 호출의 `message.content` 문자열을 공백·줄바꿈·잘못된 규칙·깨진 JSON까지 그대로 다음 호출의 `route_plan_response.content`에 넣는다. 원 HTTP 응답도 별도 파일로 저장하고 SHA를 함께 결속한다. 호스트가 rule_ids를 수정·정렬·선택하거나 정답 깊이/노드/부모 연결을 넣지 않는다. envelope에 내용이 없으면 null로 전달하고 미측정으로 기록한다.

## 판정 경계

1차 계획은 `rule_ids` 목록으로 평가한다. planned_D는 문제 규칙을 이용한 사후 계획 진단값이며 실제 증명 D가 아니다. 2차의 actual_D는 이전과 같은 strict 증명 평가기로 원 DAG에서만 계산한다.

staged 종단 성공은 **유효하고 요구 깊이에 맞는 모델 계획 + 그 계획 원문 전달 + 규칙 순서까지 그대로 따르는 strict 증명 + 최종 실제 D 이행**을 모두 요구한다. 틀린 계획 뒤에 모델이 알아서 다른 정답을 만들면 최종 그래프의 국소 성공은 보존하되 종단 성공은 아니다. 파싱 불가와 미실행은 논리 오답으로 채우지 않는다.

같은 문제·seed의 shallow/deep 두 조건을 모두 이행해야 대응쌍 성공이다. 방식별6쌍이다. 6/6은 이 고정 문제의 제한된 다음 단계 검토 기준이지 일반적 A/D/M 증명, hidden layer 제어, 비용 우월성이 아니다. 이전 v064/v065 실패를 소급 변경하지 않는다.

## 안전한 운영

기존 소스와 evidence는 변경하지 않는다. 같은 v066 설치본도 전 파일의 바이트가 같을 때만 재사용한다. 다르면 보존 백업한다. 이미 실행한 계획은 `.started` 표지 때문에 다시 실행하지 않는다. HTTP/모델 identity/생성상한 오류는 멈추고 원문을 보존한다. 자동 재시도 또는 성공할 때까지 새 RunName 실행은 없다.

명시적 사용자 실행 후 출력 위치:

```text
llm_experiments/v066/experiments/v066_staged_<시간>.plan.json
llm_experiments/v066/results_llm/v066_staged_<시간>/summary.ko.md
llm_experiments/v066/results_llm/v066_staged_<시간>_evidence.zip
llm_experiments/v066/results_llm/v066_staged_<시간>_independent.json
```

## 개별 명령

```powershell
$env:V066_BASELINE='D:\보존 경로\v065_construct_20260913_181003_418911_evidence.zip'
python -X utf8 -B -m unittest discover -s tests -v
python -X utf8 -B run.py prepare --baseline $env:V066_BASELINE --run-name v066_manual --out ..\experiments\v066_manual.plan.json
python -X utf8 -B run.py execute --plan ..\experiments\v066_manual.plan.json --baseline $env:V066_BASELINE --out ..\results_llm\v066_manual
python -X utf8 -B verify.py ..\results_llm\v066_manual_evidence.zip
```

실제로 동결한 소스·반례·시험 로그는 별도 분석·검증 ZIP에 기록한다. 이 환경의 합성 HTTP 검증과 사용자 GPU의 실제 36회 모델 실험은 다르다. Windows 전용 native 시험이 실행되지 않았다면 그 범위를 명시한다.
