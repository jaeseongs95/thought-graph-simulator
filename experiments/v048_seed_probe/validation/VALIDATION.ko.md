# v048 실제 검증 기록

## 완료한 검증

| 검증 | 실제 결과 | 기록 |
|---|---|---|
| 최초 신규 기능 시험 | 66개 통과 | `INITIAL_FUNCTIONAL_TESTS.log` |
| 추가한 적대적 회귀 시험, 수정 전 | 5개 모두 실패: 보호 기능이 없음을 재현 | `REVIEW_BEFORE_FIX.log` |
| 같은 적대적 회귀 시험, 수정 후 | 5개 모두 통과 | `REVIEW_AFTER_FIX.log` |
| 원 패키지 최종 전체 시험 | **166개 통과**: 기존 v047 75개 + v048 91개 | `SELFTEST.log` |
| 기본 10-seed 규모의 CLI 실행 | 가짜 HTTP 요청 **960회** 기록 | `SYNTHETIC_960_CLI.log` |
| 가짜 서버 종료 후 원문 감사 | 실행 직후 결과와 같음 | `SYNTHETIC_960_RESULT.json` |
| 본 감사기를 import하지 않는 별도 수동 진리표 검사 | 합성 원문 **960건** 및 실제 부모값 전달 대조 | `INDEPENDENT_SYNTHETIC_CHECK.json` |
| 실제 사용자 v047 자료 재감사 | 96건, 기존 18/24·24/24·24/24와 일치 | `ACTUAL_BASELINE_COMPATIBILITY.json` |
| 실제 v047 설정 수입 및 요청 생성 호환 | 슬롯/부모값 조합 **1,200회 바이트 비교** 일치 | 같은 호환 검사 JSON |
| 사용자 v047 원문 변경 여부 | 변경 없음 | 같은 호환 검사 JSON |
| 고정 v047 코드 및 시험 보존 | 받은 패키지의 Python 소스와 바이트 일치 | `BUILD_STATUS.json` |
| 배포 ZIP을 새 폴더에 풀어 재시험 | **166개 모두 통과** | `RELEASE_UNPACK_SELFTEST.log` |
| 배포 ZIP 속 합성 증거 ZIP을 다시 풀어 감사 | 오프라인 감사 통과, 960회 기록 확인 | `RELEASE_EVIDENCE_REPLAY.log` |

## 원시 합성 증거

`SYNTHETIC_960_EVIDENCE.zip` 안에 960회 요청·응답, event 체인, 런타임 식별 기록, 소스 스냅샷, 외부 v048 계획과 묶음 파일 해시를 담았다. 가짜 모델 이름은 `test-only:4b-instruct`이며 출처는 `synthetic_fixture`, 새 모델 추론 표기는 False다.

합성 서버가 원식에는 항상 false, 교환식·primitive에는 올바른 값을 반환하도록 설정한 결과를 검사한 것이다. 합성 점수 180/240·240/240·240/240은 **프로그램이 그 패턴을 제대로 수집·채점했는지**의 증거이며 사용자의 모델 성과가 아니다.

전체 파이프라인의 중간값·최종값 여덟 비트 256조합 시험도 포함한다. 모든 단계가 맞는 한 조합만 전체 성공이며, 최종값만 모두 맞고 중간값이 틀린 15조합은 전체 경로 성공으로 세지 않았다. 256조합은 코드 검사용 합성 경우의 수다.

## 실제 사용자 자료의 범위

이번에 받은 실제 자료에는 v047 실행 폴더 안의 `plan.snapshot.json`이 있었고, 별도로 보관한 원래 외부 계획 파일은 없었다. 따라서 제작 환경의 실제 자료 수입은 `snapshot_only`로 기록했다. 그 snapshot의 계획 해시는 사용자가 제시한 `62e31da3fcc552c600affa9f4c1d18162e6919003d2df37d115b3f4486a8620a`와 일치한다.

v048 동결 계획 생성과 원문 호환 검사는 네트워크 호출 없이 수행했다. 실제 모델 호출을 960회 실행한 것은 아니다.


## 0.4.8-r1 Windows 인코딩 패치 추가 검증

| 검증 | 실제 결과 | 기록 |
|---|---|---|
| 패치 후 전체 selftest | **171개 통과** | `SELFTEST_WINDOWS_FIX.log` |
| 기존 UTF-8 즉시 decode 방식으로 CP949 재현 | 동일 계열 `UnicodeDecodeError` 재현 | `WINDOWS_ENCODING_REGRESSION.log` |
| 새 bytes 수집 + strict fallback 방식 | 같은 CP949 stdout/stderr를 손실 없이 복원 | 같은 로그 |
| UTF-8/CP949/ASCII/불완전 바이트 회귀 | 추가 5개 시험 모두 통과 | `SELFTEST_WINDOWS_FIX.log` |
| 패치 후 합성 HTTP 전체 경로 | **960회** 요청, 서버 종료 후 재감사 동일 | `SYNTHETIC_960_WINDOWS_FIX.log`, `SYNTHETIC_960_WINDOWS_FIX_EVIDENCE.zip` |
| 패치 후 독립 원문 검사 | 960회 및 pipeline 부모값 전달 확인 | `INDEPENDENT_WINDOWS_FIX.json` |
| 실제 사용자 v047 원문으로 계획 준비 | `--accept-snapshot`에서 네트워크·새 추론 없이 성공 | `ACTUAL_V047_PREPARE_WINDOWS_FIX.log` |

이 패치는 테스트/검증 subprocess 텍스트 경계만 변경한다. 실제 LLM HTTP 실행기, 원식/교환식/파이프라인 요청 생성, seed 목록, 스케줄, 채점 및 비용 집계는 변경하지 않았다. 실제 Windows OS에서의 최종 실행 확인은 사용자의 `python -m paired_probe_v048 selftest` 결과로 남는다.

## 실행 환경과 남은 제약

패치 제작 환경은 Linux x86_64, Python 3.13.5다. 실제 Windows/PowerShell 프로세스 자체는 이 환경에서 실행하지 않았지만, CP949 바이트를 생성하는 자식 프로세스로 사용자가 보고한 디코딩 실패를 재현하고 수정 경로를 검증했다. Python 코드는 3.10 이상에서 제공되는 문법·표준 라이브러리 범위로 작성했으며, 사용자의 Python 3.12/Windows에서는 포함된 `selftest`를 먼저 실행하도록 안내했다.

실험의 실제 모델 성공률, 다른 seed에서의 재현 여부, 다른 표현·모델·A/D/M 조작의 효과는 이 제작 검증으로 측정하지 않았다. 기본 `run`의 원시 결과로 판정할 항목이다.

## 재현 명령

패키지 루트에서:

```text
python -m paired_probe_v048 selftest
python validation/reproduce_synthetic_960.py --out <새로운_검증_폴더>
```

독립 합성 원문 검사:

```text
python validation/independent_raw_check.py --plan <새로운_검증_폴더>/external_plan/v048.plan.json --run <새로운_검증_폴더>/run
```

둘째 스크립트도 실제 Ollama를 호출하지 않는다. 새 검증 폴더만 사용하며 기존 검증 결과를 덮어쓰지 않는다.
