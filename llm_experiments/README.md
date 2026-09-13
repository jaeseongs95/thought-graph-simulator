# LLM 실험 자료

v047 이후의 실험 자료는 버전별로 보관한다. 코드, 사전 계획, 실행 결과를 같은 버전에서 찾을 수 있으며, 완료된 버전의 파일은 새 실험 때문에 수정하지 않는다.

```text
llm_experiments/
├─ legacy/
│  └─ pre_v047/
│     └─ results_llm/
├─ v047/
│  ├─ probe/
│  ├─ experiments/
│  └─ results_llm/
├─ ...
└─ v058/
   ├─ probe/
   ├─ experiments/
   ├─ results_llm/
   ├─ validation/
   └─ releases/
```

- `probe/`: 해당 버전의 코드, 시험, 실행 스크립트와 문서
- `experiments/`: 실행 전에 동결한 계획, baseline ZIP과 preflight 기록
- `results_llm/`: 원문 run, capture, evidence ZIP, 독립 검산과 자동화 로그
- `validation/`, `releases/`: 해당 버전에 실제로 필요한 추가 검증 자료와 배포본

| 버전 | 주제 |
| --- | --- |
| v047 | paired probe |
| v048 | seed probe |
| v049 | expression probe |
| v050 | criterion probe |
| v051 | A/D/M pilot |
| v052 | A/D/M diagnostic |
| v053 | depth probe |
| v054 | order probe |
| v055 | model probe |
| v056 | layout probe |
| v057 | selection probe |
| v058 | order replay |

v047~v057 패키지 안의 README와 동결 자료에는 실행 당시의 `experiments/` 경로가 남아 있을 수 있다. 재현성 증거의 바이트를 보존하기 위해 고치지 않았으며, 현재 위치는 이 문서를 기준으로 찾는다.

같은 이유로 완료된 패키지의 `probe/windows/*.ps1`도 옛 공용 `results_llm/`과 `experiments_vNNN/` 배치를 계산하는 역사적 실행 기록이다. 새 구조에서 그대로 실행하지 말고 해당 `probe/`를 작업 디렉터리로 삼아 Python 모듈 CLI에 현재 버전의 `experiments/`, `results_llm/` 또는 직전 버전 경로를 명시한다. 각 패키지의 `selftest`는 `probe/`에서 그대로 실행할 수 있다.

현재 경로를 직접 지정할 때는 `probe/` 기준으로 자기 버전 계획을 `../experiments/<new_run>.plan.json`, 결과를 `../results_llm/<new_run>`에 둔다. 직전 버전 evidence는 `../../vNNN/results_llm/<bundle>.zip` 형식으로 찾는다. v047의 원자료는 `../../legacy/pre_v047/results_llm/`, v048의 기준 run과 계획은 각각 `../../v047/results_llm/`과 `../../v047/experiments/`에 있다. v055의 capture와 plan도 현재 분류에서는 `../experiments/`에 둔다. 기존 artifact 이름은 재사용하지 않는다.

새 버전은 처음부터 `llm_experiments/vNNN/` 아래에 만든다. 코드는 `probe/`, 계획은 `experiments/`, 실행 결과는 `results_llm/`에 두고 기존 버전이나 같은 이름의 자료를 덮어쓰지 않는다. v047 이전 결과와 당시 소스 위치는 [legacy 안내](legacy/pre_v047/README.md)를 따른다.
