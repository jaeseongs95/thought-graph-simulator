# local_llm v0.4.1 — 수정 범위와 다음 실행

**교체 대상은 `local_llm` 폴더뿐이다. `adm_minimal.py`, `examples`, 기존 `results_llm`은 그대로 둔다.**
기존 `local_llm` 폴더를 프로젝트 밖에 보관하고 새 폴더로 교체한다. 과거 결과 폴더 이름은 바꾸지 않는다. 파일을 덮어 섞기보다 폴더 자체를 교체한다.

이번 패치는 모델 성능이 좋아졌다고 가정하지 않는다. 확인된 all_schema 거짓 양성을 고치고 원문 근거 연결 진단을 추가한다. 기본 모델·sampling·통합 프롬프트는 유지한다. 새 모델을 다운로드할 필요가 없다.

## 1. 코드 자체 검사 — LLM/네트워크 없음

프로젝트 루트의 PowerShell에서:

```powershell
py -3 -m local_llm selfcheck
```

오프라인 회귀 시험 전체를 실행하는 명령:

```powershell
py -3 -m unittest discover -s local_llm/tests -v
```

시험 통과는 코드와 시험 픽스처에 대한 결과다. 모델의 실제 증명 능력과 같지 않다.

## 2. 기존 pilot 원문 재검사 — LLM/네트워크 없음

```powershell
py -3 -m local_llm inspect-results --input results_llm/v04_pilot_01 --out results_llm/v041_pilot_audit_01
```

확인 파일: `results_llm/v041_pilot_audit_01/reanalysis.md`, `reanalysis.json`.
`first_invalid_step`에 기대 전제와 실제 부모 원자를, `selected_component_support_valid`에 선택된 부분의 유효성을 기록한다. 원본 성공/실패는 바꾸지 않는다.

## 3. 원인 분리용 12회 진단 — 여기부터 실제 LLM 호출

Ollama가 실행 중이고 기존 `qwen3:4b-instruct`가 설치된 상태에서:

```powershell
# 계획 확인만 수행: 네트워크/LLM 없음
py -3 -m local_llm.causal_probe --plan-only

# 새 진단: 실제 LLM 12회
py -3 -m local_llm.causal_probe --out results_llm/v041_probe_01
```

기존 calibration 24회, smoke 6회, pilot 39회를 다시 돌릴 필요는 없다. 이번 진단은 프롬프트 묶음의 영향과 JSON format 제약의 영향을 나누는 별도 과제다. 기존 ADM 성공률에 합산하지 않는다.

확인 파일:

```text
results_llm/v041_probe_01/summary.md
results_llm/v041_probe_01/causal_probe.json
results_llm/v041_probe_01/task_comparisons.json
results_llm/v041_probe_01/cases/
```

의미적 실패도 보존하고 다음 조건을 실행한다. 통신·모드 오류 등 실제 실행 장애가 발생하면 원문 기록을 확인한다. 동일 출력 폴더가 이미 있으면 `_02`처럼 새 폴더명을 쓴다. 다른 버전의 기존 실행 폴더에 `--resume`하지 않는다.

## 12회가 구별하는 것

| 진단 | 호출 | 비교 |
|---|---:|---|
| 3개의 deep 증명 과제 | 6 | 동일 문제/seed/format에서 기존 프롬프트 vs 간결 프롬프트 묶음 |
| 같은 고정 증명의 최종 도식 | 3 | 동일 messages에서 union schema / schema만 허용 / JSON만 |
| 수락 기준 판정 | 3 | 근거 없는 목표 / 목표가 아닌 사실 / 이미 사실인 목표 |

간결 프롬프트는 여러 표현 요소를 함께 바꾸므로 예시 또는 언어 하나의 인과 효과로 해석하지 않는다. schema만 허용하는 조건은 호스트가 표현 종류를 강제하므로 A 조절 성공이 아니다. JSON만 조건도 JSON 형식 제약은 남는다. 판정 정의나 정답 증명을 코드가 응답에 채워 넣는 처리는 없다.

## 실제 작성·검사 범위

수정본에서 139개 오프라인 단위/회귀/모의 API 시험, 21개 selfcheck를 실행했다. 기존 69개 응답의 상태와 오류, HTTP 요청 바이트가 유지됨을 확인했다. 새 LLM 추론·모델 다운로드·GPU·Windows 실행은 작성 환경에서 하지 않았다. 상세 기록은 `local_llm/BUILD_STATUS.json`, `local_llm/validation/`을 참조한다.

## 상세 참고

`PROTOCOL.ko.md`: 기존 실험의 의미 계약과 v0.4.1 부록.
`REFERENCE_v04.ko.md`: 기존 v0.4 명령·모델 설정 참고. 그 문서의 전체 69회 실행 절차를 지금 다시 수행하라는 뜻이 아니다.
`CHANGES.ko.md`: 이번 변경 내역.
