"""Independently verify a frozen v063 forensic analysis report.

This tool reads the v062 evidence archive and the v063 analysis JSON.  It does
not import ``analyze_v062``, production measurement code, or an evidence source
snapshot.  It preserves the v062 official measurement and admission gate, then
reconstructs only the report's raw-response forensic fields.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
V062_TOOLS = ROOT.parents[1] / "v062" / "probe" / "tools"
if str(V062_TOOLS) not in sys.path:
    sys.path.insert(0, str(V062_TOOLS))

# These are sealed independent helpers, not the v062 production scorer.  In
# particular, neither import resolves a source_snapshot path.
from verify_v062 import (  # noqa: E402
    call_status,
    independent_measure,
    schema_valid,
    unpack,
    verify as legacy_verify,
)
from independent_graph_forensic import load as strict_load, sha  # noqa: E402


REPORT_LIMIT = 8 * 1024 * 1024
VARIANTS = ("target_k03", "target_k17")
REPORT_CONTRACT = "v062-failure-forensics-r1"
RECEIPT_CONTRACT = "independent-v063-forensics-r1"


def _read_report(path: Path) -> tuple[bytes, dict[str, Any]]:
    """Load a bounded strict JSON report without accepting duplicate keys/NaN."""
    if not path.is_file():
        raise ValueError("analysis report is not a regular file")
    if path.stat().st_size > REPORT_LIMIT:
        raise ValueError("analysis report exceeds 8 MiB")
    raw = path.read_bytes()
    try:
        value = strict_load(raw)
    except (ValueError, UnicodeError) as error:
        raise ValueError("invalid analysis report JSON") from error
    if not isinstance(value, dict):
        raise ValueError("analysis report must be an object")
    return raw, value


def node_diagnostics(
    problem: dict[str, Any], payload: Any, target: str
) -> dict[str, Any]:
    """Rebuild raw error locations without pruning or assigning a repaired score."""
    empty = {
        "final_rule_label_matches_target": None,
        "final_atom_matches_goal": None,
        "node_diagnostics": None,
        "final_ancestor_ids": None,
        "outside_final_ancestry_ids": None,
        "has_nodes_outside_final_ancestry": None,
        "error_nodes_inside": None,
        "error_nodes_outside": None,
        "errors_only_outside_final_ancestry": None,
    }
    if not schema_valid(payload):
        return empty

    nodes_list = payload["nodes"]
    counts = Counter(node["id"] for node in nodes_list)
    nodes = {node["id"]: node for node in nodes_list}
    rules = {rule["id"]: rule for rule in problem["rules"]}
    unique = all(count == 1 for count in counts.values())
    final = nodes.get(payload["final_node_id"]) if unique else None

    # Use a parent-closure fixed point rather than the analyzer's DFS.  Missing
    # parent references never enter the declared ancestor set, matching the
    # report contract while leaving the missing-parent error on the raw node.
    ancestors: set[str] = set()
    if final is not None:
        ancestors.add(payload["final_node_id"])
        while True:
            expanded = ancestors | {
                parent
                for node_id in ancestors
                for parent in nodes[node_id]["parents"]
                if parent in nodes
            }
            if expanded == ancestors:
                break
            ancestors = expanded

    details: list[dict[str, Any]] = []
    for index, node in enumerate(nodes_list):
        errors: list[str] = []
        parents = node["parents"]
        if counts[node["id"]] != 1:
            errors.append("duplicate_id")
        if (final is not None and node["id"] == payload["final_node_id"]
                and node["atom"] != problem["goal"]):
            errors.append("final_goal_mismatch")
        if len(parents) != len(set(parents)):
            errors.append("duplicate_parent")
        if any(parent not in nodes for parent in parents):
            errors.append("missing_parent")
        if node["rule_id"] is None:
            if parents:
                errors.append("fact_with_parents")
            if node["atom"] not in problem["facts"]:
                errors.append("unreachable_fact")
        elif node["rule_id"] not in rules:
            errors.append("unregistered_rule")
        else:
            rule = rules[node["rule_id"]]
            if node["atom"] != rule["conclusion"]:
                errors.append("wrong_atom")
            if unique and all(parent in nodes for parent in parents):
                atoms = Counter(nodes[parent]["atom"] for parent in parents)
                if atoms != Counter(rule["premises"]):
                    errors.append("premise_counter_mismatch")
        if unique:
            visited: set[str] = set()
            pending = list(parents)
            while pending:
                node_id = pending.pop()
                if node_id == node["id"]:
                    errors.append("cycle_member")
                    break
                if node_id not in nodes or node_id in visited:
                    continue
                visited.add(node_id)
                pending.extend(nodes[node_id]["parents"])
        details.append({
            "index": index,
            "id": node["id"],
            "atom": node["atom"],
            "rule_id": node["rule_id"],
            "parents": list(parents),
            "errors": sorted(set(errors)),
            "in_final_ancestry": node["id"] in ancestors if final else None,
        })

    inside = sum(bool(node["errors"])
                 for node in details if node["in_final_ancestry"] is True)
    outside = sum(bool(node["errors"])
                  for node in details if node["in_final_ancestry"] is False)
    return {
        "final_rule_label_matches_target": final["rule_id"] == target if final else None,
        "final_atom_matches_goal": final["atom"] == problem["goal"] if final else None,
        "node_diagnostics": details,
        "final_ancestor_ids": sorted(ancestors) if final else None,
        "outside_final_ancestry_ids": sorted(set(nodes) - ancestors) if final else None,
        "has_nodes_outside_final_ancestry": bool(set(nodes) - ancestors)
        if final else None,
        "error_nodes_inside": inside if final else None,
        "error_nodes_outside": outside if final else None,
        "errors_only_outside_final_ancestry": inside == 0 and outside > 0
        if final else None,
    }


def summarize(
    rows: list[dict[str, Any]], seeds: list[int], complete: bool
) -> dict[str, Any]:
    """Recreate the forensic report's group, seed, and stratum fields exactly."""
    lookup = {(row["seed"], row["variant"], row["repeat"]): row for row in rows}
    if len(lookup) != len(rows):
        raise ValueError("duplicate seed/variant/repeat")

    def group(cells: list[dict[str, Any]]) -> dict[str, Any]:
        seen = [row for row in cells if row["observed"]]
        measured = [row for row in seen
                    if row["official_measurement"]["proof_valid"] is not None]

        def count(key: str) -> int:
            return sum(row["official_measurement"][key] is True for row in seen)

        return {
            "assigned": len(cells),
            "observed": len(seen),
            "semantic_measured": len(measured),
            "format_valid": count("format_valid"),
            "proof_valid": count("proof_valid"),
            "strict_valid": count("strict_valid"),
            "instruction_fulfilled": count("instruction_fulfilled"),
            "instruction_rate": (
                count("instruction_fulfilled") / len(cells)
                if complete and cells and len(measured) == len(cells) else None
            ),
            "final_rule_label_matches_target": sum(
                row["diagnostics"]["final_rule_label_matches_target"] is True
                for row in seen
            ),
            "final_atom_matches_goal": sum(
                row["diagnostics"]["final_atom_matches_goal"] is True
                for row in seen
            ),
            "has_nodes_outside_final_ancestry": sum(
                row["diagnostics"]["has_nodes_outside_final_ancestry"] is True
                for row in seen
            ),
            "errors_only_outside_final_ancestry": sum(
                row["diagnostics"]["errors_only_outside_final_ancestry"] is True
                for row in seen
            ),
            "selected_rule_ids": dict(Counter(
                row["official_measurement"]["selected_rule_id"] or "unmeasured"
                for row in seen
            )),
            "call_error_counts": dict(Counter(
                error for row in seen
                for error in row["official_measurement"]["errors"]
            )),
            "actual_depths": dict(Counter(
                str(row["official_measurement"]["actual_D"])
                if row["official_measurement"]["actual_D"] is not None
                else "unmeasured"
                for row in seen
            )),
        }

    seed_rows = []
    for seed in seeds:
        cells = [lookup.get((seed, variant, repeat))
                 for variant in VARIANTS for repeat in (0, 1)]
        ids = [row["official_measurement"]["selected_rule_id"]
               if row and row["observed"] else None for row in cells]
        seed_rows.append({
            "seed": seed,
            "ids_A0_A1_B0_B1": ids,
            "label_repeat_stable": (
                ids[0] == ids[1] and ids[2] == ids[3]
                if all(value is not None for value in ids) else None
            ),
        })

    strata: dict[str, dict[str, Any]] = {}
    for axis in (
        "sequence", "period", "previous_variant", "repeat_distance",
        "prompt_eval_cached_count",
    ):
        strata[axis] = {}
        for value in sorted({str(row.get(axis)) for row in rows}):
            strata[axis][value] = {
                variant: group([
                    row for row in rows
                    if str(row.get(axis)) == value and row["variant"] == variant
                ])
                for variant in VARIANTS
                if any(str(row.get(axis)) == value and row["variant"] == variant
                       for row in rows)
            }
    return {
        "groups": {
            variant: group([row for row in rows if row["variant"] == variant])
            for variant in VARIANTS
        },
        "seed_rows": seed_rows,
        "strata": strata,
    }


def reconstruct_report(bundle: Path, legacy_receipt: dict[str, Any]) -> dict[str, Any]:
    """Recreate the full analysis report from manifest-verified raw evidence."""
    raw = bundle.read_bytes()
    data, _ = unpack(raw)
    plan = strict_load(data["external_plan/v062.plan.json"])
    stored = strict_load(data["run/summary.json"])
    events = [strict_load(line) for line in data["run/events.jsonl"].splitlines()]
    call_events = {
        event["action"]["id"]: event
        for event in events if event["action"]["kind"] == "call"
    }
    rows: list[dict[str, Any]] = []
    slot_fields = (
        "id", "seed", "variant", "repeat", "sequence", "period",
        "previous_variant", "repeat_distance", "target_rule_id",
    )
    for slot in plan["slots"]:
        base = {key: slot[key] for key in slot_fields}
        event = call_events.get(slot["id"])
        if event is None:
            rows.append({
                **base,
                "observed": False,
                "official_measurement": None,
                "diagnostics": None,
            })
            continue

        prefix = "run/calls/" + slot["id"] + "/"
        request_raw = data[prefix + "request.wire.json"]
        response_raw = data[prefix + "response.raw.json"]
        request = strict_load(request_raw)
        problem_text = request["messages"][0]["content"].rsplit("\n\nproblem: ", 1)[1]
        problem = strict_load(problem_text.encode("utf-8"))
        _, raw_category, payload = call_status(
            response_raw,
            request["model"],
            event["http_status"],
            event["transport_error"],
        )
        official_measurement = independent_measure(problem, payload, slot)
        try:
            envelope = strict_load(response_raw)
            cached = envelope.get("prompt_eval_cached_count") \
                if isinstance(envelope, dict) else None
        except (ValueError, UnicodeError):
            cached = None
        if type(cached) is not int or cached < 0:
            cached = None
        rows.append({
            **base,
            "observed": True,
            "official_measurement": official_measurement,
            "diagnostics": node_diagnostics(problem, payload, slot["target_rule_id"]),
            "raw_parse_category": raw_category,
            "payload": payload,
            "request_sha256": sha(request_raw),
            "response_sha256": sha(response_raw),
            "prompt_eval_cached_count": cached,
        })

    expected_depth = {"target_k03": 1, "target_k17": 2}
    strict_target_depth_calls = sum(
        row["observed"]
        and row["official_measurement"]["strict_valid"] is True
        and row["official_measurement"]["target_rule_match"] is True
        and row["official_measurement"]["actual_D"]
        == expected_depth[row["variant"]]
        for row in rows
    )
    stable_seed_blocks = 0
    for seed in plan["seeds"]:
        cells = [
            next(row for row in rows
                 if row["seed"] == seed and row["variant"] == variant
                 and row["repeat"] == repeat)
            for variant in VARIANTS for repeat in (0, 1)
        ]
        measurements = [row["official_measurement"] for row in cells]
        all_strict = all(
            measurement is not None and measurement["strict_valid"] is True
            for measurement in measurements
        )
        if all_strict:
            signatures = [
                (measurement["selected_rule_id"], measurement["actual_D"],
                 measurement["strict_valid"], measurement["instruction_fulfilled"])
                for measurement in measurements
            ]
            stable_seed_blocks += int(
                signatures[0] == signatures[1] and signatures[2] == signatures[3]
            )
    admission_gate = {
        "required_calls": 40,
        "strict_target_depth_calls": strict_target_depth_calls,
        "stable_seed_blocks": stable_seed_blocks,
        "expected_actual_D": expected_depth,
    }
    admission_gate_passed = (
        bool(strict_target_depth_calls == len(rows)
             and stable_seed_blocks == len(plan["seeds"]))
        if legacy_receipt["complete"] else None
    )
    return {
        "contract": REPORT_CONTRACT,
        "bundle_sha256": sha(raw),
        "independent_receipt": legacy_receipt,
        "plan_sha256": plan["plan_sha256"],
        "event_tip": stored["event_tip"],
        "model": plan["identities"]["candidate"]["model"],
        "model_digest": plan["identities"]["candidate"]["digest"],
        "source_evidence_kind": stored["evidence_kind"],
        "source_recorded_new_model_inference": stored["new_model_inference"],
        "official_admission_gate_passed": admission_gate_passed,
        "official_admission_gate": admission_gate,
        **summarize(rows, plan["seeds"], legacy_receipt["complete"]),
        "rows": rows,
        "independent_problem_count": 1,
        "new_model_inference": False,
        "posthoc_diagnostics": True,
        "repaired_scores_generated": False,
        "legacy_parse_error_text_is_not_trusted": True,
        "limits": [
            "Node error locations are post-hoc diagnostics, not repaired proof scores.",
            "A matching final-rule label does not imply a valid target proof.",
            "Raw-derived parse category replaces unverified legacy diagnostic text in this report.",
            "One problem and repeated seeds do not support model-wide or internal causal claims.",
        ],
    }


def _exact_compare(expected: Any, actual: Any, path: str, differences: list[str]) -> int:
    """Compare values and container shape with JSON type sensitivity."""
    checked = 1
    if type(expected) is not type(actual):
        differences.append(path + " (type)")
        return checked
    if isinstance(expected, dict):
        expected_keys = set(expected)
        actual_keys = set(actual)
        if expected_keys != actual_keys:
            differences.append(path + " (keys)")
        for key in sorted(expected_keys & actual_keys):
            checked += _exact_compare(expected[key], actual[key], path + "." + key, differences)
        return checked
    if isinstance(expected, list):
        if len(expected) != len(actual):
            differences.append(path + " (length)")
        for index, (left, right) in enumerate(zip(expected, actual)):
            checked += _exact_compare(left, right, f"{path}[{index}]", differences)
        return checked
    if expected != actual:
        differences.append(path)
    return checked


def verify_report(bundle: Path, report_path: Path) -> dict[str, Any]:
    """Verify an entire v063 forensic analysis report against raw v062 evidence."""
    bundle = Path(bundle)
    report_path = Path(report_path)
    report_raw, report = _read_report(report_path)
    if not bundle.is_file():
        raise ValueError("evidence archive is not a regular file")
    if bundle.stat().st_size > 100 * 1024 * 1024:
        raise ValueError("evidence archive exceeds 100 MiB")
    bundle_before_raw = bundle.read_bytes()
    bundle_before = sha(bundle_before_raw)
    report_before = sha(report_raw)
    legacy_receipt = legacy_verify(bundle)
    if sha(bundle.read_bytes()) != bundle_before:
        raise ValueError("evidence archive changed during legacy verification")
    expected = reconstruct_report(bundle, legacy_receipt)
    if sha(bundle.read_bytes()) != bundle_before:
        raise ValueError("evidence archive changed during reconstruction")
    if (not report_path.is_file()) or report_path.stat().st_size > REPORT_LIMIT:
        raise ValueError("analysis report changed during reconstruction")
    if sha(report_path.read_bytes()) != report_before:
        raise ValueError("analysis report changed during reconstruction")

    differences: list[str] = []
    checked = _exact_compare(expected, report, "report", differences)
    if differences:
        preview = ", ".join(differences[:8])
        raise ValueError("analysis report exact comparison failed: " + preview)

    return {
        "contract": RECEIPT_CONTRACT,
        "bundle_sha256": bundle_before,
        "report_sha256": sha(report_raw),
        "complete": legacy_receipt["complete"],
        "observed_calls": legacy_receipt["observed_calls"],
        "compared_fields": checked,
        "differences": [],
        "legacy_receipt": legacy_receipt,
        "production_imports": False,
        "limitation": (
            "원문 기반 forensic report의 필드 일관성 검산이다. v062의 기존 "
            "사람이 읽는 parse_error 문구는 독립 재생성하지 않으며, raw_parse_category만 "
            "신뢰한다. 보정 증명·보정 D·새 성공 지표·외부 실행 인증은 제공하지 않는다."
        ),
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    receipt = verify_report(args.bundle, args.report)
    output = json.dumps(receipt, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(output)
    print(output, end="")


if __name__ == "__main__":
    main()
