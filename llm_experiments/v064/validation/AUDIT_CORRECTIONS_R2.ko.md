# r1 감사 finding 교정 — r2

r1 ZIP과 감사 결과는 보존했다. 감사 종료 후 probe만 교정했으며 연구 문제·seed·조건·호출 수·실제 D 성공 기준은 바꾸지 않았다. 코드 변경에 따라 새 계획·새 합성 실행·새 source ZIP이 필요하다.

|Finding|메인 처분|교정 내용|관련 검증|
|---|---|---|---|
|V064-SA-R1-F001|accepted|모든 완료 action의 중단 사유를 순서대로 계산한다. 첫 중단 사유 뒤에는 완료 또는 시작된 다른 action이 없어야 한다. complete는 중단 사유가 없어야 하며 stopped는 마지막 원인과 일치해야 한다. 오류 event 직후 프로세스가 끊긴 crashed도 뒤 action이 없어야 한다.|첫 call identity/HTTP/생성상한, 첫 metadata digest를 바꾸고 원문·record·event·두 보고서·manifest까지 재작성한 4반례|
|V064-SA-R1-F002|accepted|초과 계수 관측 자체를 일괄 거부하던 검사를 제거하고 위 F001의 중단 계약으로 제한한다. 설정 초과 관측을 지우거나 성공으로 보정하지 않는다.|eval_count4097의 stopped 원문·부분 요약·independent receipt 생성, 뒤 실행 거부|
|V064-SA-R1-F003|accepted|정확히 하나의 started-but-uncompleted action에 한해 저장 순서의 request/response prefix를 허용한다. request는 동결 바이트 prefix, response는 1MiB+1, 미확정 record는 JSON 크기 제한으로 보존한다. pending_action receipt에 명시하고 완료 관측·의미 지표에서 제외한다. 임의의 후속 경로는 허용하지 않는다.|응답 저장 후 중단, 요청 일부 저장 중단, metadata 일부 저장 중단, 미래 action 파일/변조 pending 요청 거부|

미확정 record는 완료 event와 결속되지 않은 원문 자료다. JSON 의미를 승인하거나 성공 지표로 올리지 않는다. not_observed는 완료 관측 기록이 없다는 상태이며 호출 미발생의 인증이 아니다. torn event/손상된 committed JSON처럼 기존 완결 기록을 파싱할 수 없는 자료를 복구해 정상 실행으로 바꾸는 도구는 아니다.

r2의 테스트·새 폴더 실행·봉인 digest·감사 재확인 결과는 별도 일반검증 및 최종 completion에 결속한다. 이 문서의 accepted는 재확인 완료를 대신하지 않는다.
