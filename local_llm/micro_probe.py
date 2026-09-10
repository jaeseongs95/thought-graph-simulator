"""v0.4.2: 실패를 더 돌려 세지 않고, 입력 읽기/원자 판정/근거 연결/사실절을 분리한다.

12회: 입력 대조 4, 기준 중간값 4, 전체 증명/고정 경로 연결 2, 최종 도식 2.
--group을 지정하면 해당 묶음만 실행한다. 모델 정답의 자동 보충/수리/재시도 없음.
"""
from __future__ import annotations
import argparse
import copy
import json
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from .common import ContractError, REPO, digest, load_core, require, wire_json, write_json
from .calibration import output_schema as old_schema
from .calibration_v4 import fixtures, assess_payload as old_assess
from .causal_probe import compact_messages
from .design import reference_depths
from .evidence import support
from .protocol import STRING, BOOL, array, obj, validate_schema
from .task_evidence import criterion_evidence

CONTRACT = "micro-v042"
GROUPS = ("control", "criterion", "graph", "schema")
FINDING = obj({"answer_only_accepts": BOOL, "proof_and_goal_accepts": BOOL, "gap_detected": BOOL})


def output_schema(case: dict) -> dict:
    task = case["task"]
    if task == "input_echo":
        return obj({"token": STRING, "flag": BOOL})
    if task == "literal_equality":
        return obj({"equal": BOOL})
    if task == "criterion_witness":
        return obj({"observed": obj({"probe_atom": STRING, "goal_atom": STRING, "facts": array(STRING, 1, 10)}),
                    "primitives": obj({"same_as_goal": BOOL, "in_facts": BOOL}), "finding": FINDING})
    if task == "edge_map":
        return obj({"links": array(obj({"node_id": STRING, "parent_node_ids": array(STRING, 0, 10)}), 1)})
    return old_schema(case)


def build_plan(core: Any, seed: int = 1729, groups: list[str] | None = None,
               format_mode: str = "schema") -> dict:
    require(type(seed) is int and 0 <= seed < 2**31 - 1000, "시드 범위 오류")
    require(format_mode in {"schema", "json", "none"}, "format-mode 오류")
    chosen = groups or list(GROUPS)
    require(bool(chosen) and len(chosen) == len(set(chosen)) and set(chosen) <= set(GROUPS), "group 선택 오류")
    fixed = fixtures(); problems = {p["id"]: copy.deepcopy(p) for p, _ in fixed}
    p0 = problems["K01"]
    given = copy.deepcopy(p0); given["id"] = "K11"; given["facts"].append(given["goal"])
    problems[given["id"]] = given
    cases = []
    def add(name: str, task: str, group: str, p: dict, **extra: Any) -> None:
        if group not in chosen: return
        c = {"problem_id": p["id"], "problem_sha256": core.digest(p),
             "role": {"kind": "neutral", "A": None, "D_policy": None, "M": None},
             "role_id": name, "task": task, "repeat": 0, "seed": seed,
             "calibration_version": 4, "probe_contract": CONTRACT,
             "diagnostic_group": group, "format_mode": format_mode, **extra}
        c["case_id"] = digest(c)[:24]; cases.append(c)
    # 입력복사는 정답을 알려주는 대조다. 추론/ADM 성공률에 포함하지 않는다.
    add("control_echo_1", "input_echo", "control", p0, echo={"token": "NX_47Q", "flag": False})
    add("control_echo_2", "input_echo", "control", p0, echo={"token": "VT_83R", "flag": True})
    add("control_equal", "literal_equality", "control", p0, operands={"left": "Ca", "right": "Ca"})
    add("control_not_equal", "literal_equality", "control", p0, operands={"left": "Ca", "right": "Cc"})
    for label, p, atom in (("goal_not_fact", p0, p0["goal"]), ("fact_not_goal", p0, p0["facts"][0]),
                           ("goal_is_fact", given, given["goal"]), ("neither", p0, "Cz")):
        add("criterion_" + label, "criterion_witness", "criterion", p, probe_atom=atom)
    p3, proof = fixed[2]
    add("graph_K03_full", "proof", "graph", p3, depth_policy="deep")
    skeleton = {"nodes": [{k: copy.deepcopy(v) for k, v in n.items() if k != "parent_node_ids"}
                          for n in proof["nodes"]], "selected_final_node_id": proof["selected_final_node_id"]}
    add("graph_K03_edges", "edge_map", "graph", p3, skeleton=skeleton,
        host_supplied="노드 원자/규칙/최종 선택만 제공. 부모 ID는 제공하지 않음. 계획·D 성과로 세지 않음.")
    for hint in (False, True):
        add("schema_K03_" + ("fact_first" if hint else "explicit_contract"), "schema", "schema", p3,
            view_scope="final_node_only", provided_proof=copy.deepcopy(proof), fact_first=hint)
    random.Random(seed + 420031).shuffle(cases)
    used = {c["problem_id"] for c in cases}; problems = {k: p for k, p in problems.items() if k in used}
    for p in problems.values(): core.check_problem(p)
    return {"profile": "micro-probe", "experiment_kind": "calibration", "probe_contract": CONTRACT,
            "repeats": 1, "seed": seed, "problems": list(problems.values()), "roles": [], "cases": cases,
            "assigned_calls": len(cases), "reference_depths": {k: reference_depths(p) for k, p in problems.items()},
            "warnings": [], "scope": "diagnostic_only_no_combined_ADM_rate", "groups": chosen,
            "design_note": "입력복사·고정 경로 연결은 도움을 제공한 진단이다. 전체 증명/ADM 성공으로 합산하지 않는다. "
                           "format 대조는 메시지에 같은 전체 스키마를 포함하고 format 필드만 변경한다."}


def messages(problem: dict, case: dict) -> list[dict]:
    task = case["task"]
    if task == "input_echo":
        result = [{"role": "system", "content": "입력 전달 대조 검사다. 입력 token 문자열과 flag boolean을 그대로 같은 필드에 복사하라. 해석·변환하지 않는다. JSON 객체 하나만 출력한다."},
                  {"role": "user", "content": wire_json(case["echo"])}]
    elif task == "literal_equality":
        result = [{"role": "system", "content": "left와 right 문자열이 글자까지 정확히 동일하면 equal=true, 다르면 equal=false다. JSON 객체 하나만 출력한다."},
                  {"role": "user", "content": wire_json(case["operands"])}]
    elif task == "criterion_witness":
        result = [{"role": "system", "content": (
            "단독 사실 주장 probe를 검사한다. rules로 새 증명을 만들지 않는다.\n"
            "observed에 입력의 probe.atom, problem.goal, problem.facts를 각각 probe_atom, goal_atom, facts로 그대로 적는다.\n"
            "primitives.same_as_goal은 probe.atom과 problem.goal이 정확히 같은 문자열인지다.\n"
            "primitives.in_facts는 probe.atom이 problem.facts 배열의 원소인지다.\n"
            "finding.answer_only_accepts = same_as_goal; finding.proof_and_goal_accepts = same_as_goal AND in_facts; "
            "finding.gap_detected = same_as_goal AND NOT in_facts.\n"
            "각 중간값과 최종 판정을 직접 작성한다. 이 값들은 프로그램이 대신 채우지 않는다. JSON 객체 하나만 출력한다.")},
            {"role": "user", "content": "problem: " + wire_json(problem) + "\nprobe: " + wire_json({"atom": case["probe_atom"], "rule": None, "parents": []})}]
    elif task == "edge_map":
        result = [{"role": "system", "content": (
            "증명 경로와 각 노드의 atom/rule_id는 이미 주어졌다. 새 경로를 선택하거나 노드를 추가하지 않는다.\n"
            "각 노드의 부모 ID만 직접 작성하라. rule_id=null인 사실은 빈 부모 배열이다. 규칙 노드는 그 규칙의 "
            "모든 premises 원자를 담고 있는 앞선 노드 ID를 정확히 연결한다. 직전 노드가 아니라 원자 대응을 확인한다.\n"
            "links에는 모든 노드를 한 번씩 넣는다. 출력은 node_id와 parent_node_ids만 가진 항목의 배열을 포함하는 JSON이다.")},
            {"role": "user", "content": "problem: " + wire_json(problem) + "\nskeleton: " + wire_json(case["skeleton"])}]
    else:
        result = compact_messages(problem, case)
        if case.get("fact_first"):
            result[0]["content"] += ("\n작성 순서 대조: clauses의 첫 항목들에는 증명의 최초 사실을 각각 if=[]인 절로 적고, "
                                     "그 뒤에 사용한 규칙 절을 적는다. if=[]는 빈 절이 아니라 그 사실의 전제가 없다는 뜻이다.")
    # format은 디코더 제약이다. 모델 입력에서도 동일한 완전 명세를 읽을 수 있게 한다.
    result[0]["content"] += "\n출력 JSON Schema(정답값이 아닌 형식 명세):\n" + wire_json(output_schema(case))
    return result


def make_request(config: dict, case: dict, problem: dict) -> dict:
    require(case.get("probe_contract") == CONTRACT, "진단 계약 불일치")
    body = {"model": config["model"], "messages": messages(problem, case), "stream": False,
            "keep_alive": "10m", "options": dict(config["options"], seed=case["seed"])}
    fmt = case["format_mode"]
    if fmt != "none": body["format"] = output_schema(case) if fmt == "schema" else "json"
    if config.get("think") is not None: body["think"] = config["think"]
    return body


def assess_payload(core: Any, problem: dict, case: dict, payload: dict) -> dict:
    task = case["task"]
    if task in {"proof", "schema"}: return old_assess(core, problem, case, payload)
    validate_schema(payload, output_schema(case))
    comparisons: list[dict] = []
    def compare(name: str, actual: Any, expected: Any) -> None:
        comparisons.append({"field": name, "actual": copy.deepcopy(actual), "expected": copy.deepcopy(expected),
                            "matches": type(actual) is type(expected) and actual == expected})
    details: dict = {"group": case["diagnostic_group"], "host_supplied": case.get("host_supplied"), "output_modified": False}
    if task == "input_echo":
        for k, v in case["echo"].items(): compare(k, payload[k], v)
        details["not_reasoning_performance"] = True
    elif task == "literal_equality":
        x = case["operands"]; compare("equal", payload["equal"], x["left"] == x["right"])
    elif task == "criterion_witness":
        observed = {"probe_atom": case["probe_atom"], "goal_atom": problem["goal"], "facts": problem["facts"]}
        for k, v in observed.items(): compare("observed." + k, payload["observed"][k], v)
        ev = criterion_evidence(problem, case["probe_atom"], payload["finding"])
        for k, v in ev["expected_primitives"].items(): compare("primitives." + k, payload["primitives"][k], v)
        for k, v in ev["expected"].items(): compare("finding." + k, payload["finding"][k], v)
        details["criterion"] = ev
        a, b = payload["primitives"]["same_as_goal"], payload["primitives"]["in_facts"]
        from_actual = {"answer_only_accepts": a, "proof_and_goal_accepts": a and b, "gap_detected": a and not b}
        details["finding_matches_own_primitives"] = payload["finding"] == from_actual
        details["first_failed_observable_stage"] = next((stage for stage in ("observed", "primitives", "finding")
            if any(not x["matches"] and x["field"].startswith(stage + ".") for x in comparisons)), None)
        details["stage_note"] = "출력된 중간값의 불일치 위치다. 비공개 내부 사고 과정을 입증하지 않는다."
    elif task == "edge_map":
        fixed = case["skeleton"]; keys = [n["node_id"] for n in fixed["nodes"]]
        ids = [n["node_id"] for n in payload["links"]]
        compare("all_nodes_once", len(ids) == len(set(ids)) and set(ids) == set(keys), True)
        links_complete = comparisons[-1]["matches"]
        if not links_complete:
            compare("all_links_valid", None, True)
            details.update(not_a_planning_or_D_success=True, missing_or_duplicate_links_not_reconstructed=True)
            return {"valid_completion": False, "role_adherent": None, "calibration_task": task,
                    "task_checks": {x["field"]: x["matches"] for x in comparisons},
                    "task_comparisons": comparisons, "details": details,
                    "negative_controls": [], "negative_controls_ok": None}
        lookup = {x["node_id"]: x["parent_node_ids"] for x in payload["links"]}
        # 호스트는 답을 생성하지 않고 제출된 부모를 그대로 붙여 core와 별도 검사에 보낸다.
        proposed = {"nodes": [dict(n, parent_node_ids=copy.deepcopy(lookup[n["node_id"]])) for n in fixed["nodes"]],
                    "selected_final_node_id": fixed["selected_final_node_id"]}
        ev = support(problem, proposed)
        from .protocol_v2 import proof_only_trace
        verified = core.verify(problem, proof_only_trace(core, problem, proposed))
        require(ev["full_support_valid"] == verified["valid"], "독립 근거 검사와 core 판정 불일치")
        compare("all_links_valid", ev["full_support_valid"], True)
        details.update(support=ev, core_audit=verified,
                       not_a_planning_or_D_success=True,
                       missing_link_entries_not_credited=True)
    else:
        raise ContractError("알 수 없는 v042 진단 과제")
    checks = {x["field"]: x["matches"] for x in comparisons}
    return {"valid_completion": all(checks.values()), "role_adherent": None, "calibration_task": task,
            "task_checks": checks, "task_comparisons": comparisons, "details": details,
            "negative_controls": [], "negative_controls_ok": None,
            "interpretation": "분리 진단. 입력복사/고정 경로 지지는 통합 ADM 또는 독립 계획 성과가 아님."}


def summarize_probe(plan: dict, records: list[dict]) -> dict:
    lookup = {r["case"]["case_id"]: r for r in records}; groups = {}
    rows = []
    for c in plan["cases"]:
        r = lookup.get(c["case_id"]); name = c["diagnostic_group"]
        g = groups.setdefault(name, {"assigned": 0, "recorded": 0, "accepted": 0})
        g["assigned"] += 1; g["recorded"] += int(r is not None); g["accepted"] += int(bool(r and r["status"] == "accepted"))
        rows.append({"case_id": c["case_id"], "name": c["role_id"], "group": name,
                     "status": r["status"] if r else "not_started", "audit": (r or {}).get("audit"),
                     "task_diagnostics": (r or {}).get("task_diagnostics")})
    if "control" not in groups or groups["control"]["recorded"] != groups["control"]["assigned"]:
        decision = "control_not_fully_measured"
    elif groups["control"]["accepted"] != groups["control"]["assigned"]:
        decision = "stop_scaling_up_check_input_or_runtime_pair"
    elif "criterion" not in groups or groups["criterion"]["recorded"] != groups["criterion"]["assigned"]:
        decision = "control_passed_criterion_not_fully_measured"
    elif groups["criterion"]["accepted"] != groups["criterion"]["assigned"]:
        decision = "control_passed_literal_decision_unreliable_in_this_condition"
    else:
        decision = "controls_and_criterion_passed_inspect_graph_and_schema_separately"
    from .decision_evidence import aggregate_witnesses
    stages = aggregate_witnesses(records)
    criterion_count = groups.get("criterion", {}).get("assigned", 0)
    if (decision == "control_passed_literal_decision_unreliable_in_this_condition"
            and stages["assessable_cases"] == criterion_count
            and stages["observed_correct_cases"] == criterion_count
            and stages["primitives_correct_cases"] == criterion_count):
        decision = "input_and_primitives_correct_final_finding_inconsistent"
    return {"stage_evidence": stages, "contract": CONTRACT, "groups": groups, "cases": rows, "next_evidence_action": decision,
            "decision_is_diagnostic_not_cause_proof": True, "not_an_ADM_success_rate": True,
            "interpretation": "다수결/통합 평균을 사용하지 않는다. 반증된 조건을 별도로 기록한다. "
                              "단일 시드에서의 대응 비교는 해당 입력의 관측이며 모델 일반 성능 추정이 아니다."}


def main(argv: list[str] | None = None) -> int:
    from .__main__ import generation_arguments, generation_config
    from .client import APIError
    from .runner import run
    parser = argparse.ArgumentParser(description=__doc__)
    generation_arguments(parser)
    parser.add_argument("--seed", type=int, default=1729)
    parser.add_argument("--group", action="append", choices=GROUPS)
    parser.add_argument("--format-mode", choices=("schema", "json", "none"), default="schema")
    parser.add_argument("--allow-core-change", action="store_true")
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--save-plan", type=Path)
    args = parser.parse_args(argv)
    try:
        require(args.prompt_profile == "factorized-v4", "micro_probe는 고정 v042 메시지를 사용한다. --prompt-profile을 변경하지 마세요.")
        core, info = load_core(args.allow_core_change)
        plan = build_plan(core, args.seed, args.group, args.format_mode)
        if args.save_plan:
            require(not args.save_plan.exists(), "계획 파일이 이미 존재합니다."); write_json(args.save_plan, plan)
        if args.plan_only:
            print(json.dumps({"model_called": False, "assigned_calls": plan["assigned_calls"], "groups": plan["groups"],
                "format_mode": args.format_mode, "cases": [c["role_id"] for c in plan["cases"]], "note": plan["design_note"]}, ensure_ascii=False, indent=2))
            return 0
        config = generation_config(args)
        out = args.out or REPO / "results_llm" / f"v042_micro_{datetime.now():%Y%m%d_%H%M%S}"
        print(f"분리 진단: {plan['assigned_calls']}회 / 그룹={','.join(plan['groups'])} / format={args.format_mode}", flush=True)
        return run(core, info, plan, config, out, args.resume, fail_on_model_failure=args.fail_on_model_failure)
    except (ContractError, APIError, OSError, ValueError) as exc:
        print(f"오류: {exc}", file=sys.stderr); return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
