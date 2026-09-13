# v064: A/D/M 연구 복귀를 위한 직접 D 대조

[연구 복귀 결정서](docs/RESEARCH_RETURN.ko.md)와 [동결 프로토콜](docs/PROTOCOL.ko.md)을 먼저 확인한다. 이 소스의 실제 실험은 Qwen의 세 문제 × 두 seed × shallow/deep/neutral, 최대 **18회 추론**이다. 개발·검증에서는 실제 모델을 호출하지 않았다. T02는 개발 회귀, 새 두 문제는 사전 모델 응답 미관측의 설계자 선정 구조이며 독립 외부 holdout은 아니다.

Python 3.10 이상, 표준 라이브러리만 필요하다. 과거 버전의 실행 소스는 의존하지 않는다. 입력은 별도로 보존된 `v058_order_02_evidence.zip`이며 SHA256은 `d8fd5b2123d38023aaf7c7c0427f54ab6fe650d6b85a695790cb7a5b5b852761`이다. 소스 ZIP에는 이 큰 입력과 과거 중첩 소스 체인을 넣지 않았다. ZIP 안의 source snapshot은 실행·import하지 않는다.

## 무추론 준비 검사

저장소 루트에서 다음을 실행한다. 이 모드는 자체시험의 **가짜 로컬 HTTP 서버**만 사용하며 실제 Ollama 조회·추론·다운로드·시작을 하지 않는다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\llm_experiments\v064\probe\windows\Run-v064.ps1 -CheckOnly -NoPause
```

별도 폴더에 배포본을 풀었다면 `-Baseline "D:\보존 위치\v058_order_02_evidence.zip"`으로 원본을 지정한다. 상대 경로 입력도 시작 위치에서 절대 경로로 변환한다. 준비 검사는 새 계획 파일을 만들며 추론을 시작하지 않는다.

## 실제 사용자 실행

Ollama와 원래 digest의 Qwen 모델이 사용자가 관리하는 로컬 서버에 이미 있어야 한다. **`windows/Run-v064.cmd`를 더블클릭하면 실제 추론을 실행한다.** 또는:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\llm_experiments\v064\probe\windows\Run-v064.ps1 -NoPause
```

실행기는 자체시험 → 입력·경로 깊이 확인 → 새 RunName/계획 → 모델 metadata 확인 → 추론 → 감사·증거 ZIP → 독립 검산을 수행한다. 서버를 시작하거나 모델을 다운로드·갱신하지 않는다. identity가 다르면 중단한다. 같은 실행의 실패 후 자동 재개·새 이름 재시도는 없다. 다시 실행하려면 사용자가 별도로 판단해 직접 시작해야 하며, 이전 자료는 보존된다.

호출 상한은 18회, 생성 설정 상한은 73,728 tokens다. 입력 토큰은 사전 확정하지 않았으며 원응답의 실제 계수를 기록한다. metadata는 12묶음으로 별도이며 추론으로 세지 않는다. 형식/논리 오답은 예정 호출을 계속하고 전송·identity 오류는 부분 자료를 남기고 멈춘다. native stderr가 있다는 이유만으로 실패시키지 않으며 종료코드를 기준으로 판단하고 stdout/stderr를 모두 로그에 남긴다.

## 개별 명령

아래 명령의 작업 위치는 `probe`이다. 계획·결과 파일은 기존 경로를 덮어쓰지 않는다.

```powershell
$env:V064_BASELINE = 'D:\보존 위치\v058_order_02_evidence.zip'
python -X utf8 -B -m unittest discover -s tests -v
python -X utf8 -B run.py prepare --baseline $env:V064_BASELINE --run-name v064_direct_01 --out ..\experiments\v064_direct_01.plan.json
python -X utf8 -B run.py execute --plan ..\experiments\v064_direct_01.plan.json --baseline $env:V064_BASELINE --out ..\results_llm\v064_direct_01
python -X utf8 -B verify.py ..\results_llm\v064_direct_01_evidence.zip
```

`prepare`는 HTTP를 전혀 사용하지 않는다. `execute`는 실제 추론 명령이다. 테스트용 `--synthetic` 계획은 결과에 synthetic 출처를 명시하며 연구 성과로 사용하지 않는다. 프로세스가 강제로 끊겨 결과 ZIP이 없으면, 동일한 고정 소스로 `run.py finalize --run <보존된 실행 폴더>`를 실행해 **추론 없이** 부분 기록을 묶는다. 이미 summary/ZIP이 있으면 덮어쓰지 않는다.

## 결과와 보증 범위

각 실행 폴더에는 plan, 시작 표지·event chain·원문, 모델 metadata, source 해시·사본, status, summary JSON·한국어 보고서가 남는다. 폴더 옆에는 evidence ZIP과 independent JSON이 생성된다. 독립 검산기는 생산 측정/보고 모듈을 import하지 않고 기준선·계획·요청·원응답·D·지표·한국어 보고서를 재계산한다.

파싱 불가·미실행을 논리 오답이나 D=0으로 채우지 않는다. 모든 지시에서 같은 유효 D를 내면 선택적 제어로 승인하지 않는다. 규칙 이름만 맞아도 부모 연결이 틀리면 실패다. 중립 조건의 성공으로 directed 실패를 보정하지 않는다. 소스·무결성 검사 통과와 실제 모델 성공은 다르며, 두 계산기가 공유한 명세 오류와 외부 실행 인증의 한계는 남는다.

현재 테스트는 실제 크기의 고정 기준선을 필요로 한다. 작은 합성 ZIP으로 대체해 실제 중첩 입력 검사를 생략하지 않는다. 원자료 재분석·과거 단계형 반례·실제 테스트 로그·최종 감사는 배포 ZIP 밖 `validation/`에 있다. 개발 중의 합성 실행을 실제 모델 실험으로 합산하지 않는다.

## 소스 패키지

```powershell
python -X utf8 -B build_release.py --out ..\releases\v064_direct_D_source_r3.zip
python -X utf8 -B build_release.py --check ..\releases\v064_direct_D_source_r3.zip
```

새 소스만 포함하며 ZIP 시간·권한 메타데이터를 고정한다. 최종 배포본을 빈 폴더에 풀고 원본 baseline 경로를 지정해 검사한다. 실제 전달본의 SHA와 감사 대상은 `validation/FINAL_REVIEW.ko.md`에서 확인한다.

교정판 r2는 모든 action의 최초 중단 사유를 검사하며, event 전 중단된 한 action의 미확정 원문을 pending_action으로 보존한다. 완료 관측에 합치지 않으며 이후 action·동결 요청과 다른 바이트는 거부한다. 제공자의 생성 설정 초과 보고도 stopped 원자료와 독립 receipt로 남긴다. 검증 대상 r1 ZIP은 교정 전 기록이며 실제 전달은 r3 ZIP을 사용한다.

r3는 미확정 record도 연속된 완전 request/response 쌍 뒤에서만 보존하도록 저장 순서 검사를 보완했다. r1/r2는 교정 전 감사 기록이며 실제 전달본은 r3다.
