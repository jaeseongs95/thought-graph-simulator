# v064 소스 독립 재감사 r2

판정은 **감사 완료 / 후보 미완료**다. r2 후보 `v064_direct_D_source_r2.zip`의 감사 전후 SHA-256은 `8a033eba7b6d31392b20a0d78fd52b5fcbd136753dc4e3fc05e8d336da6360ac`, `audit_input_r2.json`은 `73bd82f5fcd937f985ab0eb096d21b88e9fac23410d3e83de6684c709e41245c`로 불변이다. r1 ZIP과 r1 감사 두 파일도 기존 digest 그대로다.

r2 manifest의 source 16개, 작업 트리 `probe`, `fresh_source_r2`, 결정적 rebuild의 바이트가 일치했다. audit_input의 evidence 13개 hash도 모두 일치했다. r1 대비 protocol, 문제, seed, D 성공 기준, `design.py`, `measure.py`, `run.py`, Windows launcher는 바뀌지 않아 r1의 연구 설계·원자료 감사를 재사용했다. 변경 범위는 `verify.py`, 관련 보고 문구·시험·문서다.

원 finding별 재확인 결과는 다음과 같다.

- `V064-SA-R1-F001`: **resolved**. 첫 call의 model을 바꾸고 response, record, 전체 event chain, summary, 한국어 보고서, manifest를 다시 계산한 반례가 `VerificationError: action after mandatory stop`으로 거부됐다. r2 verifier는 모든 완료 action을 순서대로 검사해 최초 stop reason 뒤 action을 허용하지 않는다.
- `V064-SA-R1-F002`: **resolved**. `eval_count=4097`을 보존한 stopped evidence를 직접 검산해 exit 0, `state=stopped`, `observed_calls=1`, `verified=true`를 확인했다. 초과 관측을 성공으로 보정하지 않으며 전체 D 판정은 미완결로 남는다.
- `V064-SA-R1-F003`: **unresolved**. 정상 response 저장 후 중단 evidence는 exit 0, `observed_calls=0`, `pending_action`, `semantic_measurement=not_measured`로 올바르게 보존됐다. 그러나 pending record의 선행 wire 완료 조건에 공백이 있다.

새 차단 finding `V064-SA-R2-F001`을 기록했다. `_pending_artifacts`는 pending record가 있을 때 선행 wire가 하나라도 있으면 허용한다. 정상 pending evidence에서 response wire를 제거하고 그 뒤 쓰기 단계인 partial record만 추가해 manifest를 다시 계산한 번들 SHA-256 `fe0e4412bd5d731f1bb17ab0b8800ab658bc8285953b8fee797813fda760f877`을 r2 verifier가 `verified=true`로 승인했다. runner는 request 전체 저장, response 전체 저장, record 저장 순서이므로 이 조합은 생성될 수 없다.

call pending record는 exact/full request와 response가 모두 존재할 때만 허용해야 한다. metadata pending record도 연속된 완전 request/response pair 뒤에서만 허용해야 한다. record 자체는 계속 opaque, uncommitted, `not_measured`로 남겨야 한다. request-only+record와 metadata 홀수 prefix+record 재서명 반례를 거부하고 정상 no-record prefix 및 response pending을 계속 승인한 새 후보를 봉인한 뒤 재확인이 필요하다.

제공된 정상·pending·over-budget evidence는 fresh source verifier로 직접 실행해 모두 exit 0이었다. 봉인된 일반검증과 새 빈 폴더 Windows CheckOnly 로그는 19 tests/exit 0을 기록하지만, 감사자는 전체 suite를 반복하지 않았고 시험 개수를 연구 가설의 증거로 사용하지 않았다. 실제 Ollama 호출·다운로드·서버 시작은 수행하지 않았다. 실제 모델 성과, A/M 성과와 외부 실행 사실은 미확인이다.
