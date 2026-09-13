# v059 소스 검증 기록

실제 v059 모델 추론은 실행하지 않았다. 아래 결과는 코드·증거 처리·실행기 계약에 대한 오프라인 검증이다. 합성 응답은 `synthetic_fixture`로 기록하며 연구 성과에 합산하지 않는다.

## 1차 후보에서 수행한 검사

|검사|결과|근거|
|---|---|---|
|v058 원문 재분석|80호출·40 metadata, 독립 1,649필드 차이 0|`validation/v058_reanalysis.json`|
|실제 v058 기준선 import|생산 감사·독립 검산과 두 sequence의 choice 요청 동일성 확인|`validation/v058_import_check.json`; 최종 CheckOnly에서도 재검산|
|설계·측정 시험|10개 통과|요청변환, 배치, 깊이구분, 누락과 반복불일치 반례|
|Windows CheckOnly 전체 selftest|28개 모두 통과, 건너뛴 시험 0개|`validation/checkonly.log`|
|Windows CheckOnly 준비→show|종료 코드 0, 실제 추론 없음|`validation/checkonly.json`|
|최종 검증용 계획|40추론·60 action; 생성·동결·검사 완료|`experiments/v059_rules_validation_01.plan.json`|

Windows 검증 명령은 저장소 루트에서 다음과 같다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\llm_experiments\v059\probe\windows\Run-v059.ps1 -CheckOnly -NoPause -RunName v059_rules_validation_01
```

28개 시험은 설계·측정 10개, 실행·무결성 11개, 독립 검산 7개다. 40개 정상 mock 호출, 20 metadata, 100 HTTP 요청의 일정을 검사했다. transport 오류, 응답 모델 오류, metadata 실패, 블록 이후 identity drift가 중단되는지 확인했다. 잘못된 규칙 ID나 파싱 오류를 교정하지 않고 보존하는지도 검사했다.

삭제된 응답, 바뀐 응답, 중복 event, 추가 호출, 누락된 소스 snapshot, 재해시한 실행표·요약·요청 변조, ZIP 중복·경로 이탈, 반대 sequence 기준 요청 불일치도 반례로 확인했다. 감사 실패 보고가 링크를 따라 외부 파일을 덮어쓰지 않는 시험도 통과했다.

최종 검증용 계획의 SHA-256은 `be66923af2960097020cfd3c8833fe0bc615122ea3d3d8dd5c7c5abdd487f094`다. 이 값은 해당 소스와 입력을 검사한 계획의 내용 해시이며, 설치된 모델이 이후에도 같은 상태임을 보증하지 않는다. 실제 실행 전에는 현재 최종 소스에서 새 이름의 계획을 준비한다.

## 같은 관점으로 수행한 소스 검토

측정·구성타당성 검토는 요청 조작 범위, actual D와 implied_depth 분리, 분모와 null 규칙에서 차단 결함을 찾지 못했다. `stable_within_both`는 올바른 선택이 아니라 출력 ID의 안정성이라는 뜻을 프로토콜에 명시했다. 선택 규칙 위치는 각 trial measurement에 보존된다.

인과·통계 검토도 차단 결함을 찾지 못했다. 블록 내부 균형과 전역 이력 균형이 다르며, 발생 차수로 맞춘 조건 비교를 직접적인 인과효과로 읽지 않도록 프로토콜을 보완했다. 같은 조건에서의 변동과 순열 간 차이를 별도로 집계한다.

증거·구현 관점의 검토와 구현·설계에 참여하지 않은 감사자의 최종 판정은 소스 밖 `validation/`에 기록한다. 최종 배포 ZIP의 manifest, 새 위치에 푼 뒤의 selftest, 봉인된 후보 해시와 findings 처리는 [최종 검증 보고](../../validation/FINAL_REVIEW.ko.md)에서 확인한다. 이 문서는 소스 패키지에 포함되지만 실행 로그와 감사 결과는 별도 산출물이다.

## 최종 감사에서 발견한 결함과 재검증

1차 최종 감사는 한국어 요약문 변조가 독립 검산을 통과한다는 반례를 발견해 후보를 차단했다(F-001). JSON 결과와 manifest를 검사하는 것만으로 사람이 읽는 결론의 의미 무결성이 보장되지 않았다. 수정 후보는 독립 검산기가 원자료에서 재구성한 보고서로 한국어 요약의 기대 바이트를 만들고 정확히 비교하도록 한다. 요약을 변조한 뒤 manifest를 재해시하는 회귀시험도 검증 대상에 추가한다.

위의 28개 시험과 계획 해시는 수정 전 기록이다. 수정 후보의 최종 시험 수, 새 계획, 배포 해시, 재감사 판정은 별도 [최종 검증 보고](../../validation/FINAL_REVIEW.ko.md)에 기록한다. 이 파일은 저장소의 별도 검증 산출물이므로 소스 ZIP만 해제한 환경에는 포함되지 않는다.

## 검증의 한계

metadata identity는 모델명·digest·서버 버전과 추적하는 `details`, `template`, `parameters`, `model_info` 필드를 비교한다. `parameters`의 고유한 줄 순서는 정규화하고 `show_sha256` 전체는 동일성 비교에서 제외한다. 따라서 `/api/show`의 미추적 필드 변화까지 모두 중단시키지는 않는다(F-002). 응답 원문은 보존하지만, 이 계약만으로 모든 모델 상태가 같다고 주장할 수 없다.

mock 실행 시험에서는 앞 버전의 전체 LLM 실험을 재현하지 않는다. 앞 버전 검산 호출을 명시적으로 대체하는 fixture와 최소 v058 ZIP을 사용하고, v059의 원자료 선택·변환·실행·감사·독립 재구성은 검사한다. 실제 v058 입력에 대한 생산·독립 import는 별도의 실제 증거 검사로 수행했다.

독립 검산기의 `production_imports=false`는 구현 계약과 import 검사에 근거하며 플랫폼 수준 실행 인증은 아니다. 과거 독립 도구의 공통 명세를 일부 공유한다. 형식 오류의 상세 문구와 `parse_error` 설명은 타입을 확인하되 생산 라이브러리와 글자 단위로 독립 재계산하지 않는다. 연구 지표, 유효성, 순서, 요청과 응답, 집계는 별도로 재구성한다.

생성된 Python 캐시의 삭제는 자동 승인 검토에서 정책상 차단됐다. 캐시는 보존하고 배포 도구의 제외 규칙으로 소스 ZIP과 manifest에 넣지 않는다. 실제 모델의 v059 선택 변화, 실행 당시 캐시의 인과 역할과 다른 문제로의 일반화는 이번 검증으로 확인하지 않았다.
