"""8회 분리 교정 실험. 본 ADM 실험과 분모·성과를 혼합하지 않는다.

증명 생성, 주어진 증명의 도식화, 주어진 기록의 검토, 수락 기준 비교를 분리한다.
고정 입력을 제공한 과제에서 모델이 그 증명 자체를 생성했다고 주장하지 않는다.
"""
from __future__ import annotations

import copy
from typing import Any

from .common import digest, require, wire_json
from .design import reference_depths
from .protocol import BOOL, STRING, array, obj, validate_schema
from .protocol_v2 import PROOF_SCHEMA, VIEWS_SCHEMA, proof_only_trace, view_to_core

CAL_PROBLEM = {
    "id": "calibration_only", "facts": ["CalStart"],
    "rules": [
        {"id": "cal_fast", "premises": ["CalStart"], "conclusion": "CalGoal"},
        {"id": "cal_first", "premises": ["CalStart"], "conclusion": "CalMid"},
        {"id": "cal_last", "premises": ["CalMid"], "conclusion": "CalGoal"}],
    "goal": "CalGoal",
}
CAL_PROOF = {
    "nodes": [
        {"node_id": "n0", "atom": "CalStart", "rule_id": None, "parent_node_ids": []},
        {"node_id": "n1", "atom": "CalMid", "rule_id": "cal_first", "parent_node_ids": ["n0"]},
        {"node_id": "n2", "atom": "CalGoal", "rule_id": "cal_last", "parent_node_ids": ["n1"]}],
    "selected_final_node_id": "n2",
}
REVIEW_SCHEMA = obj({"checked_node_ids": array(STRING, 1), "support_valid": BOOL,
                     "goal_match": BOOL, "proof_and_goal_accepts": BOOL})
CRITERION_SCHEMA = obj({"answer_only_accepts": BOOL, "proof_and_goal_accepts": BOOL,
                        "gap_detected": BOOL})


def build_calibration_plan(core: Any, seed: int = 1729) -> dict:
    require(type(seed) is int and 0 <= seed < 2**31 - 1000, "시드 범위 오류")
    problem = copy.deepcopy(CAL_PROBLEM)
    fact_goal = copy.deepcopy(problem)
    fact_goal["id"] = "calibration_goal_given"
    fact_goal["facts"].append(problem["goal"])
    for p in (problem, fact_goal):
        core.check_problem(p)
    bad = copy.deepcopy(CAL_PROOF)
    bad["nodes"][1]["parent_node_ids"] = []
    tasks = [
        ("proof_shallow", "proof", problem, {"depth_policy": "shallow"}),
        ("proof_deep", "proof", problem, {"depth_policy": "deep"}),
        ("schema_on_fixed_proof", "schema", problem, {"provided_proof": copy.deepcopy(CAL_PROOF)}),
        ("review_valid_proof", "review", problem, {"provided_proof": copy.deepcopy(CAL_PROOF)}),
        ("review_invalid_proof", "review", problem, {"provided_proof": bad}),
        ("criterion_unsupported_goal", "criterion", problem, {"probe_atom": problem["goal"]}),
        ("criterion_non_goal_fact", "criterion", problem, {"probe_atom": problem["facts"][0]}),
        ("criterion_supported_goal", "criterion", fact_goal, {"probe_atom": fact_goal["goal"]}),
    ]
    cases = []
    for name, task, p, extra in tasks:
        case = {"problem_id": p["id"], "problem_sha256": core.digest(p),
                "role": {"kind": "neutral", "A": None, "D_policy": None, "M": None},
                "role_id": name, "repeat": 0, "seed": seed, "task": task, **extra}
        case["case_id"] = digest(case)[:24]
        cases.append(case)
    return {"profile": "calibrate", "experiment_kind": "calibration", "repeats": 1, "seed": seed,
            "problems": [problem, fact_goal], "roles": [], "cases": cases, "assigned_calls": len(cases),
            "reference_depths": {p["id"]: reference_depths(p) for p in (problem, fact_goal)},
            "warnings": [], "scope": "calibration_only_not_joint_ADM_measurement"}


def output_schema(case: dict) -> dict:
    return copy.deepcopy({"proof": PROOF_SCHEMA, "schema": VIEWS_SCHEMA,
                          "review": REVIEW_SCHEMA, "criterion": CRITERION_SCHEMA}[case["task"]])


def messages(problem: dict, case: dict) -> list[dict]:
    task = case["task"]
    header = "외부 지식 없이 주어진 유한 명제 과제를 수행하라. JSON 객체 하나만 출력한다.\n"
    details = "문제: " + wire_json(problem)
    if task == "proof":
        header += ("증명 하나의 nodes와 selected_final_node_id만 작성한다. view/review는 작성하지 않는다.\n"
                   "node_id는 n0,n1처럼 만들고 atom/규칙명과 혼동하지 마라. parent_node_ids와\n"
                   "selected_final_node_id는 이미 만든 node_id만 가리킨다. 부모를 먼저 출력한다.\n"
                   "사실은 rule_id=null, parent_node_ids=[]. 규칙은 모든 전제를 정확히 인용한다.\n"
                   "모든 가능한 규칙을 나열하지 않는다. 선택한 최종 노드의 지지 조상만 출력한다.\n"
                   "사실은 깊이 0, 규칙은 1+max(부모 깊이). 같은 원자의 지지 경로 내 반복은 금지한다.\n")
        details += ("\n유효한 증명 중 최종 지지 깊이가 "
                    + ("가장 작은" if case["depth_policy"] == "shallow" else "가장 큰")
                    + " 경로 하나를 선택하라.")
    elif task == "schema":
        header += ("증명은 입력으로 고정되어 있다. 그 증명을 생성하거나 수정하는 과제가 아니다.\n"
                   "모든 노드에 universal_schema view를 작성한다. 사실 노드도 예외가 아니다.\n"
                   "각 노드와 그 지지 조상 전체의 원자를 bindings의 {variable,atom} 목록으로\n"
                   "일대일 대응한다. clauses에는 그 부분 증명의 모든 사실(if=[])과 사용 규칙을\n"
                   "변수로 치환해 한 번씩 담는다. conclusion_var는 해당 노드 원자의 변수다.\n"
                   "quantifier=forall_boolean_valuations. 바인딩은 비울 수 없다.\n")
        details += "\n고정 증명: " + wire_json(case["provided_proof"])
    elif task == "review":
        header += ("입력 증명을 고치지 말고 재검사하라. checked_node_ids에는 모든 노드 ID를 한 번씩 쓴다.\n"
                   "support_valid는 사실 출처·규칙/전제 일치·부모 참조·순서·최종 지지 연결성이\n"
                   "모두 맞는지다. goal_match는 선택된 최종 노드의 atom==goal 여부다.\n"
                   "proof_and_goal_accepts는 두 조건이 모두 참일 때만 참이다.\n")
        details += "\n검토할 증명: " + wire_json(case["provided_proof"])
    else:
        header += ("두 수락 기준을 각각 계산한다. answer_only_accepts는 오직 probe.atom==goal이다.\n"
                   "proof_and_goal_accepts는 목표 일치와 유효한 증명을 모두 요구한다.\n"
                   "이번 probe는 rule=null,parents=[]인 단독 사실 주장이다. 따라서 probe.atom이\n"
                   "원문 facts에 들어 있어야 유효한 증명이다. gap_detected는 두 판정이 다른지다.\n")
        details += "\nprobe: " + wire_json({"atom": case["probe_atom"], "rule": None, "parents": []})
    details += "\n출력 형식: " + wire_json(output_schema(case))
    return [{"role": "system", "content": header}, {"role": "user", "content": details}]


def _supplied_support(core: Any, problem: dict, supplied: dict) -> tuple[dict, bool, bool]:
    trace = proof_only_trace(core, problem, supplied)
    lookup = {n["id"]: n for n in trace["nodes"]}
    final = lookup.get(trace["final"])
    goal_match = final is not None and final["atom"] == problem["goal"]
    # 목표 비교와 독립적으로 support를 검사하기 위해 최종 원자를 진단용 목표로 삼는다.
    # 공급된 기록의 규칙/부모/사실은 변경하지 않는다.
    diagnostic_problem = copy.deepcopy(problem)
    if final is not None:
        diagnostic_problem["goal"] = final["atom"]
    diagnostic_trace = copy.deepcopy(trace)
    diagnostic_trace["problem_sha256"] = core.digest(diagnostic_problem)
    support_valid = bool(final is not None and core.verify(diagnostic_problem, diagnostic_trace)["valid"])
    return trace, support_valid, goal_match


def assess_payload(core: Any, problem: dict, case: dict, payload: dict) -> dict:
    validate_schema(payload, output_schema(case))
    task = case["task"]
    checks: dict = {}
    details: dict = {}
    comparisons: list[dict] = []
    if task == "proof":
        from .audit import simple_paths
        trace = proof_only_trace(core, problem, payload)
        verified = core.verify(problem, trace)
        ref = reference_depths(problem)
        target = ref["minimum" if case["depth_policy"] == "shallow" else "maximum"]
        checks = {"valid_proof": verified["valid"],
                  "requested_depth": verified["valid"] and verified["metrics"]["D"] == target,
                  "simple_paths": simple_paths(problem, trace) if verified["valid"] else False}
        from .diagnostics import raw_diagnostics
        diagnostic = raw_diagnostics(problem, wire_json(payload), v2=True)
        # bare proof에는 view가 없으므로 통합 스키마 검사 결과는 진단에서 제외한다.
        selection = {key: diagnostic.get(key) for key in
                     ("all_local_steps_valid", "selected_component_depth", "all_nodes_in_selected_component",
                      "unrelated_node_ids", "final_reference_exists", "selected_component_support_valid",
                      "selected_component_depth_if_grounded", "first_invalid_step", "unrelated_node_ids_independent")}
        selection["selected_component_depth_matches_target"] = diagnostic.get("selected_component_depth") == target
        selection["note"] = "선택 연결부의 깊이만 관측. 무관한 노드를 제거하거나 전체 증명을 성공으로 바꾸지 않음"
        comparisons = [{"field": "valid_proof", "actual": verified["valid"], "expected": True,
                        "matches": checks["valid_proof"]},
                       {"field": "D_on_valid_full_proof", "actual": verified["metrics"].get("D") if verified["valid"] else None,
                        "expected": target, "matches": checks["requested_depth"]},
                       {"field": "simple_paths_on_valid_full_proof", "actual": checks["simple_paths"] if verified["valid"] else None,
                        "expected": True, "matches": checks["simple_paths"]}]
        details = {"core_audit": verified, "D_target": target, "selection_diagnostic": selection,
                   "host_supplied": "진단용 instance view와 빈 reviews만 부착. A/M은 측정하지 않음"}
    elif task == "schema":
        trace = proof_only_trace(core, problem, case["provided_proof"])
        items = payload["node_views"]
        keys = [item["node_id"] for item in items]
        require(len(keys) == len(set(keys)), "교정: 중복 view 노드 id")
        trace["views"] = {item["node_id"]: view_to_core(item["view"]) for item in items}
        verified = core.verify(problem, trace)
        checks = {"valid_schema_views": verified["valid"],
                  "all_schema": verified["valid"] and bool(items) and
                                all(item["view"]["kind"] == "universal_schema" for item in items)}
        comparisons = [{"field": "valid_schema_views", "actual": verified["valid"], "expected": True,
                        "matches": checks["valid_schema_views"]},
                       {"field": "A_on_valid_representation", "actual": verified["metrics"].get("A") if verified["valid"] else None,
                        "expected": "schema", "matches": bool(verified["valid"] and verified["metrics"].get("A") == "schema")}]
        comparisons.append({"field": "all_node_view_kinds", "actual": [item["view"]["kind"] for item in items],
                            "expected": ["universal_schema"] * len(trace["nodes"]),
                            "matches": [item["view"]["kind"] for item in items] == ["universal_schema"] * len(trace["nodes"])})
        details = {"core_audit": verified, "view_kinds_returned": [item["view"]["kind"] for item in items],
                   "host_supplied": "문제와 전체 증명을 고정 입력으로 제공"}
    elif task == "review":
        trace, support_valid, goal_match = _supplied_support(core, problem, case["provided_proof"])
        expected = {"support_valid": support_valid, "goal_match": goal_match,
                    "proof_and_goal_accepts": support_valid and goal_match}
        ids = payload["checked_node_ids"]
        checks = {k: payload[k] is v for k, v in expected.items()}
        checks["complete_evidence"] = len(ids) == len(set(ids)) and set(ids) == {n["id"] for n in trace["nodes"]}
        comparisons = [{"field": key, "actual": payload[key], "expected": value, "matches": checks[key]}
                       for key, value in expected.items()]
        comparisons.append({"field": "checked_node_ids", "actual": ids,
                            "expected": [n["id"] for n in trace["nodes"]],
                            "matches": checks["complete_evidence"]})
        details = {"actual": copy.deepcopy(payload), "expected": expected,
                   "host_supplied": "유효/손상된 증명 입력. 모델에 판정 정답은 미제공"}
    else:
        atom = case["probe_atom"]
        answer = atom == problem["goal"]
        proof = answer and atom in problem["facts"]
        expected = {"answer_only_accepts": answer, "proof_and_goal_accepts": proof,
                    "gap_detected": answer != proof}
        checks = {key: payload[key] is value for key, value in expected.items()}
        comparisons = [{"field": key, "actual": payload[key], "expected": value, "matches": checks[key]}
                       for key, value in expected.items()]
        details = {"actual": copy.deepcopy(payload), "expected": expected,
                   "host_supplied": "시험 probe. 모델에 판정 정답은 미제공"}
    valid = all(checks.values())
    return {"valid_completion": valid, "role_adherent": None,
            "calibration_task": task, "task_checks": checks, "details": details,
            "task_comparisons": comparisons,
            "task_checks_note": "task_checks의 true/false는 정답과 일치 여부다. 모델이 출력한 판정값이 아님.",
            "negative_controls": [], "negative_controls_ok": None,
            "interpretation": "단독 교정 과제의 성공 여부. 통합 ADM 성공·축 독립성 결과가 아님."}
