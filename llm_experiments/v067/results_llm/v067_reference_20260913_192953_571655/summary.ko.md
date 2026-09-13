# v067 정상 참조 계획 재구성 양성 대조

실행 상태: complete / 관측: 12/12 / provenance: live
**실험자가 정답 규칙 경로를 입력으로 제공했다. 모델의 자율적인 D 제어나 모델 계획→생성의 종단 성공이 아니다.**
참조 입력 재구성: 4/12, 미측정 0, 양성 대조 기준: 불통과.

|문제|참조 종류|제공된 규칙 경로|관측/배정|논리 유효|엄격 증명|순서 이행|재구성 성공|미측정|
|---|---|---|---:|---:|---:|---:|---:|---:|
|T02|reference_short|r83|2/2|2|2|2|2|0|
|T02|reference_long|r21,r57,r04,r69|2/2|0|0|2|0|0|
|E01_shared_fork|reference_short|n52|2/2|2|2|2|2|0|
|E01_shared_fork|reference_long|n08,n91,n37|2/2|2|0|0|0|0|
|E02_two_vs_four|reference_short|m18,m76|2/2|0|0|2|0|0|
|E02_two_vs_four|reference_long|m33,m05,m84,m41|2/2|0|0|0|0|0|

## 해석과 종료
12/12이면 정상 계획을 입력했을 때 이 생성 인터페이스가 재구성할 수 있다는 기준선만 얻는다. 과거 v066의 실패를 취소하거나 원인이 계획기 하나뿐이었다고 단정하지 않는다.
12건이 모두 측정됐는데 성공이 0/12이면 이 모델과 현재 전체-DAG 출력 계약의 양성 대조도 종료한다. 부분 성공은 해당 문제·참조 경로·seed에 한정한다. 같은 문구를 바꾸며 자동 반복하지 않는다.
미관측·파싱 불가이면 전부 오답으로 채우지 않고 전체 기준은 미판정이다. A/M·내부 사고·비용 우월성·새 문제 일반화는 측정하지 않았다.
이 대조의 정답 입력은 명시적 조건이다. 모델의 출력 노드·부모·final 참조는 추가·삭제·수선하지 않는다.

다음 결정 코드: preserve_partial_scope_no_automatic_extension
실패 계층: {'proof_failures': 6, 'strict_only_failures': 2, 'reference_order_mismatch': 4, 'unmeasured': 0, 'not_observed': 0}
원응답 비용 계수: {'prompt_eval_count': 8332, 'eval_count': 2494, 'total_duration': 38550881200, 'prompt_eval_cached_count': 7016}
계획 SHA-256: 1d88337db00c2ede3fc26e72a359e62867e43f2ea17fed1b04d77afcf7327710
