# v086 r2 — 독립 재검토에 따른 수정

## 판단

v085에서 관측한 절차를 동결한 신규 구조 재현이라는 방향은 유지한다. 기존 정확한 수치군, 직접군, 두 단계군의 동시 비교와 실험자가 제공한 D/W, 실제 goal proof DAG 재채점, 표시 강건성, 신규 수치 조합의 별도 집계는 서로 정합적이다. 변경된 주가설·문제·배정은 없다.

## 재현한 결함

1. `byte_diagnostics086.collect`는 실제 graph 결과의 `error_codes`가 아니라 존재하지 않는 `errors`를 읽었다. 전제 누락 응답에서 기본 summary는 실패를 맞게 판정했지만 보조 `graph_errors`는 빈 배열이었다. 생산/독립 보고서가 이 보조 함수를 공유하므로 서로 일치한다는 시험만으로는 발견하지 못했다.
2. `exchange`의 `read(amt)`는 Content-Length에 미달한 EOF를 정상으로 반환할 수 있었다. 실제 loopback 반례에서 선언 길이보다 23바이트 적은 응답의 error가 None이었다. chunked 응답에서 마지막 chunk가 없으면 IncompleteRead가 누적 본문과 함께 상위로 빠져 저장되지 않았다.

이는 실제 v086 모델에서 관측한 사건이 아니라 검토 중 만든 합성 실패 반례다. 기존 v085 결과가 틀렸다는 증거로 사용하지 않는다.

## 수정

- `graph_result.error_codes`를 원래 목록대로 복사한다. 서로 겹치는 오류도 보존하고 source summary를 변경하지 않는다.
- 제한된 `read1` 읽기로 본문을 누적하고 Content-Length 완결성을 검사한다. 불완전 chunk, timeout, HTTP 프로토콜 오류를 transport 오류로 반환한다. 이미 반환된 본문은 저장하고 재시도하지 않는다. 정상 요청·응답 바이트 및 정상 경로는 바꾸지 않는다.
- 알려진 미시작 r1만 보존 후 설치한다. 가드·started 계획·실제 결과 폴더가 있으면 소스 교체를 차단한다. 변경된 r1 또는 기존 보존본도 덮어쓰지 않는다.

`data/protocol.json`, `design086.py`, `cases086.py`, `report086.py`, `audit086.py`, `numeric086.py`, legacy 채점기와 고정 v085 배포본은 원본과 동일하다. 따라서 r2는 연구 처치를 수정한 새 실험이 아니라 진단·전송·안전 설치 수정이다. 정상 배치의 주평가 의미는 바뀌지 않는다.

## 검증 방식

기존 전체 자체시험에 실패 graph 보조 보고, 중복 오류 보존, 완전/불완전 Content-Length와 chunked 전송, timeout의 부분 본문 보존, 응답 크기 상한, HTTP 오류, 중단 배치의 실제 ZIP 독립 검산, r1 안전 설치 시험을 추가한다. 합성 응답은 Qwen 성과가 아니며 실제 모델 호출은 하지 않는다. 수행 결과는 배포 외부의 `VALIDATION_RESULT_v086_r2.json`과 시험 원문 로그에 기록한다.

## 외부 기술 근거

RFC 9112 §6.3, §8은 선언한 Content-Length에 미달한 수신과 종료 chunk가 없는 전송을 불완전 메시지로 다룬다. Python http.client의 HTTPException/IncompleteRead 및 HTTPResponse.read1 계약을 교차 확인했다. 이 외부 근거는 HTTP 처리 수정에만 사용했고 연구 문제·결과를 외부 일반론으로 대체하지 않았다.

- https://www.rfc-editor.org/rfc/rfc9112.html#section-8
- https://docs.python.org/3.12/library/http.client.html
