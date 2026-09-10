"""A/D/M을 분리해 설명한다. 현재 평가 문제의 답을 생성/삽입하지 않는다.

factorized-v4와 definitions-v4는 예시 유무만 다른 대응 프로필이다.
증명 예시는 D만, 동일 고정 증명의 표현 대안은 A만, 검토 종류는 M만 설명한다.
"""
from __future__ import annotations

import copy

from .common import wire_json
from .prompts_v2 import DEMO_PROBLEM, DEMO_INSTANCE, DEMO_SCHEMA, SYSTEM_PROMPT, role_text
from .protocol_v2 import TRANSPORT_SCHEMA
from . import calibration_v4

PROFILES = {"factorized-v4", "definitions-v4"}
BASE = SYSTEM_PROMPT.replace(
    "내부 사고 독백·설명문·마크다운은 출력하지 않는다. 정답 인증서를 작성하는 과제다.",
    "최종 응답(message.content)은 JSON 인증서 하나다. thinking 채널 사용 여부는 실행 모드를 따른다. "
    "최종 응답에는 설명문이나 마크다운을 넣지 않는다.")
SEPARATION = """
A, D, M은 서로 다른 출력 요구다.
A는 같은 증명의 표현만 바꾼다. schema라는 이유로 긴 증명을 고르지 않는다.
D는 선택한 증명 DAG의 최대 의존 깊이만 바꾼다. 출력 글자 수나 검토 개수가 아니다.
M0는 검토 없음, M1은 argument 한 개, M2는 argument와 acceptance_criterion 각 한 개다.
M2를 M1 하나로 대신하지 않는다. 판단값이 같아 보이더라도 검토 종류를 생략하지 않는다.
각 필드는 이번 입력으로 다시 계산한다. 형식 예시의 결과/원자/규칙을 복사하지 않는다.
목표를 고정한다는 말은 목표를 처음부터 사실로 추가해도 된다는 뜻이 아니다.
M2의 probe는 원래 증명과 다른 단독 주장이다. 본 증명의 유효성과 혼동하지 않는다.
단독 사실 probe의 정의:
 answer_only_accepts := (probe.atom == problem.goal)
 proof_and_goal_accepts := answer_only_accepts AND (probe.atom IN problem.facts)
 gap_detected := (answer_only_accepts != proof_and_goal_accepts)
위 식은 판정의 의미 정의다. 실제 입력의 답은 제공하지 않았다.
"""


def examples(task: str | None = None) -> str:
    def bare(payload: dict) -> dict:
        return {"nodes": [{k: copy.deepcopy(v) for k, v in n.items() if k != "view"}
                           for n in payload["nodes"]],
                "selected_final_node_id": payload["selected_final_node_id"]}
    blocks = ["\n설명용 고정 문제(평가 문제 아님): " + wire_json(DEMO_PROBLEM)]
    if task in {None, "proof"}:
        blocks += ["\nD만 설명하는 두 증명(표현·검토는 여기서 미지정): " + wire_json({
            "shallow_proof_only": bare(DEMO_INSTANCE), "deep_proof_only": bare(DEMO_SCHEMA)})]
    if task in {None, "schema"}:
        alternatives = [{"node_id": n["node_id"],
                         "instance_alternative": {"kind": "instance", "atom": n["atom"]},
                         "schema_alternative": copy.deepcopy(n["view"])} for n in DEMO_SCHEMA["nodes"]]
        blocks += ["\nA만 설명하는 고정 증명: " + wire_json(bare(DEMO_SCHEMA)),
                   "\n이 고정 증명의 각 노드는 양쪽 표현 모두 가능하다: " + wire_json(alternatives)]
    if task in {None, "review"}:
        # 완성된 A/D/M 조합이 아니라 같은 주어진 증명에 필요한 검토 구조만 보여준다.
        blocks += ["\nM 설명용 고정 증명: " + wire_json(bare(DEMO_SCHEMA)),
                   "\nM0=[]; M1=아래 첫 항목만; M2=아래 두 항목. 입력에 따라 판정값은 달라진다: "
                   + wire_json(DEMO_SCHEMA["verification_reviews"])]
    if task == "criterion":
        # 동일 정답 복사를 막기 위해 이 과제에는 예시 판정값을 주지 않는다.
        return ""
    return "".join(blocks) + "\n"


def messages(problem: dict, role: dict, profile: str = "factorized-v4") -> list[dict]:
    system = BASE + SEPARATION
    if profile == "factorized-v4":
        system += examples()
    return [{"role": "system", "content": system},
            {"role": "user", "content": "평가할 원문 문제:\n" + wire_json(problem)
             + "\n이번 출력 역할:\n" + role_text(role)
             + "\n모든 역할 공통 출력 형식:\n" + wire_json(TRANSPORT_SCHEMA)}]


def calibration_messages(problem: dict, case: dict, profile: str = "factorized-v4") -> list[dict]:
    result = calibration_v4.messages(problem, case)
    result[0]["content"] = ("최종 응답(message.content)에는 요청된 JSON 객체 하나만 쓴다. "
                             "thinking 채널 사용 여부는 실행 모드를 따른다.\n" + result[0]["content"])
    if case["task"] == "proof":
        result[0]["content"] += ("선택할 증명 하나를 정한 뒤 그 지지 조상만 출력한다. "
                                 "대안 경로를 남기지 않는다.\n")
    if profile == "factorized-v4":
        result[0]["content"] += examples(case["task"])
    result[0]["content"] += "\n설명용 예시가 아니라 user의 현재 입력만 평가한다. 현재 과제 스키마 외 필드를 추가하지 않는다.\n"
    return result
