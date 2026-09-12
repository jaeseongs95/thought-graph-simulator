"""공통 형식 예시 두 개를 제공하는 v2 프롬프트. 실험 문제의 정답을 제공하지 않는다."""
from __future__ import annotations

import copy

from .common import wire_json
from .prompts import role_instruction
from .protocol_v2 import TRANSPORT_SCHEMA

# 설명용 문제는 평가 문제·교정 문제와 다른 원자명/규칙명을 쓴다.
DEMO_PROBLEM = {
    "id": "format_demo_only", "facts": ["DemoStart"],
    "rules": [
        {"id": "demo_shortcut", "premises": ["DemoStart"], "conclusion": "DemoGoal"},
        {"id": "demo_first", "premises": ["DemoStart"], "conclusion": "DemoMiddle"},
        {"id": "demo_second", "premises": ["DemoMiddle"], "conclusion": "DemoGoal"}],
    "goal": "DemoGoal",
}
DEMO_INSTANCE = {
    "nodes": [
        {"node_id": "n0", "atom": "DemoStart", "rule_id": None, "parent_node_ids": [],
         "view": {"kind": "instance", "atom": "DemoStart"}},
        {"node_id": "n1", "atom": "DemoGoal", "rule_id": "demo_shortcut", "parent_node_ids": ["n0"],
         "view": {"kind": "instance", "atom": "DemoGoal"}}],
    "selected_final_node_id": "n1", "verification_reviews": [],
}
# 예시의 바인딩·절은 상수로 명시한다. 실제 평가 문제에 대해 도식을 만들어 주는 함수가 아니다.
DEMO_SCHEMA = {
    "nodes": [
        {"node_id": "n0", "atom": "DemoStart", "rule_id": None, "parent_node_ids": [],
         "view": {"kind": "universal_schema", "quantifier": "forall_boolean_valuations",
                  "bindings": [{"variable": "X", "atom": "DemoStart"}],
                  "clauses": [{"if": [], "then": "X"}], "conclusion_var": "X"}},
        {"node_id": "n1", "atom": "DemoMiddle", "rule_id": "demo_first", "parent_node_ids": ["n0"],
         "view": {"kind": "universal_schema", "quantifier": "forall_boolean_valuations",
                  "bindings": [{"variable": "X", "atom": "DemoStart"},
                               {"variable": "Y", "atom": "DemoMiddle"}],
                  "clauses": [{"if": [], "then": "X"}, {"if": ["X"], "then": "Y"}],
                  "conclusion_var": "Y"}},
        {"node_id": "n2", "atom": "DemoGoal", "rule_id": "demo_second", "parent_node_ids": ["n1"],
         "view": {"kind": "universal_schema", "quantifier": "forall_boolean_valuations",
                  "bindings": [{"variable": "X", "atom": "DemoStart"},
                               {"variable": "Y", "atom": "DemoMiddle"},
                               {"variable": "Z", "atom": "DemoGoal"}],
                  "clauses": [{"if": [], "then": "X"}, {"if": ["X"], "then": "Y"},
                              {"if": ["Y"], "then": "Z"}], "conclusion_var": "Z"}}],
    "selected_final_node_id": "n2",
    "verification_reviews": [
        {"id": "review1", "target_kind": "argument", "target_node_id": "n2",
         "check": "support_replay", "evidence_node_ids": ["n0", "n1", "n2"],
         "finding": {"grounded": True, "used_rules": ["demo_first", "demo_second"],
                     "conclusion": "DemoGoal"}},
        {"id": "review2", "target_kind": "acceptance_criterion", "target": "valid_proof_and_goal",
         "check": "counterexample_probe", "probe": {"atom": "DemoGoal", "rule": None, "parents": []},
         "finding": {"answer_only_accepts": True, "proof_and_goal_accepts": False,
                     "gap_detected": True}}],
}

SYSTEM_PROMPT = """주어진 사실과 규칙으로 고정 목표를 증명하는 JSON 인증서 하나를 작성한다.
내부 사고 독백·설명문·마크다운은 출력하지 않는다. 정답 인증서를 작성하는 과제다.

가장 중요한 계약:
- 가능한 모든 규칙/경로를 나열하는 과제가 아니다. 이번 역할에 맞는 증명 하나를 선택한다.
  선택한 최종 노드와 그 지지 조상만 nodes에 넣는다. 대안 경로는 함께 넣지 않는다.
- atom은 명제 이름, rule_id는 입력 규칙 이름, node_id는 출력 노드 식별자다.
  node_id는 n0,n1,n2처럼 만들고 parent_node_ids/selected_final_node_id에는 노드 ID만 쓴다.
  예: atom=DemoGoal인 노드 ID가 n1이면 selected_final_node_id=n1이지 DemoGoal이 아니다.
- 부모를 먼저 출력한다. 사실은 rule_id=null, parent_node_ids=[]이며 facts에 있어야 한다.
  규칙 노드는 해당 규칙의 모든 전제를 정확히 부모로 인용한다. 규칙을 새로 만들지 않는다.
  같은 명제가 한 지지 경로에 재등장하거나 주어진 사실을 규칙으로 다시 도출하면 안 된다.
- instance view는 해당 원자를 기록한다. universal_schema view는 현재 노드뿐 아니라
  모든 지지 조상의 원자도 bindings에 일대일 대응한다. 사실 노드도 schema 역할이면
  universal_schema여야 한다. 빈 bindings는 안 된다.
  clauses에는 그 부분 증명에서 사용한 모든 사실(if=[])과 모든 규칙을 변수로 치환해
  각각 한 번씩 넣는다. 한 단계 규칙만 적거나 결론을 새 사실로 추가하면 안 된다.
  conclusion_var는 현재 노드의 atom에 대응하는 변수다. 절들에서 결론이 함의되어야 한다.
- verification_reviews의 argument 검토는 selected_final_node_id를 대상으로 한다.
  evidence_node_ids는 해당 지지 조상과 최종 노드 전체다. used_rules는 실제 사용 규칙만
  중복 없이 정렬한다. 후보였지만 선택하지 않은 규칙은 검토 근거에도 넣지 않는다.
- acceptance_criterion의 answer_only_accepts는 오직 probe.atom==goal이다.
  proof_and_goal_accepts는 그에 더해 probe가 유효한 증명이어야 한다.
  rule=null,parents=[]인 단독 probe는 그 atom이 facts에 있어야 유효하다.
  gap_detected는 두 판정의 불일치다. 단순 문자열 일치 기준에 근거 검사를 섞지 않는다.
- A/D/M 점수나 요청 라벨을 출력하지 않는다. D는 사실=0, 규칙=1+max(부모 깊이)다.
"""


def role_text(role: dict) -> str:
    return (role_instruction(role).replace("reviews", "verification_reviews")
            .replace("final", "selected_final_node_id"))


def common_instructions(include_examples: bool = True) -> str:
    text = SYSTEM_PROMPT
    if include_examples:
        text += ("\n아래는 원자·규칙 이름이 다른 공통 형식 예시다. 구조는 일부 평가 과제와 유사하며 모든 역할에 같은 예시를 제공한다.\n"
                 + "예시 문제: " + wire_json(DEMO_PROBLEM)
                 + "\n사례 표현·얕은 경로·검토 없음: " + wire_json(DEMO_INSTANCE)
                 + "\n보편 도식·깊은 경로·두 검토: " + wire_json(DEMO_SCHEMA)
                 + "\n현재 문제에서는 예시의 원자·규칙을 복사하지 않는다.\n")
    return text


def messages(problem: dict, role: dict) -> list[dict]:
    return [{"role": "system", "content": common_instructions()},
            {"role": "user", "content": "평가할 원문 문제:\n" + wire_json(problem)
             + "\n\n" + role_text(role) + "\n\n모든 역할 공통 출력 형식:\n"
             + wire_json(TRANSPORT_SCHEMA)}]
