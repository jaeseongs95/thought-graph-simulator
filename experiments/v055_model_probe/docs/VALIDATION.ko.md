# 검증 기록과 재현 범위

## 검증 환경

Python 3.13.5 / Linux x86_64. Windows PowerShell은 직접 실행하지 않았고 실제 사용자 Qwen/Gemma의 v055 추론도 실행하지 않았다. 실제 데이터 분석은 첨부 v054의 120개 응답을 대상으로 했으며 새 코드 실행은 분리된 합성 HTTP 서버를 사용했다.

## 직접 확인한 범위

원본 v054 전체630개 시험은 수정 없이 통과했다. 초기 새 v055 시험55개도 통과했지만 이것만으로 검토를 끝내지 않았다. 미관측 대응쌍을 실패와 분리하는 검토에서 추가한4개 시험은 수정 전 실패했고 수정 후 모두 통과했다. 별도 그래프 계산기의15개 의미·반례 시험도 통과했다.

후보/기준의 실제 이름을 기대값으로 삼아 한쪽에 유리한 채점을 하지 않는지 검사했다. 두 모델 모두 정답, 둘 다 첫 경로, v054 같은 기준 모델 대 정답 후보, 정답 기준 대 첫 경로 후보, 미등록 규칙, 파싱 불가 응답을 각각240회씩 합성 HTTP로 실행했다. HTTP 중단1회, 두 번째 모델의 첫 호출에서 중단13회도 실행했다. 원문 증거를 ZIP으로 다시 묶고 생산 감사와 별도 구현의 검산을 수행했다. 모두 synthetic_fixture이며 실제 모델 성공률이 아니다.

최종 전체 회귀와 배포 ZIP 해제본의 전체 재시험은 동일한 코드에 대해 별도 프로세스로 실행한다. **이번 전달물의 최종 실행 수치·종료 코드·실행 시간·배포 ZIP SHA와 로그는 함께 제공되는 분석 ZIP의 `VALIDATION_RESULT.json`, `v055_full_tests.log`, `v055_release_full_tests.log`에 있다.** 오래된 630개 통과 기록을 새 코드의 전체 통과로 재사용하지 않는다.

## 독립성의 정확한 뜻

생산 감사: 고정 계획, 허용 파일 목록, source fingerprint, source snapshot, raw 요청/응답 해시, 이벤트 순서, 40개 metadata 기록의 identity, 호출수/중단원인을 재구성한다.

독립 검증기: 생산 채점기를 import하지 않고 원문 JSON, 직접 구성한 그래프/깊이/부모 관계 검사, 방향·순서·모델 대응 재집계를 수행한다. 이 검증기는 metadata raw 해시까지만 검사하고 identity의 의미는 생산 감사/별도 변이 시험과 병행한다. 별도 외부 심사자/모델이 검토했다는 의미가 아니다.

## 보존과 변경

`docs/PRESERVED_SOURCE_MANIFEST.json`은 기존152개 Python 파일의 바이트 해시다. 이 가운데 기존 생산 fingerprint 파일은83개다. 새 생산 모듈11개를 추가해 새 fingerprint는94개다. 기존 평가기/프롬프트/문제/규칙은 수정하지 않았다.

새로운 변화는 두 모델 identity 동결과 실행, 요청 model 값 변경, 모델별 같은 지표의 재사용, 모델 간 비교 보고, 실행·감사·Windows 진입점, 새 시험/독립 검산 도구다. 기존 규칙 오류를 고쳐주거나 결과를 성공 쪽으로 바꾸는 변화는 없다.

## 다시 실행

```powershell
python tools\validate_release.py
python -m model_probe_v055 selftest --all
python tools\independent_verify_v055.py ..\results_llm\v055_model_01_evidence.zip --out ..\results_llm\v055_model_01_independent.json
```

Python 최적화 옵션 `-O`는 독립 검증기에서 거부한다. 원문이 변한 경우 해시 검사만 새로 쓰지 말고 변경 출처를 확인해야 한다. 배포본을 직접 수정한 뒤 이전 capture/계획을 재사용하면 source fingerprint 불일치로 중단한다.
