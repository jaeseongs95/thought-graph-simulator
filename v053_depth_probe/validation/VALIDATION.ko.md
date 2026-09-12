# 실제 검증 기록

## 완료한 검사

|검사|결과|원시 기록|
|---|---|---|
|원래 r2 전체 회귀|484/484, 종료 0|r2_full_selftest.log/.exit|
|최종 기존+신규 전체 회귀|546/546 = 기존 484 + 신규 62, 종료 0|v053_full_tests.log/.exit|
|원본 참조 진단 결함 재현|동일 반례 3개 실패, 종료 1|reference_red.log/.exit|
|교정된 참조 진단|동일 반례 3개 통과, 종료 0|reference_green.log/.exit|
|실제 v052 baseline 오프라인 수입|성공, 새 모델 호출 0|actual_compatibility.json|
|기존 v047~v052 코어 보존|59개 전부 원래 r2와 바이트 일치|actual_compatibility.json|
|새 실험 original 방향 요청|실제 v052 요청 40개와 바이트 일치|actual_compatibility.json|
|defined 요청 차이|60쌍 모두 정의 문단 하나만 추가|actual_compatibility.json|

546개 최종 시험은 173.496초에 완료됐으며 실제 반환 코드가 0임을 확인했다. 기존 r2의 기록만 새 코드의 통과 기록으로 재사용한 것이 아니다. 추가한 테스트의 초안 작성 오류와 수정 경계는 `docs/REVIEW_AND_FIXES.ko.md`에 기록했다.

## 보존한 합성 서버 실행 3종

|합성 서버 행동|실제 HTTP 호출|유효 증명|선택적 대응 성공|독립 채점 불일치|
|---|---:|---:|---:|---:|
|요청 방향대로 올바른 그래프 반환|120|120|40/40|0|
|항상 같은 얕은 경로 반환|120|120|0/40|0|
|없는 최종 노드 ID 반환|120|0|0/40|0|

총 360회는 **가짜 모델 서버**에 대한 새 v053 호출이다. 실제 연구 성공으로 집계하지 않는다. 시험 준비에 사용한 이전 버전 fixture 호출은 이 표의 v053 360회와 별도다.

각 실행은 `synthetic_perfect.zip`, `synthetic_ignore_roles.zip`, `synthetic_bad_final.zip`으로 보존했다. 독립 검사기는 원시 응답에서 5개 필드×120 + 방향 판정 80 = 680개 의미 필드를 대조했으며 각 자료에서 불일치 0개다. 대응쌍도 독립적으로 다시 계산해 production 집계와 비교했다. 이 코드는 production 채점기나 정답 fixture를 import하지 않는다.

`synthetic_*_independent.json`과 `synthetic_validation.json`이 결과다. 배포 ZIP을 새 폴더에 풀어 수행한 추가 시험·오프라인 재감사와 ZIP 해시 확인은 함께 제공한 분석 묶음의 `release_verification.json` 및 `fresh_release_full_tests.log`를 따른다.

## 검사한 실패·우회

원시 응답 변경, 요청 바이트 변경 후 이벤트 해시 체인까지 재작성, 미등록 호출 파일, 소스 snapshot 변경, 모델 identity 불일치, 실행 후 identity 변경, 전송 503, 모델 응답 identity 변경, 출력 잘림, 기존 PASS 보고서 잔존, 기존 파일 덮어쓰기, JSON 중복 키, 없는 최종 참조, 중복 노드, 사용되지 않은 노드, 잘못된 규칙·부모·목표, 실제 깊이와 노드 수의 혼동을 검사했다.

전송 오류는 한 번 호출 후 중단되며 자동 재시도하지 않는다. 추론 전 identity 실패는 0회다. 오프라인 감사에는 모델 응답 생성이나 source snapshot 실행을 사용하지 않는다.

## 재현 명령

모듈 폴더에서:

```powershell
python -m depth_probe_v053 selftest --all
python .\tools\reproduce_reference_fix.py old
python .\tools\reproduce_reference_fix.py fixed
python .\tools\independent_verify_v053.py .\validation\synthetic_perfect.zip --out .\synthetic_perfect_recheck.json
```

`old` 반례 명령의 종료 1과 3개 실패는 의도된 원본 결함 재현 결과다. `fixed`는 종료 0이어야 한다. 정상 시험 실패를 은폐하기 위한 예외처리가 아니다.

## 최종 분석 교차검사

완전 복사 지표는 원래 생산 코드에서도 0/20이다. 원문 reference_record와 실제 응답을 별도로 대조해 nodes/final_node_id/reviews는 20/20 동일하지만 node_views는 20/20 모두 달라졌음을 확인했다. 이로써 분석 초안의 복사 성공 해석을 교정했다. 기존 측정 코드 수정은 필요하지 않았다.

T02 M0↔M1의 7쌍은 독립 증명 구조 서명으로 같은 경로 유지까지 확인했다. 중립 응답의 깊이 4 증명 2개도 별도로 확인했다. 상세 기록은 분석 묶음의 additional_raw_checks.json 및 스크립트에 있다.

## 실제 제약

실행 환경은 Linux/Python 3.13이며 상세 버전은 environment.json이다. Windows·PowerShell에서 직접 실행한 것은 아니다. 사용자 PC의 Qwen 모델에 새 v053 추론을 요청한 적이 없다. 실제 사용자 모델의 분석 대상은 첨부된 v052 440개 응답이다. source/runtime/event 해시는 동봉 자료의 일관성 증거이며 외부 물리 실행 인증이 아니다.
