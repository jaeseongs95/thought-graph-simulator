"""24회 구성요소 진단. 각 호출은 독립 과제이며 본 실험 성공률과 섞지 않는다.

증명 6, 도식 6(전체/최종 노드만의 쌍), 논증 검토 6, 기준 판정 6.
진단용 고정 증명은 모델에 제공했다고 명시한다. 실패 출력은 수정하지 않는다.
"""
from __future__ import annotations

import copy
import random
from typing import Any

from . import calibration
from .common import digest, require, wire_json
from .design import reference_depths
from .protocol import validate_schema
from .protocol_v2 import proof_only_trace, view_to_core


def fixtures() -> list[tuple[dict, dict]]:
    # 고정 입력: 시험 중 생성/선택한 정답을 LLM에 주는 경로가 아니다.
    definitions = [
        ("K01", ["Ca"], [(["Ca"], "Cc"), (["Ca"], "Cb"), (["Cb"], "Cc")], "Cc",
         [("Ca", None, []), ("Cb", 1, [0]), ("Cc", 2, [1])]),
        ("K02", ["Da", "Db"], [(["Da", "Db"], "De"), (["Da"], "Dc"),
          (["Dc", "Db"], "Dd"), (["Dd"], "De")], "De",
         [("Da", None, []), ("Db", None, []), ("Dc", 1, [0]),
          ("Dd", 2, [2, 1]), ("De", 3, [3])]),
        ("K03", ["Ea"], [(["Ea"], "Ee"), (["Ea"], "Eb"),
          (["Eb"], "Ec"), (["Eb"], "Ed"), (["Ec", "Ed"], "Ee")], "Ee",
         [("Ea", None, []), ("Eb", 1, [0]), ("Ec", 2, [1]),
          ("Ed", 3, [1]), ("Ee", 4, [2, 3])]),
    ]
    result = []
    for pid, facts, definitions_, goal, node_defs in definitions:
        # 배열 순서/규칙명에 direct/step 등 힌트를 넣지 않는다.
        rules = [{"id": f"k{(j * 7 + 3) % 31:02d}", "premises": p, "conclusion": c}
                 for j, (p, c) in enumerate(definitions_)]
        problem = {"id": pid, "facts": facts, "rules": copy.deepcopy(rules), "goal": goal}
        nodes = [{"node_id": f"n{i}", "atom": atom,
                  "rule_id": None if rid is None else rules[rid]["id"],
                  "parent_node_ids": [f"n{x}" for x in parents]}
                 for i, (atom, rid, parents) in enumerate(node_defs)]
        random.Random(500 + len(rules)).shuffle(problem["rules"])
        proof = {"nodes": nodes, "selected_final_node_id": nodes[-1]["node_id"]}
        result.append((problem, proof))
    return result


def build_calibration_plan(core: Any, seed: int = 1729) -> dict:
    require(type(seed) is int and 0 <= seed < 2**31 - 1000, "시드 범위 오류")
    fixed = fixtures()
    problems = {p["id"]: p for p, _ in fixed}
    tasks: list[tuple[str, str, dict, dict]] = []
    for index, (problem, proof) in enumerate(fixed, 1):
        for depth in ("shallow", "deep"):
            tasks.append((f"proof_{index}_{depth}", "proof", problem, {"depth_policy": depth}))
        for scope in ("all_nodes", "final_node_only"):
            tasks.append((f"schema_{index}_{scope}", "schema", problem,
                          {"provided_proof": copy.deepcopy(proof), "view_scope": scope}))
    p0, proof0 = fixed[0]
    bad_parent = copy.deepcopy(proof0)
    bad_parent["nodes"][1]["parent_node_ids"] = []
    nong = {"nodes": [copy.deepcopy(proof0["nodes"][0])], "selected_final_node_id": "n0"}
    orphan = copy.deepcopy(nong)
    orphan["nodes"][0]["atom"] = "Orphan"
    unrelated = copy.deepcopy(proof0)
    unrelated["nodes"].append({"node_id": "extra", "atom": p0["goal"],
                                "rule_id": "k03", "parent_node_ids": ["n0"]})
    reviews = [(p0, proof0), (p0, bad_parent), (p0, nong), (p0, orphan),
               (fixed[2][0], fixed[2][1]), (p0, unrelated)]
    for i, (p, proof) in enumerate(reviews, 1):
        tasks.append((f"review_{i:02d}", "review", p, {"provided_proof": copy.deepcopy(proof)}))
    # 가능한 기준 판정 패턴 3종을 각각 2회. 'goal_given' 같은 정답 단서 ID는 입력하지 않는다.
    for index, (problem, _) in enumerate(fixed[:2]):
        goal_given = copy.deepcopy(problem)
        goal_given["id"] = f"K{index + 11:02d}"
        goal_given["facts"].append(problem["goal"])
        problems[goal_given["id"]] = goal_given
        for sub, p, atom in [(0, problem, problem["goal"]),
                             (1, problem, problem["facts"][0]),
                             (2, goal_given, goal_given["goal"])]:
            tasks.append((f"criterion_{index * 3 + sub + 1:02d}", "criterion", p, {"probe_atom": atom}))
    cases = []
    for name, task, problem, extra in tasks:
        case = {"problem_id": problem["id"], "problem_sha256": core.digest(problem),
                "role": {"kind": "neutral", "A": None, "D_policy": None, "M": None},
                "role_id": name, "repeat": 0, "seed": seed, "task": task,
                "calibration_version": 4, **extra}
        case["case_id"] = digest(case)[:24]
        cases.append(case)
    random.Random(seed + 600013).shuffle(cases)
    for problem in problems.values():
        core.check_problem(problem)
    return {"profile": "calibrate", "experiment_kind": "calibration", "repeats": 1, "seed": seed,
            "problems": list(problems.values()), "roles": [], "cases": cases,
            "assigned_calls": len(cases),
            "reference_depths": {p["id"]: reference_depths(p) for p in problems.values()},
            "warnings": [], "scope": "v4_component_diagnostics_not_joint_ADM_measurement"}


def messages(problem: dict, case: dict) -> list[dict]:
    result = calibration.messages(problem, case)
    if case.get("view_scope") == "final_node_only":
        # 전체 노드 제출 지시를 남긴 채 반대 지시를 덧붙이지 않는다.
        result[0]["content"] = (
            "외부 지식 없이 주어진 고정 증명의 최종 노드에 대한 universal_schema view 하나만 작성하라.\n"
            "최종 노드와 모든 지지 조상의 원자를 bindings의 {variable,atom}에 일대일 대응한다.\n"
            "clauses에는 그 부분 증명의 모든 사실(if=[])과 실제 사용 규칙을 변수로 치환해 한 번씩 쓴다.\n"
            "현재 결론을 새 사실로 가정하지 않는다. conclusion_var는 최종 노드의 원자 변수다.\n"
            "quantifier=forall_boolean_valuations. 반환 node_views에는 최종 노드 항목 딱 하나만 쓴다.\n"
            "증명은 입력으로 제공되며 생성/수정 대상이 아니다. 출력 스키마에 맞는 JSON 객체 하나만 반환한다.\n")
    return result


def assess_payload(core: Any, problem: dict, case: dict, payload: dict) -> dict:
    if case.get("view_scope") != "final_node_only":
        return calibration.assess_payload(core, problem, case, payload)
    validate_schema(payload, calibration.output_schema(case))
    trace = proof_only_trace(core, problem, case["provided_proof"])
    items = payload["node_views"]
    correct_scope = len(items) == 1 and items[0]["node_id"] == trace["final"]
    is_schema = correct_scope and items[0]["view"]["kind"] == "universal_schema"
    if correct_scope:
        trace["views"][trace["final"]] = view_to_core(items[0]["view"])
    verified = core.verify(problem, trace) if correct_scope else None
    valid_schema = bool(is_schema and verified and verified["valid"])
    checks = {"requested_view_scope": correct_scope, "schema_kind": bool(is_schema),
              "valid_final_schema": valid_schema}
    return {"valid_completion": all(checks.values()), "role_adherent": None,
            "calibration_task": "schema", "task_checks": checks,
            "task_comparisons": [{"field": k, "actual": v, "expected": True, "matches": v}
                                 for k, v in checks.items()],
            "details": {"core_audit": verified, "view_scope": "final_node_only",
                        "host_supplied": "증명 전체와 중간 노드 instance view는 고정 입력/진단용. 최종 도식만 모델 산출물.",
                        "scope_note": "A 전체 성공이 아니다. 같은 고정 증명의 all_nodes 과제와 작성 부담을 비교한다."},
            "negative_controls": [], "negative_controls_ok": None,
            "interpretation": "구성요소 진단이며 전체 ADM 성공으로 집계하지 않음"}
