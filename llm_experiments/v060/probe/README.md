# v060: k10 후치 배열에서 선택 위치 진단

v059에서는 두 배열 모두 두 번째 전체 규칙을 골랐다. 그 위치가 첫 목표 도출 규칙과 같아 두 설명을 구분할 수 없었다. v060은 `[k17,k03,k10]`과 `[k03,k17,k10]`을 비교해 두 예측을 분리한다. 10개 seed에 ABBA/BAAB를 배정하고 각 조건을 두 번씩 관측하는 40회 실험이다.

[v059 분석](docs/V059_ANALYSIS.ko.md)과 [사전 프로토콜](docs/V060_PROTOCOL.ko.md)에 제3자 의견, 교차검증, 경쟁 예측과 해석 한계를 적었다. `k10` 후치는 두 조건에서 같지만 v059와 다른 배치다. 결과는 새 배치의 관측 패턴으로 해석한다. 선택 ID의 implied_depth는 생성 증명의 D가 아니며, 실제 D와 proof 유효성은 null로 남긴다.

## 준비와 오프라인 검증

Python 3.10 이상과 표준 라이브러리를 사용한다. ZIP을 새 빈 폴더에 풀고 동봉한 `llm_experiments/v057`, `v058`, `v059`, `v060`의 상대 위치를 유지한다. 아래 명령은 `llm_experiments/v060/probe`에서 실행한다.

```powershell
python -B -m terminal_position_v060 selftest
python -B tools/analyze_v059.py ../../v059/results_llm/v059_rules_01_evidence.zip --out ../validation/new_v059_analysis.json
python -B -m terminal_position_v060 prepare --baseline-bundle ../../v058/results_llm/v058_order_02_evidence.zip --out ../experiments/v060_position_01.plan.json
python -B -m terminal_position_v060 show --plan ../experiments/v060_position_01.plan.json
```

prepare와 show는 모델을 호출하지 않는다. 후속 질문은 v059 결과에서 도출했고, 요청의 기준선은 이미 감사 가능한 v058 원요청을 사용한다. prepare는 v058 ZIP을 생산 감사와 독립 검산으로 확인한다. 역사적 응답은 새 실행의 관측값으로 복사하지 않는다.

소스 ZIP에는 연구 증거 ZIP과 모델 가중치를 넣지 않는다. 별도로 보존한 v058·v059 evidence ZIP을 위 경로에 두거나 명령에서 실제 경로를 지정한다. 계획은 소스 지문을 포함하므로 소스가 바뀌면 최종 소스에서 새 계획을 만들어야 한다. 기존 계획·결과·ZIP 경로는 보존한다.

## 실제 실행

다음 run 명령은 Ollama를 통해 **실제 추론 40회**를 수행한다. 이번 소스 제작·검증에서는 실제 모델 실험을 실행하지 않았다.

```powershell
python -B -m terminal_position_v060 run --plan ../experiments/v060_position_01.plan.json --out ../results_llm/v060_position_01
python -B -m terminal_position_v060 audit --plan ../experiments/v060_position_01.plan.json --run ../results_llm/v060_position_01
python -B -m terminal_position_v060 bundle --plan ../experiments/v060_position_01.plan.json --run ../results_llm/v060_position_01 --out ../results_llm/v060_position_01_evidence.zip
python -B tools/verify_v060.py ../results_llm/v060_position_01_evidence.zip --out ../results_llm/v060_position_01_independent.json
```

Windows에서는 `windows/Run-v060.cmd`를 더블클릭하면 된다. 실행기는 사용하지 않은 실행명을 고른 뒤 자체시험, v059 증거 재분석, v058 기준선 검증, 계획 준비, Ollama 확인, 40회 추론, 감사, 증거 ZIP 생성과 독립 검산을 차례로 수행한다. 기존 실행은 덮어쓰지 않으며 실패한 추론을 자동으로 재시도하지 않는다.

입력과 준비만 검사하려면 다음 명령을 실행한다. CheckOnly는 실제 모델 추론을 실행하지 않는다.

```powershell
windows\Run-v060.cmd -CheckOnly -NoPause
```

기본 입력 경로 외의 증거는 `-BaselineBundle <v058 evidence ZIP 경로>`와 `-V059EvidenceBundle <v059 evidence ZIP 경로>`로 지정한다. 필요하면 `-SkipSelfTest`, `-NoOpen`, `-NoPause`를 함께 사용할 수 있다.

transport나 identity 오류는 즉시 중단하며 자동 재시도·재개·모델 다운로드는 없다. 원응답을 고치거나 다른 규칙을 대신 선택하지 않는다. 부분 실행도 별도 audit와 bundle로 보존할 수 있다. metadata 조회는 상태 초기화가 아니다.

## 결과 읽기

조건별 `goal_reachable_choice`와 `instruction_fulfilled`를 구분한다. k17은 목표 도달에 유효해도 shallow 지시 이행에는 실패한다. 형식 오류와 미실행은 별도로 남기며 전체 비율의 분모를 충족하지 못하면 null을 둔다.

`summary.json`에는 선택 ID, 전체 위치와 terminal 순위, seed별 A0/A1/B0/B1, 조건 간 비교와 조건 내 반복, 순서·직전 조건·반복 간격의 분포가 있다. 각 seed의 두 반복이 모두 같을 때 사전 예측표와 비교한다. 일치하는 패턴을 내부 기제가 확인됐다는 뜻으로 읽지 않는다. `summary.ko.md`와 독립 검산 결과를 원자료와 함께 보존한다.

## 배포 검증

```powershell
python -B tools/build_release.py --out ../releases/v060_terminal_position_source.zip
python -B tools/build_release.py --check ../releases/v060_terminal_position_source.zip
```

manifest를 확인한 뒤 새 위치에 압축을 풀고 그 안에서 selftest를 실행한다. 배포본은 보존된 v057/v058/v059 의존성과 v060의 코드·시험·문서·실행기를 포함한다. 최종 소스 감사와 실제 실행한 검증 결과는 `../validation/FINAL_REVIEW.ko.md`에서 확인한다.
