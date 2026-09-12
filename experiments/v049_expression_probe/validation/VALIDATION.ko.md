# 실제 검증 범위

## 실행 환경과 결과

실제 시험 환경은 Linux·Python 3.13.5이다. Windows/PowerShell 실기 실행, 실제 사용자 Ollama의 새 추론은 수행하지 않았다. Python 3.10 문법 검사도 했으나 이는 Python 3.10 런타임 실행 시험이 아니다.

- **전체 selftest: 243/243 통과.** 기존 v047/v048 및 Windows 인코딩 회귀 171개 + v049 신규 72개.
- **배포 후보 ZIP을 새 폴더에 풀어 동일한 243개 시험 통과.** 종료 코드 0.
- 최종 배포 파일의 실행 코드·테스트·인코딩 helper는 그 추출본에서 통과한 코드와 바이트가 같다. 이후 추가된 파일은 검증 로그·문서·독립 재현 스크립트·합성 증거이며 실제 실험 코드는 변경하지 않았다.
- **세 가지 검토 회귀:** 수정 전 3개 모두 실패, 수정 후 같은 3개 모두 통과.
- **합성 HTTP 전체 실행:** 본 v049 실행기에 480회 요청을 실제 전송·수신. 원식 60/80, 나머지 직접식 80/80, pipeline 전체 80/80으로 기록되는 시나리오를 시험했다. 의도적 오답을 올바르게 실패로 기록하는 시험이다.
- **합성 HTTP 서버를 종료한 뒤** 보존 원문으로 재감사했으며 실행 직후 report와 전체 객체가 일치했다.
- 별도 shunting-yard 계산기와 수동 진리표로 위 합성 원문 480건 및 부모값 전달 80건을 재확인했다. 본 감사기/정답표를 import하지 않았다.
- 사용자가 제공한 실제 v048 evidence ZIP으로 새 `prepare`가 성공했다. 이는 원문 재감사·계획 생성이며 새 모델 추론이 아니다.
- v047/v048 코어와 Windows subprocess helper 17개 파일은 이전 수정판과 바이트가 같다.

## 어떤 반례를 검사했는가

입력·seed·순서·정책 변경 후 자체 해시 재생성, 원문 변경, 소스 snapshot 변경, event 순서 변경, 바뀐 부모값을 정답으로 교체한 child, 최종값만 우연히 맞는 잘못된 중간값, 형식 오류와 bool 강제변환, 모델 정체성 불일치, 통신 중단, 서버 설정 변경, 누락 usage, 반복 불안정성, 원본 PASS 요약 무효화, ZIP 경로 이탈·예약명·링크·중복·해시 오류, 감사/묶음 생성 사이의 변경을 시험했다.

네 입력의 중간·최종값 8비트 256조합을 모두 검사하여 전체 trace 성공은 정확한 한 조합뿐임을 확인했다. 최종값만 모두 맞는 나머지 15개 조합은 trace 성공이 아니다. 통합 시험에서도 동일한 가림 오류를 실제 원문 복사본에 주입했을 때 최종값 80/80은 유지되지만 trace는 79/80으로 계산됐다.

부모가 잘못된 bool이면 실행기는 그대로 다음 AND에 전달한다. 부모가 bool을 내놓지 못하면 child만 blocked이며 모델 응답을 자동 재시도하지 않는다. 인프라 오류는 미완료로 처리하고 전체 차이·상호작용을 null로 남긴다.

## 파일

- `SELFTEST.log`: 전체 243개 시험.
- `RELEASE_SELFTEST.log`, `RELEASE_SELFTEST.exit`: ZIP 추출본의 전체 243개 시험 및 종료 코드.
- `REVIEW_BEFORE_FIX.log`, `REVIEW_AFTER_FIX.log`: 실제 세 반례의 수정 전/후 결과.
- `SYNTHETIC_480_EVIDENCE.zip`: 합성 HTTP 실행 증거. 실제 LLM 결과가 아님.
- `SYNTHETIC_480_RESULT.json`, `SYNTHETIC_480_SUMMARY.ko.md`: 합성 실행·재감사·독립 계산 결과.
- `independent_raw_check.py`: 별도 계산기.
- `ACTUAL_V048_PREPARE.log`: 사용자 v048 ZIP을 이용한 오프라인 prepare 출력.
- `LEGACY_UNCHANGED.json`: 고정 이전 코드와의 바이트 비교.
- `PYTHON310_SYNTAX.json`: 문법 검사 범위.
- `FINAL_RELEASE_CHECK.json`: 최종 배포 추출본과 시험 완료 코드의 동일성 및 합성 증거 재감사.

## 합성 실행을 새 폴더에서 재현

```powershell
python .\validation\reproduce_synthetic.py --out-dir .\synthetic_reproduction_01
```

출력 폴더가 이미 있으면 덮어쓰지 않는다. 실제 Ollama가 아니라 시험용 HTTP 서버에만 요청한다. 기본 selftest에도 전체 규모 실행 시험이 포함된다.

## 해석 경계

코드 시험 성공은 v049의 실제 LLM 실험 성공을 뜻하지 않는다. 그 실제 결과는 사용자의 `run`에서 수집된다. 데이터 해시와 외부 계획은 일관성 검사이지 외부 서버 실행의 전자서명은 아니다. Windows 실행은 사용자 환경의 `selftest`를 먼저 통과한 뒤 진행하도록 했다.
