# r3 교정

r2 감사 V064-SA-R2-F001을 수용했다. 원 V064-SA-R1-F003의 미해소 부분이기도 하다. verify._pending_artifacts에서 record 저장의 선행조건을 최소1개 이상의 연속된 완전 request/response 쌍으로 제한했다. call의 경우 전체 sequence가 한 쌍이므로 full request+response 모두 필요하다. request byte prefix 불일치와 response 앞의 partial request는 기존 검사가 거부한다. metadata도 홀수 prefix 뒤의 record를 거부한다.

record 자체는 opaque/uncommitted이며 의미 지표는 여전히 미측정이다. request-only+record, partial request+record, metadata request-only+record의 재서명 반례를 거부하고, 완전한 wire 쌍 뒤의 opaque record는 observed_calls=0으로 보존하는 회귀를 추가했다. 연구 설계·실행기·측정기·보고서·동결 protocol은 변경하지 않았다. r2 source ZIP과 감사 두 파일은 보존했다.

새 source ZIP r3와 새 빈폴더 검증 후 원 감사자가 해당 finding과 변경 영향만 재확인한다. 채택 자체는 해결 판정을 대신하지 않는다.
