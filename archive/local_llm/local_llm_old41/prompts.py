"""모든 조건이 공유하는 과제 설명과 역할 지시. 정답 trace·참조 깊이를 포함하지 않는다."""
from __future__ import annotations

from .common import canonical
from .protocol import TRANSPORT_SCHEMA

SYSTEM_PROMPT = """너는 주어진 유한 명제 문제의 증명 기록을 작성한다.
외부 지식이나 새 규칙을 추가하지 말고 facts와 rules만 사용한다.
완성된 증명 인증서를 JSON 객체 하나로 제출하라. 내부 사고 독백은 요구하지 않는다.
설명문, 마크다운, 주석, 도구 호출은 출력하지 마라.

공통 계약:
1. nodes는 부모가 자식보다 앞서는 순서다. 각 id는 유일하다.
   사실 노드는 facts의 원자, rule=null, parents=[]다.
   규칙 노드는 원래 규칙 id와 결론을 쓰고, parents로 모든 전제를 정확히 인용한다.
   같은 원자가 한 부모 연결 경로에 재등장하지 않아야 한다. 주어진 사실은 사실로 끝낸다.
   final이 가리키는 노드의 atom은 goal이어야 한다. 모든 노드는 final의 지지에 연결되어야 한다.
   목표를 근거 없는 사실로 선언하거나, 부모 생략·복제·순환으로 깊이를 늘리지 마라.
2. 각 노드의 view는 다음 두 방식 중 하나다.
   instance: kind=instance, atom은 해당 노드의 원자.
   universal_schema: 해당 노드와 모든 지지 조상의 사용 원자에 변수들을 일대일 대응시키고,
   binding에 변수명->원자명을 쓴다. quantifier=forall_boolean_valuations.
   assumptions에는 그 부분 증명의 사실을 if=[]인 절로, 사용 규칙을 변수로 치환한 절로
   각각 한 번씩 넣는다. if는 전제 변수 목록, then은 결론 변수다.
   conclusion은 해당 노드 원자에 대응하는 변수다. 가정 추가·삭제·중복은 금지한다.
   변수명 변경뿐 아니라 해당 가정들에서 결론이 모든 불리언 배정에 대해 성립해야 한다.
3. reviews는 선택한 검토를 기록한다. 검토를 추가해도 증명 parents를 늘리지 마라.
   argument 검토: target은 검토 대상 노드 id, check=support_replay.
   evidence는 대상 노드와 모든 지지 조상의 id를 정확히 한 번씩 담는다.
   finding에는 재검사한 grounded, 사용 규칙 id의 중복 없는 정렬 목록 used_rules,
   대상 원자의 conclusion을 적는다.
   acceptance_criterion 검토: target=valid_proof_and_goal, check=counterexample_probe.
   probe는 atom 하나를 rule=null, parents=[]로 주장하는 시험 입력이다.
   finding에는 그 시험 입력을 정답 일치 기준과 증명+목표 기준으로 각각 검사한
   answer_only_accepts, proof_and_goal_accepts, gap_detected를 실제 판정하여 적는다.
   기준 검토는 원래 증명 자체를 바꾸는 것이 아니다.
4. A/D/M 요청 라벨이나 직접 계산한 점수 필드를 출력하지 마라.
   D는 사실 0, 규칙 적용 1+max(부모 D)로 외부에서 다시 측정한다.
   출력 JSON 스키마는 모든 역할에서 동일하다. 스키마에 맞아도 의미가 틀리면 거부된다.
"""


def role_instruction(role: dict) -> str:
    if role["kind"] == "neutral":
        return ("역할 조건: 중립 대조. 표현 방식, 유효한 증명 경로, 검토 여부를 자유롭게 선택하라. "
                "공통 계약에 맞는 기록을 제출하라.")
    a = ("모든 노드를 instance로 표현하라." if role["A"] == "instance" else
         "모든 노드를 universal_schema로 표현하라.")
    d = ("가능한 유효 증명 중 최종 지지 깊이가 가장 작은 경로를 선택하라."
         if role["D_policy"] == "shallow" else
         "가능한 유효 증명 중 최종 지지 깊이가 가장 큰 경로를 선택하라. "
         "무관한 노드나 같은 원자의 반복으로 깊이를 부풀리지 마라.")
    m = {
        0: "검토 없이 증명만 제출하라. reviews는 빈 배열이다.",
        1: "final을 대상으로 argument 검토 한 개를 수행하라.",
        2: ("final의 argument 검토를 수행한 뒤, acceptance_criterion 검토를 한 개 수행하라. "
            "기준 검토에서는 goal을 근거 없는 단독 사실로 주장하는 probe를 사용하고, "
            "두 수락 기준의 판정과 차이를 직접 계산하라."),
    }[role["M"]]
    return f"이번 역할 조건:\nA: {a}\nD 경로 정책: {d}\nM: {m}"


def messages(problem: dict, role: dict) -> list[dict]:
    return [{"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": (
                "고정된 원문 문제:\n" + canonical(problem) + "\n\n" + role_instruction(role)
                + "\n\n모든 조건 공통 출력 스키마:\n" + canonical(TRANSPORT_SCHEMA))}]
