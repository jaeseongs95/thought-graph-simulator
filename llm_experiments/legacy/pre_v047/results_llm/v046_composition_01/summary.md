# NOT→AND 연결 결과

네 파이프라인 중 모든 단계가 맞은 수: 4/4

| a,b | 정답 | 이전 직접식 | 순서 대조 | 새 NOT | 새 AND | 단계 전체 통과 |
| --- | --- | --- | --- | --- | --- | --- |
| [False, False] | False | False | False | True | False | True |
| [False, True] | False | False | False | False | False | True |
| [True, False] | True | False | True | True | True | True |
| [True, True] | False | False | False | False | False | True |

정답과 일치한 최종값과 모든 의존 단계의 유효성을 구별한다. 중간 오답이 우연히 상쇄되어도 파이프라인 성공이 아니다.
이전 중간 입력을 재사용한다. NOT와 AND는 새 호출이며 전처리 추출까지 포함한 신규 종단 간 실행은 아니다.
직접식 대 체인은 호출 수/식 구조/입력 배치가 함께 다르다. 일반적 모델 크기/양자화 효과나 내부 원인 확정이 아니다.
과거 직접식 실패를 새로운 결과로 덮어쓰지 않는다.
