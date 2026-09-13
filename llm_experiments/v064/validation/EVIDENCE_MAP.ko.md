# 연구 복귀 원자료 대조

이번 기준은 한국어 논문 `research/paper/TTS_논문_v1.0.pdf`(2026-09-10), 제한된 실행 명세 `docs/research_note.md` R0.1, 현재 `AGENTS.md`와 `adm_minimal.py`이다. 영어 논문도 함께 추출했으나 축의 문구를 합성해 새 정의로 만들지 않았다. 정확한 파일 해시는 baseline.json, 원문 텍스트는 같은 validation 폴더에 있다.

## 정의와 적용 범위

논문 3.2절의 A0~A4는 관측/사례 관계/사례군 규칙/역할 치환 스키마/영역 간 보존 대응의 서열형 코드북이다. simulator는 instance와 universal schema 두 표현만 구현한다. 두 범주를 A0~A4 전체의 검증으로 확대하지 않는다. 연구 노트는 당시 논문을 확보하지 못했다고 명시한다. 이번에는 논문을 직접 대조했으며 그 역사적 문구를 수정하지 않는다.

논문 3.3절의 D는 기록된 부모 관계의 깊이이며 타당성과 분리될 수 있다. simulator와 후속 LLM 계약은 성과 지표 actual_D를 유효한 목표 증명에만 부여한다. 무효 증명의 actual_D=null을 유지한다. 논문의 구조적 D_raw와 유효 증명의 D를 혼용하지 않는다. 추가 중간 명제 때문에 D 대조는 모든 명제가 동일한 Q-exact가 아니라 문제·근거·목표를 고정한 Base-fixed 대조다.

논문 3.4절의 M은 검토 대상이다. M0 대상 문제, M1 논증 근거·가정, M2 평가 기준·목표·검증 절차 적합성이다. 검토 수준과 검토 정오는 별도이다. simulator verify는 views의 치환·보편 타당성, reviews의 target_kind와 근거를 검사한다. 길이·규칙 ID·메타 표현만으로 A/M을 올리지 않는다.

논문 부록 C/F와 supplement/experiment_manifest.json은 H1~H8의 실제 검증을 완료했다고 하지 않는다. 특히 보충 manifest는 DESIGN_NOT_EXECUTED, preregistered=false, execution_ready=false이며 모델·평가기·효용/효과 모델 등 자산이 null이다. B3−B2 및 비용 효율을 이번 작은 D 검사와 동일시하지 않는다. 보충 명세의 전체 배정 대비 유효 완료 비율은 미완료를 비성공으로 집계하지만, 이는 논리 오답이나 측정된 D=0으로 바꾸는 규칙이 아니다.

## 누적 근거의 네 수준

|수준|확인된 범위|남은 질문|
|---|---|---|
|simulator에서 구조를 정의·구성|adm_minimal.py simulate/verify의 명시적 Horn 증명, 표현·검토 구조 및 보존된 실행 기록|일반 자연어 코드북의 신뢰도·구성타당도|
|실제 LLM의 지정 구조 구성|v058 Qwen T02 shallow 원문 20/20 유효 D=1; 같은 조건 choice 15/20 얕은 규칙|깊은 생성과 방향별 대응 제어; 모델·문제별 범위|
|동일 문제에서 선택적 구조 제어|이번에 확인한 v058~v063 근거로는 입증되지 않음|shallow/deep 양쪽 유효 증명과 실제 D 변화|
|새 구조 재현과 비용 가치|이번 자료로 입증되지 않음|개발에 쓰지 않은 구조, 적절한 대조, 추가 호출·토큰·시간 및 모델별 비교|

이 표는 저장소 전체에서 성공이 절대로 없다는 주장이 아니라 이번에 직접 확인한 근거의 범위다. 작은/큰 모델 동등 성능, 비용 절감, hidden layer 제어는 포함하지 않는다.

## 직접 확인과 판본 차이

- v058 ZIP d8fd5b…2761: Qwen T02 그래프의 20개 원응답은 모두 D1의 유효 증명, choice는 r83 15개/r69 5개. Gemma K01 graph 20개 무효, choice k17 20개. 서로 다른 모델에 다른 문제가 주어져 순수 모델 효과가 아니다.
- v059 ZIP 3f9b1e…85c5: original k17 20개, terminal_swap k03 20개.
- v060 ZIP 5a2aee…2c68: deep_first k17 20개, shallow_first k03 20개. 첫 terminal 예측과 맞지만 내부 알고리즘을 발견한 것이 아니다.
- v061 ZIP 650c3f…e4dc: shallow/deep 모두 k03 20개씩. choice의 implied_depth와 actual_D는 다르다.
- v062 ZIP baea75…9fd: graph 40개 모두 무효. v063에서 마지막 규칙 문자열 일치 39/40, 짧은 조건의 조상 밖 오류만 16/20을 진단했다. 이 오류 노드를 지우지 않는다.
- v063 소스 ZIP 449321…34ac: 오프라인 진단 버전이며 실제 모델 실행이 아니다. Gemma/K01 진단 분기는 종료하되 연구 전체를 종료하는 근거로 쓰지 않는다.

이번 임시 원문 집계의 첫 판본은 v058의 `rule`을 v062의 `rule_id`로 읽어 KeyError를 실패로 잘못 분류했다. `raw_crosscheck.json`을 보존하고 `raw_crosscheck_corrected.json`에서 판본별 필드를 사용해 교정했다. 과거 생산 코드나 증거가 잘못된 것은 아니다. choice 집계에는 영향이 없다. 이를 모델 실패의 새 증거로 세지 않는다.

## 이전 단계형 실행

`local_llm/composition_probe.py`와 `legacy/pre_v047/results_llm/v046_composition_01`의 실제 요청·응답을 대조했다. NOT의 bool 반환값을 다음 AND 요청 b에 그대로 넘긴 4건은 모두 일치한다(staged_transfer_check.json). NOT 국소 결과, 실제 전달값에 대한 AND 국소 결과, 원문 공식에 대한 최종값을 분리하면 4/4 단계 전체 성공이다(staged_raw_check.json).

기존 원시 입력을 재사용한 신규 게이트 호출이며, 추출부터 새로 수행한 A/D/M 종단 간 실행은 아니다. 호스트가 NOT→AND 연결을 제공했다. 직접식과 체인은 호출 수·입력 배치·식 구조가 함께 달라진 묶음 비교다. 이 기록은 무보정 외부 실행이 가능하다는 근거이며 자율적인 D 선택이나 비용 절감의 증거는 아니다.

## 재사용 경계

보존된 독립 검산 receipt는 해당 ZIP 해시와 일치하는지 확인해 내부 일관성의 과거 검사 기록으로 재사용한다. PASS나 시험 개수를 새로운 연구 관측으로 더하지 않는다. 이번 결론의 핵심 규칙·원응답·전달값은 직접 확인했다. 증거 ZIP의 source_snapshot은 실행하거나 import하지 않았다. 입력의 중첩 ZIP은 과거 증거이며, 새 버전의 소스 의존성으로 무제한 복제할 이유가 아니다.
