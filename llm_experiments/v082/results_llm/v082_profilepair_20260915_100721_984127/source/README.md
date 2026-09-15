# v082 — 후보 계산표 후 ID 선택 짝대조

v081의 rule_ids 출력 분기를 종료하고 기존 candidate_id 선택기와, 후보별 구조 계산표를 먼저 작성한 뒤 같은 candidate_id를 선택하는 방식을 비교한다. 생성기는 explicit_rule을 유지한다.

## 연구 질문

동일 문제와 목표에서 후보를 하나씩 D(의존 깊이)와 W(규칙 수)로 측정한 **모델 원응답**을 제공하면 실제 선택과 증명 종단이 개선되는가? 사전 계획은 `docs/PREREGISTRATION.ko.md`, 구현 범위는 `docs/IMPLEMENTATION_REVIEW.ko.md`다.

계산표 16개는 문제×seed×후보당 한 번만 생성하고 같은 조건의 모든 표시·지표·방향에 공유한다. 값을 호스트가 계산하여 주거나 틀린 원문을 보정하지 않는다. 정상 응답의 잘못된 계산표를 제외하고 성공률을 계산하지 않는다. 주평가의 graph 종단과, 계산표까지 정확해야 하는 추가 계약을 분리한다.

## 실행 환경과 입력

Python 3.10 이상, 기존 로컬 Ollama, `qwen3:4b-instruct`의 v081 identity를 사용한다. 이 코드는 모델을 내려받거나 업데이트하거나 서버를 기동하지 않는다. 모델/서버 identity가 기존 배치와 다르면 중단한다.

필수 기존 입력: `v081_routepair_20260915_090344_919459_evidence.zip`.
SHA-256: `8e6be3196a49b3ed5dffbb926bceaa978030b6c0df7b00fe8d86de26a27db74a`.
파일명에 `(1)`이 붙어도 내용 해시가 같으면 사용할 수 있다.

자동 실행 파일에는 이 소스 ZIP과 동일한 내용이 포함되어 있다. Downloads에 `Run-v082-Auto.ps1`을 저장한 뒤:

```powershell
# 설치·자체시험·v081 재감사·계획 생성만. 모델 조회/추론 없음.
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v082-Auto.ps1" -CheckOnly -AllTests

# 실제 한 배치. 기존 Ollama가 실행 가능한 상태여야 한다.
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v082-Auto.ps1"
```

저장소와 evidence를 찾지 못하는 경우에만 명시 경로를 사용한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v082-Auto.ps1" -RepoRoot "D:\codex\AI논문\thought-graph-simulator" -Baseline "$env:USERPROFILE\Downloads\v081_routepair_20260915_090344_919459_evidence.zip"
```

`-CheckOnly`는 started 가드를 만들지 않는다. 검사 결과와 계획만 보존한다. 실제 실행은 별도 새 계획으로 시작한다. 이미 실제 배치가 시작됐다면 새 RunName으로 우회하지 않는다. 상태만 읽으려면 같은 자동화 명령에 `-InspectOnly`를 붙인다.

## 원본 소스 직접 실행

정식 ZIP 전체를 추출한 `llm_experiments/v082/probe`에서 실행한다. 아래 테스트용 환경 변수는 과거 evidence 재감사에만 사용된다.

```powershell
$env:V082_BASELINE = "$env:USERPROFILE\Downloads\v081_routepair_20260915_090344_919459_evidence.zip"
python -X utf8 -B -m unittest discover -s tests -p "test_*.py" -v
python -X utf8 -B launch.py --check-only --all-tests --repo-root "D:\codex\AI논문\thought-graph-simulator" --baseline "$env:V082_BASELINE"
```

정식 ZIP에는 prior/v081_source.zip이 들어 있으며 기존 배치의 검산기를 해시 확인 후 임시 디렉터리에서 실행한다. 원 v081 파일과 소스는 변경하지 않는다. 과거 evidence는 재배포 ZIP에 포함하지 않는다.

## 배정과 결과

두 군 각각 D 64조건/32쌍, W 32조건/16쌍. 선택 호출 192회. 본실험 graph 192개, 공통 지정 경로 graph 16개. 후보 계산표 16개. 모든 선택이 요구 경로를 고르면 추론 1,420회, 최대 1,484회. 진행 슬롯은 metadata 16개를 포함해 1,500개다. 후보를 매핑할 수 없으면 해당 graph를 실행하지 않고 생략 사유를 기록하므로 실제 호출 수는 더 적을 수 있다.

결과 위치:

```text
llm_experiments/v082/results_llm/
  v082_profilepair_<시각>/
    plan.json
    status.json
    summary.json
    summary.ko.md
    wire/                         # 원요청 및 원 HTTP 응답
    records/                      # 완료/시작/dispatch 사건
  v082_profilepair_<시각>_evidence.zip
  v082_profilepair_<시각>_independent.json
```

별도 검산:

```powershell
python -X utf8 -B verify082.py "D:\경로\v082_profilepair_..._evidence.zip"
```

`summary.json`의 `groups`는 기존 graph 기준 성과다. `profile_analysis.profiles`는 고유 계산표 16개의 판정, `profile_analysis.trial_diagnostics`와 `pipeline_pairs`는 그 원문을 공유한 선택·추가 계약 결과다. 반복 사용한 계산표 정확도를 독립 표본 수로 부풀리지 않는다. 계산표 원문 자체를 모델 내부 사고의 충실한 기록으로 간주하지 않는다.

## 안전한 종료

한 배치 후 종료. 자동 재시도, 모델 갱신, 서버 시작, 기존 결과 덮어쓰기, 가드 삭제가 없다. 중단 시 기존 파일을 먼저 확인한다. 합성 시험의 정상 답은 소프트웨어 검사이며 실제 Qwen 성과가 아니다. H01~H04는 이미 사용한 네 진단 구조이며 새로운 일반화 시험으로 부르지 않는다.

## 계산표 출력 예산

새 계산표 호출은 최대 출력 1,024토큰으로 사전 제한했다. 두 원응답이 같은 선택 입력에 들어가므로 보조 출력이 불필요하게 커지는 것을 제한한다. 기존 선택·생성의 API 옵션과 4,096토큰 상한은 유지한다. 길이 종료는 계산 실패나 D=0으로 채우지 않고 별도 미측정 상태로 보존하며 자동 재시도하지 않는다. 이 상한이 실제 모델의 작성 성공을 보장하는 것은 아니다.
