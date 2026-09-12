# local_llm v0.4.5

교체 및 실행 명령은 ZIP 최상위 `START_HERE.ko.md`를 읽는다.

기존 결과의 점수나 core를 바꾸지 않고, factor 16건을 원문 재검사하며 COPY/AND/NOT/AND-NOT 단일 연산을 분리한다.
새 `operator_probe`는 원래 ADM 본 실험과 별도다. 모델 출력값을 코드가 정답으로 대체하지 않는다.

- 변경: `CHANGES.ko.md`
- 실험 해석: `PROTOCOL.ko.md`
- 실제 오프라인 검증 범위: `BUILD_STATUS.json`
- 구버전 실행 안내: `HISTORY_v0441_README.ko.md`
