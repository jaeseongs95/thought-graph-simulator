# v090 — 새 선택·새 facts에서 시작하는 의미 ID D 종단 대조

## 목적

v089의 atom_alias 유지 29/32, atom_tagged 유지 28/32는 과거 유효 facts를 지원받은 연속 생성 결과였다. v090은 기존 baseline과 의미 ID 생성군을 **공통의 새 two-stage 선택 + 생성군별 새 facts**부터 비교한다. 과거 graph 응답을 초기 이력으로 사용하지 않는다.

기본 생성기 승격이나 신규 구조 holdout이 아니라, 알려진 U01~U08에서 전체 D 종단 개선이 있는지를 확인하는 고정 진단이다.

## 실행

`Run-v090-Auto.ps1`은 정확한 소스 ZIP을 내부에 포함한다. 원본 v089 evidence를 `llm_experiments/v089/results_llm` 또는 Downloads에 보존한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v090-Auto.ps1" -CheckOnly -AllTests
```

자체시험·calibration·prepare가 모두 성공한 후 실행한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v090-Auto.ps1"
```

기준선 자동 탐색이 불가능한 경우 `-Baseline`에 다음 원본 ZIP 경로를 지정한다.

```text
v089_idcross_20260916_122755_207556_evidence.zip
SHA-256: 8ba60eda9670e1c7298b6f10cf6801875bd5f7c67f4f39cb23ee473b4600838b
```

설치 위치는 `llm_experiments/v090/probe`, 설치 manifest는 `RELEASE_MANIFEST_v090.json`이다. 이전 v089/v088 소스·manifest·guard·계획·로그·evidence를 수정하지 않는다. 알려지지 않은 기존 v090 설치를 덮어쓰지 않는다.

`-CheckOnly`는 Ollama를 조회하지 않으며 모델을 실행하지 않는다. 다만 로컬 자체시험, calibration, 원 v089 evidence 검산, 새로운 plan·로그 작성은 수행한다. `-AllTests`는 호환 옵션이며 이 배포본은 생략해도 전체 자체시험을 실행한다. 모델 다운로드, 서버 시작, 자동 재시도는 없다.

실제 실행 전에 Ollama 0.34.1과 원래 qwen3:4b-instruct가 이미 실행 가능한 상태여야 한다. 모델 digest와 metadata는 각 구조×seed 블록 전후에 fail-closed 검사한다. runtime이 달라지면 중단 기록을 보존하고 임의로 허용하지 않는다.

## 네 군과 평가

| 군 | facts ID | 규칙 노드 ID | 모델이 해야 하는 일 |
|---|---|---|---|
| baseline | 기존 자유 ID | 기존 자유 ID | 기존 explicit_rule 전체 생성 |
| short_uniform | n0001 계열 사전 표 | n0004 계열 현재 ID 지정 | 새 facts 작성, atom/rule/parents/final 작성 |
| atom_alias | 원자명=ID 사전 표 | 결론 원자명=현재 ID 지정 | 동일 |
| atom_tagged | node_원자명 사전 표 | node_결론 원자명 현재 ID 지정 | 동일 |

세 지정군은 같은 header·지원 필드·schema 지원 수준을 사용한다. facts에서 공개된 atom→ID 표와 허용 ID enum만 추가한다. 규칙에서 이미 제공되는 requested_rule의 결론으로 정한 현재 ID singleton enum만 추가한다. **정답 부모 목록, 필터링된 노드 목록, 새 전제, 중간 결과, 정답 graph를 제공하지 않는다.**

facts 노드 객체는 모델이 새로 출력한다. 잘못된 facts/ID도 원문 그대로 이후 요청의 history로 보낸다. 사후 이름 바꾸기, 충돌 회피용 새 ID 부여, 부모 추가, 응답 재시도, 성공한 군 선택은 없다.

baseline과 지정군의 비교는 ID 표상 및 지정 지원을 함께 포함하는 절차 효과다. 의미 명명 효과를 더 구체적으로 구분하기 위해 **동일 지원 수준의 short_uniform** 대조를 둔다.

## 사전 주평가

atom_alias − baseline의 **엄격 양방향 D 종단 성공률 차이**다. 각 구조마다 2 seeds × 4 표시의 8쌍을 집계하고, 8개 구조를 동일 가중한다. tagged의 결과를 보고 주평가를 바꾸지 않는다.

보조 대비: tagged − baseline, short − baseline, alias − short, tagged − short, tagged − alias. 단일 경로, 네 표시 전체, facts, ID 계약, 생성 의미, 최초 오류 전이, 직전 유효 경로 위험집합, 깊이·구조별 분포와 응답별 계산량을 별도로 기록한다.

## 배정·호출

- 기존 8개 구조, seed 64001001·64001002, 후보 위치×후보 ID 4표시, shallow/deep.
- 새 공유 선택 128단위: 값 비교 128회 + ID 조회 128회.
- 각 군 새 graph 128개, 양방향 pair 64개, 네 표시 bundle 16개.
- 전체 graph 512개, 목표 경로 선택 시 실제 추론 3,520회.
- 매핑 가능한 선택에서 경로 길이에 따른 추론 범위 3,392~3,648회.
- 최대 추론 슬롯 3,648개 + metadata 32개 = action 3,680개.
- 선택 출력이 형식 오류/매핑 불가능이면 이후 graph를 사전 규칙대로 skip한다. 미실행 graph의 의미 정확도를 실패로 만들지 않으며, 관측된 선택 실패와 전체 trace 실패를 별도로 남긴다.

## 산출물

```text
llm_experiments/v090/results_llm/
  v090_freshid_<timestamp>/
  v090_freshid_<timestamp>_evidence.zip
  v090_freshid_<timestamp>_independent.json
```

evidence에는 원요청·원응답, dispatch marker, hash-chain record, source snapshot, protocol/plan, runtime metadata, 상태, summary, diagnostics, 원본 v089 baseline을 포함한다. 설치 영수증과 시험·calibration 로그는 `automation_logs`에 별도 보존한다.

## 구현 검증 재현

Python 3.10 이상, 표준 라이브러리만 사용한다. 개발/검증 과정에서 원본 source 폴더 안에 파일을 추가하지 않는다.

```text
python -X utf8 -B selftest090.py --out <새 폴더>/selftest.json
python -X utf8 -B calibrate090.py --out <새 폴더>/calibration.json
python -X utf8 -B reproduce_synthetic.py --baseline <원본 v089 evidence.zip> --out <존재하지 않는 검증 폴더>
```

자체시험에는 `V090_BASELINE` 환경변수로 기준선 ZIP 경로를 전달한다. 자동 launcher는 이 값을 설정한다. synthetic execution은 실제 HTTP 호출 함수를 합성 교환기로 대체하며 새로운 Qwen 결과가 아니다.

`verify090.py`는 요청 재구성, 의미 판정, runtime 및 file/event 검사를 생산 설계와 별도로 수행한다. 집계·한국어 보고와 diagnostics 일부는 공유한다. 그룹·양방향·네 표시·주평가·구조별 대비·공유 선택 수는 `audit_metrics090.py`에서 별도로 재계산한다.

## 해석 범위

외부의 정확 D 수치와 고정된 primitive inference system 아래에서 출력된 proof DAG의 D_DAG를 측정한다. 모델의 자력 D 계산, hidden-state 제어, A/M 축 또는 새로운 구조 일반화를 주장하지 않는다. 현재 경로에서는 facts와 파생 atom이 중복되지 않는다는 조건을 검사하므로 semantic ID를 임의의 중복 도출 graph에 그대로 적용하지 않는다.
