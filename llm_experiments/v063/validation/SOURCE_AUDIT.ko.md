# v063 봉인 소스 독립 감사

판정은 `pass_with_diagnostic`이다. 차단 finding은 0개이며, `cooperative-sealed` / `sealed-artifact-v1` 조건에서 candidate 완료 판정은 `complete`다. 감사자는 계획·구현·통합에 참여하지 않았고 봉인 ZIP과 probe를 수정하지 않았다.

감사 전후 candidate는 `llm_experiments/v063/releases/v063_forensics_source_r1.zip`, SHA256 `4493217731fd0cf40c5deac91921b93b090109664cc697f7cf33901bf2b834ac`이다. 기준 ZIP SHA256은 `33830e414b93174b2fbc36ec46d4675ab8e15321abd5608db301a487d8561da4`, v062 evidence SHA256은 `baea752ac1a55dc7a20b42b41ced69b3c8e126105f65deea8ebecc8dde3f09fd`로 동결 입력과 일치했다.

직접 검사는 다음 결과를 냈다.

- 기준 source ZIP과 candidate를 엔트리별로 대조했다. 이전 소스 360개는 모두 동일했고, 이전 파일 삭제는 없으며, manifest 갱신과 v063 신규 파일 9개만 존재한다.
- evidence의 source snapshot은 읽거나 실행·import하지 않았다. 외부 plan, events, summary와 40개 request/response만 별도 표준 라이브러리 감사기로 읽어 40개 payload·공식 측정·부모 조상 폐쇄·노드 오류를 전부 다시 대조했고 `differences=[]`였다.
- 공식 `proof_valid`, `strict_valid`, `instruction_fulfilled`는 모두 0/40이고 `actual_D`는 40/40 `null`이다. 최종 규칙 라벨은 39/40, 최종 atom은 40/40 일치했다. 최종 조상 밖 노드는 40/40, 조상 안 오류는 23/40, 오류가 밖에만 있는 경우는 17/40이었다. 이는 성공 재채점이 아닌 별도 위치 진단이다.
- `independent.json`은 5,294개 필드를 전체 대조해 `differences=[]`를 기록했다. `completion.json`이 결속한 결과 3파일 해시도 모두 현재 파일과 일치했다.
- 일반검증 로그는 원본과 fresh 해제본에서 각각 10 tests 통과, Windows offline launcher 통과를 기록한다. 정상, partial missingness, schema/parse/논리 실패, semantic tampering, duplicate key/NaN/형 경계, 입력 재해시, 기존 출력 보존 반례가 포함된다.
- manifest 369개 파일과 ZIP 370개 엔트리를 검사했다. 중복·위험 경로·manifest 해시 오류·fresh 해제본 차이는 모두 0이었다. v063 실행 경로에는 네트워크나 새 LLM 추론 호출이 없다.
- 분석 문서는 측정·구성타당성, 인과·통계·연구방향, 구현계약·재현성의 세 역할을 구분하고 초기 주장, X1~X3 교차검토, `ancestor_only_D` 철회, 근거, 후속 holdout 방향과 관측 한계를 기록한다.

진단 finding `D001`: fresh 해제본에서 배포 빌더를 다시 실행하면 370개 엔트리 내용과 전체 길이는 동일했지만 ZIP SHA256은 `3c217a73e3fa296af41cb6d07fd848dc3a509865a3f71052b5d9b6a6a94983d`였다. 370개 엔트리 timestamp가 빌드 시각으로 달라진 것이 원인이다. 추출 소스와 manifest 재현성, 현재 candidate의 봉인 검증은 충족하므로 차단하지 않는다. 향후 release에서 고정 timestamp와 정규화된 ZIP metadata를 사용하면 봉인 archive 바이트도 재생성할 수 있다. 이번 candidate는 다시 만들거나 수정하면 안 된다.

남은 한계는 `cooperative-sealed`가 같은 사용자 권한의 악의적 writer를 방어하지 않는다는 점, 외부 실행 인증이 아니라 내부 원자료 일관성 감사라는 점, 한 모델 digest·한 문제·반복 seed만 관측했다는 점이다. 패널에 요청한 model/reasoning 실제 적용값도 생성 도구가 반환하지 않아 미확인이다.

구조화된 명령·결과와 finding 필드는 `source_audit_result.json`에 보존했다.
