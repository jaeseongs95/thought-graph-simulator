# local_llm v0.4.3


## 설치

기존 `local_llm` 폴더를 다른 이름으로 보관하고 이 ZIP의 `local_llm` 폴더로 교체한다.
`adm_minimal.py`, `examples/`, 기존 `results_llm/`은 그대로 둔다. 모델 재다운로드나 패키지 추가 설치는 없다. Python 3.10 이상, 기존 Ollama가 필요하다. 이번 대응 실험이 끝나기 전에 모델/서버/샘플링 설정을 바꾸지 않는다.

## 실행

저장소 루트의 PowerShell에서 실행한다. 아래 두 명령의 `_` 앞에 역슬래시를 붙이지 않는다.

```powershell
# 원본 8건·소스 지문·대응 계획 확인. 네트워크/LLM 호출 없음.
py -3 -m local_llm.decision_probe --input results_llm/v042_micro_01 --plan-only

# 실제 LLM 8회: format만 변경 4회 + 저장된 모델 중간값을 쓰는 후속 판정 4회
py -3 -m local_llm.decision_probe --input results_llm/v042_micro_01 --out results_llm/v043_decision_01
```

출력 폴더는 원본과 다른 새 폴더다. 원본 이름은 변경하지 않는다. 이미 같은 출력 폴더가 있다면 동일 조건 재개는 `--resume`, 별도 반복은 새 `_02` 이름을 사용한다. 실패 조건을 통과할 때까지 자동 재추론하지 않는다.

모델 digest, 템플릿 메타데이터, 서버 버전, core, 생성 설정이 원본과 다르면 새 추론 전에 중단한다. 이는 기존 실패를 차단하는 성능 게이트가 아니라 비교 조건 검사다.

## 결과를 보는 순서

`results_llm/v043_decision_01/summary.md` → `decision_probe.json` → `task_evidence.json` / `task_comparisons.json` → `cases/*/request.wire.json`, `response.raw.json`.

format_json과 staged를 각각 보고 원본 조건별 변화로 판단한다. 두 군의 합계는 본 A/D/M 성능이 아니다. staged 성공은 원래 원샷 실패를 성공으로 바꾸지 않는다. 프로그램은 모델 중간값·최종값을 정답으로 보충하지 않는다.

원본 8건을 새 상세 표로 재검사만 하려면:

```powershell
py -3 -m local_llm inspect-results --input results_llm/v042_micro_01 --out results_llm/v043_micro_audit_01
```

이 명령은 추론하지 않는다. 기존 calibration/smoke/pilot 전체를 다시 실행할 필요가 없다.

## 단독 군과 오프라인 시험

```powershell
# 한 군만 필요할 때: 4회 (두 군을 이미 실행했다면 다시 실행하지 않는다)
py -3 -m local_llm.decision_probe --input results_llm/v042_micro_01 --arm staged --out results_llm/v043_staged_01

# 배포 코드 자체 시험. 기존 저장소의 core/examples가 있어야 한다.
py -3 -m unittest discover -s local_llm/tests -v
```

204개 단위·회귀·모의 API 시험과 selfcheck 21개는 오프라인 검사다. 제공자가 새 LLM 추론, 모델 다운로드, Windows/GPU 실험을 실행한 것은 아니다. 기존 자료에서는 입력/기본 비교는 맞고 finding만 상수화됐으며, 이 수정의 실제 효과는 사용자의 새 응답으로 판단한다.


---

## 기존 명령 참고 (v0.4.2 이하)

아래는 하위 호환 명령 설명이다. 이번 결과에서는 위 decision_probe 절차를 먼저 사용한다.

# local_llm v0.4.2 — 관측된 실패의 구성요소 진단

기존 `adm_minimal.py`와 동일 저장소의 Python 3.10 이상을 사용한다. Python 런타임은 표준 라이브러리만 사용한다. Ollama 서버와 모델은 사용자의 PC에서만 호출된다. 모델 가중치는 포함하지 않는다.

## 교체

기존 `local_llm`을 보관하고 이번 `local_llm`으로 폴더 교체. 기존 core·문제·결과를 보존한다. 소스 ZIP에는 대체 `adm_minimal.py`가 없다. 과거 결과를 새 버전으로 이어서 쓰지 않는다. 새 하위 폴더를 사용한다.

## 가장 먼저

```powershell
py -3 -m local_llm selfcheck
py -3 -m local_llm inspect-results --input results_llm/v041_probe_01 --out results_llm/v042_probe_audit_01
py -3 -m local_llm.micro_probe --group control --group criterion --out results_llm/v042_micro_01
```

앞 두 명령은 모델을 호출하지 않는다. 마지막은8회다. 기존 calibration/smoke/pilot/causal 69/12회를 반복할 필요 없다. 기본 모델은 기존 `qwen3:4b-instruct`, temperature0.7, top_p0.8, top_k20, min_p0, context8192, output4096, think 생략이다.

## 새 진단 그룹

| 그룹 | 횟수 | 검사 |
| --- | ---: | --- |
| control | 4 | 입력 그대로 복사2, 동일/다른 문자열 비교2 |
| criterion | 4 | 목표 일치×초기 사실 소속 네 경우. 모델이 observed/primitives/finding을 작성 |
| graph | 2 | K03 전체 깊은 증명, 원자/규칙/경로 고정 후 부모만 연결 |
| schema | 2 | 최종 도식, 같은 입력에 최초 사실절 우선 작성 지시만 추가 |

`--group`을 생략하면12회 모두다. 최소 선택을 위한 계획 확인:

```powershell
py -3 -m local_llm.micro_probe --plan-only
py -3 -m local_llm.micro_probe --group control --group criterion --plan-only
```

입력복사에는 복사할 답이 주어지고 edge_map에는 노드/경로가 제공된다. 두 진단을 독립 추론·D 계획·통합 ADM 성공으로 세지 않는다. 프로그램은 누락한 부모·사실절·boolean을 대신 채우지 않는다. edge_map이 일부 노드를 빠뜨리면 빈 부모로 재구성하지 않고 실패로 기록한다.

## 출력 읽기

`summary.md`: 실행 완료와 과제 성공을 분리한다.
`micro_probe.json`: 그룹별 결과, 모든 응답의 판정, 다음 진단 분기.
`task_evidence.json`: JSON 오류 경로, 실제/기대 전제, 누락 사실절, 진리값 반례, 중간값 증거.
`task_comparisons.json`: 모델 실제값·기대값·일치 여부.
`cases/`: 원문 HTTP 요청과 응답, record, 사용량/모델 적재 정보.

### 다음 진단 분기

- `control_not_fully_measured`: 기본 대조가 없거나 미완료. 다른 그룹만 선택했을 때도 이 표시가 가능하며 실패 확정이 아니다.
- `stop_scaling_up_check_input_or_runtime_pair`: control 중 실패. 상위69조건을 늘리지 말고 입출력/디코딩 대응 조건을 확인.
- `control_passed_criterion_not_fully_measured`: 기본 대조 통과, 기준 중간값은 아직 충분히 기록되지 않음.
- `control_passed_literal_decision_unreliable_in_this_condition`: 입력 대조는 통과했지만 criterion witness 실패. `first_failed_observable_stage`의 observed/primitives/finding을 확인.
- `controls_and_criterion_passed_inspect_graph_and_schema_separately`: 원자 판정까지 통과. graph/schema를 각각 확인. 일반 성능 보증은 아님.

실패한 중간값은 출력상 위치다. 실제 내부 사고 단계가 그렇다고 단정하지 않는다. 성공한 중간값도 과거 v041의 숨은 원인을 소급해 증명하지 않는다.

## 출력 제약만 바꾸는 대응 실행

같은 group/seed/model/settings를 유지한다. 모든 모드의 메시지에는 동일한 완전 JSON Schema가 들어간다. API의 format만 변경한다.

```powershell
py -3 -m local_llm.micro_probe --group control --group criterion --format-mode json --out results_llm/v042_micro_json_01
py -3 -m local_llm.compare_runs --left results_llm/v042_micro_01 --right results_llm/v042_micro_json_01 --vary format --out results_llm/v042_compare_format_01
```

`--format-mode none`은 format 필드를 보내지 않는 대조다. 이때도 엄격한 출력 검증은 유지한다. 설명 문장이 섞였다고 JSON을 자동 추출하지 않는다. schema모드와 동시에 temperature/model을 바꾸지 않는다.

## 그래프·도식 분리

```powershell
py -3 -m local_llm.micro_probe --group graph --group schema --out results_llm/v042_graph_schema_01
```

전체 그래프만 실패하고 edge_map은 성공하면, 호스트가 경로를 제공한 조건에서 연결 작업을 수행했다는 관측이다. 모델의 독립 경로 계획 성공이 아니다. fact_first만 통과해도 해당 지시 효과의 단서이며 대규모 일반화 결과는 아니다.

## 그 밖의 대응 요인

`--temperature 0`은 샘플링 대조이며 보편적인 정답 설정이 아니다. 동일한 다른 조건을 유지하고 별도 폴더에 저장한 뒤 `compare_runs --vary temperature`를 사용한다.

`--seed`를 바꾸면 `--vary seed`로 비교할 수 있다. 같은 문제의 반복을 새로운 문제 수로 세지 않는다.

다른 호환 체크포인트는 `--model`로 지정한다. `doctor`/런타임 메타데이터 검사는 유지된다. 다른 모델 계열을 임의로 Instruct-2507로 오인하는 우회는 제공하지 않는다. `compare_runs --vary model`은 가중치/양자화/템플릿 묶음 비교로 해석한다. 두 모델이 같은 크기라는 이유로 순수 양자화 효과라고 부르지 않는다.

다른 로컬 Ollama 서버는 `--endpoint`로 선택할 수 있다. `compare_runs --vary server`는 같은 모델 digest, 메타데이터, 실제 요청을 요구한다. 운영체제·GPU·서버 버전까지 달라지면 서버 묶음 차이이지 단일 소프트웨어 버그 증명은 아니다.

비교 도구는 모든 배정 기록, 같은 core/하네스/문제/과제 계약과 변경 요인 외 HTTP 필드의 일치를 검사한다. 선택한 요인이 실제로 바뀌지 않아도 거부한다. 기록상 통제는 서버 내부 캐시/토큰 흐름의 관측을 대신하지 않는다.

## 과거 결과 유지

`causal_probe`, `run`, `calibrate` 명령은 기존 계약대로 남겼다. 과거12건의 요청/상태/전체 audit는 유지된다. 기존 결과 원문은 수정하지 않으며 `inspect-results`는 별도 출력 경로만 받는다.

`final_is_goal_atom`은 최종 포인터에 원자 문자열을 잘못 넣었는지 보는 과거 오류 지표다. 실제 최종 명제가 목표와 같은지는 `selected_final_node_atom_matches_goal`로 구별한다.

## 오프라인 시험

```powershell
py -3 -m unittest discover -s local_llm/tests -v
```

172개 단위·회귀·모의 API 시험. 실제 보존 응답12건과 이전 회귀자료, 자료형 반례, 세 도식 조건 보존, 미완성 부모 출력 거부, 원자 판정 중간값,12회 mock 실행, 단일요인 요청 비교를 포함한다. 테스트의 모의 정답은 테스트 안에서만 생성한다. 실제 모델을 호출하지 않는다.

최종 검증 상태는 `BUILD_STATUS.json`에 기록한다. LLM/GPU/Windows 실측 성능이 개선됐다고 확인한 배포물이 아니다.
