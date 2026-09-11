"""분리 진단 전용 보고. 본 ADM 역할 성공으로 올려 세지 않는다."""
from __future__ import annotations

from collections import Counter


def component_summary(plan: dict, records: list[dict]) -> dict:
    lookup = {r["case"]["case_id"]: r for r in records}
    problems = {p["id"]: p for p in plan["problems"]}
    groups: dict[str, dict] = {}
    patterns: dict[str, dict] = {}
    actual_patterns: Counter = Counter()
    schema: dict[str, dict] = {}
    schema_conditions = []
    fields = ("answer_only_accepts", "proof_and_goal_accepts", "gap_detected")
    for case in plan["cases"]:
        record = lookup.get(case["case_id"])
        task = case["task"]
        group_name = task + ("/" + case.get("view_scope", "all_nodes") if task == "schema" else "")
        group = groups.setdefault(group_name, {"assigned": 0, "recorded": 0, "accepted": 0})
        group["assigned"] += 1
        group["recorded"] += int(record is not None)
        group["accepted"] += int(record is not None and record["status"] == "accepted")
        if task in {"criterion", "criterion_witness", "decision_stage"}:
            p = problems[case["problem_id"]]
            answer = case["probe_atom"] == p["goal"]
            valid = answer and case["probe_atom"] in p["facts"]
            expected = (answer, valid, answer != valid)
            key = ",".join(str(x).lower() for x in expected)
            entry = patterns.setdefault(key, {"assigned": 0, "accepted": 0, "parsed_responses": 0})
            entry["assigned"] += 1
            entry["accepted"] += int(record is not None and record["status"] == "accepted")
            details = ((record or {}).get("audit") or {}).get("details", {})
            actual = (details.get("criterion", {}).get("actual", {}) if task == "criterion_witness"
                      else details.get("actual", {}))
            if all(type(actual.get(k)) is bool for k in fields):
                entry["parsed_responses"] += 1
                actual_patterns[",".join(str(actual[k]).lower() for k in fields)] += 1
        if task == "schema" and case.get("calibration_version") == 4:
            bucket = schema.setdefault(case["problem_id"], {})
            observation = {"case_id": case["case_id"], "role_id": case["role_id"],
                "variant": case.get("probe_variant"), "view_scope": case["view_scope"],
                "status": record["status"] if record else "not_started",
                "accepted": bool(record and record["status"] == "accepted"),
                "api_generated_tokens": ((record or {}).get("usage") or {}).get("eval_count")}
            bucket.setdefault(case["view_scope"], []).append(observation)
            schema_conditions.append({"problem_id": case["problem_id"], **observation})
    pairs = []
    for pid, scopes in schema.items():
        row = {"problem_id": pid, "ambiguous_scope_comparison": any(len(v) > 1 for v in scopes.values())}
        for scope, observations in scopes.items():
            row[scope] = (observations[0] if len(observations) == 1 else
                          {"ambiguous": True, "conditions": observations,
                           "note": "같은 범위에 여러 조건이 있어 한 건을 대표로 선택하지 않음"})
        pairs.append(row)
    from .decision_evidence import aggregate_witnesses
    from .decision_table import summarize_records
    return {"decision_contract_by_arm": summarize_records(plan, records),
            "criterion_witness_stages": aggregate_witnesses(records), "groups": groups, "criterion_expected_patterns": patterns,
            "criterion_actual_patterns": dict(actual_patterns),
            "criterion_constant_output_observed": (len(actual_patterns) == 1 and sum(actual_patterns.values()) > 1),
            "criterion_pattern_field_order": list(fields),
            "schema_scope_pairs": pairs, "schema_scope_conditions": schema_conditions,
            "note": "상수 응답은 관측 패턴이다. 복사/캐시 등 원인을 단정하지 않는다. 최종 도식 단독 성공을 전체 A 성공으로 세지 않는다."}
