# v091 — 고정 생성기의 신규 구조·동일 구조 재명명 분리 평가

이 배포본은 v090의 네 생성기와 실제 요청 렌더러를 보존한다. 실패한 응답을 고치지 않고, 새로운 topology의 종단 효과와 기존 topology의 표면 재명명 효과를 별도로 측정한다. 자체시험·calibration·합성 실행은 실제 Qwen 연구 결과가 아니다.

## 실행

`Run-v091-Auto.ps1`은 소스 ZIP을 포함한 단일 실행 파일이다. 기존 프로젝트에 `llm_experiments/v091/probe`를 설치하며 v090 및 그 이전 소스·manifest·로그·guard·evidence를 수정하지 않는다.

먼저 Downloads에서 다음을 실행한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v091-Auto.ps1" -CheckOnly -AllTests
```

자체시험·calibration·prepare가 통과하면 `-CheckOnly` 없이 실행한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v091-Auto.ps1"
```

Ollama 서버는 사용자가 실행해 둔 0.34.1이어야 한다. 모델은 동일 digest의 `qwen3:4b-instruct`이며 다운로드·갱신·서버 시작은 하지 않는다. runtime identity가 다르면 모델 추론 전에 중단한다. 실제 실행 이후 frozen guard를 삭제하거나 새 RunName으로 재실행하지 않는다. CheckOnly는 inference guard를 만들지 않고 Ollama에도 조회하지 않는다. CheckOnly에서 사용한 이름은 plan/log 보존 때문에 실제 실행에 재사용하지 않는다.

기준선은 `v090_freshid_20260916_145527_520790_evidence.zip`이다. `v090/results_llm` 또는 Downloads에서 SHA-256이 일치하는 원본을 찾는다. 필요 시 `-RepoRoot`와 `-Baseline`으로 기존 경로를 지정한다. 기준선은 소스·계약·과거 원요청 회귀를 검증하는 자료이며 새로운 facts 이력에 넣지 않는다.

## 세 평가 묶음

| cohort | 대상 | 역할 |
|---|---|---|
| known_original | U01~U08 원형 | 같은 배치에서 기존 구조 재실행 |
| known_renamed | U01~U08의 R1 전단사 재명명 | topology·D·규칙수·순서는 동일, 원자명·규칙명만 변경 |
| new_topology | V01~V08 | 새 의존 구조의 주평가 |

각 묶음은 8문제×2seed×4표시×2방향×4군=512개 새 graph다. 두 known 묶음은 같은 8개 topology이므로 신규 구조 16개로 세지 않는다. 전체 구조는 기존8+신규8=16개, 입력 표면형은24개, graph는1,536개다.

모든 묶음의 생성군은 `baseline`, `short_uniform`, `atom_alias`, `atom_tagged`이며 새 two-stage 선택을 군끼리 공유하고 facts부터 별도로 새로 생성한다. 기존과 동일한 규칙 지정·ID 지원·schema·sampling을 사용한다. 정답 부모 목록·자동 부모 보충·응답 재명명·성공군 대체·재시도는 없다.

## 주평가와 호출 규모

주평가는 **new_topology만**의 구조 동일가중 `atom_alias − baseline` 엄격 양방향 D 종단 차이다. known 결과, 재명명 대비, 5개 보조 대조는 별도 필드다. new 결과가 나쁘다고 known과 합산하거나 tagged로 주평가를 교체하지 않는다.

전체 공유 선택은 compare384+lookup384=768회. 각 군은384개 graph를 생성한다. 목표 경로 선택 시10,560회, 매핑 가능한 선택에서 규칙 길이에 따른 호출 범위10,176~10,944회, metadata32개를 포함한 최대action10,976개다. 매핑 불능 선택은 관측된 선택 실패로 남기고 이후 graph를 논리 오답·깊이0으로 채우지 않는다. 단일 배치이며 묶음별로 별도 자동 실행하거나 좋은 결과만 골라 합치지 않는다.

## 해석과 출력

`summary.ko.md`와 `summary.json`은 세 cohort별 성공·pair·bundle·구조별 효과를 분리한다. `renaming_contrasts`는 original/R1을 topology·seed·표시·방향으로 대응한다. `diagnostics.json`은 최초 오류·prefix 위험집합·이전 부모 재사용·조상 치환 관측을 기록한다. ID 변경은 사전 문제 변환에만 적용하고 모델의 응답 content는 공백까지 그대로 다음 입력에 넘긴다.

완료 파일은 `v091_structural_<timestamp>_evidence.zip`과 `_independent.json`이다. source snapshot, frozen plan, 원요청/원응답/dispatch, runtime metadata, summary, diagnostics, 해시 manifest를 보존한다.

## 검증과 재현

배포 ZIP에서 설치한 probe에서 자체시험을 실행한다. 필요한 기준선은 환경변수 `V091_BASELINE`으로 지정한다. 소스 디렉터리 안에 검증 출력 파일을 추가하면 해시가 달라지므로 출력은 별도 폴더에 둔다.

```text
python -X utf8 -B selftest091.py --out <새 폴더>/selftest.json
python -X utf8 -B calibrate091.py --out <새 폴더>/calibration.json
python -X utf8 -B reproduce_synthetic.py --baseline <v090 evidence 원본> --out <존재하지 않는 새 폴더>
```

`reproduce_synthetic.py`는 HTTP 교환기를 합성 교환기로 바꾸어 전체 실행을 시험한다. 실제 Qwen이나 포트11434를 호출하지 않는다. corpus는 `python -X utf8 -B build_corpus091.py --out <새 경로>/corpus.json`으로 모델 없이 재현한다. 최종 배포 검증의 실제 수치·환경·제외 항목은 외부 `VALIDATION_RESULT_v091.json`에 기록한다.

설계 세부 사항은 `docs/PREREGISTRATION.ko.md`, 구현 경계는 `docs/IMPLEMENTATION.ko.md`를 참조한다.
