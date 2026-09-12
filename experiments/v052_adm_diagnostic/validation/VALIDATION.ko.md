# v052 실제 검증 기록

## 수행 환경과 범위

Linux·Python 3.13.5에서 실행했다. Windows/PowerShell 실기 시험과 사용자의 실제 Qwen 모델 추론은 수행하지 않았다. 기존 Windows UTF-8/CP949 subprocess 처리 및 한글 경로 시험은 보존했다.

## 완료된 시험

| 항목 | 결과 | 증거 |
|---|---|---|
| 신규 단위·통합·명령행 시험 | 63개 통과 | NEW_SELFTEST.log |
| 이전 417개를 포함한 전체 시험 | 480개 통과, 종료 0 | FULL_SELFTEST.log |
| 추가 미측정 구분 회귀시험 | 2개가 추가 당시부터 통과 | REVIEW_ADDITIONAL_CHECKS.log |
| 사용자 실제 v051 증거로 prepare | 원문 재감사·계획 생성 성공, 추론 없음 | REAL_V051_PREPARE.log |
| 이전 소스 보존 | v047~v051와 subprocess helper 48파일 바이트 일치 | UNCHANGED_FILES.json |
| 정상 합성 HTTP 실행 | 440회; 본 역할 240/240 | SYNTHETIC_perfect.zip |
| 역할 무시 합성 HTTP 실행 | 440회; 유효 본 기록 240/240, 역할 부합 20/240, 중립 대비 차이 0 | SYNTHETIC_ignore_roles.zip |
| 최종 참조 오류 합성 HTTP 실행 | 440회; 본 기록/역할 0/240, 복사 진단은 별도 성공 | SYNTHETIC_bad_final.zip |
| 서버 종료 후 재감사 | 세 실행 모두 저장된 전체 report와 동일 | OFFLINE_REAUDIT.log |
| 별도 의미 검사 | 세 실행 각 440건; 생산 채점기와 440/440 일치 | INDEPENDENT_*.json |

독립 검사기는 생산 감사기/합성 응답 생성기를 import하지 않는다. 원문·manifest·지지 DAG·도식의 모든 Boolean 배정·검토값을 다시 계산한다. 세 증거의 manifest 대상은 각각 949파일이다.

합성 HTTP 1,320회는 코드 검증이다. 실제 작은 LLM의 연구 성과로 합산하지 않는다. selftest 내부의 추가 합성 요청 수도 새 LLM 표본으로 세지 않는다.

## 성공을 오인하지 않게 한 반례

최종 노드 지정 오류, 경로 두 개 나열, 근거 없는 사실, 잘못된 규칙·부모, views/bindings 중복, 결론을 가정으로 주입한 도식, 잘못된 M2 진리값, 다른 역할 라벨, 역할 무시, 복사만 성공, 통신 중단, 모델 identity 변경, 원문·계획·코드 변조를 검사했다.

잘못된 M2를 넣은 경우 전체 성공은 실패하지만, 별도로 유효한 증명과 A/D 관측은 남긴다. 원문을 읽지 못한 경우는 논리 오답으로 추정하지 않고 미측정으로 남긴다.

## 수정 이력의 정직한 범위

v051에서 확인된 통합 출력 실패를 반영하여 명시적인 인터페이스, 중립 대조, 복사 진단, D 단독 진단 및 논문 핵심 결과 분리를 구현했다. 새 코드의 추가 검사 두 개는 최초부터 통과했으며, 발견하지 않은 결함의 수정 전 실패 기록을 만들지 않았다. 기존 v051을 재채점해 성공으로 바꾸지 않았다.

## 새 폴더 배포 시험

배포 ZIP을 별도 새 폴더에 해제한 뒤 전체 480개 시험이 다시 통과했고 종료 코드는 0이었다. RELEASE_SELFTEST.log 및 RELEASE_SELFTEST.exit에 기록했다. 추출본의 독립 검사기로 동봉 합성 ZIP 세 개도 모두 재검사했다(RELEASE_INDEPENDENT.log). 최종 배포본의 모든 Python 파일이 시험한 추출본과 바이트 단위로 같음을 RELEASE_SOURCE_MATCH.json에 기록했다. 최종 재포장 때 추가한 것은 문서·검증 로그뿐이다.
