# v074 — D 경로 선택에서 실제 증명 생성까지

**실제 Qwen 추론은 아직 실행 전이다.** v073 수치 인터페이스 분기는 종료했다. 이 버전은 숫자/공백 탐색을 반복하지 않고 후보 경로 선택 원응답을 단계별 증명 생성에 연결한다.

상세 설계: `docs/PROTOCOL.ko.md`  
업데이트된 장부: `docs/PLAN_LEDGER.ko.md`  
이전 r1 원문: `docs/PLAN_LEDGER_v073_frozen.ko.md`

## 실행

기존 Ollama 서버와 `qwen3:4b-instruct`가 있어야 한다. Python 3.10 이상과 표준 라이브러리만 사용한다. 설치나 다운로드를 자동 수행하지 않는다.

배포된 `Run-v074-Auto.ps1`을 다운로드 폴더에 저장하고 기존 v073 evidence ZIP을 다운로드 폴더 또는 `llm_experiments/v073/results_llm`에 보관한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v074-Auto.ps1"
```

추론 없는 설치·자체시험·v073 재검산·계획 생성:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v074-Auto.ps1" -CheckOnly
```

저장소 또는 파일을 자동으로 찾지 못할 때만 명시한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v074-Auto.ps1" -RepoRoot "D:\codex\AI논문\thought-graph-simulator" -Baseline "$env:USERPROFILE\Downloads\v073_interface_20260914_060416_993148_evidence.zip"
```

`-PythonPath`로 설치된 python.exe를 명시할 수 있다. `-AllTests`는 전체 합성/반례 시험을 선택한다. 기본 실행은 빠른 오프라인 논리 시험을 수행한 뒤 v073 감사와 계획 생성을 진행한다. 기존 소스가 다른 내용이면 덮어쓰지 않고 중단한다. `-NoOpen`은 결과 탐색기 열기를 생략한다.

## 규모와 결과

선택기·생성기는 같은 Qwen이다. 본실험은 24건, 참조 구성은 12건이다. 최대 214회 추론이며 실제 선택 경로 길이에 따라 달라진다. 모든 요구에 맞는 경로 선택이면 총 186회다. 실행 로그의 226개 진행 슬롯에는 추론하지 않는 조건부 생략과 모델 정보 점검이 포함된다.

```text
llm_experiments/v074/results_llm/v074_endtoend_<시각>_evidence.zip
llm_experiments/v074/results_llm/v074_endtoend_<시각>_independent.json
```

두 파일이 분석 입력이다. `summary.ko.md`는 함께 생성되지만 요약만으로 검증을 대체하지 않는다.

## 오류와 보존

실패한 선택·그래프를 교정하지 않는다. 형식상 대응 가능한 오선택도 그 경로대로 실행한다. 후보 ID를 읽을 수 없으면 생성 호출은 미실행 사유를 남긴다. HTTP/transport/identity 또는 생성 예산 초과는 배치를 중단한다. 원문과 pending을 보존하고 자동 재시도하지 않는다.

인터럽트 후 증거만 다시 묶는 명령은 **추론하지 않는다**. 반드시 해당 실행의 동결 소스에서 수행한다.

```powershell
python -X utf8 -B .\llm_experiments\v074\probe\run.py finalize --run ".\llm_experiments\v074\results_llm\v074_endtoend_실제실행이름"
```

이미 완성된 산출물은 내용이 동일할 때만 재확인을 허용한다. 다른 내용으로 덮어쓰지 않는다. 다음 버전 또는 다음 배치를 자동 실행하지 않는다.

## 검증 범위

`measure.py`와 `stages.py`는 v069 소스와 바이트 동일하게 유지했다. `audit_graph.py`는 과거 독립 검산의 Kahn/고정점 계산을 이식했다. `verify.py`와 `audit_model.py`는 생산 요청·채점 모듈을 import하지 않고 일정, 실제 선택 원문, 요청, 단계 계약, 최종 graph와 집계를 재계산한다. 증거는 동결 소스를 포함한다.

검산은 번들 내부 일관성을 확인할 뿐 외부 장비의 실제 실행 사실이나 완전히 일관되게 새로 작성된 허위 로그를 인증하지 않는다. 테스트의 합성 HTTP는 모델 성능 결과가 아니다. Windows PowerShell 네이티브 검증 여부는 배포 검증 기록을 따른다.

이 배치의 성공 여부는 새로운 종단 계약의 결과다. v069 구성 성공, v073 부분 숫자 성공, 코드 시험 성공을 본실험 성공으로 합산하지 않는다.
