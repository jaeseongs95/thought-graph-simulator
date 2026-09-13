# v068 — 전체 graph vs nodes→final 참조 재구성 대조

v067 실제 12개 원응답은 **4/12 성공**이다. 기존 성공·실패 판정은 바꾸지 않는다. 이번 버전은 정상 참조 경로를 제공한 상태에서 **증명 노드 배열을 먼저 작성하고, 그 원문을 본 별도 모델 호출이 최종 노드 ID만 지정하는 출력 계약**을 한 번 비교한다. 자율 D 제어 실험이 아니다.

## 실행

별도로 제공한 `Run-v068-Auto.ps1` 한 파일을 PC 다운로드 폴더에 저장한 뒤 실행한다. 소스 ZIP이 파일 안에 들어 있으므로 별도 압축 해제가 필요 없다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\Run-v068-Auto.ps1"
```

기존 Ollama와 `qwen3:4b-instruct`를 켜 둔다. 프로그램은 모델 다운로드·갱신·서버 시작을 하지 않는다. 기존 저장소를 자동 탐색하고, `llm_experiments/v068`에 새 버전으로 설치한다. v067은 덮어쓰지 않는다.

입력은 이번 v067 evidence ZIP이다. 파일명이 달라도 SHA-256이 다음과 같은 파일만 사용한다.

```text
68ab53158bdbcdbd1f079be1b1400950cd881d12191a0a8ac307d582444b205f
```

기본 검색 위치는 저장소의 `llm_experiments/v067/results_llm`, `results_llm`, 사용자 다운로드 폴더다. 원본 파일 이름의 `(1)` 같은 복사 접미사는 허용한다. 자동 탐색이 안 되는 경우 `-RepoRoot '저장소 경로' -Baseline '이번 v067 evidence ZIP 경로'`를 지정한다.

`-CheckOnly`를 붙이면 소스 검증·단위시험·v067 재감사·계획 생성까지만 한다. 실제 Ollama 조회와 추론은 없다. `-AllTests`는 실행 전 전체 합성 HTTP·변조·하위프로세스 시험을 포함한다. 기본 실행은 빠른 논리/무보정/요청 대조 시험을 수행한다.

## 무엇을 비교하나

세 문제 × 두 seed × 짧고 긴 참조 = 12개 짝에서 비교한다.

- direct: v067과 요청 바이트가 동일한 전체 graph 출력, 12회.
- staged: nodes만 출력 12회 → 실제 원문 전달 → final_node_id만 출력 12회.

총 모델 호출은 최대 36회다. 개별 호출의 옵션은 v067과 같다. `num_predict=4096`이므로 설정상 생성 상한은 147,456이며 실제 사용량이 아니다. 두 단계는 한 단계보다 호출과 생성 상한이 크므로 동일 예산 대조나 비용 우월성 검사가 아니다. 문제/경로별 두 seed에서 direct/staged 순서를 반전한다.

호스트는 두 모델이 사전에 나누어 맡은 필드만 결합한다. 첫 응답의 nodes를 수정하지 않고, 둘째 응답의 final_node_id를 추측·치환하지 않는다. final 응답을 만들 때 정답 후보 노드 목록이나 선택된 목표 ID를 호스트가 제공하지 않는다. 형식상 전달 가능한 틀린 nodes 원문도 그대로 다음 호출에 들어간다.

## 결과 위치

```text
llm_experiments/v068/results_llm/v068_nodesfinal_<시각>/summary.ko.md
llm_experiments/v068/results_llm/v068_nodesfinal_<시각>_evidence.zip
llm_experiments/v068/results_llm/v068_nodesfinal_<시각>_independent.json
llm_experiments/v068/results_llm/automation_logs/<실행이름>/run.log
```

분석용으로 evidence ZIP과 independent JSON을 함께 올린다. 오류로 중단된 결과도 보존되며 같은 실행을 자동 재시도하지 않는다. 시작 표지만 있고 응답이 없는 pending 호출은 미측정으로 남는다. 중단 시 receipt의 inference_calls는 시작 표지 수이므로 실제 서버 수신 건수의 인증으로 사용하지 않는다.

## 수동 실행

소스 ZIP을 전체 추출한 뒤 `llm_experiments/v068/probe`에서 실행한다.

```powershell
$env:V068_BASELINE='D:\보존경로\v067_reference_20260913_192953_571655_evidence.zip'
python -X utf8 -B -m unittest discover -s tests -v
python -X utf8 -B run.py prepare --baseline $env:V068_BASELINE --run-name v068_manual --out ..\experiments\v068_manual.plan.json
python -X utf8 -B run.py execute --plan ..\experiments\v068_manual.plan.json --baseline $env:V068_BASELINE --out ..\results_llm\v068_manual
python -X utf8 -B verify.py ..\results_llm\v068_manual_evidence.zip
```

Python 3.10 이상이며 외부 pip 패키지는 필요 없다. `verify.py`는 생산 채점기·보고서·요청 생성기를 import하지 않고 원문, 요청, 스케줄, 전달값과 증명 구조를 재계산한다. 독립 코드는 같은 문제 명세·실험 계약을 공유한다. 별도 연구자/외부 에이전트의 독립 재현을 뜻하지 않는다. 개발 중 합성 응답 시험과 실제 Qwen 추론은 구별하며 **이 소스를 작성하는 동안 실제 Qwen v068 추론은 실행하지 않았다.**
