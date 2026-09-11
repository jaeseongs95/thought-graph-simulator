# local_llm v0.4.6

기존 `local_llm` 폴더를 보관하고 ZIP 안의 `local_llm`로 교체합니다.
`adm_minimal.py`, `examples/`, `results_llm/`은 변경하지 않습니다. 모델을 다시 설치하지 않습니다.

## 1. 원문 감사 — 추론 없음

프로젝트 루트 PowerShell:

```powershell
py -3 -m local_llm.operator_audit --input results_llm/v045_operator_01 --out results_llm/v046_operator_audit_01
```

기존 16건의 원문 요청과 판정을 재현합니다. LF/CRLF/BOM만 다른 core는 허용하되 실제 소스 변경이나 보존 파일의 바이트 변경은 거부합니다.

## 2. 새 호출 — 최대 12회

```powershell
py -3 -m local_llm.composition_probe --input results_llm/v045_operator_01 --out results_llm/v046_composition_01
```

1단계: **새 NOT 4회** + `((NOT b) AND a)` **표기 대조 4회**.
2단계: 방금 모델이 낸 NOT의 bool 값을 그대로 `b` 자리에 전달하여 **새 AND 4회**.

NOT가 틀린 bool을 내도 정답으로 고치지 않고 그대로 전달합니다. 중간 단계가 틀리면 최종값이 우연히 맞더라도 파이프라인 통과가 아닙니다.
NOT가 JSON/프로토콜을 위반하여 사용할 bool을 내지 못하면 해당 AND는 호출하지 않고 `blocked_inputs`로 남깁니다. 네 입력의 분모는 유지합니다.

우선 읽을 파일:

```text
results_llm/v046_composition_01/summary.md
results_llm/v046_composition_01/composition_probe.json
```

세부 요청/응답/중간값/채점은 `phase_one/`, `phase_two/`에 각각 있습니다.
이전 `and_not_b` 응답은 비교 기준으로만 보존하며 새 결과로 대체하지 않습니다.

## 선택 실행

계획만 확인 — 네트워크/추론 없음:

```powershell
py -3 -m local_llm.composition_probe --input results_llm/v045_operator_01 --plan-only
```

표기 대조를 빼고 새 NOT→AND만 최대 8회:

```powershell
py -3 -m local_llm.composition_probe --input results_llm/v045_operator_01 --chain-only --out results_llm/v046_chain_01
```

중단 후 동일 명령에 `--resume`을 붙입니다. 코드·모델·설정·입력이 달라졌으면 재개를 거부합니다.
완료된 실패를 성공이 나올 때까지 다시 호출하지 않습니다.

```powershell
py -3 -m local_llm.composition_probe --input results_llm/v045_operator_01 --out results_llm/v046_composition_01 --resume
```

현재 모델/서버/설정과 원래 기준선이 달라졌다는 오류가 나오면 우회하지 말고 해당 오류와 metadata를 보존합니다.

## 실제 가중치 파일 확인 — 추론/네트워크 없음

이번 업로드에는 가중치 해시 검사 결과가 없었습니다. 다음은 기존 검사 명령입니다.

```powershell
py -3 -m local_llm.model_integrity --input results_llm/v045_operator_01 --check-weights --out results_llm/v046_weights_01.json
```

로컬 모델 파일을 읽어 이름에 기록된 blob SHA-256과 비교합니다. 이것이 일치해도 양자화 품질·커널 정확성·추론 성능을 보장하지는 않습니다. 기존 output 파일이 있다면 새 이름을 사용합니다.

## 해석

- 단독 NOT/AND 성공과 복합식 성공을 구분합니다. `and_not_b`는 출력 하나지만 내부 논리식에 두 게이트가 있습니다.
- 표기 대조는 같은 메시지에서 `expression` 값만 바꿉니다. 정답과 논리적 의미는 같습니다.
- NOT→AND 연결은 호스트가 사전에 제공한 그래프입니다. 모델이 작업 분해나 계획 수립까지 했다는 성과가 아닙니다.
- 기존 a/b는 과거 모델 입력 판정에서 온 값입니다. 게이트 호출은 새로 하지만 입력 추출을 처음부터 다시 하는 신규 종단 간 ADM 실험은 아닙니다.
- 실행 완료와 전 조건 통과는 다릅니다. 새 성능은 사용자 로컬 실행으로만 측정합니다.
