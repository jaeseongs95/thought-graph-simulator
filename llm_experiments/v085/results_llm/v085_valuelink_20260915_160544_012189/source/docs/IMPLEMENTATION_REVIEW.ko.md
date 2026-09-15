# v085 구현 검토와 검증 경계

## 보존한 기반

`legacy/`의 graph/단계/기존 응답 판정기는 v084와 동일한 바이트다. `data/v084_protocol.json`은 기존 protocol 원문이고, `prior/v084_source.zip`은 고정된 v084 소스 배포본이다. 이전 evidence를 확인할 때 이 알려진 독립 검산기를 별도 프로세스로 실행한다. 이전 bundle 안의 알 수 없는 소스를 임의 실행하지 않는다.

기존 `candidate_id`, `correct_values` 요청과 증명 생성의 요청 계약은 그대로 두었다. 원응답에 따라 다음 generation history가 달라질 수 있으므로, 동일 seed의 모델 응답까지 같다고 보장하지 않는다. 회귀시험은 보존된 v084 원문에 기반해 실제 요청을 바이트 단위로 재구성한다.

## 새 코드의 역할

- `design085.py`: 네 군·compare/lookup·참조·최대 슬롯을 고정하고 실제 원문으로 다음 요청을 구성한다. 틀린 값·ID를 정답으로 바꾸지 않는다.
- `numeric085.py`: 숫자 비교와 nullable 후보 ID의 엄격한 형식 판정. Boolean/문자열/실수를 정수로 고치지 않는다.
- `report085.py`: 기존 graph 측정에 선택 단계 전체 trace를 결합한다. 목표 graph 우연 도달과 전체 종단 성공을 분리한다.
- `audit085.py`: 생산 design/report/measure/stages를 import하지 않는 독립 일정·요청·형식·graph·trace·집계 재구성. `render085.py`는 이미 계산된 결과를 표시만 하는 공유 모듈이다.
- `run085.py`, `verify085.py`: 실제 loopback HTTP 또는 개발시험의 합성 transport, metadata identity, 시작표지/원문/commit, 부분 배치와 frozen guard, archive/원응답 검증.
- `launch.py`, `windows/Auto.template.ps1`: 명시한 설치·검사·실행. 모델이나 Python 패키지를 설치하지 않는다.

## 시험에서 구별하는 반례

비교가 틀리지만 조회는 그 값을 충실하게 따름; 비교가 맞지만 ID 조회가 틀림; 둘 다 틀려 실제 목표 graph가 우연히 맞음; 후보에 없는 정수; null; 잘못된 JSON/schema; 길이 종료; 원문 공백; 같은 숫자 요청 반복; 보정된 target 값으로 lookup 요청 변조; 해시를 다시 쓴 request/response/summary/source 변조; dispatch 뒤 중단; 응답 저장 뒤 commit 중단; Windows/POSIX 경로 구분자 차이 등을 검사한다.

production/독립 채점 일치는 내부 일관성 증거다. 다수의 정상·무효 graph 반례, 부분 배치, 실제 v084 요청 회귀를 함께 쓰지만 이를 모델 연구 결과나 외부 실행 인증으로 바꾸지 않는다.

## 배포와 실제 실행 제약

소스와 배포 ZIP은 해시로 결합하며 PS1 내장 ZIP도 해당 배포와 일치해야 한다. 기존 v085가 다른 내용이면 자동 덮어쓰지 않는다. 원본 v084 evidence는 새 버전 검산에 읽기 전용으로 사용한다. bundle의 허용 용량/멤버 수는 늘어난 슬롯을 수용하도록 상한을 확대하되 경로·중복·압축 확장 검사를 유지한다.

실제 Windows/Ollama에서 새 스키마를 사용한 v085 추론은 개발 자체시험과 다른 단계다. PowerShell이 없는 개발 환경에서 native parser 검사는 제외로 남긴다. 제공되는 검증 JSON의 실제 실행 환경·시험 수·제외 사유를 확인한다. 무추론 설치 점검이 통과해도 실제 모델의 새 lookup 응답 성공을 예고하는 결과는 아니다.

## 분석 경계

이번 처치는 비교와 조회 분리, 문맥 축소, 새 출력 형식, 추가 호출을 포함한 절차 묶음이다. v084의 hidden-state 내부 원인을 하나로 식별하는 순수 요인 실험이 아니다. 목적은 실제 D 종단을 유지한 채 관측 가능한 실패 위치를 분리하고 절차 전체의 효과를 측정하는 것이다. 두 단계군이 좋아지지 않으면 기존 지원군을 유지한다. 좋은 표시·성공 조건만 채택하지 않는다.
