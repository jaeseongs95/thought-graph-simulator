# v061: 같은 규칙 순서에서 짧게/길게 선택 지시 비교

v060에서는 규칙 순서를 바꾸자 앞에 놓인 목표 도출 규칙을 선택했다. v061은 배열을 `[k03,k17,k10]`으로 고정하고 지시의 `작은`을 `큰`으로 바꾼다. 짧게 고르라는 조건에서 `k03`, 길게 고르라는 조건에서 `k17`로 전환하는지 확인하는 40회 실험이다.

[v060 분석과 교차검토](docs/V060_ANALYSIS.ko.md), [v061 사전 프로토콜](docs/V061_PROTOCOL.ko.md)에 근거와 경쟁 예측을 적었다. 선택 ID의 implied_depth는 실제 생성 증명의 D가 아니다. 이번 소스 제작에서는 실제 모델 추론을 실행하지 않는다.

## 준비와 오프라인 검사

Python 3.10 이상과 표준 라이브러리를 사용한다. 배포 ZIP을 새 빈 폴더에 풀고 동봉한 `llm_experiments/v057`부터 `v061`까지의 상대 위치를 유지한다. 아래 명령은 `llm_experiments/v061/probe`에서 실행한다.

```powershell
python -X utf8 -B -m direction_choice_v061 selftest
python -X utf8 -B tools/analyze_v060.py ../../v060/results_llm/v060_position_01_evidence.zip --historical-bundle ../../v059/results_llm/v059_rules_01_evidence.zip --out ../validation/new_v060_analysis.json
python -X utf8 -B -m direction_choice_v061 prepare --baseline-bundle ../../v058/results_llm/v058_order_02_evidence.zip --out ../experiments/v061_direction_01.plan.json
python -X utf8 -B -m direction_choice_v061 show --plan ../experiments/v061_direction_01.plan.json
```

prepare와 show는 모델을 호출하지 않는다. 기준 요청은 독립 검산이 가능한 v058 evidence에서 가져오고, 후속 질문은 v060 관측에서 도출했다. 연구 증거 ZIP과 모델 가중치는 소스 배포본에 넣지 않는다. 별도로 보존한 증거 ZIP을 위 경로에 두거나 실제 경로를 인자로 지정한다. v059 입력은 역사 비교를 할 때만 필요하며 생략할 수 있다.

## Windows 실행

`windows/Run-v061.cmd`를 더블클릭하면 자체시험, v060 증거 재분석, 기준선 검증, 새 계획 준비, 실제 Ollama 추론 40회, 감사와 증거 ZIP 생성, 독립 검산을 차례로 실행한다. 기존 실행명을 덮어쓰지 않으며 다음 사용 가능한 `v061_direction_XX`를 고른다.

입력과 계획 준비만 검사하려면 다음을 실행한다. CheckOnly는 실제 모델 추론을 하지 않는다.

```powershell
windows\Run-v061.cmd -CheckOnly -NoPause
```

기본 경로 외의 입력은 `-BaselineBundle <v058 evidence ZIP 경로>`와 `-V060EvidenceBundle <v060 evidence ZIP 경로>`로 지정한다. 필요하면 `-SkipSelfTest`, `-NoOpen`, `-NoPause`를 사용할 수 있다.

## 수동 실행과 결과 보존

아래 run 명령은 실제 모델을 40회 호출한다. transport나 identity 오류는 중단하고, 자동 재시도·재개·모델 다운로드는 하지 않는다.

```powershell
python -X utf8 -B -m direction_choice_v061 run --plan ../experiments/v061_direction_01.plan.json --out ../results_llm/v061_direction_01
python -X utf8 -B -m direction_choice_v061 audit --plan ../experiments/v061_direction_01.plan.json --run ../results_llm/v061_direction_01
python -X utf8 -B -m direction_choice_v061 bundle --plan ../experiments/v061_direction_01.plan.json --run ../results_llm/v061_direction_01 --out ../results_llm/v061_direction_01_evidence.zip
python -X utf8 -B tools/verify_v061.py ../results_llm/v061_direction_01_evidence.zip --out ../results_llm/v061_direction_01_independent.json
```

부분 실행도 audit와 bundle로 보존할 수 있다. 원응답을 수정하거나 다른 답으로 대체하지 않는다. 소스 지문이 계획과 달라지면 실행할 수 없으므로 변경된 소스에서는 새 계획을 만든다.

## 결과 읽기

`summary.ko.md`와 `summary.json`을 함께 본다. shallow 조건에서는 `k03`, deep 조건에서는 `k17`이 지시 이행이다. deep 조건에서 `shallow_success=false`가 나와도 `instruction_fulfilled=true`이면 해당 지시를 충족한 것이다.

양 조건의 지시 이행과 선택 ID 전환, 조건 내 반복 불일치를 함께 확인한다. B−A가 0이라는 사실만으로 성공이나 실패를 판단하지 않는다. 두 조건 모두 성공해도, 모두 실패해도 0이 될 수 있다. 40회는 K01 한 문제의 10개 seed 블록이며, actual_D와 proof 유효성은 측정하지 않는다. 캐시·실행 이력은 통제됐다고 가정하지 않는다.

## 배포 검사

```powershell
python -X utf8 -B tools/build_release.py --out ../releases/v061_direction_choice_source_r1.zip
python -X utf8 -B tools/build_release.py --check ../releases/v061_direction_choice_source_r1.zip
```

새 폴더에 풀어 selftest를 다시 실행한 뒤 최종 판본을 별도 감사한다. 완료된 검사·감사 근거는 배포 ZIP 밖 `../validation/FINAL_REVIEW.ko.md`에 남긴다. ZIP 안 문서를 포함한 파일을 감사 뒤 바꾸면 새 판본으로 검증해야 한다.
