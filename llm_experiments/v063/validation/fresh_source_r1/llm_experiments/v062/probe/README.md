# v062: 마지막 규칙을 지정한 최소 증명 구성

v061은 같은 규칙 배열에서 shallow/deep 지시를 바꿔도 40회 모두 `k03`를 선택했다. v062는 규칙 ID만 고르는 단계를 마치고, 마지막 규칙을 지정받은 모델이 실제 부모 연결을 갖는 증명을 구성할 수 있는지 검사한다.

[v061 분석·방향 판정](docs/V061_ANALYSIS.ko.md)과 [v062 사전 프로토콜](docs/V062_PROTOCOL.ko.md)에 경쟁 의견과 채택 이유, 측정 정의, 종료 기준을 적었다. 성공해도 자유로운 깊이 선택이나 A/M 제어의 증거로 해석하지 않는다.

## 준비

Python 3.10 이상과 표준 라이브러리를 사용한다. 소스 ZIP을 새 폴더에 풀고 `llm_experiments/v057`~`v062` 상대 위치를 유지한다. 연구 evidence와 모델 가중치는 배포본에 포함하지 않는다. 별도로 보존한 v058 및 v061 evidence ZIP을 기본 상대 경로에 놓거나 실행 인자로 지정한다.

아래 명령은 `llm_experiments/v062/probe`에서 실행한다. selftest는 합성 응답만 사용한다. prepare/show는 모델을 호출하지 않는다.

```powershell
python -X utf8 -B -m construction_probe_v062 selftest
python -X utf8 -B tools/analyze_v061.py ../../v061/results_llm/v061_direction_01_evidence.zip --out ../validation/new_v061_analysis.json
python -X utf8 -B -m construction_probe_v062 prepare --baseline-bundle ../../v058/results_llm/v058_order_02_evidence.zip --out ../experiments/v062_construction_01.plan.json
python -X utf8 -B -m construction_probe_v062 show --plan ../experiments/v062_construction_01.plan.json
```

분석기에 선택적으로 `--historical-v060 <ZIP> --historical-v059 <ZIP>`를 주면 이전 실행을 별도로 비교한다. 과거 실행들을 새 독립 문제 표본으로 합산하지 않는다.

## Windows 실행

`windows/Run-v062.cmd`를 더블클릭하면 자체시험, v061 재분석, v058 기준선 검증, 새 계획 준비, **실제 모델 추론 40회**, 증거 생성과 독립 검산을 실행한다. 기존 실행명을 덮어쓰지 않고 다음 사용 가능한 `v062_construction_XX`를 고른다.

입력·계획 준비만 확인하려면 다음을 실행한다. CheckOnly에서는 모델을 호출하지 않는다.

```powershell
windows\Run-v062.cmd -CheckOnly -NoPause
```

기본 경로를 바꾸려면 `-BaselineBundle <v058 ZIP>`와 `-V061EvidenceBundle <v061 ZIP>`를 사용한다. `-SkipSelfTest`, `-NoOpen`, `-NoPause`도 지원한다.

## 수동 실행과 보존

다음 run 명령은 실제 모델을 호출한다. 오류 시 자동 재시도·재개·응답 보정·모델 다운로드를 하지 않는다.

```powershell
python -X utf8 -B -m construction_probe_v062 run --plan ../experiments/v062_construction_01.plan.json --out ../results_llm/v062_construction_01
python -X utf8 -B -m construction_probe_v062 audit --plan ../experiments/v062_construction_01.plan.json --run ../results_llm/v062_construction_01
python -X utf8 -B -m construction_probe_v062 bundle --plan ../experiments/v062_construction_01.plan.json --run ../results_llm/v062_construction_01 --out ../results_llm/v062_construction_01_evidence.zip
python -X utf8 -B tools/verify_v062.py ../results_llm/v062_construction_01_evidence.zip --out ../results_llm/v062_construction_01_independent.json
```

부분 실행도 audit/bundle로 보존한다. 원응답이나 이전 실행 증거를 수정하지 않는다. 준비한 계획과 소스 지문이 달라졌으면 새 실행 이름으로 새 계획을 준비한다.

## 결과 읽기

`summary.ko.md`와 `summary.json`에서 형식, 논리적 증명 유효성, 사용하지 않은 노드가 없는 strict 유효성, 목표 도달, 지정 마지막 규칙 이행을 나누어 본다. D는 유효한 실제 부모 연결에서만 계산한다. 지정 규칙은 A에서 `k03`, B에서 `k17`이며, 문제에서 기대되는 실제 D는 각각 1과 2다. 기대값은 채점과 사전 결정에 사용하며 프롬프트에 정답 그래프나 깊이를 넣지 않는다.

40/40 strict 유효·지정 규칙 일치·기대 D와 10개 seed의 반복 안정성이 모두 충족되어야 다음 자유 깊이 지시 실험을 준비할 수 있다. 이 문턱은 공학적 준비 기준이며 일반화나 통계적 유의성의 증명이 아니다. 미실행·측정 불가는 null로 남긴다. 실패하면 오류 층위를 기록하고 K01 choice 반복을 더 늘리지 않는다.

## 배포 검사

```powershell
python -X utf8 -B tools/build_release.py --out ../releases/v062_construction_source_r1.zip
python -X utf8 -B tools/build_release.py --check ../releases/v062_construction_source_r1.zip
```

최종 ZIP을 새 빈 폴더에 풀어 manifest와 selftest를 다시 검사한 후, 구현에 참여하지 않은 검토자가 같은 ZIP을 감사한다. 이번 제작의 실제 검증 결과와 남은 한계는 배포 ZIP 밖 `validation/FINAL_REVIEW.ko.md`에 기록한다. 소스 자체시험과 실제 모델 실험은 서로 다른 결과다.
