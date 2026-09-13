# v059: Gemma K01 선택의 규칙 순열 진단

v058에서 Gemma는 유효한 선택 ID를 20회 출력했지만 모두 깊은 규칙 `k17`을 골랐다. v059는 facts·규칙 내용·ID·goal·지시·모델 옵션을 고정한 채 두 terminal rule의 목록 순서만 바꾼다. 10개 seed에 ABBA/BAAB를 배정해 총 40회 호출하며, 조건 간 변화와 같은 조건의 반복 변동을 나누어 기록한다.

[다각도 분석](docs/V058_ANALYSIS.ko.md), [사전 프로토콜](docs/V059_PROTOCOL.ko.md), [검증 결과](docs/VALIDATION.ko.md)를 함께 읽는다. choice의 implied_depth는 실제 생성 증명의 D가 아니다. 결과는 이 문제·모델·두 순열에서의 탐색적 민감도로 해석한다.

## 오프라인 검사와 계획 준비

Python 3.10 이상과 표준 라이브러리를 사용한다. 작업 디렉터리는 `llm_experiments/v059/probe`다. 소스 ZIP은 새 빈 폴더에 풀고 함께 든 v057/v058/v059의 상대 위치를 유지한다. 실제 연구 증거 ZIP과 모델 가중치는 소스 ZIP에 넣지 않는다.

```powershell
python -B -m rule_order_v059 selftest
python -B tools/analyze_v058.py ../../v058/results_llm/v058_order_02_evidence.zip --out ../validation/new_v058_analysis.json
python -B -m rule_order_v059 prepare --baseline-bundle ../../v058/results_llm/v058_order_02_evidence.zip --out ../experiments/v059_rules_01.plan.json
python -B -m rule_order_v059 show --plan ../experiments/v059_rules_01.plan.json
```

독립 재분석과 prepare는 실제 모델을 호출하지 않는다. prepare는 v058 전체 기준선을 생산 감사와 독립 검산으로 확인한다. 동봉 source_snapshot은 실행하지 않는다. 소스가 바뀌면 동결 계획 검사가 거부하므로 최종 소스에서 새 계획을 만든다. 기존 계획·결과·ZIP 경로는 덮어쓰지 않는다.

Windows에서는 `llm_experiments/v059/probe/windows/Run-v059.cmd`를 더블클릭하면 된다. 실행기는 사용하지 않은 실행명을 고르고, 자체시험과 v058 증거 재분석, 계획 준비, Ollama 확인, 40회 추론, 감사, 증거 ZIP 생성, 독립 검산을 차례로 수행한다. 기존 실행은 덮어쓰지 않으며 실패한 추론을 재시도하지 않는다.

추론 없이 실행기와 입력만 검사하려면 저장소 루트에서 다음을 실행한다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\llm_experiments\v059\probe\windows\Run-v059.ps1 -CheckOnly -NoPause
```

점검용 계획과 baseline 사본은 실행별 로그 폴더에 만든다. `ExecutionPolicy Bypass`는 해당 프로세스에만 적용되며 시스템 정책을 수정하지 않는다. `-SkipSelfTest`, `-RunName v059_rules_02`, `-BaselineBundle <경로>`, `-NoOpen`, `-NoPause`를 선택적으로 지정할 수 있다.

## 실제 실행

아래 run 명령 또는 `windows/Run-v059.cmd` 더블클릭은 **Ollama 추론 40회**를 수행한다. 소스 제작·검증 작업에서는 실제 모델 실험을 실행하지 않았다. 원클릭 실행기는 자체시험·새 계획 준비·실행·번들·독립 검산을 차례로 수행한다. `-BaselineBundle <경로>`로 입력 ZIP을 지정할 수 있다.

```powershell
python -B -m rule_order_v059 run --plan ../experiments/v059_rules_01.plan.json --out ../results_llm/v059_rules_01
python -B -m rule_order_v059 audit --plan ../experiments/v059_rules_01.plan.json --run ../results_llm/v059_rules_01
python -B -m rule_order_v059 bundle --plan ../experiments/v059_rules_01.plan.json --run ../results_llm/v059_rules_01 --out ../results_llm/v059_rules_01_evidence.zip
python -B tools/verify_v059.py ../results_llm/v059_rules_01_evidence.zip --out ../results_llm/v059_rules_01_independent.json
```

transport나 identity 실패는 즉시 중단하며 자동 재시도·재개·모델 다운로드는 없다. 중단된 결과도 별도 audit/bundle로 보존할 수 있다. metadata 조회는 모델·캐시를 초기화하지 않는다. JSON 파싱 불가와 미실행은 별도로 기록한다.

## 결과 확인

`summary.ko.md`는 조건별 형식·선택·shallow 성공을 보여준다. `summary.json`에는 10개 seed의 네 관측, 조건 간 대응표, 같은 조건 반복표, sequence·period·직전 조건·반복 간격별 분포가 있다. 전체 미완료 또는 해당 비교의 미측정이 있으면 전체 비율은 null이다. 40호출과 20개 대응 비교를 독립 문제 표본으로 합산하지 않는다.

## 소스 패키지 검사

```powershell
python -B tools/build_release.py --out ../releases/v059_rule_order_source.zip
python -B tools/build_release.py --check ../releases/v059_rule_order_source.zip
```

최종 ZIP을 새 폴더에 푼 뒤 그 안에서 selftest를 실행한다. source manifest는 문서·코드·실행기와 보존된 v057/v058 의존성의 바이트 해시를 포함한다. 최종 독립 감사 대상과 실제 실행한 검증은 검증 기록에서 확인한다.
