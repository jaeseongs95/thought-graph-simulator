# local_llm v0.4.4.1

프로젝트 루트의 [START_HERE.ko.md](../START_HERE.ko.md)를 먼저 읽으세요.
기존 모델·core·본 A/D/M 검증 계약은 변경하지 않습니다.

이번 패치의 추가 수정은 provenance 판정입니다. `adm_minimal.py`의 과거 스냅샷 raw bytes는
manifest의 raw SHA-256으로 엄격히 보존 검증하고, 현재 working tree와의 동일성은 BOM/줄바꿈만
정규화한 Git blob identity로 판정합니다. 따라서 Windows CRLF와 LF 차이는 허용하지만 실제 코드 편집은 허용하지 않습니다.

이번 변경은 `decision_stage` 상세진단 연결, 군별 네 입력 진리표·필요조건 검사,
한 요인 대조의 실행/채점/보고, 선택적 로컬 가중치 blob SHA-256 확인입니다.
기존 `selfcheck`, `calibrate`, `micro_probe`, `decision_probe`, `run` 경로는 유지합니다.
새 명령은 `decision_audit`, `factor_probe`, `model_integrity`입니다.

```powershell
py -3 -m local_llm.decision_audit --input results_llm/v043_decision_01 --out results_llm/v044_audit_01
py -3 -m local_llm.factor_probe --input results_llm/v043_decision_01 --plan-only
py -3 -m local_llm.factor_probe --input results_llm/v043_decision_01 --out results_llm/v044_factor_01
```

기본 대조는 16회입니다. `--arm`으로 군을 고르면 군당 4회입니다.
원래 실패는 보존합니다. 정답값을 강제하는 enum/const, 누락값 보충, 잘못된 부울값 교정은 없습니다.
이름 치환 군의 값은 수정하지 않고 키 대응만 복원하여 원래 기준으로 채점합니다.

## 오프라인 시험

기존 저장소 루트에서:

```powershell
py -3 -m unittest discover -s local_llm/tests -v
py -3 -m local_llm selfcheck
```

실제 모델 실행 없이 동작합니다. tests/fixtures에는 과거 원문 응답과 실행 환경 기록이 포함됩니다.
공개 배포 시에는 개인 경로 등 기록의 공개 범위를 별도로 검토하세요.

## 판정 해석

- 과제 성공: 해당 한 응답의 입력·최종 부울값이 모두 계약을 충족.
- `all_conditions_verified`: 네 입력이 각 한 번 있고 전부 정확한 유한 검증. 일반 성능 추정 아님.
- `false_acceptance_count`: 모델의 `proof_and_goal_accepts=true` 오판정. 기존 검증기의 수락 횟수가 아님.
- `all_four_rows_match_ignore_b_shortcut`: 관측된 네 행이 `(a,a,false)`와 일치. 내부 알고리즘 규명 아님.

이전 버전 안내는 `HISTORY_v043_README.ko.md`에 남겼습니다.
