# 저장소 구조

이 저장소는 하나의 애플리케이션을 계속 고치는 방식이 아니라, 각 실험 버전의 코드와 결과를 함께 보존하는 연구 저장소다. 따라서 과거 폴더를 합치거나 이름을 바꾸면 기존 실행 계획, 해시, 증거 ZIP의 경로가 깨질 수 있다. 아래 구분을 기준으로 필요한 위치를 찾고 새 실험은 새 버전 폴더에 추가한다.

## 빠른 길잡이

| 찾는 것 | 위치 | 설명 |
| --- | --- | --- |
| 결정론적 기준선 | `adm_minimal.py` | LLM 없이 A/D/M 기록을 생성하고 검사하는 단일 실행 코드 |
| 기준선 입력과 시험 | `examples/`, `tests/` | 고정 문제, 예시 trace, 단위시험 |
| 기준선 결과 | `results/` | 결정론적 실행 결과와 로그 |
| 연구 문서 | `docs/`, `research/` | 기준선 연구 노트와 논문·보충 자료 |
| 현재 LLM 기준선 | `local_llm/` | v0.4.6 실행 코드 |
| 초기 LLM 실험 | `archive/local_llm/` | v0.1~v0.4.5 계열의 역사적 소스 스냅샷 |
| v047 이후 실험 작업공간 | `experiments/` | 버전별 실행 패키지, 동결 계획, LLM 결과를 함께 보관 |
| 실험 코드 | `experiments/v047_paired_probe/` ~ `experiments/v054_order_probe/` | 현재 Git에 기록된 구현, 시험, 실행 스크립트, 검증 자료 |
| 실행 전 동결 계획 | `experiments/experiments_v047/` ~ `experiments/experiments_v054/` | 해당 버전의 실험 입력 또는 계획 |
| LLM 실행 결과 | `experiments/results_llm/` | run별 원문, 감사 결과, capture, plan, evidence ZIP |
| 배포 무결성 | `MANIFEST.sha256` | 결정론적 기준선 배포 파일의 SHA-256 목록 |

## 버전 흐름

```text
결정론적 기준선
├─ adm_minimal.py
├─ examples/
├─ tests/
└─ results/

초기 LLM 계열
├─ local_llm/                     현재 기준선 v0.4.6
└─ archive/local_llm/
   ├─ local_llm_old*              v0.1~v0.4.2 스냅샷
   ├─ local_llm_43                v0.4.3
   ├─ local_llm_0441              v0.4.4.1
   └─ local_llm_045               v0.4.5

후속 LLM 실험
└─ experiments/
   ├─ experiments_v047/ ... experiments_v054/   동결 계획
   ├─ results_llm/                              실행 결과와 증거
   ├─ v047_paired_probe/
   ├─ v048_seed_probe/
   ├─ v049_expression_probe/
   ├─ v050_criterion_probe/
   ├─ v051_adm_pilot/
   ├─ v052_adm_diagnostic/
   ├─ v053_depth_probe/
   └─ v054_order_probe/

연구 자료
├─ docs/                           결정론적 기준선 연구 노트
└─ research/
   ├─ paper/                       논문 자료
   └─ supplement/                  보충 자료
```

`archive/local_llm/`의 폴더도 삭제 후보가 아니라 재현용 스냅샷이다. 원래 폴더 이름을 유지했으며, 버전 간 중복 코드는 당시 실행 상태를 보존하므로 공통 모듈로 합치지 않는다.

## 새 실험을 추가할 때

1. 직전 버전의 폴더와 `experiments/results_llm/` 자료를 수정하지 않는다.
2. 새 코드는 `experiments/vNNN_<주제>_probe/`, 실행 계획은 필요하면 `experiments/experiments_vNNN/`에 둔다.
3. 실행 결과는 `experiments/results_llm/vNNN_<주제>_<run>/`처럼 새 run 이름으로 기록한다.
4. 결과 폴더, capture, plan, 감사 JSON, evidence ZIP은 한 실행의 증거 묶음으로 취급한다.
5. 각 버전의 실행법과 검증 명령은 해당 폴더의 `README.md`를 따른다.

## 로컬 생성 파일

루트 `.gitignore`는 Python 캐시, 테스트 캐시, IDE 설정과 임시 백업을 새 변경에서 제외한다. 이 규칙은 `results/`와 `experiments/`의 연구 자료를 무시하지 않는다. 연구 결과는 생성 파일이더라도 검증 근거이므로 별도로 보존한다.
