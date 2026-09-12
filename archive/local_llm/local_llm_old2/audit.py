"""기존 verify()를 재사용하되 형식·증명·표현·검토·역할 준수를 분리한다."""
from __future__ import annotations

import copy
from typing import Any



def simple_paths(problem: dict, trace: dict) -> bool:
    ancestors: dict[str, set[str]] = {}
    for node in trace["nodes"]:
        parent_atoms: set[str] = set()
        for key in node["parents"]:
            parent_atoms.update(ancestors[key])
        if node["atom"] in parent_atoms:
            return False
        if node["atom"] in problem["facts"] and node["rule"] is not None:
            return False
        ancestors[node["id"]] = parent_atoms | {node["atom"]}
    return True


def negative_controls(core: Any, problem: dict, trace: dict) -> list[dict]:
    """검증기 점검용 변조. 모델의 오류 탐지 능력으로 집계하지 않는다."""
    output = []
    def add(name: str, change) -> None:
        bad = copy.deepcopy(trace)
        change(bad)
        check = core.verify(problem, bad)
        output.append({"name": name, "applicable": True,
                       "rejected": not check["valid"], "error": check.get("error")})
    def final_node(t: dict) -> dict:
        return next(n for n in t["nodes"] if n["id"] == t["final"])
    add("problem_binding", lambda t: t.update(problem_sha256="0" * 64))
    add("self_cycle", lambda t: final_node(t).update(parents=[t["final"]]))
    unknown = "__unknown_rule__"
    while unknown in {r["id"] for r in problem["rules"]}:
        unknown += "_"
    add("unknown_rule", lambda t: final_node(t).update(rule=unknown))
    add("duplicate_node", lambda t: t["nodes"].append(copy.deepcopy(t["nodes"][0])))
    add("missing_view", lambda t: t["views"].pop(t["final"]))
    add("injected_coordinate", lambda t: t.update(A=4, D=99, M=2))
    if problem["goal"] not in problem["facts"]:
        add("ungrounded_fixed_goal", lambda t: final_node(t).update(rule=None, parents=[]))
    else:
        output.append({"name": "ungrounded_fixed_goal", "applicable": False,
                       "rejected": None, "error": "목표 자체가 주어진 사실이므로 이 변조는 반례가 아님"})
    schemas = [key for key, view in trace["views"].items() if view["kind"] == "universal_schema"]
    if schemas:
        add("empty_schema", lambda t: t["views"][schemas[-1]].update(assumptions=[]))
    for index, review in enumerate(trace["reviews"]):
        field = "grounded" if review["target_kind"] == "argument" else "proof_and_goal_accepts"
        def flip(t: dict, idx: int = index, key: str = field) -> None:
            t["reviews"][idx]["finding"][key] = not t["reviews"][idx]["finding"][key]
        add(f"false_review_{index}", flip)
    return output


def evaluate_trace(core: Any, problem: dict, trace: dict, role: dict, reference: dict) -> dict:
    full = core.verify(problem, trace)
    # 아래 사본은 진단에만 쓴다. 원문 trace·최종 full 판정을 교체하지 않는다.
    proof = copy.deepcopy(trace)
    proof["views"] = {n["id"]: {"kind": "instance", "atom": n["atom"]} for n in trace["nodes"]}
    proof["reviews"] = []
    proof_audit = core.verify(problem, proof)
    representation = copy.deepcopy(trace)
    representation["reviews"] = []
    representation_audit = core.verify(problem, representation)
    reviews = copy.deepcopy(proof)
    reviews["reviews"] = copy.deepcopy(trace["reviews"])
    review_audit = core.verify(problem, reviews)
    is_simple = simple_paths(problem, trace) if proof_audit["valid"] else False
    final = next((n for n in trace["nodes"] if n["id"] == trace["final"]), None)
    kinds = [r["target_kind"] for r in trace["reviews"]]
    target_level = max([0] + [1 if kind == "argument" else 2 for kind in kinds])
    observed = {
        "A": representation_audit["metrics"].get("A") if representation_audit["valid"] else None,
        "D": proof_audit["metrics"].get("D") if proof_audit["valid"] else None,
        "M_target": target_level,
    }
    valid = bool(full["valid"] and is_simple)
    matches = {"A": None, "D": None, "M": None}
    d_target = None
    if role["kind"] == "directed":
        kind = "instance" if role["A"] == "instance" else "universal_schema"
        matches["A"] = bool(representation_audit["valid"] and
                            all(v["kind"] == kind for v in trace["views"].values()))
        d_target = reference["minimum" if role["D_policy"] == "shallow" else "maximum"]
        matches["D"] = bool(proof_audit["valid"] and is_simple and d_target is not None
                            and observed["D"] == d_target)
        expected_kinds = {0: [], 1: ["argument"],
                          2: ["argument", "acceptance_criterion"]}[role["M"]]
        arguments_target_final = all(r["target"] == trace["final"] for r in trace["reviews"]
                                     if r["target_kind"] == "argument")
        criteria_probe_goal = all(r["probe"]["atom"] == problem["goal"] for r in trace["reviews"]
                                 if r["target_kind"] == "acceptance_criterion")
        matches["M"] = bool(review_audit["valid"] and kinds == expected_kinds
                            and arguments_target_final and criteria_probe_goal)
    controls = negative_controls(core, problem, trace) if full["valid"] else []
    controls_ok = all(c["rejected"] for c in controls if c["applicable"]) if controls else None
    return {
        "fixed_goal_match": final is not None and final["atom"] == problem["goal"],
        "proof_valid": proof_audit["valid"],
        "representation_assessable": proof_audit["valid"],
        "review_assessable": proof_audit["valid"],
        "representation_valid": representation_audit["valid"] if proof_audit["valid"] else None,
        "review_valid": review_audit["valid"] if proof_audit["valid"] else None,
        "simple_support_paths": is_simple,
        "baseline_trace_valid": full["valid"], "valid_completion": valid,
        "observed": observed, "D_target": d_target, "role_matches": matches,
        "role_adherent": (valid and all(matches.values())) if role["kind"] == "directed" else None,
        "support_graph_sha256": core.digest({"nodes": trace["nodes"], "final": trace["final"]}),
        "audits": {"full": full, "proof_only_diagnostic": proof_audit,
                   "representation_diagnostic": representation_audit,
                   "review_diagnostic": review_audit},
        "negative_controls": controls, "negative_controls_ok": controls_ok,
        "diagnostic_note": "사본의 표현/검토 제거는 실패 층위 진단용이며 원문 복구나 성공 판정에 쓰지 않음",
    }
