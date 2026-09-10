"""선택형 explicit-v3 프롬프트. 기본 legacy-v2와 다른 실험 조건이다.

전체 예시에서 A/D/M을 한 묶음으로 결합하지 않고 구성요소별 예시를 제공한다.
정답 생성기, 현재 문제의 참조 경로/깊이/판정값은 호출하거나 삽입하지 않는다.
원인 하나만 바꾸는 실험이 아니므로 개선되어도 단일 원인을 입증하지 않는다.
"""
from __future__ import annotations

import copy

from .common import wire_json
from .protocol_v2 import TRANSPORT_SCHEMA
from .prompts_v2 import DEMO_PROBLEM, DEMO_INSTANCE, DEMO_SCHEMA, SYSTEM_PROMPT, role_text

PROFILE = "explicit-v3"


def component_examples() -> str:
    def bare(value: dict) -> dict:
        return {"nodes": [{key: copy.deepcopy(item) for key, item in node.items() if key != "view"}
                           for node in value["nodes"]],
                "selected_final_node_id": value["selected_final_node_id"]}
    proof_examples = {"shallow_proof_only": bare(DEMO_INSTANCE), "deep_proof_only": bare(DEMO_SCHEMA)}
    views = [{"node_id": node["node_id"],
              "instance_alternative": {"kind": "instance", "atom": node["atom"]},
              "schema_alternative": copy.deepcopy(node["view"])} for node in DEMO_SCHEMA["nodes"]]
    return ("\n다음은 현재 평가 문제의 답이 아닌 고정 형식 예시다. 다른 원자 이름을 사용한다.\n"
            "예시 문제: " + wire_json(DEMO_PROBLEM)
            + "\nD 설명용 증명만: " + wire_json(proof_examples)
            + "\nA 설명용 표현만: 위 deep 증명의 각 노드는 다음 두 표현 중 어느 쪽도 가능하다. "
              "schema라고 깊은 경로를 선택해야 하는 것은 아니다.\n" + wire_json(views)
            + "\nM 설명용 검토만: 위 deep 증명에서 M0=[], M1=첫 검토 하나, M2=두 검토다.\n"
            + wire_json(DEMO_SCHEMA["verification_reviews"])
            + "\n위 예시의 필드를 현재 입력에 기계적으로 복사하지 말고 각 값의 의미를 계산한다.\n")


EXPLICIT_INSTRUCTIONS = """
제출 전 구분:
1. 선택한 증명과 탐색 중 발견한 모든 증명은 다르다. 최종 노드에서 parent_node_ids를
   거꾸로 따라갈 수 없는 노드는 제출 대상이 아니다. 최종 노드만 고르고 대안 노드를
   함께 남기면 실패다. 출력할 증명 경로부터 선택하고 그 경로의 노드만 작성한다.
2. 깊이는 출력 길이나 검토 개수가 아니라 지지 규칙의 최대 연쇄 길이다.
   shallow/deep 선택은 A 표현이나 M 검토 개수와 별도로 한다. 표현 예시가 경로를 정하지 않는다.
3. schema의 현재 노드도 bindings에 들어가야 한다. 부모의 schema를 그대로 복사하면 안 된다.
4. M2는 M1의 다른 이름이 아니다. argument 검토 뒤 acceptance_criterion 검토가 있어야 한다.
5. 단독 사실 probe에 대한 정의는 다음과 같다. 새 증명을 찾아 probe를 보충하지 않는다.
   answer_only_accepts := (probe.atom == problem.goal)
   proof_and_goal_accepts := answer_only_accepts AND (probe.atom IN problem.facts)
   gap_detected := (answer_only_accepts != proof_and_goal_accepts)
   이 식은 의미 정의이며 실제 입력에 대한 true/false 정답을 제공한 것이 아니다.
   모델은 세 필드를 각각 계산한다. 본 증명의 유효성과 별도 probe의 유효성을 섞지 않는다.
"""


def messages(problem: dict, role: dict) -> list[dict]:
    return [{"role": "system", "content": SYSTEM_PROMPT + component_examples() + EXPLICIT_INSTRUCTIONS},
            {"role": "user", "content": "평가할 원문 문제:\n" + wire_json(problem)
             + "\n모든 역할 공통 출력 형식:\n" + wire_json(TRANSPORT_SCHEMA)
             + "\n이번 출력에 적용할 조건:\n" + role_text(role)}]


def calibration_messages(problem: dict, case: dict) -> list[dict]:
    from .calibration import messages as legacy_messages
    result = legacy_messages(problem, case)
    result[0]["content"] += component_examples() + EXPLICIT_INSTRUCTIONS
    result[0]["content"] += ("\n현재 과제의 출력 스키마만 따른다. 구성요소 예시는 형식 설명이다. "
                             "증명 단독 과제에는 view/review를 추가하지 않는다. "
                             "검토/기준 비교 과제에서는 새 증명을 생성하지 않는다.\n")
    return result
