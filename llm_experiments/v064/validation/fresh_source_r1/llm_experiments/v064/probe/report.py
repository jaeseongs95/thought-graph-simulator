"""Frozen v064 result aggregation and Korean report rendering."""
from __future__ import annotations

import base64
from collections import defaultdict
from copy import deepcopy

import common
import measure


CONTRACT = "v064-report-r1"
_USAGE_FIELDS = ("prompt_eval_count", "eval_count", "total_duration", "prompt_eval_cached_count")
_SEMANTIC_FIELDS = ("format_valid", "proof_valid", "strict_valid", "actual_D", "final_rule_id", "error_codes")
_STATES = {"complete", "stopped", "crashed"}
_RECORD_KEYS = {"id", "http_status", "error", "elapsed_ns", "request_sha256", "response_sha256", "response_b64"}


def _run_state(state) -> str:
    value = state.get("state") if isinstance(state, dict) else state
    if value not in _STATES:
        raise ValueError("state must be complete, stopped, or crashed")
    return value


def _problem_index(plan: dict) -> dict[str, dict]:
    problems = plan["protocol"]["problems"]
    indexed = {problem["id"]: problem for problem in problems}
    if len(indexed) != len(problems):
        raise ValueError("duplicate protocol problem id")
    return indexed


def _record_index(records: list[dict], slot_ids: set[str]) -> dict[str, dict]:
    if not isinstance(records, list):
        raise ValueError("records must be a list")
    indexed = {}
    for record in records:
        if (not isinstance(record, dict) or set(record) != _RECORD_KEYS
                or record.get("id") not in slot_ids):
            raise ValueError("record must refer to one planned call slot")
        if (record["http_status"] is not None and (type(record["http_status"]) is not int or record["http_status"] < 0)
                or record["error"] is not None and not isinstance(record["error"], str)
                or type(record["elapsed_ns"]) is not int or record["elapsed_ns"] < 0
                or not all(isinstance(record[key], str) for key in ("request_sha256", "response_sha256", "response_b64"))):
            raise ValueError("record observation fields have invalid types")
        slot_id = record["id"]
        if slot_id in indexed:
            raise ValueError("duplicate observed record id")
        indexed[slot_id] = record
    return indexed


def _usage(raw) -> dict:
    return {
        key: raw.get(key) if isinstance(raw, dict) and isinstance(raw.get(key), int)
        and not isinstance(raw.get(key), bool) and raw.get(key) >= 0 else None
        for key in _USAGE_FIELDS
    }


def _decode_raw(record: dict):
    encoded = record.get("response_b64")
    if encoded is None:
        return None
    if not isinstance(encoded, str):
        raise ValueError("response_b64 must be a base64 string or null")
    try:
        return common.load(base64.b64decode(encoded.encode("ascii"), validate=True))
    except (UnicodeError, ValueError):
        return None


def _base_fixed(problem: dict, payload) -> dict:
    atoms = []
    if isinstance(payload, dict) and isinstance(payload.get("nodes"), list):
        atoms = [node.get("atom") for node in payload["nodes"] if isinstance(node, dict) and isinstance(node.get("atom"), str)]
    facts = list(problem["facts"])
    goal = problem["goal"]
    return {
        "fixed_facts": facts,
        "fixed_goal": goal,
        "emitted_node_atoms": atoms,
        "added_propositions": sorted(set(atoms) - set(facts) - {goal}),
    }


def _strict_proof_path(payload) -> str | None:
    """Return a canonical rule/parent path only for an already strict proof.

    Node identifiers and list ordering are model-chosen presentation details.  The
    recursive representation instead records the final rule and its parent paths,
    so equal actual D alone is never used as evidence that a path was fixed.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("nodes"), list):
        return None
    nodes = {node["id"]: node for node in payload["nodes"] if isinstance(node, dict) and isinstance(node.get("id"), str)}
    final = payload.get("final_node_id")
    if final not in nodes:
        return None
    cache: dict[str, dict] = {}

    def visit(node_id: str) -> dict:
        if node_id not in cache:
            node = nodes[node_id]
            cache[node_id] = {
                "atom": node["atom"],
                "rule": node["rule"],
                "parents": sorted((visit(parent) for parent in node["parents"]), key=common.wire),
            }
        return cache[node_id]

    return common.sha(common.wire(visit(final)))


def _empty_semantics() -> dict:
    return {field: None for field in _SEMANTIC_FIELDS}


def _row(plan: dict, slot: dict, record: dict | None, problems: dict[str, dict]) -> dict:
    problem = problems[slot["problem_id"]]
    row = {
        **deepcopy(slot),
        "status": "not_observed",
        "http_status": None,
        "error": None,
        "elapsed_ns": None,
        "request_sha256": None,
        "response_sha256": None,
        "response_b64": None,
        **_empty_semantics(),
        "usage": _usage(None),
        "base_fixed": _base_fixed(problem, None),
    }
    if record is None:
        return row
    for key in ("http_status", "error", "elapsed_ns", "request_sha256", "response_sha256", "response_b64"):
        row[key] = deepcopy(record.get(key))
    raw = _decode_raw(record)
    status, payload = measure.parse_response(raw, record.get("http_status"), record.get("error"), plan["identity"]["model"])
    row["status"] = status
    row["usage"] = _usage(raw)
    row["base_fixed"] = _base_fixed(problem, payload)
    if status == "ok":
        row.update(measure.assess(problem, payload))
        if row["strict_valid"] is True:
            row["base_fixed"]["strict_proof_path_sha256"] = _strict_proof_path(payload)
    elif status in {"invalid_json", "invalid_schema"}:
        # The response was observed far enough to identify an output/envelope
        # format failure.  A proof, strict closure, and D remain unmeasured.
        row["format_valid"] = False
    return row


def _directed_pair(problem: dict, seed: int, rows: list[dict], ranges: dict[str, list[int]]) -> dict:
    by_direction = {row["direction"]: row for row in rows}
    shallow = by_direction["shallow"]
    deep = by_direction["deep"]
    minimum, maximum = ranges[problem["id"]]
    measurable = shallow["strict_valid"] is not None and deep["strict_valid"] is not None
    strict_min_max = None
    if measurable:
        strict_min_max = bool(
            shallow["strict_valid"] is True and deep["strict_valid"] is True
            and shallow["actual_D"] == minimum and deep["actual_D"] == maximum
            and shallow["actual_D"] != deep["actual_D"]
        )
    return {
        "problem_id": problem["id"],
        "seed": seed,
        "shallow_id": shallow["id"],
        "deep_id": deep["id"],
        "expected_min_D": minimum,
        "expected_max_D": maximum,
        "shallow_status": shallow["status"],
        "deep_status": deep["status"],
        "shallow_strict_valid": shallow["strict_valid"],
        "deep_strict_valid": deep["strict_valid"],
        "shallow_actual_D": shallow["actual_D"],
        "deep_actual_D": deep["actual_D"],
        "measurement_available": measurable,
        "strict_min_max": strict_min_max,
    }


def _neutral(problem: dict, seed: int, rows: list[dict]) -> dict:
    row = next(row for row in rows if row["direction"] == "neutral")
    return {
        "problem_id": problem["id"],
        "seed": seed,
        "id": row["id"],
        "status": row["status"],
        "strict_valid": row["strict_valid"],
        "actual_D": row["actual_D"],
        "final_rule_id": row["final_rule_id"],
        "diagnostic_only": True,
    }


def _problem_summary(problem_id: str, pairs: list[dict], rows: list[dict], full_complete: bool) -> dict:
    denominator_available = full_complete and all(pair["measurement_available"] for pair in pairs)
    strict_pairs = sum(pair["strict_min_max"] for pair in pairs) if denominator_available else None
    directed_rows = [row for row in rows if row["direction"] != "neutral"]
    all_directed_paths_measured = full_complete and all(row["strict_valid"] is True for row in directed_rows)
    paths = [row["base_fixed"].get("strict_proof_path_sha256") for row in directed_rows]
    return {
        "problem_id": problem_id,
        "assigned_directed_pairs": len(pairs),
        "measurable_directed_pairs": len(pairs) if denominator_available else None,
        "strict_min_max_pairs": strict_pairs,
        "strict_min_max_rate": strict_pairs / len(pairs) if denominator_available and pairs else None,
        "all_directed_same_strict_proof_path": (
            len(set(paths)) == 1 and paths[0] is not None if all_directed_paths_measured else None
        ),
    }


def summarize(plan: dict, records: list[dict], state) -> dict:
    """Return all planned rows, keeping missing and parse failures distinct."""
    if plan.get("contract") != "v064-plan-r1":
        raise ValueError("v064 plan contract required")
    run_state = _run_state(state)
    problems = _problem_index(plan)
    slots = plan["slots"]
    record_by_id = _record_index(records, {slot["id"] for slot in slots})
    rows = [_row(plan, slot, record_by_id.get(slot["id"]), problems) for slot in slots]
    grouped: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["problem_id"], row["seed"]].append(row)
    ranges = plan["protocol"]["depth_ranges"]
    directed_pairs = []
    neutral_diagnostics = []
    for problem in plan["protocol"]["problems"]:
        for seed in plan["protocol"]["seeds"]:
            block_rows = grouped[problem["id"], seed]
            if len(block_rows) != 3 or {row["direction"] for row in block_rows} != {"shallow", "neutral", "deep"}:
                raise ValueError("planned block does not contain three directions")
            directed_pairs.append(_directed_pair(problem, seed, block_rows, ranges))
            neutral_diagnostics.append(_neutral(problem, seed, block_rows))
    observed_calls = sum(row["status"] != "not_observed" for row in rows)
    full_complete = run_state == "complete" and observed_calls == len(rows)
    directed_denominator_available = full_complete and all(pair["measurement_available"] for pair in directed_pairs)
    all_directed = all(pair["strict_min_max"] for pair in directed_pairs) if directed_denominator_available else None
    development = plan["protocol"]["development_problem"]
    development_pairs = [pair for pair in directed_pairs if pair["problem_id"] == development]
    evaluation_pairs = [pair for pair in directed_pairs if pair["problem_id"] != development]
    summaries = [_problem_summary(problem["id"], [pair for pair in directed_pairs if pair["problem_id"] == problem["id"]],
                                  [row for row in rows if row["problem_id"] == problem["id"]], full_complete)
                 for problem in plan["protocol"]["problems"]]
    parse_or_envelope_failures = sum(row["status"] in {"invalid_json", "invalid_schema", "incomplete_response"} for row in rows)
    logical_failures = sum(row["status"] == "ok" and row["strict_valid"] is False for row in rows)
    same_strict_proof_path_observed = (
        any(summary["all_directed_same_strict_proof_path"] is True for summary in summaries)
        if full_complete and all(summary["all_directed_same_strict_proof_path"] is not None for summary in summaries)
        else None
    )
    bounded_pilot = (
        None if all_directed is None
        else False if same_strict_proof_path_observed is True
        else all_directed
    )
    return {
        "contract": CONTRACT,
        "run_name": plan["run_name"],
        "provenance": plan["provenance"],
        "plan_sha256": plan["plan_sha256"],
        "state": run_state,
        "assigned_calls": len(rows),
        "observed_calls": observed_calls,
        "full_complete": full_complete,
        "rows": rows,
        "problem_summaries": summaries,
        "directed_pairs": directed_pairs,
        "neutral_diagnostics": neutral_diagnostics,
        "overall": {
            "directed_pair_denominator": len(directed_pairs) if directed_denominator_available else None,
            "strict_min_max_pairs": (sum(pair["strict_min_max"] for pair in directed_pairs)
                                       if directed_denominator_available else None),
            "strict_min_max_rate": (sum(pair["strict_min_max"] for pair in directed_pairs) / len(directed_pairs)
                                    if directed_denominator_available and directed_pairs else None),
            "development_pairs": (len(development_pairs)
                                  if full_complete and all(pair["measurement_available"] for pair in development_pairs) else None),
            "development_strict_min_max_pairs": (sum(pair["strict_min_max"] for pair in development_pairs)
                                                   if full_complete and all(pair["measurement_available"] for pair in development_pairs) else None),
            "evaluation_pairs": (len(evaluation_pairs)
                                  if full_complete and all(pair["measurement_available"] for pair in evaluation_pairs) else None),
            "evaluation_strict_min_max_pairs": (sum(pair["strict_min_max"] for pair in evaluation_pairs)
                                                  if full_complete and all(pair["measurement_available"] for pair in evaluation_pairs) else None),
            "bounded_A_or_M_pilot": bounded_pilot,
            "same_strict_proof_path_observed": same_strict_proof_path_observed,
        },
        "usage": {
            field: sum(row["usage"][field] for row in rows if row["usage"][field] is not None)
            if full_complete and all(row["usage"][field] is not None for row in rows) else None
            for field in _USAGE_FIELDS
        },
        "limits": {
            "A": "not_measured",
            "M": "not_measured",
            "neutral": "diagnostic_only",
            "evaluation_scope": plan["protocol"]["evaluation_scope"],
            "repeated_seeds_are_independent_problems": False,
            "metadata_is_not_cache_reset": True,
            "parse_or_envelope_failures": parse_or_envelope_failures,
            "logical_failures": logical_failures,
        },
    }


def render(report: dict) -> str:
    """Render the frozen Korean human-readable summary without altering scores."""
    overall = report["overall"]
    decision = overall["bounded_A_or_M_pilot"]
    decision_text = "미판정" if decision is None else ("통과" if decision else "불통과")
    lines = [
        "# v064 직접 D 대조 결과",
        "",
        f"실행 상태: {report['state']} / 관측 호출: {report['observed_calls']}/{report['assigned_calls']} / 완결 분모: {report['full_complete']}",
        f"기록 성격(provenance): {report['provenance']}",
        f"주판정(여섯 directed 대응쌍 모두 strict·최소/최대 실제 D): {decision_text}",
        "",
        "|문제|directed 쌍|strict 최소/최대 쌍|모든 directed 규칙·부모 경로 동일|",
        "|---|---:|---:|---:|",
    ]
    for summary in report["problem_summaries"]:
        lines.append("|{problem_id}|{assigned_directed_pairs}|{strict_min_max_pairs}|{all_directed_same_strict_proof_path}|".format(**summary))
    lines.extend([
        "",
        "neutral 조건은 진단용이며 주 성공 지표에 포함하지 않는다.",
        "파싱·envelope 실패와 논리적 증명 실패는 별도로 기록한다. 미관측 또는 비완결 실행에서는 전체 비율을 제시하지 않는다.",
        "T02는 개발 기준선이고 E01_shared_fork·E02_two_vs_four는 설계자가 정한 사전 미관측 구조다. 구조적 평가문제 두 개이지만 무작위 모집단이나 외부 독립 holdout은 아니다.",
        "A와 M은 이번 D-only 대조에서 측정하지 않는다. 실제 D는 모든 노드가 유효하고 최종 조상 closure를 만족할 때만 기록한다.",
    ])
    return "\n".join(lines) + "\n"
