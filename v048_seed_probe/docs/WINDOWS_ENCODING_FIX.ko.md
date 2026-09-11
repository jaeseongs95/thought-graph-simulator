# Windows subprocess 인코딩 수정 검토

## 문제 범위

사용자가 Windows 11 / Python 3.12에서 `selftest`를 거쳐 계획을 준비하는 과정에서 다음 예외를 관찰했다.

```text
UnicodeDecodeError: 'utf-8' codec can't decode byte 0xb0 ...
Exception in thread ... subprocess.py ... _readerthread
```

소스를 재검사한 결과 실제 Ollama 실행기와 계획 생성기는 외부 명령을 `subprocess`로 실행하지 않는다. 충돌 지점은 `selftest`에 포함된 CLI 회귀시험과 합성 재현 스크립트였다. 이 코드가 자식 Python의 stdout/stderr를 `text=True, encoding='utf-8'`로 즉시 디코딩했기 때문에, Windows 레거시 코드페이지(CP949) 바이트가 나오면 Python 내부 reader thread에서 예외가 발생할 수 있었다.

따라서 LLM 요청·응답 JSON, seed 계획, 채점, A/D/M 연구 설계를 바꿀 문제는 아니며 subprocess 텍스트 경계만 수정했다.

## 수정

1. `subprocess.run(..., text=True, encoding='utf-8')`를 테스트·검증 경로에서 제거했다.
2. stdout/stderr는 먼저 `bytes`로 완전히 수집한다.
3. 자식 Python에는 `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`을 전달한다.
4. 수집 후 UTF-8을 우선하여 strict decode하고, 시스템 선호 인코딩 및 CP949를 손실 없는 fallback으로 시도한다.
5. `errors='replace'` 또는 `errors='ignore'`는 사용하지 않는다.
6. 어떤 허용 인코딩으로도 해석할 수 없는 바이트는 명시적인 `SubprocessDecodeError`로 중단한다.
7. 실제 artifact/JSON/Markdown 저장 인코딩은 기존대로 UTF-8을 유지한다.
8. 수정된 소스와 기존 계획을 섞지 않도록 v048 패치 버전을 `0.4.8-r1`로 올렸다. 소스 fingerprint가 달라지므로 패치 전 생성 계획은 새 소스에서 그대로 실행되지 않는다.

## 제3자 관점의 논쟁과 합의

### 이식성 관점

- 주장 A: Windows에서는 아예 CP949로 읽으면 된다.
- 주장 B: 연구 산출물 전체를 CP949에 맞추면 플랫폼 종속성이 커진다.
- 합의: **UTF-8 artifact 계약은 유지하고 subprocess 경계만 플랫폼 호환 처리한다.**

### 증거 보존 관점

- 주장 A: `errors='replace'`면 크래시는 가장 쉽게 막을 수 있다.
- 주장 B: 검증 로그 문자가 변형되면 오류 메시지 자체가 증거로서 손실된다.
- 합의: **replacement/ignore는 금지하고 성공하는 strict codec으로만 해석한다.**

### 실패 안전성 관점

- 주장 A: 어떤 바이트든 최대한 문자열로 만들어 시험을 계속해야 한다.
- 주장 B: 허용 codec 어느 것으로도 해석되지 않는 출력은 정상 텍스트라고 가정하면 안 된다.
- 합의: **UTF-8/시스템 인코딩/CP949로 정확히 복원되지 않으면 명시적으로 실패한다.** reader thread에서 비동기적으로 깨지는 기존 상태보다 판정 가능성이 높다.

### 연구 설계 관점

- 주장 A: 인코딩 수정 시 실험 소스도 함께 손대는 편이 편하다.
- 주장 B: 현재 오류는 평가 실험이 아니라 테스트 하네스 경계이므로 논리·seed·요청 생성에 변경을 섞으면 비교 가능성을 해친다.
- 합의: **원식/교환식/파이프라인, seed 목록, 스케줄, 채점, 비용 집계는 변경하지 않는다.** 패치 버전과 테스트 보조 코드만 변경한다.

### fallback 해석 관점

- 우려: CP949 fallback이 예상치 못한 바이트를 문자로 해석할 수 있다.
- 판단: 이 유틸리티는 임의 바이너리가 아니라 CLI stdout/stderr라는 명시적 텍스트 채널에만 사용한다. 실제 실험 요청·응답 원문에는 적용하지 않는다. 또한 `TextProcessResult`가 실제 사용한 stdout/stderr codec을 별도 필드로 보존한다.

## 회귀 검증

- 과거 방식 재현: `검증 완료`를 CP949로 출력하는 자식 프로세스를 `encoding='utf-8'`로 읽으면 동일한 `UnicodeDecodeError` 발생.
- 새 방식: 같은 바이트를 손실 없이 `검증 완료`로 복원하고 실제 codec을 `cp949`로 기록.
- UTF-8 한글 stdout/stderr: 자식 Python UTF-8 강제 후 정상 복원.
- ASCII: 정상.
- 허용 codec으로 해석 불가능한 잘린 바이트: 명시적 `SubprocessDecodeError`.
- 전체 selftest: 171개 통과.
- 합성 HTTP 전체 경로: 960회 요청 완료, 서버 종료 후 재감사 결과 동일.
- 독립 진리표 검사: 960회 원문 및 파이프라인 부모값 전달 확인.
- 사용자 v047 원문: `--accept-snapshot` 기준으로 실제 모델 호출 없이 v048 계획 생성 성공.

## 결론

수정 방향은 타당하다. 관측된 오류의 실제 경계만 변경했고 연구 실험의 독립변수·요청·채점 계약은 유지했다. 패치 전 v048 계획이 이미 생성됐다면 실행하지 말고 새 패치 소스로 계획을 다시 생성해야 한다.
