# v062 봉인 소스 독립 감사

## 판정

- `audit_state`: `completed`
- `candidate_completion`: `complete`
- 보증 경계: `cooperative-sealed` / `sealed-artifact-v1`
- 후보 SHA-256(감사 시작·종료): `33830e414b93174b2fbc36ec46d4675ab8e15321abd5608db301a487d8561da4`
- 차단 finding: 0건
- 진단 finding: 1건

봉인된 `v062_construction_source_r1.zip`은 C1–C8의 필수 조건을 충족한다. v061 원자료는 40회 모두 `k03` 선택, shallow 20/20 이행, deep 0/20 이행으로 다시 확인됐다. 따라서 choice ID 반복을 늘리기보다 마지막 규칙을 외부에서 지정하고 실제 부모 연결 DAG를 구성하게 하는 v062 방향은 타당하다. 이 판정은 한 문제의 조건부 구성 준비도에 한정되며 자유 깊이 선택, A/M 제어, 내부 기제나 일반화를 뜻하지 않는다.

## 기준별 직접 확인

| 기준 | 판정 | 핵심 근거 |
|---|---|---|
| C1 | PASS | v061 evidence manifest 전체 해시, 60 actions/40 calls/20 metadata, 원응답 40개와 저장 재분석을 직접 대조했다. 모든 응답은 `gemma3:4b`, `final_rule_id=k03`였다. `actual_D=null`, 독립 문제 1개, pooled effect 없음과 외부 인증·인과 한계도 유지됐다. |
| C2 | PASS | `V061_ANALYSIS.ko.md`는 공통 한계와 다음 단계 우선순위의 이견을 분리하고, 세 대안과 반론을 기록하며 채택안을 만장일치가 아닌 조건부 조정 결정으로 명시한다. v059/v060 보존 evidence의 선택 패턴도 직접 대조했다. |
| C3 | PASS | 실제 CheckOnly plan의 10 seed·40 slots·60 actions를 재구성했다. 같은 seed의 A/B는 지정 규칙 literal 한 곳만 다르고, 반복 요청은 byte-identical이며 model/options/facts/rules/goal은 고정됐다. 모든 request hash가 일치했다. |
| C4 | PASS | exact bounded schema, 부모 존재·중복, 규칙 전제 multiset, 비순환성, 최종 goal, target, strict ancestry와 parents 기반 D를 코드에서 확인했다. 생산 DFS와 독립 Kahn 측정기를 고정 seed의 schema-valid 무작위 DAG 5,000개에 대조해 차이가 없었다. |
| C5 | PASS(진단 1건) | plan·baseline·source fingerprint·실행 순서·raw hash·event chain·metadata identity·상태·파일 집합·독립 재측정이 결속된다. 40-call 상한, 20 metadata, warmup 0, retry/repair/resume/download 금지와 첫 fatal failure 중단을 확인했다. |
| C6 | PASS | 원본과 fresh ZIP selftest가 각각 27 tests, exit 0이었다. complete/partial/schema/logical/tamper/독립검산 범위를 소스에서 확인했고 analyzer 7개 반례를 별도로 재실행해 모두 통과했다. |
| C7 | PASS | 후보의 360개 manifested payload와 `RELEASE_MANIFEST.json`을 검사했다. baseline 336파일은 byte-for-byte 보존됐고 신규 파일은 선언된 24개뿐이다. fresh extract의 361파일과 ZIP 전체 entry 및 현재 source가 모두 바이트 일치했다. |
| C8 | PASS | 실제 Windows `-CheckOnly` 기록은 v061 재분석과 v062 prepare/show만 실행했고 서버 시작·모델 호출·추론 결과 생성을 하지 않았다. CheckOnly 분기는 서버 시작 코드보다 앞에 있으며 README·프로토콜은 offline/synthetic/actual 실행을 구분한다. |

## Finding

### V062-SA-D01 — `parse_error` 진단 문자열의 독립 결속 누락 (`diagnostic`)

- 기준: C5
- 근거: `tools/verify_v062.py:911`은 `parse_error`가 null 또는 문자열인지 검사하지만, `:915`의 exact comparison은 `valid_payload`, `transport_error`, `response_identity_error`에만 적용한다. 임시 synthetic invalid-schema bundle에서 첫 trial의 실제 `parse_error`를 `FORGED_DIAGNOSTIC`으로 바꾸고 manifest를 다시 해시했을 때 verifier가 `differences=[]`로 수용하는 반례를 재현했다.
- 영향: raw-derived status, format/proof/strict/D/target 지표, 집계와 admission gate에는 영향이 없어 완료를 막지 않는다. 다만 rehashed evidence에서 per-trial 실패 원인 문자열이 바뀌어도 독립 검산이 탐지하지 못해 후속 원인 분석의 신뢰가 낮아진다.
- 권고: 다음 revision에서 `invalid_response`와 `invalid_payload_schema`의 `parse_error`를 독립적으로 재구성해 exact comparison하거나 안정적인 오류 category를 별도 결속하고, `parse_error` rehash 변조 회귀시험을 추가한다.
- 미확인: 없음.

## 실행·무결성 요약

`source_audit_input.json` SHA-256은 `68cb9d0d67dfbdb3bf0c55805d55b57401b1a0bb677fba317cd0d010e5ab185b`로 일치했다. 봉인 입력에는 일반 검증 완료 후 감사 시작과 source writer 중단이 기록돼 있으며, 감사자는 후보를 수정하지 않았다. 후보 ZIP은 감사 시작과 결과 작성 후 모두 `33830e414b93174b2fbc36ec46d4675ab8e15321abd5608db301a487d8561da4`였다. 기준 source ZIP은 `ee0e877ec0dd80b2210c0530e50f12aad0d55af8fd6b83a3086f32b48167e760`였다. 후보 ZIP에는 duplicate, case collision, unsafe path, directory entry, symlink, encryption, CRC 오류나 manifest hash mismatch가 없었다.

기록된 원본 selftest와 fresh-extract selftest는 각각 27개 시험을 통과했다. 감사자는 전체 suite를 다시 반복하지 않았고, 새 불확실성을 겨냥한 5,000개 DAG 교차검산, analyzer 7개 반례와 `parse_error` 변조 반례만 오프라인으로 실행했다. 실제 LLM/Ollama 실행, 서버 시작, 모델 다운로드, evidence ZIP의 source snapshot import는 하지 않았다.

## 잔여 한계

- 이전 패널에는 `gpt-5.6-terra`/`xhigh`가 요청됐지만 도구가 실제 적용값을 반환하지 않아 미확인이다. 이 감사에 요청된 `gpt-5.6-sol`/`xhigh`의 실제 적용값도 미확인이다.
- 이전 패널의 원시 reviewer transcript는 봉인 입력에 결속되지 않았다. 이 감사는 통합 문서의 경쟁 논거와 원자료를 직접 검토했으며 transcript provenance는 확인하지 못했다.
- v061의 해시·event chain은 내부 일관성을 보이지만 외부 실행 사실을 인증하거나 같은 OS 사용자 권한의 의도적 조작을 배제하지 않는다.
- `cooperative-sealed`는 악의적인 동일 principal을 방어하지 않는다. `native-atomic-host`나 외부 서명 증명은 요청되지 않았다.
- 실제 v062 모델 응답은 이번 범위에서 생성하지 않았으므로 아직 미측정이다.
