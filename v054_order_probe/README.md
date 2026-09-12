# v054 — 규칙 나열 순서와 D 방향 제어 대조

v053 실제 결과는 유효 증명 116/120, 선택적 D 제어 0/40이었다. 깊이 정의를 덧붙여도 역할에 따른 경로 변경은 나타나지 않았다. 이 버전은 모델을 바꾸거나 점수를 보정하지 않고, **규칙의 제시 순서에 따른 경로 선택과 shallow/deep 요청에 따른 제어를 구분**한다.

## 설치와 실행

ZIP의 `v054_order_probe` 폴더를 기존 `thought-graph-simulator` 저장소 아래에 **추가**한다. `v053_depth_probe`, 이전 결과와 증거 ZIP은 교체하거나 삭제하지 않는다.

PowerShell에서 새 폴더로 이동한 다음 실행한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\windows\Run-All.ps1
```

기준선은 `..\results_llm\v053_depth_01_evidence.zip`을 우선 후보로 찾는다. 폴더 안 또는 저장소 루트의 같은 이름도 후보이며, 후보가 여러 개이면 임의로 고르지 않는다. 그 경우 경로를 지정한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\windows\Run-All.ps1 -BaselineBundle "C:\자료\v053_depth_01_evidence.zip"
```

실행 순서는 `selftest → prepare → show → run → audit → bundle`이다. `prepare/show`는 오프라인이며 모델을 호출하지 않는다. 자체 시험은 시험용 로컬 HTTP 서버를 사용하며 사용자 Ollama에 접속하지 않는다. 실제 `run`만 기준선에 고정된 로컬 모델로 120회 추론한다.

기본 산출물은 아래와 같다.

```text
..\experiments_v054\v054_order_01.plan.json
..\results_llm\v054_order_01\summary.ko.md
..\results_llm\v054_order_01\status.json
..\results_llm\v054_order_01_evidence.zip
```

이미 파일이 존재하면 덮어쓰지 않는다. 별도 재실행에는 새 이름을 지정한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\windows\Run-All.ps1 -RunName v054_order_02
```

## 바뀌는 것과 유지하는 것

**바뀌는 것은 입력 JSON의 `rules` 배열에서 직접 경로와 연쇄 경로의 블록 순서뿐이다.** 연쇄 내부 순서, 규칙 ID·전제·결론, 초기 사실, 목표, 지시문, 출력 schema, 모델 identity, 옵션과 전체 seed는 유지한다. 규칙 순서는 요청 방향과 무관하다. 호스트가 요청 방향에 맞는 규칙을 먼저 배치해 주는 방식이 아니다.

`original` 60개 요청은 실제 v053 `original` 60개 요청과 바이트가 같다. `swapped` 60개 요청은 대응 original에서 규칙 순서만 다르다. 정의 추가 문단을 다시 섞지 않는다.

| 문제 | original | swapped |
|---|---|---|
| K01 | k10 → k17 → k03 | k03 → k10 → k17 |
| T02 | r83 → r21 → r57 → r04 → r69 | r21 → r57 → r04 → r69 → r83 |

위 화살표는 **배열의 나열 순서**다. 논리적 함의를 뜻하지 않는다.

## 무엇이 성공인가

각 순서 안에서 같은 문제·seed의 shallow와 deep이 모두 유효하고, 실제 깊이가 각각 최소와 최대에 맞아야 선택적 성공이다. 두 순서에서 모두 이 조건을 만족하는지도 따로 보고한다.

규칙 순서만 바꾸자 경로가 바뀌더라도, shallow/deep 지시에는 같은 경로로 답한다면 **순서 효과는 있지만 D 선택적 제어는 실패**다. 유효 증명 생성, 순서에 따른 변화, 방향 제어를 서로 다른 표로 확인한다. 중립 40회는 별도 대조이며, 같은 응답의 재채점을 새 표본으로 세지 않는다.

## 시험과 독립 재검산

```powershell
python -m order_probe_v054 selftest
python -m order_probe_v054 selftest --all
python tools\independent_verify_v054.py ..\results_llm\v054_order_01_evidence.zip --out ..\results_llm\v054_order_01_independent.json
```

첫 명령은 새 모듈 시험, 둘째는 v047~v054 전체 시험이다. 셋째는 생산 채점기와 별도 구현된 원문 의미 재검산이며, 전체 수집이 완료되고 HTTP 전송이 정상인 120회를 대상으로 한다. source/runtime/요청 재생성 검사를 대신하지 않으므로 기본 실행의 `audit`과 함께 사용한다.

합성 전수실행과 독립 재검사를 다시 만들 때는 다음을 사용한다. 기존 출력 경로는 허용하지 않는다.

```powershell
python tools\validate_release_v054.py --out ..\validation_v054_replay
```

단위 시험·합성 서버 시험의 성공은 실제 Qwen 연구 성과가 아니다. 실제 모델의 새 v054 결과는 실행 후 생성되는 증거로 판단한다.

상세 설계는 `docs/PROTOCOL.ko.md`, 반론 검토와 수정 사항은 `docs/REVIEW_AND_CHANGES.ko.md`, 검증 범위는 `docs/VALIDATION.ko.md`를 참고한다.
