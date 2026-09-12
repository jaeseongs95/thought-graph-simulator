# v048: 발견 seed를 제외한 다중-seed 대조

v047에서 관측한 `(a AND (NOT b))`의 실패와 `((NOT b) AND a)`·실제 NOT→AND 연결의 성공이 **다른 생성 seed에서도 유지되는지** 조사한다. 기존 `local_llm`, `adm_minimal.py`, `v047_paired_probe`, 기존 결과는 교체하지 않는다.

기본 실험은 새 seed 10개 × 네 입력 × 여섯 경로 순서 × (원식 1회 + 교환식 1회 + 연결식 2회) = **최대 960회**다. NOT에서 유효한 bool이 나오지 않으면 해당 AND 호출만 생략하고 전체 파이프라인 실패로 기록한다. 그때 실제 호출 수는 960보다 작아질 수 있다.

Python 3.10 이상과 표준 라이브러리만 사용한다. 추가 `pip install`·모델 다운로드·모델 업데이트는 필요 없다. 원 패키지의 제작 시험 환경은 Linux였지만, 0.4.8-r1에서는 Windows CP949/UTF-8 충돌을 합성 재현하는 회귀시험을 추가했다. 실제 Windows OS 자체의 실행은 사용자 환경에서 `selftest`로 최종 확인한다.


## Windows Python 3.12 인코딩 패치 (0.4.8-r1)

`selftest`의 자식 Python CLI 출력을 즉시 UTF-8로 디코딩하던 경로를 수정했다. Windows 한국어 코드페이지(CP949) 출력이 섞여도 `_readerthread`의 `UnicodeDecodeError`가 발생하지 않도록 stdout/stderr를 먼저 bytes로 수집하고, 자식 Python에는 UTF-8을 강제하며, 필요한 경우 CP949를 손실 없이 strict decode한다. `errors="replace"`는 사용하지 않는다. 실제 실험 JSON/Markdown/원문은 계속 UTF-8이다.

**패치 전 소스로 v048 계획 파일을 이미 만들었고 아직 실제 `run`을 시작하지 않았다면 그 계획 파일을 삭제하고 이 패치로 `prepare`를 다시 실행한다.** 소스 fingerprint가 바뀌었으므로 이전 계획과 새 소스를 섞지 않는다. 실제 `run`을 이미 시작했다면 그 결과는 보존하고 새 RunName/새 계획으로 다시 시작한다.

상세 원인·검토·회귀 결과는 `docs/WINDOWS_ENCODING_FIX.ko.md`와 `validation/WINDOWS_ENCODING_REGRESSION.log`를 본다.

## 1. 설치

전체 ZIP의 `v048_seed_probe` 폴더를 저장소 아래에 둔다.

```text
thought-graph-simulator/
├─ local_llm/                       기존 그대로
├─ v047_paired_probe/               기존 그대로
├─ experiments_v047/
│  └─ v047_paired_01.plan.json       기존 외부 동결 계획
├─ results_llm/
│  └─ v047_paired_01/               기존 원문
└─ v048_seed_probe/                 이 패키지
   ├─ paired_probe_v048/
   ├─ paired_probe_v047/            변경하지 않은 감사 호환 코드
   ├─ tests_v048/
   ├─ tests_v047/
   ├─ docs/
   └─ validation/
```

## 2. 오프라인 시험 및 계획 동결

현재 PowerShell이 기존 `v047_paired_probe`에 있다면 다음부터 실행한다.

```powershell
Set-Location ..\v048_seed_probe

python -m paired_probe_v048 selftest
if ($LASTEXITCODE -ne 0) { throw "오프라인 시험 실패. 여기서 중단합니다." }

python -m paired_probe_v048 prepare --baseline-run ..\results_llm\v047_paired_01 --baseline-plan ..\experiments_v047\v047_paired_01.plan.json --out ..\experiments_v048\v048_seed_01.plan.json
if ($LASTEXITCODE -ne 0) { throw "기준선 감사 또는 계획 생성 실패." }
```

`prepare`는 v047의 `summary.json` 점수를 믿지 않는다. 동봉된 고정 v047 감사기로 원문을 다시 계산하며, 정확도와 무관하게 자료 완결성과 비교 가능성을 확인한다. 원문·설정의 수입 전후 해시를 비교하고, 새 실험에서는 발견 seed 1729를 제외한다.

여기까지 실제 Ollama 추론은 없다. `selftest`가 띄우는 서버는 테스트용 합성 HTTP 서버다.

**외부 v047 계획 파일이 실제로 없는 경우만** 아래 대체 명령을 사용한다. 자동 대체하지 않는다. 이 경로는 `snapshot_only`라는 약한 기준선 고정 방식으로 기록된다.

```powershell
python -m paired_probe_v048 prepare --baseline-run ..\results_llm\v047_paired_01 --accept-snapshot --out ..\experiments_v048\v048_seed_01.plan.json
if ($LASTEXITCODE -ne 0) { throw "계획 생성 실패." }
```

둘 중 하나만 실행한다. 같은 출력 계획은 덮어쓸 수 없다. `--accept-snapshot`은 v047 참조에만 적용되며, 생성된 v048 외부 계획 파일은 계속 별도로 보존해야 한다.

## 3. 실제 작은 모델 실행

v047에 사용한 Ollama 서버를 실행한 상태에서 다음을 수행한다. 모델·temperature·프롬프트·출력 스키마는 기존 원문에서 보존한다. 실험 중 다른 모델을 실행하거나 서버·모델 설정을 바꾸지 않는다.

```powershell
python -m paired_probe_v048 run --plan ..\experiments_v048\v048_seed_01.plan.json --out ..\results_llm\v048_seed_01
if ($LASTEXITCODE -ne 0) { throw "수집 미완료 또는 계약 오류. 기존 결과 폴더를 보존하세요." }

python -m paired_probe_v048 audit --plan ..\experiments_v048\v048_seed_01.plan.json --run ..\results_llm\v048_seed_01
if ($LASTEXITCODE -ne 0) { throw "오프라인 재감사 실패 또는 수집 미완료." }

Get-Content ..\results_llm\v048_seed_01\summary.ko.md -Encoding UTF8
```

`run`만 실제 모델 추론을 수행한다. 모델의 오답·형식 오류는 실패로 수집한다. 통신 오류나 응답 모델 불일치는 원문을 보존하고 중단하며 자동 재시도하지 않는다. 모델 digest·모델 정보 해시·Ollama 버전이 v047과 다르면 동등 실험으로 진행하지 않는다.

미완료 실행은 재개하거나 성공 부분만 합치지 않는다. 재실행이 필요하면 이전 자료를 보존한 채 별도 실험 이름과 새 계획을 사용하고, 재실행 이유를 기록한다. 모델 점수가 마음에 들지 않는다는 이유로 새 seed를 다시 선택하지 않는다.

## 4. 결과 묶기

```powershell
python -m paired_probe_v048 bundle --plan ..\experiments_v048\v048_seed_01.plan.json --run ..\results_llm\v048_seed_01 --out ..\results_llm\v048_seed_01_evidence.zip
if ($LASTEXITCODE -ne 0) { throw "증거 ZIP 생성 실패." }
```

이 ZIP은 결과 원문, 실행 소스 스냅샷, 별도 v048 동결 계획, 파일별 해시를 함께 담는다. v048 결과 재감사에 필요한 원문은 들어가지만, 과거 v047 원문 전체를 다시 담지는 않는다. v047 원문은 기존 폴더에서 계속 보존한다.

## 5. 결과 파일

| 파일 | 확인할 내용 |
|---|---|
| `summary.ko.md` | 전체 및 seed별 정확도, 양성 조건, 경로 성공, 비용 |
| `summary.json` | 분모·누락값·호출 상태·캐시·로딩 등 전체 집계 |
| `seed_results.json`, `seeds.csv` | 새 seed별 결과와 기존 현상의 재현 여부 |
| `trials.csv` | 입력·조건별 최종값과 파이프라인 중간값 |
| `calls.csv` | 실제 호출별 토큰·시간·요청 해시 |
| `request_repeats.csv` | 같은 요청의 반복에서 실제 응답이 달라졌는지 |
| `calls/`, `events.jsonl` | 채점 전의 요청·응답 원문과 연결 기록 |
| `audit.json` | 가장 최근 감사의 자료 판정. 재감사 실패 시 과거 PASS를 무효화 |

모델의 100% 정답과 자료 수집 성공은 다르다. 미실행 판단은 `not_recorded`와 null로 구분하며 완결 비교값을 만들지 않는다. 연결식은 교환식과도 비교하므로, 약한 원식만 기준으로 삼아 연결식의 우위를 주장하지 않는다.

## 보조 스크립트

`windows/Run-NextStep.ps1`에 같은 명령을 넣었다. `-Stage Prepare`, `Run`, `Audit`, `Bundle`로 구분하며 기본값은 추론이 없는 `Prepare`다. 직접 Python 명령과 중복 실행하지 않는다.

## 문서

- `docs/PROTOCOL.ko.md`: 사전 고정 실험 계약과 비용 정의.
- `docs/REVIEW_AND_FIXES.ko.md`: 상충하는 검토 관점, 실제 발견된 다섯 문제, 수정 근거.
- `docs/NEXT_STEPS.ko.md`: 결과에 따른 후속 연구 경로.
- `docs/SOURCE_NOTES.ko.md`: 기존 코드 출처와 확인한 공식 API 문서.
- `validation/VALIDATION.ko.md`: 실제 실행한 시험과 실행하지 않은 범위.

`validation/SYNTHETIC_960_EVIDENCE.zip`의 결과는 가짜 서버 검증 자료다. 사용자의 실제 모델에 대한 새 실험 결과가 아니다.
