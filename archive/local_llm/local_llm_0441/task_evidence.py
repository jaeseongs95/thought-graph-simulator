"""과제별 원문 증거. 판정/입력/모델 출력 수정 없이 실패 위치를 별도 기록한다.

core.verify·생성기의 도식 함수를 사용하지 않는 도식 조항/진리값 교차검사다.
비정규 bindings 객체는 관측만 하며 허용된 전송 형식으로 자동 변환하지 않는다.
"""
from __future__ import annotations

from collections import Counter
from itertools import product
from typing import Any

from .common import ContractError, strict_json
from .evidence import support


def explain_shape(value: Any, schema: dict, path: str = "$", depth: int = 0) -> list[dict]:
    """anyOf에서 버려졌던 분기별 오류 위치를 제공한다. 기존 검증기는 바꾸지 않는다."""
    if depth > 50:
        return [{"path": path, "error": "diagnostic_depth_limit"}]
    if "anyOf" in schema:
        choices = [explain_shape(value, x, path, depth + 1) for x in schema["anyOf"]]
        if any(not x for x in choices):
            return []
        # kind를 사용한 명시 분기가 있으면 그 분기의 구체적 오류를 우선 노출한다.
        if isinstance(value, dict) and isinstance(value.get("kind"), str):
            for branch, errors in zip(schema["anyOf"], choices):
                if branch.get("properties", {}).get("kind", {}).get("const") == value["kind"]:
                    return errors
        return [{"path": path, "error": "no_matching_branch", "branches": choices}]
    errors = []
    if "const" in schema and (type(value) is not type(schema["const"]) or value != schema["const"]):
        errors.append({"path": path, "error": "constant_mismatch", "expected": schema["const"], "actual": value})
    types = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}
    kind = schema.get("type")
    if kind is not None and (kind not in types or type(value) is not types[kind]):
        return errors + [{"path": path, "error": "type_mismatch", "expected": kind,
                          "actual": type(value).__name__}]
    if kind == "object":
        props = schema.get("properties", {})
        for k in schema.get("required", []):
            if k not in value:
                errors.append({"path": f"{path}.{k}", "error": "missing_field"})
        for k, v in value.items():
            if k in props:
                errors += explain_shape(v, props[k], f"{path}.{k}", depth + 1)
            elif schema.get("additionalProperties") is False:
                errors.append({"path": f"{path}.{k}", "error": "extra_field"})
            elif isinstance(schema.get("additionalProperties"), dict):
                errors += explain_shape(v, schema["additionalProperties"], f"{path}.{k}", depth + 1)
    elif kind == "array":
        if not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", 1000):
            errors.append({"path": path, "error": "array_length", "actual": len(value)})
        for i, v in enumerate(value[:128]):
            errors += explain_shape(v, schema.get("items", {}), f"{path}[{i}]", depth + 1)
    elif kind == "string":
        if not schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", 100000):
            errors.append({"path": path, "error": "string_length", "actual": len(value)})
    return errors


def criterion_evidence(problem: dict, atom: str, payload: Any) -> dict:
    """문자열 동일성·목록 소속·불리언 결합을 구분. 원래 출력에 없는 중간 판정은 추측하지 않는다."""
    a = atom == problem["goal"]
    b = atom in problem["facts"]
    want = {"answer_only_accepts": a, "proof_and_goal_accepts": a and b,
            "gap_detected": a and not b}
    actual = payload if isinstance(payload, dict) else {}
    checks = {k: type(actual.get(k)) is bool and actual[k] == v for k, v in want.items()}
    booleans = all(type(actual.get(k)) is bool for k in want)
    return {"input": {"probe_atom": atom, "goal": problem["goal"], "facts": problem["facts"]},
            "expected_primitives": {"same_as_goal": a, "in_facts": b}, "expected": want,
            "actual": {k: actual.get(k) for k in want}, "matches": checks,
            "actual_internal_consistency": (not (actual["proof_and_goal_accepts"] and not actual["answer_only_accepts"])
                and actual["gap_detected"] == (actual["answer_only_accepts"] and not actual["proof_and_goal_accepts"]))
                if booleans else None,
            "primitive_failure_localized": False,
            "note": "원래 과제는 primitive 출력을 받지 않는다. 내부 어느 연산이 틀렸는지 이 결과로 단정하지 않는다."}


def _clause(antecedents: tuple[str, ...], conclusion: str) -> dict:
    return {"if": list(antecedents), "then": conclusion}


def schema_evidence(problem: dict, proof: dict, payload: Any) -> dict:
    """고정 증명의 지지 조항과 반환 도식을 직접 대조한다. 비정규 출력은 관측으로만 읽는다."""
    graph = support(problem, proof)
    result: dict = {"provided_proof_valid": graph.get("full_support_valid", False), "views": [],
                    "score_effect": "none", "output_modified": False}
    if not graph.get("full_support_valid"):
        result["reason"] = "고정 입력 증명이 유효하지 않아 도식의 기대 조항을 산출하지 않음"
        return result
    nodes = {n["node_id"]: n for n in proof["nodes"]}
    rules = {r["id"]: r for r in problem["rules"]}
    if not isinstance(payload, dict) or not isinstance(payload.get("node_views"), list):
        result["reason"] = "node_views 형식 오류"
        return result
    for item in payload["node_views"][:128]:
        if not isinstance(item, dict):
            result["views"].append({"error": "view_item_not_object"}); continue
        key, v = item.get("node_id"), item.get("view")
        if not isinstance(key, str) or key not in nodes or not isinstance(v, dict):
            result["views"].append({"node_id": key, "error": "unknown_node_or_view_shape"}); continue
        used: set[str] = set()
        pending = [key]
        while pending:
            k = pending.pop()
            if k not in used:
                used.add(k); pending.extend(nodes[k]["parent_node_ids"])
        expected = set()
        for k in used:
            n = nodes[k]
            if n["rule_id"] is None:
                expected.add(((), n["atom"]))
            else:
                r = rules[n["rule_id"]]
                expected.add((tuple(sorted(r["premises"])), r["conclusion"]))
        entry: dict = {"node_id": key, "kind": v.get("kind"),
            "expected_atoms": sorted({nodes[k]["atom"] for k in used}),
            "expected_clauses": [_clause(a, b) for a, b in sorted(expected)],
            "binding_container": type(v.get("bindings")).__name__, "issues": []}
        if v.get("kind") != "universal_schema":
            entry["issues"].append("not_schema"); result["views"].append(entry); continue
        pairs = v.get("bindings")
        binding: dict[str, str] = {}
        if isinstance(pairs, list):
            for pair in pairs[:10]:
                if not isinstance(pair, dict) or set(pair) != {"variable", "atom"} or not all(isinstance(x, str) for x in pair.values()):
                    entry["issues"].append("binding_item_shape"); continue
                if pair["variable"] in binding: entry["issues"].append("duplicate_binding_variable")
                binding[pair["variable"]] = pair["atom"]
        elif isinstance(pairs, dict) and len(pairs) <= 10 and all(isinstance(k, str) and isinstance(x, str) for k, x in pairs.items()):
            # 읽을 수 있는 원자 대응을 증거로만 제시. 변환/정규화한 payload를 evaluator에 보내지 않는다.
            binding = dict(pairs)
            entry["issues"].append("bindings_object_not_required_array")
            entry["noncanonical_mapping_observation_only"] = True
        else:
            entry["issues"].append("unreadable_bindings")
        if set(binding.values()) != set(entry["expected_atoms"]) or len(binding) != len(entry["expected_atoms"]):
            entry["issues"].append("binding_not_bijection_on_used_atoms")
        returned = []
        raw_clauses = v.get("clauses")
        if not isinstance(raw_clauses, list) or len(raw_clauses) > 128:
            entry["issues"].append("clauses_shape"); raw_clauses = []
        variables_valid = True
        for c in raw_clauses:
            if not (isinstance(c, dict) and set(c) == {"if", "then"}
                    and isinstance(c["if"], list) and all(isinstance(x, str) and x in binding for x in c["if"])
                    and isinstance(c["then"], str) and c["then"] in binding):
                variables_valid = False; entry["issues"].append("invalid_clause_or_unknown_variable"); continue
            if len(c["if"]) != len(set(c["if"])):
                entry["issues"].append("duplicate_clause_premise")
            returned.append((tuple(sorted(binding[x] for x in c["if"])), binding[c["then"]]))
        counts = Counter(returned)
        missing, extra = expected - set(returned), set(returned) - expected
        entry.update(returned_clauses=[_clause(a, b) for a, b in returned],
            missing_clauses=[_clause(a, b) for a, b in sorted(missing)],
            missing_fact_atoms=sorted(b for a, b in missing if not a),
            extra_clauses=[_clause(a, b) for a, b in sorted(extra)],
            duplicate_clauses=[_clause(a, b) for (a, b), n in counts.items() if n > 1],
            grounded_clauses_exact=not missing and not extra and all(n == 1 for n in counts.values()))
        cv = v.get("conclusion_var")
        conclusion_valid = isinstance(cv, str) and cv in binding and binding[cv] == nodes[key]["atom"]
        entry["conclusion_grounding_valid"] = conclusion_valid
        entry["counterexample_valuation"] = None
        entry["supplied_clauses_entail_conclusion"] = None
        if variables_valid and conclusion_valid and 0 < len(binding) <= 10:
            variables = sorted(binding)
            for bits in product((False, True), repeat=len(variables)):
                valuation = dict(zip(variables, bits))
                if all(not all(valuation[x] for x in c["if"]) or valuation[c["then"]] for c in raw_clauses) and not valuation[cv]:
                    entry["counterexample_valuation"] = valuation
                    break
            entry["supplied_clauses_entail_conclusion"] = entry["counterexample_valuation"] is None
        result["views"].append(entry)
    return result


def task_diagnostics(problem: dict, case: dict, content: Any, schema: dict | None = None) -> dict:
    output: dict = {"task": case.get("task"), "score_effect": "none", "output_modified": False,
                    "json_valid": False, "shape_errors": []}
    try:
        payload = strict_json(content)
        output["json_valid"] = True
        if schema is not None:
            output["shape_errors"] = explain_shape(payload, schema)
        if case.get("task") == "proof":
            output["support"] = support(problem, payload) if isinstance(payload, dict) else {"shape_valid": False}
        elif case.get("task") == "schema":
            output["schema"] = schema_evidence(problem, case["provided_proof"], payload)
        elif case.get("task") == "criterion":
            output["criterion"] = criterion_evidence(problem, case["probe_atom"], payload)
        elif case.get("task") == "criterion_witness":
            from .decision_evidence import witness_evidence
            output["criterion_witness"] = witness_evidence(problem, case, payload)
        if case.get("task") in ("criterion_witness", "decision_stage"):
            from .decision_table import row_evidence
            output["decision_contract"] = row_evidence(problem, case, payload)
    except (ContractError, TypeError, KeyError, ValueError, RecursionError) as exc:
        output["diagnostic_error"] = f"{type(exc).__name__}: {exc}"
    return output
