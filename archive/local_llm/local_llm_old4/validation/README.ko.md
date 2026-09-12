# 검증 기록

`offline_tests.txt`: 결정론적 코드/회귀/Mock API 시험 실행 로그. Mock의 accepted는 실제 모델의 성공이 아니다.

`selfcheck.json`: 21개 고정 하네스 양성/음성 검사. 모델 호출 없음.

`static_source_checks.json`: Python 3.10 문법 검사와 현재 Python의 구문 컴파일. 파일을 검사했으며 새 LLM 추론은 하지 않았다.

`v03_replay.json`: 사용자가 올린 v0.3 pilot 39응답의 재판정 요약. 원본 폴더는 변경하지 않았다.

`plan_*.json`: 새 기본 문제의 호출 계획. 실행 결과가 아니다.

`model_policy_actual_v03.json`: 사용자 기존 GGUF 메타데이터의 Thinking-2507 식별과 non-thinking 요청 차단 검사. 서버를 호출하지 않고 보존된 메타데이터를 사용했다.

`package_validation.json`은 ZIP 외부의 별도 파일로 제공한다. 최종 ZIP을 다시 풀어 코드 시험과 배포 해시를 확인한 결과다. 내부 해시는 무결성 점검용이며 외부 전자서명이나 신뢰된 게시 이력의 대체물이 아니다.
