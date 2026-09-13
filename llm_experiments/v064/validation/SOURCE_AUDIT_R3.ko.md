# v064 소스 독립 제한 재감사 r3

판정은 **감사 완료 / 후보 완료**다. r3 후보 `v064_direct_D_source_r3.zip`의 감사 전후 SHA-256은 `238b4997ceaa4191fb79498cc12647010bd02056cf7ac96a0ca0752712ff4553`, `audit_input_r3.json`은 `1de12447fbdd8396a47eb2c9433914256b25fcecd318046d808973472c2ed74d`로 불변이다. r1/r2 감사 파일도 기존 digest 그대로다.

`V064-SA-R1-F003`과 `V064-SA-R2-F001`은 모두 **resolved**다. r3 `verify.py:820-821`은 pending record 앞에 최소 한 개의 완전한 request/response pair와 짝수 wire prefix를 요구한다. 직접 재서명한 call 요청 전용+record, call 부분 요청+record, metadata 홀수 prefix+record 반례는 모두 `VerificationError`로 거부됐다. call과 metadata의 완전 wire pair 뒤 opaque record는 승인됐고 `observed_calls=0`, `semantic_measurement=not_measured`를 유지했다. 봉인된 정상 pending evidence도 `state=crashed`, `record_committed=false`로 같은 계약을 충족했다.

r2 대비 source 변경은 `verify.py`, 해당 contract test와 README 전달판본뿐이다. candidate manifest의 source 16개, ZIP member, `fresh_source_r3`와 결정적 rebuild의 바이트가 일치했고, `audit_input_r3`의 evidence 10개 및 source 16개 hash도 모두 직접 대조했다. r1 F001/F002의 해소 영역과 연구 계약 파일은 r2와 동일하므로 기존 독립 검토를 재사용했다. 새 blocking 또는 diagnostic finding은 없다.

해시 결속 로그는 통합 19검사와 새 빈 폴더 Windows CheckOnly 19검사 exit 0을 기록하지만, 감사자는 전체 suite를 반복하지 않았고 시험 개수를 연구 성과 근거로 사용하지 않았다. 실제 Ollama 추론·모델 다운로드·서버 시작은 수행하지 않았다. 실제 v064 모델 및 A/M 성과는 미관측이며, 합성 evidence와 hash는 외부 실행 사실의 인증이 아니다.
