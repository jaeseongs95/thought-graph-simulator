# v083 — 세 가설의 동결 대조 실험

v082의 실제 분석을 출발점으로 **정확한 외부 자료의 지원**, **전체 계산표 대 숫자 요약**, **요청 지표의 숫자 교환**을 비교한다. 정확한 자료는 실험자가 사전 작성한 양성 대조이며 모델의 자력 계산 결과가 아니다.

## 실행

필요 환경은 기존 Python 3.12 이상과 기존 Ollama/qwen3:4b-instruct 설치다. 모델·서버 identity는 v082에 기록된 계약을 유지한다. 자동 업데이트·다운로드·서버 시작은 하지 않는다. 추가 Python 패키지는 없다.

필수 외부 입력: `v082_profilepair_20260915_100721_984127_evidence.zip`. 파일명 접미사 `(1)` 등은 허용하지만 내용 해시가 정확히 일치해야 한다. Downloads 또는 저장소의 `llm_experiments/v082/results_llm`에서 찾는다.

```powershell
# 설치·모든 자체시험·교정·기준 evidence 재감사·계획 동결까지만. 모델 조회/추론 없음.
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v083-Auto.ps1" -CheckOnly -AllTests

# 기존 Ollama가 실행 중인 상태에서 한 배치 실행.
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v083-Auto.ps1"
```

경로를 명시하는 경우:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v083-Auto.ps1" -RepoRoot "D:\codex\AI논문\thought-graph-simulator" -Baseline "$env:USERPROFILE\Downloads\v082_profilepair_20260915_100721_984127_evidence.zip"
```

`-CheckOnly`도 로컬 설치·로그·계획 파일은 생성한다. 시작 가드나 모델 호출은 만들지 않는다. 실제 실행은 별도 새 계획 이름으로 진행하며, 같은 버전의 시작 가드가 이미 있으면 중단한다. 부분 결과를 삭제하거나 반복 실행하지 않는다.

## 결과

```text
llm_experiments/v083/results_llm/
  frozen_batch.started.json
  v083_controlcross_<시각>/
    plan.json, status.json, summary.json, summary.ko.md
    wire/, records/, metadata/, source/, baseline/
  v083_controlcross_<시각>_evidence.zip
  v083_controlcross_<시각>_independent.json
```

D는 직접군·정확전체군·정확요약군만 증명 생성까지 실행한다. W와 값교환군 D는 선택 진단만 수행하므로 보고서에 ‘배정 없음’이라고 표시한다. 이는 0점이나 미실행 장애가 아니다. 선택은 네 군 각각 96개, graph는 세 군 D 각64개와 공통 참조16개로208개다.

기존 graph 성공 기준을 유지하며 미관측·논리 실패·전송/identity/길이 종료·사전 미배정을 구분한다. 제공 숫자를 따른 결과와 실제 D를 맞힌 결과도 다르다.

## 검산·개발 시험

```powershell
cd D:\codex\AI논문\thought-graph-simulator\llm_experiments\v083\probe
$env:V083_BASELINE = "$env:USERPROFILE\Downloads\v082_profilepair_20260915_100721_984127_evidence.zip"
python -X utf8 -B -m unittest discover -s tests -v
python -X utf8 -B calibrate083.py
python -X utf8 -B verify083.py "D:\경로\v083_controlcross_..._evidence.zip"
```

생산 채점과 독립 검산의 규칙 계산·요청 재구성·graph/단계/집계는 별도 구현이다. 한국어 렌더러만 공통이다. 독립 검산은 내부 일관성 확인이며 외부에서 실제 로컬 실행을 인증하는 수단은 아니다. 자체시험의 합성 응답은 모델 관측이 아니다.

세부 가설·배정·해석·종료 규칙은 `docs/PREREGISTRATION.ko.md`를 따른다.

## r2 배포 수정 (2026-09-15)

- 연구 설계, 문제, seed, 요청 계약, 채점 기준은 r1과 동일하다.
- `tests/test_runtime.py`의 fault-injection 경로 판정이 POSIX 구분자 `/`를 문자열로 하드코딩해 Windows에서 의도한 crash를 주입하지 못하던 자체시험 버그만 수정했다.
- r2 자동화는 정확히 알려진 r1 설치본만 `probe.pre_r2_windows_test_bug`로 보존 이동한 뒤 r2를 설치한다. 실제 frozen batch guard가 이미 있으면 기존 실행 차단 규칙이 그대로 우선한다.
