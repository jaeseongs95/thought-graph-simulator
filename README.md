# 고정 결과 A/D/M 역할극 최소 실험계

동일한 문제·목표 아래에서 **표현의 구체성/일반화(A), 실제 지지 깊이(D), 검토 대상(M)**을 달리하는 경로를 만들고 다시 검사합니다. LLM 호출, 모델 다운로드, GPU 코드, 네트워크 통신, 외부 패키지 의존성은 없습니다.

## 실행

Python 3.10 이상을 대상으로 작성했습니다. 실제 실행은 Linux / Python 3.13.5에서 확인했으며 Windows 런타임에서 직접 시험하지는 않았습니다. 압축 해제한 폴더에서 실행합니다. `pip install` 단계는 없습니다.

```powershell
python adm_minimal.py run
python -m unittest discover -s tests -v
```

`python` 명령 대신 Windows Python 런처를 사용하는 환경에서는 `py -3`으로 바꿉니다. 원래 결과를 보존하려면 `python adm_minimal.py run --out results_local`을 사용합니다.

## 무엇을 구현했는가

`adm_minimal.py` 한 파일이 실행 코드입니다. 같은 사실·규칙 안에 직접 경로와 합성 경로가 있는 형식 명제 문제를 사용합니다. 예를 들어 목표 g에 도달하는 `p -> g`와 `p -> q -> r -> g`를 다른 역할로 실행합니다.

A는 `instance`와 `schema`를 구분합니다. 도식은 단순 변수명 변경이 아니라 보편 양화된 명제 도식이며, 원문 문제에 대한 치환과 모든 진리값 배정에서의 타당성을 검사합니다. 이 두 범주를 논문의 A0~A4 번호와 임의로 대응시키지 않습니다.

D는 `parents`를 따라 사실 0, 규칙 적용 `1 + max(부모 깊이)`로 다시 계산합니다. `shallow`·`deep`은 생성 정책이고 D 자체는 관측값입니다. M0는 문제 도출, M1은 논증의 지지 검토, M2는 평가 기준의 적합성 검토입니다.

고정 목표를 답에 덧붙이는 구현이 아닙니다. 근거 없이 목표를 주장하거나 주어진 규칙으로 목표에 도달할 수 없으면 실패합니다. M2에서는 바로 이 무근거 목표를 시험하여 정답 일치만 보는 평가 기준의 한계를 검사합니다.

## 결과 확인

| 항목 | 실행 결과 |
| --- | --- |
| 기본 역할 조건 | 36 / 36 유효 |
| 조건별 정확한 재생성 | 36 / 36 동일 |
| 한 축씩 바꾸는 대조 | 60 / 60 통과 |
| 손상 기록 | 42 / 42 거부 |
| 단위시험 | 39 / 39 통과 |

`results/summary.json`이 요약, `results/runs.json`이 전체 기록입니다. `metrics.csv`는 UTF-8 BOM을 포함합니다. `negative_controls.json`에는 각 손상 사례와 거부 이유가 남습니다. 단위시험 내부에는 40개 고정 시드 생성 문제 × 12조건 = 480건의 추가 검사도 포함되어 있으며, 이를 별도의 독립 실험으로 계산하지 않습니다.

이 결과는 **구성한 형식 언어에서 역할 정책·좌표 측정·검증기가 작동한다는 명세/소프트웨어 검증 결과**입니다. 실제 LLM의 추론 특성·정답률·비용 효과는 이번에 측정하지 않았습니다.

## 개별 기록 검사

```powershell
python adm_minimal.py verify --trace examples/valid_trace.json
python adm_minimal.py verify --trace examples/invalid_fixed_goal_trace.json
```

두 번째 파일은 최종 목표가 그대로여도 증명 근거를 제거한 기록입니다. 거부되고 종료 코드 1을 반환하는 것이 정상입니다. 정상 종료·승인은 0, 검사 실패는 1, 파일/입력/명령행 오류는 2입니다.

직접 작성한 단일 trace JSON도 `verify --trace 파일경로`로 검사할 수 있습니다. 대응하는 원문 문제는 `--problems`로 별도 지정합니다. 문제 해시를 trace와 함께 바꾸는 것은 신뢰 기반을 새로 만드는 것이지, 기존 문제에 대한 검증을 통과하는 것이 아닙니다.

## Python에서 사용

```python
from pathlib import Path
from adm_minimal import load_problems, simulate, verify

problem = load_problems(Path("examples/problems.json"))[1]
trace = simulate(problem, a="schema", d="deep", m=2)
audit = verify(problem, trace)
assert audit["valid"], audit["error"]
print(audit["metrics"])  # {'A': 'schema', 'D': 3, 'M': 2}
```

이는 로컬 규칙 실행입니다. 모델 호출용 어댑터나 미구현 스텁이 아닙니다.

## 파일 안내

```text
adm_minimal.py                  실행 코드: 생성 / 재검사 / 실험 / CLI
README.md                       실행 안내
examples/problems.json          3개 고정 문제
examples/valid_trace.json       정상 기록
examples/invalid_fixed_goal_trace.json  목표는 같고 근거는 없는 기록
examples/*_audit.json           위 기록의 실제 검사 결과
tests/test_adm.py               단위시험 39개
results/                       실제 실행 결과와 로그
docs/research_note.md           대화 전체 분석·명세·연구자료
docs/research_note.docx         동일 연구자료의 편집용 문서
docs/research_note.pdf          동일 연구자료의 열람용 문서
MANIFEST.sha256                 배포 파일 내용의 해시 목록
```

## 설계 경계

생성기는 검증기를 호출하지 않고, 검증기는 생성기의 역할 라벨·경로 점수를 읽지 않습니다. 원문 문제를 기준으로 규칙을 다시 적용하고, 도식은 진리값 배정을 열거해 검사합니다. 이 분리는 제3자 독립 구현이나 외부 심사 완료를 뜻하지 않습니다.

기본 한도는 원자 10개, 규칙 32개, 후보 증명 256개, 노드 128개입니다. 등록되지 않은 필드나 형식은 실패 처리합니다. 자유로운 자연어 A/D/M 분류기, LLM 내부 사고 분석기, 모델 성능 벤치마크는 포함하지 않습니다.

새 문제를 추가할 수 있지만 주 실험의 축별 대조에는 서로 다른 깊이의 유효 경로가 필요합니다. 조건이 맞지 않으면 대조 실패가 보고됩니다. 결과를 좋게 만들기 위해 그 사례를 자동으로 제외하지 않습니다.

문서 작성에 사용한 도구는 실행 코드의 의존성이 아닙니다. PDF/DOCX는 이미 생성되어 있으며, 코드를 실행하려고 문서 생성 도구나 글꼴을 설치할 필요는 없습니다.
