# v067 — 정상 참조 계획 재구성 양성 대조

**정답 규칙 경로를 실험자가 제공하는 검사다. 이 결과를 자율적인 D 제어 또는 A/M 성공으로 사용하지 않는다.** v066의 모델 계획→graph 실험은0/12로 종료됐고, 여기서는 아직 관측하지 못한 '정상 계획을 받았을 때 graph를 작성할 수 있는가'만 최대12회 확인한다.

## 휴대폰 원격 실행

별도로 제공한 `Run-v067-Auto.ps1` 한 파일을 PC 다운로드 폴더에 저장하고 다음을 실행한다. 검증한 소스 ZIP이 내장되어 수동 압축 해제가 필요 없다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v067-Auto.ps1"
```

기존 저장소와 `v066_staged_20260913_185054_745451_evidence.zip`을 검색한다. 파일명뿐 아니라 SHA-256 `9ad2cf76455d5b10584183b0123be96a9211586210732af7e9ffb649aac9f90e`가 같은 원본만 사용한다. 저장소는 현재 경로/부모, `D:\codex\AI논문\thought-graph-simulator`, 바탕화면을 확인한다. 기준선은 v066/results_llm, 공용 results_llm, 다운로드 폴더에서 찾는다.

다른 위치면 `-RepoRoot '저장소 경로' -Baseline '원 v066 ZIP 경로'`를 지정한다. `-CheckOnly`는 실제 Ollama를 조회하거나 추론하지 않고 사전검사·기준선 감사·계획 생성까지만 한다. `-AllTests`는 빠른 검사가 아니라 전체 합성 시험까지 먼저 실행한다.

모델 다운로드·갱신·서버 시작은 없다. 기존 Ollama와 동일 Qwen 모델이 준비돼 있어야 한다. 실제 수집이 끝나거나 오류로 멈춘 뒤 새 실행을 자동으로 시작하지 않는다.

## 무엇이 달라졌나

v066: 모델이 규칙 경로를 선택 → 그 원문을 모델에게 전달 → 전체 graph 생성.

v067: 실험자가 정상 규칙 경로를 명시적으로 제공 → 모델이 전체 graph 생성.

세 문제×두 seed×짧고 긴 참조 두 개=12회다. 생성 옵션은 기존과 같으며 설정상 출력 총상한49,152이다. metadata12묶음은 추론수와 별도다. 경로의 정답을 알려주는 대신 노드 ID/부모/final 정답 graph는 주지 않는다. 모델의 오답은 고치지 않는다.

성공 조건은 원문 graph의 strict 타당성 + 제공한 모든 규칙의 순서 이행 + 실제 D와 참조 깊이 일치다. 12/12라도 정상 입력의 재구성 기준선일 뿐이며, 모델의 경로 선택이나 D/A/M 본 가설 성공이 아니다. 자세한 분기 종료·범위는 `docs/PROTOCOL.ko.md`를 따른다.

## 결과

```text
llm_experiments/v067/experiments/v067_reference_<실행시각>.plan.json
llm_experiments/v067/results_llm/v067_reference_<실행시각>/summary.ko.md
llm_experiments/v067/results_llm/v067_reference_<실행시각>_evidence.zip
llm_experiments/v067/results_llm/v067_reference_<실행시각>_independent.json
```

기존 결과는 덮어쓰지 않는다. 설치된 동일 버전도 실제 source hash가 같을 때만 재사용하며 변경본은 백업한다. stderr 존재가 아니라 하위 프로세스의 종료 코드로 판단하고 원시 로그를 보존한다.

## 수동 실행 및 오프라인 분석

ZIP 수동 추출 후 작업 위치는 `llm_experiments/v067/probe`다. Windows에서는 `windows/Run-v067.cmd`로도 실행할 수 있다.

```powershell
$env:V067_BASELINE='D:\보존경로\v066_staged_20260913_185054_745451_evidence.zip'
python -X utf8 -B -m unittest discover -s tests -v
python -X utf8 -B run.py prepare --baseline $env:V067_BASELINE --run-name v067_manual --out ..\experiments\v067_manual.plan.json
python -X utf8 -B run.py execute --plan ..\experiments\v067_manual.plan.json --baseline $env:V067_BASELINE --out ..\results_llm\v067_manual
python -X utf8 -B verify.py ..\results_llm\v067_manual_evidence.zip
```

현재 v066을 다시 분석하기만 할 때는 다음을 쓴다. 출력 폴더는 새 이름이어야 한다. 기존 원문은 변경하지 않는다.

```powershell
python -X utf8 -B analyze_baseline.py $env:V067_BASELINE --out ..\validation\v066_reanalysis_01
```

실제 GPU 실험과 합성 HTTP 자체시험은 provenance로 구분한다. 최종 배포 시험 수·제외 항목·ZIP 및 자동화 hash는 별도 분석·검증 ZIP에 기록했다.
