# v087 — 관측 노드 정보 × 새 노드 ID 지원

v086의 값 비교 → 후보 ID 조회를 고정하고, 생성 단계의 **부모 원자 연결·직접 전제 누락·node ID 재사용**을 분리해 검증한다. 새 구조 holdout, 선택기 수정, 자력 D 계산 실험을 동시에 하지 않는다.

## 연구 근거와 질문

v086 두 단계 D 선택은 128/128, 실제 종단은 115/128, 양방향은 51/64였다. 남은 13건은 U01·U03·U06의 D=3 경로 생성 오류였다. D=5는 16/16 성공했으므로 현재 실패를 깊이 숫자 하나로 설명하지 않는다. 근거는 해시 고정된 사용자 v086 evidence이며, 과거 결과를 v087 성과에 합산하지 않는다.

**이번 질문:** 동일한 두 단계 선택·문제·seed·기본 생성 계약에서, 실제 이력의 전체 노드 정보를 다시 보여주거나 새 노드 ID만 사전 할당하면 유효한 graph와 요구 D의 양방향 종단이 개선되는가?

## 네 생성군

| 군 | 전체 노드 id–atom 표 | 사용하지 않은 새 ID 제공 | 부모·원자·규칙 선택 |
|---|---|---|---|
| baseline | 없음 | 없음 | 모델 |
| node_inventory | 있음 | 없음 | 모델 |
| allocated_id | 없음 | 있음 | 모델 |
| inventory_allocated | 있음 | 있음 | 모델 |

노드 표는 기존 **원응답 이력의 모든 id/atom 행**이다. 정답 부모만 골라주거나 전제에 맞는 노드를 필터링하지 않는다. 중복 id와 잘못된 원자도 그대로 둔다. 파싱되지 않는 이력은 원문에 보존하고 표의 unreadable_source_slots에도 표시한다.

새 ID는 현재 이력에서 사용한 식별자와 충돌하지 않는 값을 실행기가 할당한다. 이번 rule 응답의 id만 JSON Schema enum으로 제약한다. atom/rule/parents의 정답은 제공·강제하지 않는다. **이는 사전 도구 지원 조건이며 자력 ID 관리 성공이 아니다.** 초기 facts는 기존 계약으로 생성하며 잘못된 기존 ID를 재명명하지 않는다.

지원은 rule 단계에만 적용한다. facts와 final의 프롬프트·스키마는 바꾸지 않는다. node_inventory 처치는 정보 표와 명시적 안내가 함께 들어가므로 표의 형식 하나만의 독립 효과라고 해석하지 않는다. allocated_id도 식별자 선택의 사전 도구화·스키마 제약을 포함한 처치다.

## 평가 A: 고정된 유효 원문 이력의 규칙 진단

U01~U08의 두 경로에 있는 70개 규칙 각각에서, **그 규칙 직전까지의 이력이 유효한 v086 two_stage_values trial 중 사전식 순서가 가장 이른 사례**를 택한다. 해당 원요청을 그대로 보존한다. 대상 규칙의 응답·이후 결과·전체 graph의 성공 여부는 선정에 사용하지 않는다. 따라서 target까지 성공한 사례에 기준선이 치우치는 선택을 피한다. 성공했던 규칙과 실패했던 규칙을 미리 나누어 선별하지도 않는다.

- 동일 이력을 네 군과 두 seed에 제공: **70 × 4 × 2 = 560호출**.
- 새 한 규칙 응답만 평가하며, 앞선 노드를 수정·재생성하지 않는다.
- 실제 원자 연결, 직접 전제 누락, 중복 부모, 기존 ID 재사용을 구분한다.
- 전제 수와 직접 전제 사이의 조상 관계를 보조 층으로 보고한다. 이는 관측 층별 진단이며 D·규칙 수를 모두 통제한 새 인과 실험이 아니다.
- 유효한 직전 관측 이력에 조건을 건 국소 진단이다. 이 560응답을 전체 종단 성공에 더하지 않는다. 두 seed·각 규칙을 새로운 독립 구조로 세지 않는다.

해당 anchor의 선택 정책·원문 SHA-256·원래 trial/slot을 data/anchors.json, data/anchor_provenance.json에 보존한다. 기준선의 기존 독립 검산과 직전 prefix의 별도 의미 채점으로 유효성을 확인한다.

## 평가 B: 새 선택·새 생성의 실제 D 종단

U01~U08 모두를 사용한다. 이미 관측한 진단 집합이며 새 holdout이 아니다. U02·U04·U05·U07·U08처럼 기존에 성공했던 구조도 포함해 성공 소실을 검사한다.

문제 8개 × seed 2개 × 후보 위치 2개 × ID 배정 2개 × shallow/deep 2개 = **128조건**이다. 각 조건에서 비교·조회 두 호출을 **한 번만** 새로 실행하고, 그 원응답을 네 생성군의 공통 선택 입력으로 제공한다. 전체 선택은 **256호출**이며 네 군의 독립 선택 512건으로 세지 않는다.

각 군은 같은 선택 원문에서 시작하지만, facts부터 자신의 새 graph를 생성한다. 모든 군의 첫 facts 요청은 같으며 결과와 이후 이력은 다를 수 있다. 각 군 **128graph / 양방향 64쌍 / 네 표시 묶음 16개**, 총 **512graph**다. 선택이 틀리거나 출력 계약을 지키지 못하면 다른 후보로 교체하지 않는다.

규칙 진단과 종단은 구조×seed 블록 안에서 순서대로 실행하며, 모든 군·조건·종료 규칙은 최초 추론 전에 함께 고정한다. 진단 결과가 나쁘다고 본실험을 재설계하거나 특정 군을 빼지 않는다. 군 순서는 순환 교차한다.

## 주평가와 보조 평가

**주평가:** 같은 v087 배치에서 각 구조의 양방향 D 종단 성공률 차이 `inventory_allocated − baseline`을 구한 뒤 8개 구조를 동일 비중으로 평균한다.

node_inventory−baseline, allocated_id−baseline도 사전 대비로 보고한다. 추가로 2×2 평균 효과와 상호작용 `(both − inventory − id + baseline)`을 구조별로 계산한다. 양방향 성공률 차이의 구조 동일 가중치이며, 독립 IID 표본 p값은 계산하지 않는다. 미관측 구조가 있으면 전체 효과를 계산하지 않는다.

실제 graph의 규칙·부모 원자 multiset·중복·순환·출력 순서·goal ancestry를 재검사하고 `fact depth=0`, `rule depth=1+max(premise depth)`로 D를 측정한다. 비교와 조회도 맞아야 종단 성공이다. 원자·부모·규칙·final을 보정하지 않는다.

노드 ID 지원 계약만 위반했지만 graph 의미는 맞은 사례는 분리한다. `generator_semantic_success`와 `support_contract_success`, `generator_success`를 함께 보고하며, 사전 지원 계약을 위반한 출력은 strict 종단에서 제외한다. 단방향, 양방향, 네 표시 전체, 기존 성공의 소실, 실패 원인, 고유 요청 수와 사용량을 각각 보존한다.

생산·독립 검산은 배정·요청 구성·응답 의미·규칙 검사·graph 깊이를 서로 별도로 구현한다. 원응답 판정 뒤의 표 집계와 바이트 진단 함수는 공유하므로, 알려진 정답 개수·반례·대비 부호를 별도 자체시험으로 검사한다. 독립 검산 일치는 외부 실행 사실의 인증이 아니다.

## 호출 수

| 구분 | 배정 |
|---|---:|
| 고정 이력 규칙 진단 | 560 |
| 공통 비교·조회 | 256 |
| 실제 D graph | 512건 |
| 모든 선택이 목표 경로일 때 전체 추론 | **4,080** |
| 선택 경로가 모두 최장이면 최대 추론 | **4,208** |
| metadata 포함 전체 action | **4,240** |

실제 선택에 따라 규칙 슬롯이 달라지고 필요 없는 슬롯은 `outside_selected_route`로 제외된다. 선택 출력이 매핑되지 않는 경우 별도 미배정/출력 실패로 처리한다. HTTP·identity·length·schema·미실행을 논리 실패와 섞지 않는다. W/oracle 및 별도 참조 graph는 이번 배정에 없다.

## 실행

기존 Windows 11/Python 3.12/Ollama/qwen3:4b-instruct를 대상으로 한다. 표준 라이브러리만 사용하며 Python 3.10 이상 문법이다. 모델 identity와 기존 API 옵션은 v086과 같아야 한다.

Downloads에 `Run-v087-Auto.ps1`만 새로 저장하면 된다. 소스 ZIP은 내장되어 있다. 기준 파일 `v086_holdout_20260915_195413_809765_evidence.zip`을 기존 v086/results_llm 또는 Downloads에 보존한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v087-Auto.ps1" -CheckOnly -AllTests
```

무추론 점검 후 실제 실행:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v087-Auto.ps1"
```

`-CheckOnly`는 기존 Ollama 조회·추론·서버 시작·모델 설치를 하지 않는다. 자체시험의 합성 loopback 서버만 사용한다. 실제 실행 시 기존 Ollama가 켜져 있어야 한다. 모델 다운로드·업데이트·서버 시작·자동 재시도는 하지 않는다. 필요하면 `-RepoRoot`, `-Baseline`, `-PythonPath`, `-Endpoint`를 명시한다. Endpoint는 loopback HTTP만 허용한다.

기존 파일이 수정되어 있으면 덮어쓰지 않고 중단한다. 이미 시작한 v087 배치는 새 이름으로 우회 실행하지 않는다. 중단된 가드와 원문을 보존하고 `-InspectOnly`로 상태만 확인한다. 이전 v086의 소스·evidence는 변경하지 않는다.

결과 위치:

```text
llm_experiments/v087/results_llm/
  v087_genfactor_<timestamp>/
  v087_genfactor_<timestamp>_evidence.zip
  v087_genfactor_<timestamp>_independent.json
```

전체 원문과 summary.json/summary.ko.md, diagnostics.json/diagnostics.ko.md를 evidence에 포함한다. 수동 독립 검산:

```text
python -X utf8 -B llm_experiments/v087/probe/verify087.py <v087_evidence.zip>
```

소스 ZIP을 직접 풀었을 때:

```text
python -X utf8 -B llm_experiments/v087/probe/launch.py --repo-root <저장소> --baseline <v086_evidence.zip> --check-only --all-tests
```

## 범위

이 구현은 직전 논의의 1순위인 **부모 연결 지원과 새 ID 지원의 분리 대조**다. D와 구조 복잡도의 별도 조작, 간결한 1호출 선택기 비교, 모델 자력 D 계산, 새 holdout은 같은 배치에 섞지 않았다. 관측 결과가 나온 뒤에도 사후 보정하거나 이 배치의 실패를 새 계약으로 소급 성공 처리하지 않는다.

실제 v087 모델 결과는 실행 후에만 판단한다. 합성 응답의 높은 성공률은 구현·측정기 검증이며 연구 가설의 실증이 아니다. 정확한 개발 검증 범위와 제외된 환경 검사는 함께 제공하는 검증 보고서를 확인한다.
