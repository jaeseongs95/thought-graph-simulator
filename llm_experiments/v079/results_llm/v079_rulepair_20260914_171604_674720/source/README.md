# v079 — 현재 규칙 명시의 짝대조

v078에서 관찰한 전제 연결 실패를 대상으로 하는 **한 배치짜리 생성 계약 진단**이다.
현재 규칙을 input에 다시 표시하는 효과를 검사한다. 선택기는 고치지 않으며,
H01~H04를 새 holdout으로 부르지 않는다. 실제 모델 성과는 실행 후 evidence로만 판단한다.

## 실행

기존 Ollama와 `qwen3:4b-instruct`가 이미 실행 가능한 상태에서 다운로드한 자동화 파일을 실행한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v079-Auto.ps1"
```

저장소 기본 탐색 경로: `D:\codex\AI논문\thought-graph-simulator`.
이전 v078 원 evidence ZIP을 Downloads 또는 저장소의 `llm_experiments\v078\results_llm`에 둔다.
자동화는 파일명에 `(1)`이 있어도 SHA-256으로 정확한 baseline을 찾는다.

```powershell
# 실행 전 오프라인 점검만 한다. Ollama 조회·추론·서버 시작 없음.
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v079-Auto.ps1" -CheckOnly -AllTests

# 기본 경로를 못 찾을 때만 명시한다.
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v079-Auto.ps1" -RepoRoot "D:\codex\AI논문\thought-graph-simulator" -Baseline "C:\경로\v078_p03_20260914_143647_122371_evidence.zip"

# 이미 시작된 배치가 있으면 재실행 대신 로컬 상태만 읽는다.
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v079-Auto.ps1" -InspectOnly
```

요구 환경은 Python 3.10 이상(사용자 기존 Python 3.12 사용 가능)이다. Python 외 패키지 설치는 필요 없다.
실험 identity는 첨부 v078의 모델 digest·Ollama version·template·native 설정을 그대로 고정한다.
모델/서버가 달라져 있으면 중단한다. 이 프로그램이 모델을 내려받거나 업데이트하지 않는다.

## 실험

|항목|base|explicit_rule|
|---|---|---|
|선택 원응답|한 조건의 동일 응답 공유|동일|
|facts/final 계약|v078과 동일|동일|
|rule 입력|기존 requested_rule_id|기존 필드 + requested_rule 객체|
|출력 스키마/예산/seed|v078과 동일|동일|
|부모 ID/연결·최종 graph 작성|모델|모델|

추가 필드는 해당 규칙의 `id`, `premises`, `conclusion`을 원 문제에서 그대로 복사한 것이다.
정답 부모 ID, 완성 node, binding 표, 후보 깊이를 제공하지 않는다. 원래 전제 목록의 **중복 표시**이지
새 논리 사실이나 정답 그래프 제공이 아니다. 정답 노드를 찾거나 history를 정리하는 호스트 처리는 없다.
틀린 중간 결과·선택도 원문 그대로 다음 단계에 전달한다.

공유 선택32회, 생성군별 본실험32건/참조16건/양방향16쌍이다. 총 증명96건.
최대 추론600회, 모두 목표 경로를 고르면584회, 매핑 가능한 선택의 최소 추론568회.
진행 슬롯616개는 metadata16개를 포함한다. metadata 한 슬롯은 최대3개 HTTP 조회다.
매핑되지 않는 선택은 종속 생성 호출을 건너뛰므로 실제 추론 수는 더 적을 수 있다.
군의 실행 선후는48개 공유 단위 중 각각24번씩 먼저 오도록 배정했다.

## 읽을 결과

`results_llm\v079_rulepair_<시각>\summary.ko.md` 및 `summary.json`을 읽는다.

1. 주 진단: 같은 선택에서 **선택 경로 전체 생성 충실성**, 별도 지정 경로 참조 구성.
2. 원 연구: 모든 단계·graph·경로·실제 D·요구 일치를 검사한 종단과 양방향 성공.
3. 같은 단위의 둘 다 성공/base만/명시군만/둘 다 실패/미측정과 순증.
4. 선택 방향과 유효한 graph 쌍의 forward/reversed/same/invalid/unmeasured 구분.
5. 문제별·규칙 수-D 관계별 결과와 공유 선택/생성군별 계측.

선택이 틀리면 올바른 증명을 만들었더라도 요구 D 종단에는 실패한다. 생성 개선을 선택 개선으로 쓰지 않는다.
같은 숫자의 총계라도 어떤 단위가 개선/악화됐는지는 `paired_comparisons`와 `trials`에 남는다.
`net_success_change`는 양쪽 모두 관측된 짝의 순증이다. 미측정이 있으면 전수 순증이 아니다.

## 실행·보존 원칙

설치 → 자체시험 → v078 오프라인 재감사 → 계획 동결 → 한 배치 실행 → evidence/독립 검산.
기본 실행은 핵심·계약·개입 시험을 먼저 수행한다. `-AllTests`는 전체 자체시험이다.
`-CheckOnly`는 계획까지만 만들고 started guard나 실제 추론을 만들지 않는다.
합성 시험의 성공은 실제 모델의 성과가 아니다. 합성 plan의 CLI 서버 실행은 거부한다.

결과 파일:

```text
llm_experiments/v079/results_llm/
  v079_rulepair_<시각>_evidence.zip
  v079_rulepair_<시각>_independent.json
  automation_logs/<run_name>/run.log
  frozen_batch.started.json
```

가드가 있으면 새로운 RunName으로 반복하지 않는다. 중단/실패 결과·원문·로그를 지우지 않는다.
v078 디렉터리/점수/가드는 변경하지 않는다. 정식 소스가 이미 설치되어 있으면 동일한 해시일 때만 사용한다.
독립 검산은 동일 증거의 다른 구현에 의한 확인이며 새 독립 실험 표본이나 외부 실행 인증이 아니다.

## 개발·검사

```powershell
$env:V079_BASELINE="C:\경로\v078_p03_20260914_143647_122371_evidence.zip"
python -X utf8 -B -m unittest discover -s tests -p "test_*.py" -v
python -X utf8 -B preflight.py
python -X utf8 -B verify.py "C:\경로\v079_rulepair_..._evidence.zip"
```

`design.py`는 요청 구성, `measure.py`/`stages.py`는 기존 의미 채점,
`report.py`는 생산 집계, `audit_*`/`verify.py`는 생산 모듈을 import하지 않는 독립 검산이다.
동일 보고 서식은 두 독립 집계에 적용하며, 서식 문자열의 일치 자체를 의미 독립성의 근거로 쓰지 않는다.
`tests/fixtures.py`의 정답 합성기는 시험 전용이며 실제 실행기에서는 사용하지 않는다.

Windows PowerShell 네이티브 구문 검사는 Windows에서 수행되는 조건부 시험이다.
Linux 검증에서의 skip을 Windows 실행 성공으로 바꾸어 보고하지 않는다.
