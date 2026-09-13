# v065 — 마지막 규칙을 지정한 증명 구성 검사

v064의 원문18회는 완료됐지만 D 대응은0/6이다. 이번 소스는 **지정한 마지막 규칙으로 짧은/긴 완전 증명을 각각 구성할 수 있는지** 12회만 검사한다. 지정 구성의 성공을 자율적인 D 지시 제어 성공으로 세지 않는다.

## 휴대폰 원격 실행

별도로 제공한 `Run-v065-Auto.ps1` 한 파일을 PC 다운로드 폴더에 저장한 뒤 실행한다. 소스 ZIP이 내장돼 있어 수동 압축 해제는 필요 없다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v065-Auto.ps1"
```

자동화는 현재 작업 경로와 알려진 `D:\codex\AI논문\thought-graph-simulator`, 바탕화면 저장소 순서로 기존 폴더를 찾는다. 기준선은 이번 실제 `v064_direct_20260913_172703_019_evidence.zip`이다. 저장소의 `llm_experiments\v064\results_llm`, `results_llm`, 다운로드 폴더에서 **파일명뿐 아니라 동결 SHA**가 같은 원본을 찾는다.

다른 위치라면 다음처럼 지정한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Run-v065-Auto.ps1 -RepoRoot 'D:\내 저장소\thought-graph-simulator' -Baseline 'D:\결과\v064_direct_20260913_172703_019_evidence.zip'
```

`-CheckOnly`는 실제 Ollama 접근/추론 없이 자체시험과 원문 재감사·계획 준비만 수행한다. `-AllTests`는 빠른 기본시험 대신 전체 코드 시험을 실행한다. 시험용 로컬 HTTP 응답을 실제 모델 성과로 사용하지 않는다.

소스 ZIP을 수동 추출했으면 `llm_experiments\v065\probe\windows\Run-v065.cmd`를 더블클릭한다. 같은 폴더의 `Run-v065.ps1`에서 `-CheckOnly`도 지원한다.

## 자동 처리

내장 ZIP hash → 실제 소스 파일 검사 → 신규 v065 설치/동일 파일 재사용 → 빠른16개 자체시험 → 원 v064 전체 검산 → 새 계획/RunName → 기존 Qwen identity 확인 → 최대12회 → 원문 감사·증거 ZIP·독립 검산 → 요약/결과 경로 표시.

기존 소스·결과는 삭제하지 않는다. 변경된 v065 설치본은 백업하고 정식 파일을 설치한다. 실패한 실험을 다른 이름으로 자동 재시도하지 않으며 모델 다운로드·갱신·서버 시작도 하지 않는다. Ollama와 원래 Qwen 모델은 기존처럼 준비돼 있어야 한다.

## 구성

3문제 × 2seed × 짧은/긴 마지막 규칙 지정 =12회. 원 v064 문제·seed·모델·options·schema·규칙 순서는 같다. 원래 경로 지시 문장만 아래 유형의 문장으로 바꾼다.

```text
최종 goal 노드의 rule은 반드시 'r69'로 지정한다. 이 규칙을 마지막으로 사용하는 유효한 증명 하나를 구성한다.
```

규칙 ID는 의도적으로 주어진 과제 조건이다. 전체 정답 DAG/부모/중간 노드는 제공하지 않는다. 짧고 긴 규칙을 입력으로 지정하므로 결과가 달라져도 'D만으로 스스로 선택했다'고 해석하지 않는다. `docs/PROTOCOL.ko.md`에 결과별 다음 결정·종료 기준이 있다.

## 파일과 결과

- `run.py`: 무추론 prepare, 명시적 execute, 중단자료의 오프라인 finalize.
- `measure.py`: v064와 같은 원문 증명 검사.
- `verify.py`: 생산 측정/보고 모듈을 import하지 않는 독립 원문/요청/집계/한국어 보고 검산.
- `prior/v064_source_r3.zip`: hash로 고정한 이전 배포 감사 코드. 실제 입력 증거 snapshot은 실행하지 않는다.

완료 결과는 저장소의 `llm_experiments\v065\results_llm\v065_construct_<시간>_evidence.zip` 및 `_independent.json`이다. plan은 `llm_experiments\v065\experiments` 아래에 별도 보존한다. 부분 실행은 원문을 보존하며 현재 frozen source의 finalize로 추론 없이 묶을 수 있다. 이미 만들어진 summary/ZIP을 덮어쓰지 않는다.

## 개별 명령

작업 위치는 `probe`이고 `V065_BASELINE`은 이번 원 v064 ZIP이다.

```powershell
$env:V065_BASELINE = 'D:\보존 경로\v064_direct_20260913_172703_019_evidence.zip'
python -X utf8 -B -m unittest discover -s tests -v
python -X utf8 -B run.py prepare --baseline $env:V065_BASELINE --run-name v065_manual --out ..\experiments\v065_manual.plan.json
python -X utf8 -B run.py execute --plan ..\experiments\v065_manual.plan.json --baseline $env:V065_BASELINE --out ..\results_llm\v065_manual
python -X utf8 -B verify.py ..\results_llm\v065_manual_evidence.zip
```

모든 코드·계획·원문·측정·보고는 고정된 동일 판본으로 묶인다. 합성 검사 및 소스 검증은 실제 모델의 실험 성공이 아니다. Windows 실기 실행 여부를 포함한 실제 배포 검증 결과는 별도 분석 ZIP의 `VALIDATION_RESULT.json`을 참조한다.
