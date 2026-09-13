"""독립적인 v064 증거 번들 검산기.

이 모듈은 ``design``, ``measure``, ``report``, ``run``을 import하지 않는다.
공유하는 것은 바이트/JSON/ZIP 계약을 가진 ``common``과 동결 protocol뿐이다.
"""
from __future__ import annotations

import argparse
import base64
import copy
import json
import sys
import urllib.parse
from collections import Counter, defaultdict
from pathlib import Path

import common


PLAN_CONTRACT = "v064-plan-r1"
EVIDENCE_CONTRACT = "v064-evidence-r1"
REPORT_CONTRACT = "v064-report-r1"
VERIFY_CONTRACT = "v064-independent-verify-r1"
_DIRECTION = {
    "shallow": "허용된 유효한 증명 중 최종 지지 깊이가 가장 작은 경로를 선택한다.",
    "neutral": "허용된 유효한 증명 경로 하나를 선택한다.",
    "deep": "허용된 유효한 증명 중 최종 지지 깊이가 가장 큰 경로를 선택한다.",
}
_BASELINE_DIRECTION = _DIRECTION["shallow"]
_USAGE_FIELDS = ("prompt_eval_count", "eval_count", "total_duration", "prompt_eval_cached_count")
_SEMANTIC_FIELDS = ("format_valid", "proof_valid", "strict_valid", "actual_D", "final_rule_id", "error_codes")
_STATUS = {"ok", "invalid_json", "invalid_schema", "incomplete_response", "http_error", "transport_error", "identity_error"}
_STOP_REASONS = {"transport_error", "http_error", "identity_error", "generation_budget_exceeded", "metadata_identity_error"}


class VerificationError(ValueError):
    """A bundle violated its frozen evidence contract."""


def _fail(message: str) -> None:
    raise VerificationError(message)


def _object(raw: bytes, name: str) -> dict:
    try:
        value = common.load(raw)
    except (UnicodeError, ValueError) as exc:
        raise VerificationError(name + ": invalid JSON") from exc
    if not isinstance(value, dict):
        _fail(name + ": JSON object required")
    return value


def _saved(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _require_exact_raw(files: dict[str, bytes], name: str, value) -> None:
    if files.get(name) != _saved(value):
        _fail(name + ": noncanonical or altered JSON bytes")


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _nonnegative(value, name: str, *, null: bool = False) -> None:
    if value is None and null:
        return
    if not _is_int(value) or value < 0:
        _fail(name + ": non-negative integer required")


def _base64(value, name: str) -> bytes:
    if not isinstance(value, str):
        _fail(name + ": base64 string required")
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except (UnicodeError, ValueError) as exc:
        raise VerificationError(name + ": invalid base64") from exc


def _hex_sha(value, name: str) -> None:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        _fail(name + ": lower-case SHA-256 required")


def _expect_keys(value: dict, keys: set[str], name: str) -> None:
    if set(value) != keys:
        _fail(name + ": unexpected fields")


def _slot_schedule(protocol: dict) -> list[dict]:
    problems, seeds, orders = protocol["problems"], protocol["seeds"], protocol["orders"]
    if len(problems) * len(seeds) != len(orders):
        _fail("protocol: order/block count mismatch")
    result, previous_id, previous_direction = [], None, None
    for problem_index, problem in enumerate(problems):
        problem_id = problem.get("id")
        if not isinstance(problem_id, str):
            _fail("protocol: problem id")
        for seed_index, seed in enumerate(seeds):
            if not _is_int(seed):
                _fail("protocol: seed")
            block = problem_index * len(seeds) + seed_index
            order = orders[block]
            if not isinstance(order, list) or len(order) != 3 or set(order) != set(_DIRECTION):
                _fail("protocol: each block must contain every direction once")
            for period, direction in enumerate(order):
                slot = {
                    "id": f"b{block:02d}_p{problem_index}_{direction}",
                    "problem_id": problem_id,
                    "seed": seed,
                    "seed_index": seed_index,
                    "block": block,
                    "period": period,
                    "direction": direction,
                    "previous_call_id": previous_id,
                    "previous_direction": previous_direction,
                }
                result.append(slot)
                previous_id, previous_direction = slot["id"], direction
    if len(result) != protocol["max_inference_calls"]:
        _fail("protocol: inference count")
    return result


def _actions(slots: list[dict], blocks: int) -> list[dict]:
    result = []
    for block in range(blocks):
        block_slots = [slot for slot in slots if slot["block"] == block]
        if len(block_slots) != 3:
            _fail("slot schedule: block cardinality")
        result.append({"kind": "metadata", "id": f"b{block:02d}_before"})
        result.extend({"kind": "call", "id": slot["id"]} for slot in block_slots)
        result.append({"kind": "metadata", "id": f"b{block:02d}_after"})
    return result


def _baseline(files: dict[str, bytes], protocol: dict) -> tuple[dict, dict]:
    raw = files.get("baseline/v058_evidence.zip")
    if raw is None:
        _fail("baseline/v058_evidence.zip missing")
    if common.sha(raw) != protocol["baseline_sha256"]:
        _fail("baseline ZIP SHA-256")
    try:
        source = common.unzip(raw)
    except (ValueError, OSError) as exc:
        raise VerificationError("baseline ZIP invalid") from exc
    plan_name = "external_plan/v058.plan.json"
    request_name = "run/calls/" + protocol["baseline_request_id"] + "/request.wire.json"
    if plan_name not in source or request_name not in source:
        _fail("baseline required v058 members missing")
    source_plan = _object(source[plan_name], "baseline plan")
    baseline_request = _object(source[request_name], "baseline request")
    try:
        identity = source_plan["identities"]["reference"]
    except (KeyError, TypeError) as exc:
        raise VerificationError("baseline reference identity missing") from exc
    if not isinstance(identity, dict):
        _fail("baseline reference identity")
    if baseline_request.get("model") != protocol["model"]:
        _fail("baseline request model")
    if identity.get("model") != protocol["model"] or identity.get("digest") != protocol["model_digest"]:
        _fail("baseline identity model")
    return baseline_request, identity


def _verify_plan(files: dict[str, bytes]) -> tuple[dict, list[dict], list[dict], dict]:
    if "plan.json" not in files:
        _fail("plan.json missing")
    plan = _object(files["plan.json"], "plan.json")
    _expect_keys(plan, {"contract", "run_name", "provenance", "protocol", "protocol_sha256", "source_hashes",
                        "baseline_sha256", "baseline_request", "identity", "slots", "actions", "plan_sha256"}, "plan")
    if plan["contract"] != PLAN_CONTRACT:
        _fail("plan contract")
    try:
        common.check_run_name(plan["run_name"])
    except ValueError as exc:
        raise VerificationError("plan run_name") from exc
    if plan["provenance"] not in {"live", "synthetic"}:
        _fail("plan provenance")
    protocol = common.spec()
    if not common.exact(plan["protocol"], protocol):
        _fail("plan protocol differs from frozen protocol")
    raw_protocol = (common.ROOT / "data" / "protocol.json").read_bytes()
    if plan["protocol_sha256"] != common.sha(raw_protocol):
        _fail("plan protocol SHA-256")
    if not common.exact(plan["source_hashes"], common.source_hashes()):
        _fail("plan source fingerprint differs from verifier source")
    without_hash = dict(plan)
    given_plan_sha = without_hash.pop("plan_sha256")
    _hex_sha(given_plan_sha, "plan_sha256")
    if given_plan_sha != common.sha(common.wire(without_hash)):
        _fail("plan_sha256")
    baseline_request, identity = _baseline(files, protocol)
    if plan["baseline_sha256"] != protocol["baseline_sha256"]:
        _fail("plan baseline_sha256")
    if not common.exact(plan["baseline_request"], baseline_request):
        _fail("plan baseline_request")
    if not common.exact(plan["identity"], identity):
        _fail("plan identity")
    slots = _slot_schedule(protocol)
    if not common.exact(plan["slots"], slots):
        _fail("plan slots")
    actions = _actions(slots, len(protocol["problems"]) * len(protocol["seeds"]))
    if not common.exact(plan["actions"], actions):
        _fail("plan actions")
    _require_exact_raw(files, "plan.json", plan)
    return plan, slots, actions, protocol


def _verify_runtime(files: dict[str, bytes], plan: dict) -> None:
    if "runtime.json" not in files:
        _fail("runtime.json missing")
    runtime = _object(files["runtime.json"], "runtime.json")
    _expect_keys(runtime, {"endpoint", "provenance"}, "runtime")
    if runtime["provenance"] != plan["provenance"] or not isinstance(runtime["endpoint"], str):
        _fail("runtime fields")
    try:
        parsed = urllib.parse.urlsplit(runtime["endpoint"])
    except ValueError as exc:
        raise VerificationError("runtime endpoint") from exc
    if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}):
        _fail("runtime endpoint is not loopback HTTP")
    _require_exact_raw(files, "runtime.json", runtime)


def _verify_sources(files: dict[str, bytes], plan: dict) -> set[str]:
    current = common.sources()
    expected = set(current)
    seen = {name[len("source/"):] for name in files if name.startswith("source/")}
    if seen != expected:
        _fail("source snapshot membership")
    for name, raw in current.items():
        archived = files.get("source/" + name)
        if archived != raw or plan["source_hashes"].get(name) != common.sha(archived):
            _fail("source snapshot fingerprint: " + name)
    return {"source/" + name for name in expected}


def _parse_events(files: dict[str, bytes], plan: dict, actions: list[dict]) -> tuple[list[dict], list[dict]]:
    name = "records/events.jsonl"
    if name not in files:
        _fail("records/events.jsonl missing")
    raw = files[name]
    if raw and not raw.endswith(b"\n"):
        _fail("events JSONL final newline")
    events = [] if not raw else [_object(line, "event") for line in raw.splitlines()]
    if len(events) > len(actions):
        _fail("too many events")
    tip = plan["plan_sha256"]
    for index, event in enumerate(events):
        _expect_keys(event, {"action", "record_sha256", "previous_hash", "event_hash"}, "event")
        if not common.exact(event["action"], actions[index]):
            _fail("event action sequence")
        _hex_sha(event["record_sha256"], "event record_sha256")
        _hex_sha(event["previous_hash"], "event previous_hash")
        _hex_sha(event["event_hash"], "event event_hash")
        if event["previous_hash"] != tip:
            _fail("event previous_hash chain")
        bare = dict(event)
        event_hash = bare.pop("event_hash")
        if event_hash != common.sha(common.wire(bare)):
            _fail("event_hash")
        tip = event_hash
    if raw != b"".join(common.wire(event) + b"\n" for event in events):
        _fail("events noncanonical bytes")
    return events, actions[:len(events)]


def _started_markers(files: dict[str, bytes], plan: dict, actions: list[dict], status: dict) -> list[dict]:
    count = status["started_actions"]
    markers = [name for name in files if name.startswith("records/") and name.endswith(".started.json")]
    expected = actions[:count]
    expected_names = {"records/" + action["id"] + ".started.json" for action in expected}
    if set(markers) != expected_names:
        _fail("started marker membership")
    for action in expected:
        name = "records/" + action["id"] + ".started.json"
        marker = _object(files[name], name)
        if not common.exact(marker, {"action": action, "plan_sha256": plan["plan_sha256"]}):
            _fail("started marker value")
        if files[name] != common.wire(marker):
            _fail("started marker bytes")
    return expected


def _valid_http(value) -> bool:
    return value is None or (_is_int(value) and 100 <= value <= 599)


def _valid_error(value) -> bool:
    return value is None or isinstance(value, str)


def _request_for(plan: dict, slot: dict) -> bytes:
    body = copy.deepcopy(plan["baseline_request"])
    try:
        messages, options = body["messages"], body["options"]
        content = messages[0]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise VerificationError("baseline request shape") from exc
    if not isinstance(content, str) or not isinstance(options, dict) or len(messages) != 1 or messages[0].get("role") != "user":
        _fail("baseline request message shape")
    if content.count(_BASELINE_DIRECTION) != 1 or content.count("\n\nproblem: ") != 1:
        _fail("baseline request change anchors")
    problem = next((p for p in plan["protocol"]["problems"] if p.get("id") == slot["problem_id"]), None)
    if problem is None:
        _fail("request unknown problem")
    prefix, _, _old = content.partition("\n\nproblem: ")
    messages[0]["content"] = prefix.replace(_BASELINE_DIRECTION, _DIRECTION[slot["direction"]]) + "\n\nproblem: " + common.wire(problem).decode("utf-8")
    options["seed"] = slot["seed"]
    raw = common.wire(body)
    if len(raw) > plan["protocol"]["request_utf8_byte_limit"]:
        _fail("reconstructed request byte limit")
    return raw


def _call_stop_reason(record: dict, model: str, num_predict: int) -> str | None:
    if record["error"] is not None:
        return "transport_error"
    if record["http_status"] != 200:
        return "http_error"
    raw = _base64(record["response_b64"], "call response_b64")
    try:
        envelope = common.load(raw)
    except (UnicodeError, ValueError):
        return None
    if not isinstance(envelope, dict) or envelope.get("model") != model:
        return "identity_error"
    if _is_int(envelope.get("eval_count")) and envelope["eval_count"] > num_predict:
        return "generation_budget_exceeded"
    return None


def _validate_call(files: dict[str, bytes], plan: dict, action: dict) -> tuple[dict, set[str]]:
    record_name = "records/" + action["id"] + ".json"
    if record_name not in files:
        _fail(record_name + " missing")
    record = _object(files[record_name], record_name)
    _expect_keys(record, {"id", "kind", "http_status", "error", "elapsed_ns", "request_sha256", "response_sha256", "response_b64"}, "call record")
    if record["id"] != action["id"] or record["kind"] != "call":
        _fail("call record action identity")
    if not _valid_http(record["http_status"]) or not _valid_error(record["error"]):
        _fail("call record transport fields")
    _nonnegative(record["elapsed_ns"], "call elapsed_ns")
    _hex_sha(record["request_sha256"], "call request_sha256")
    _hex_sha(record["response_sha256"], "call response_sha256")
    response = _base64(record["response_b64"], "call response_b64")
    request_name = "wire/" + action["id"] + "/request.wire.json"
    response_name = "wire/" + action["id"] + "/response.raw.json"
    if request_name not in files or response_name not in files:
        _fail("call wire member missing")
    request = files[request_name]
    if request != _request_for(plan, next(slot for slot in plan["slots"] if slot["id"] == action["id"])):
        _fail("call request differs from frozen reconstruction")
    if len(response) > 1024 ** 2 + 1:
        _fail("call response wire")
    if record["request_sha256"] != common.sha(request) or record["response_sha256"] != common.sha(response):
        _fail("call wire hash")
    if files[response_name] != response:
        _fail("call response wire binding")
    if files[record_name] != common.wire(record):
        _fail("call record bytes")
    return record, {record_name, request_name, response_name}


def _identity_matches(items: list[dict], expected: dict) -> bool:
    if len(items) != 3 or any(item["http_status"] != 200 or item["error"] is not None for item in items):
        return False
    try:
        server, tags, show = [common.load(_base64(item["response_b64"], "metadata response_b64")) for item in items]
        candidates = [model for model in tags["models"] if model.get("name") == expected["model"] or model.get("model") == expected["model"]]
        if len(candidates) != 1:
            return False
        got = {"model": expected["model"], "digest": candidates[0]["digest"], "server": server,
               "details": show.get("details", candidates[0].get("details", {})), "template": show.get("template"),
               "model_info": show.get("model_info", {}), "parameters": show.get("parameters")}
        wanted = {key: expected[key] for key in got}
        for value in (got, wanted):
            if value["parameters"] is not None:
                if not isinstance(value["parameters"], str):
                    return False
                value["parameters"] = sorted(value["parameters"].split("\n"))
        return common.exact(got, wanted)
    except (KeyError, TypeError, UnicodeError, ValueError):
        return False


def _validate_metadata(files: dict[str, bytes], plan: dict, action: dict) -> tuple[dict, set[str]]:
    record_name = "records/" + action["id"] + ".json"
    if record_name not in files:
        _fail(record_name + " missing")
    record = _object(files[record_name], record_name)
    _expect_keys(record, {"id", "kind", "items", "identity_ok"}, "metadata record")
    if record["id"] != action["id"] or record["kind"] != "metadata" or not isinstance(record["identity_ok"], bool):
        _fail("metadata record identity")
    if not isinstance(record["items"], list) or not 1 <= len(record["items"]) <= 3:
        _fail("metadata item count")
    patterns = (("server", "/api/version"), ("tags", "/api/tags"), ("show", "/api/show"))
    names = {record_name}
    previous_failed = False
    for index, item in enumerate(record["items"]):
        if not isinstance(item, dict):
            _fail("metadata item object")
        _expect_keys(item, {"name", "path", "request_b64", "response_b64", "http_status", "error", "elapsed_ns"}, "metadata item")
        if (item["name"], item["path"]) != patterns[index] or previous_failed:
            _fail("metadata endpoint sequence")
        if not _valid_http(item["http_status"]) or not _valid_error(item["error"]):
            _fail("metadata transport fields")
        _nonnegative(item["elapsed_ns"], "metadata elapsed_ns")
        request_name = "metadata/" + action["id"] + "/" + str(index) + ".request.json"
        response_name = "metadata/" + action["id"] + "/" + str(index) + ".response.raw.json"
        if request_name not in files or response_name not in files:
            _fail("metadata wire member missing")
        expected_request = common.wire({"model": plan["identity"]["model"]}) if item["name"] == "show" else b""
        if item["name"] == "show":
            if item["request_b64"] != base64.b64encode(expected_request).decode("ascii"):
                _fail("metadata show request")
        elif item["request_b64"] is not None:
            _fail("metadata GET request_b64")
        if files[request_name] != expected_request:
            _fail("metadata request wire")
        response = _base64(item["response_b64"], "metadata response_b64")
        if len(response) > 1024 ** 2 + 1 or files[response_name] != response:
            _fail("metadata response wire")
        names.update({request_name, response_name})
        previous_failed = item["http_status"] != 200 or item["error"] is not None
    if files[record_name] != common.wire(record):
        _fail("metadata record bytes")
    if record["identity_ok"] != _identity_matches(record["items"], plan["identity"]):
        _fail("metadata identity result")
    return record, names


def _schema_valid(payload) -> bool:
    if not isinstance(payload, dict) or set(payload) != {"nodes", "final_node_id"}:
        return False
    if not isinstance(payload["nodes"], list) or not 1 <= len(payload["nodes"]) <= 16 or not _text(payload["final_node_id"]):
        return False
    for node in payload["nodes"]:
        if not isinstance(node, dict) or set(node) != {"id", "atom", "rule", "parents"}:
            return False
        if not _text(node["id"]) or not _text(node["atom"]) or (node["rule"] is not None and not _text(node["rule"])):
            return False
        if not isinstance(node["parents"], list) or len(node["parents"]) > 16 or not all(_text(parent) for parent in node["parents"]):
            return False
    return True


def _text(value) -> bool:
    return isinstance(value, str) and 1 <= len(value) <= 128


def _has_cycle(nodes: dict[str, dict]) -> bool:
    """Kahn elimination is deliberately independent from the producer DFS."""
    remaining = set(nodes)
    while True:
        removable = {node_id for node_id in remaining if not any(parent in remaining for parent in nodes[node_id]["parents"])}
        if not removable:
            return bool(remaining)
        remaining.difference_update(removable)
        if not remaining:
            return False


def _closure(nodes: dict[str, dict], final_id: str) -> set[str]:
    found = {final_id}
    while True:
        expanded = found | {parent for node_id in found for parent in nodes[node_id]["parents"] if parent in nodes}
        if expanded == found:
            return found
        found = expanded


def _topological(emitted_nodes: list[dict]) -> bool:
    """Check the prompt-required presentation order separately from proof logic."""
    seen: set[str] = set()
    for node in emitted_nodes:
        if any(parent not in seen for parent in node["parents"]):
            return False
        seen.add(node["id"])
    return True


def _depth_fixedpoint(nodes: dict[str, dict], final_id: str) -> int:
    values: dict[str, int] = {}
    while final_id not in values:
        changed = False
        for node_id, node in nodes.items():
            if node_id in values:
                continue
            if node["rule"] is None:
                values[node_id] = 0
                changed = True
            elif all(parent in values for parent in node["parents"]):
                values[node_id] = 1 + max(values[parent] for parent in node["parents"])
                changed = True
        if not changed:
            _fail("strict DAG did not converge")
    return values[final_id]


def _semantic(problem: dict, payload) -> dict:
    if not _schema_valid(payload):
        return {"format_valid": False, "proof_valid": None, "strict_valid": None, "actual_D": None,
                "final_rule_id": None, "error_codes": ["schema_invalid"]}
    errors, nodes = [], {}
    for node in payload["nodes"]:
        if node["id"] in nodes:
            errors.append("duplicate_id")
        else:
            nodes[node["id"]] = node
    rules = {rule["id"]: rule for rule in problem.get("rules", []) if isinstance(rule, dict) and isinstance(rule.get("id"), str)}
    facts = set(problem.get("facts", []))
    final = nodes.get(payload["final_node_id"])
    final_rule_id = None if final is None else final["rule"]
    if final is None:
        errors.append("missing_final_node")
    elif final["atom"] != problem.get("goal"):
        errors.append("final_goal_mismatch")
    for node in nodes.values():
        parents = node["parents"]
        if len(parents) != len(set(parents)):
            errors.append("duplicate_parent")
        missing = [parent for parent in parents if parent not in nodes]
        if missing:
            errors.append("missing_parent")
        if node["rule"] is None:
            if parents:
                errors.append("fact_with_parents")
            if node["atom"] not in facts:
                errors.append("unreachable_fact")
            continue
        rule = rules.get(node["rule"])
        if rule is None:
            errors.append("unregistered_rule")
            continue
        if node["atom"] != rule.get("conclusion"):
            errors.append("wrong_atom")
        if not missing and Counter(nodes[parent]["atom"] for parent in parents) != Counter(rule.get("premises", [])):
            errors.append("premise_counter_mismatch")
    if _has_cycle(nodes):
        errors.append("cycle")
    if errors:
        return {"format_valid": True, "proof_valid": False, "strict_valid": False, "actual_D": None,
                "final_rule_id": final_rule_id, "error_codes": sorted(set(errors))}
    strict_errors = []
    if _closure(nodes, payload["final_node_id"]) != set(nodes):
        strict_errors.append("extra_unused_node")
    if not _topological(payload["nodes"]):
        strict_errors.append("non_topological_order")
    if strict_errors:
        return {"format_valid": True, "proof_valid": True, "strict_valid": False, "actual_D": None,
                "final_rule_id": final_rule_id, "error_codes": sorted(set(strict_errors))}
    return {"format_valid": True, "proof_valid": True, "strict_valid": True,
            "actual_D": _depth_fixedpoint(nodes, payload["final_node_id"]), "final_rule_id": final_rule_id, "error_codes": []}


def _parse_response(raw, http_status, error, model):
    if http_status is None or not 200 <= http_status < 300:
        return "transport_error" if http_status is None else "http_error", None
    if error is not None:
        return "transport_error", None
    if not isinstance(raw, dict):
        return "invalid_json", None
    if raw.get("model") != model:
        return "identity_error", None
    if raw.get("done") is not True or raw.get("done_reason") != "stop":
        return "incomplete_response", None
    message = raw.get("message")
    if not isinstance(message, dict) or message.get("role") != "assistant" or message.get("tool_calls"):
        return "invalid_schema", None
    if not isinstance(message.get("content"), str):
        return "invalid_schema", None
    try:
        return "ok", common.load(message["content"])
    except (UnicodeError, ValueError):
        return "invalid_json", None


def _usage(raw) -> dict:
    return {key: raw.get(key) if isinstance(raw, dict) and _is_int(raw.get(key)) and raw.get(key) >= 0 else None
            for key in _USAGE_FIELDS}


def _base_fixed(problem: dict, payload) -> dict:
    atoms = [node.get("atom") for node in payload.get("nodes", []) if isinstance(node, dict) and isinstance(node.get("atom"), str)] if isinstance(payload, dict) and isinstance(payload.get("nodes"), list) else []
    facts, goal = list(problem["facts"]), problem["goal"]
    return {"fixed_facts": facts, "fixed_goal": goal, "emitted_node_atoms": atoms,
            "added_propositions": sorted(set(atoms) - set(facts) - {goal})}


def _strict_path(payload) -> str | None:
    """Canonicalize a strict proof without trusting producer path metrics."""
    if not isinstance(payload, dict) or not isinstance(payload.get("nodes"), list):
        return None
    nodes = {node["id"]: node for node in payload["nodes"] if isinstance(node, dict) and isinstance(node.get("id"), str)}
    final = payload.get("final_node_id")
    if final not in nodes:
        return None
    values = {}
    while final not in values:
        changed = False
        for node_id, node in nodes.items():
            if node_id in values or not all(parent in values for parent in node["parents"]):
                continue
            values[node_id] = {"atom": node["atom"], "rule": node["rule"],
                               "parents": sorted((values[parent] for parent in node["parents"]), key=common.wire)}
            changed = True
        if not changed:
            return None
    return common.sha(common.wire(values[final]))


def _row(plan: dict, slot: dict, record: dict | None, problems: dict[str, dict]) -> dict:
    problem = problems[slot["problem_id"]]
    row = {**copy.deepcopy(slot), "status": "not_observed", "http_status": None, "error": None, "elapsed_ns": None,
           "request_sha256": None, "response_sha256": None, "response_b64": None,
           **{field: None for field in _SEMANTIC_FIELDS}, "usage": _usage(None), "base_fixed": _base_fixed(problem, None)}
    if record is None:
        return row
    for key in ("http_status", "error", "elapsed_ns", "request_sha256", "response_sha256", "response_b64"):
        row[key] = copy.deepcopy(record.get(key))
    try:
        raw = _base64(record["response_b64"], "row response_b64")
        envelope = common.load(raw)
    except (UnicodeError, ValueError):
        envelope = None
    status, payload = _parse_response(envelope, record["http_status"], record["error"], plan["identity"]["model"])
    row["status"], row["usage"], row["base_fixed"] = status, _usage(envelope), _base_fixed(problem, payload)
    if status == "ok":
        row.update(_semantic(problem, payload))
        if row["strict_valid"] is True:
            row["base_fixed"]["strict_proof_path_sha256"] = _strict_path(payload)
    elif status in {"invalid_json", "invalid_schema"}:
        row["format_valid"] = False
    return row


def _pair(problem: dict, seed: int, rows: list[dict], ranges: dict) -> dict:
    by_direction = {row["direction"]: row for row in rows}
    shallow, deep = by_direction["shallow"], by_direction["deep"]
    minimum, maximum = ranges[problem["id"]]
    measurable = shallow["strict_valid"] is not None and deep["strict_valid"] is not None
    strict = None
    if measurable:
        strict = bool(shallow["strict_valid"] is True and deep["strict_valid"] is True and shallow["actual_D"] == minimum
                      and deep["actual_D"] == maximum and shallow["actual_D"] != deep["actual_D"])
    return {"problem_id": problem["id"], "seed": seed, "shallow_id": shallow["id"], "deep_id": deep["id"],
            "expected_min_D": minimum, "expected_max_D": maximum, "shallow_status": shallow["status"], "deep_status": deep["status"],
            "shallow_strict_valid": shallow["strict_valid"], "deep_strict_valid": deep["strict_valid"],
            "shallow_actual_D": shallow["actual_D"], "deep_actual_D": deep["actual_D"],
            "measurement_available": measurable, "strict_min_max": strict}


def _neutral(problem: dict, seed: int, rows: list[dict]) -> dict:
    row = next(row for row in rows if row["direction"] == "neutral")
    return {"problem_id": problem["id"], "seed": seed, "id": row["id"], "status": row["status"],
            "strict_valid": row["strict_valid"], "actual_D": row["actual_D"], "final_rule_id": row["final_rule_id"], "diagnostic_only": True}


def _problem_summary(problem_id: str, pairs: list[dict], rows: list[dict], full_complete: bool) -> dict:
    denominator_available = full_complete and all(pair["measurement_available"] for pair in pairs)
    strict_pairs = sum(pair["strict_min_max"] for pair in pairs) if denominator_available else None
    directed = [row for row in rows if row["direction"] != "neutral"]
    paths_measured = full_complete and all(row["strict_valid"] is True for row in directed)
    paths = [row["base_fixed"].get("strict_proof_path_sha256") for row in directed]
    return {"problem_id": problem_id, "assigned_directed_pairs": len(pairs),
            "measurable_directed_pairs": len(pairs) if denominator_available else None,
            "strict_min_max_pairs": strict_pairs,
            "strict_min_max_rate": strict_pairs / len(pairs) if denominator_available and pairs else None,
            "all_directed_same_strict_proof_path": (len(set(paths)) == 1 and paths[0] is not None if paths_measured else None)}


def _summary(plan: dict, calls: list[dict], state: str) -> dict:
    problems = {problem["id"]: problem for problem in plan["protocol"]["problems"]}
    indexed = {record["id"]: record for record in calls}
    rows = [_row(plan, slot, indexed.get(slot["id"]), problems) for slot in plan["slots"]]
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["problem_id"], row["seed"]].append(row)
    pairs, neutral = [], []
    for problem in plan["protocol"]["problems"]:
        for seed in plan["protocol"]["seeds"]:
            block_rows = grouped[problem["id"], seed]
            if len(block_rows) != 3 or {row["direction"] for row in block_rows} != set(_DIRECTION):
                _fail("summary block schedule")
            pairs.append(_pair(problem, seed, block_rows, plan["protocol"]["depth_ranges"]))
            neutral.append(_neutral(problem, seed, block_rows))
    observed = sum(row["status"] != "not_observed" for row in rows)
    full = state == "complete" and observed == len(rows)
    development = plan["protocol"]["development_problem"]
    dev_pairs = [pair for pair in pairs if pair["problem_id"] == development]
    eval_pairs = [pair for pair in pairs if pair["problem_id"] != development]
    summaries = [_problem_summary(problem["id"], [pair for pair in pairs if pair["problem_id"] == problem["id"]],
                                  [row for row in rows if row["problem_id"] == problem["id"]], full)
                 for problem in plan["protocol"]["problems"]]
    denominator_available = full and all(pair["measurement_available"] for pair in pairs)
    all_directed = all(pair["strict_min_max"] for pair in pairs) if denominator_available else None
    same_path = (any(summary["all_directed_same_strict_proof_path"] is True for summary in summaries)
                 if full and all(summary["all_directed_same_strict_proof_path"] is not None for summary in summaries) else None)
    bounded = None if all_directed is None else False if same_path is True else all_directed
    return {"contract": REPORT_CONTRACT, "run_name": plan["run_name"], "provenance": plan["provenance"], "plan_sha256": plan["plan_sha256"],
            "state": state, "assigned_calls": len(rows), "observed_calls": observed, "full_complete": full, "rows": rows,
            "problem_summaries": summaries, "directed_pairs": pairs, "neutral_diagnostics": neutral,
            "overall": {"directed_pair_denominator": len(pairs) if denominator_available else None,
                        "strict_min_max_pairs": sum(pair["strict_min_max"] for pair in pairs) if denominator_available else None,
                        "strict_min_max_rate": sum(pair["strict_min_max"] for pair in pairs) / len(pairs) if denominator_available and pairs else None,
                        "development_pairs": len(dev_pairs) if full and all(pair["measurement_available"] for pair in dev_pairs) else None,
                        "development_strict_min_max_pairs": sum(pair["strict_min_max"] for pair in dev_pairs) if full and all(pair["measurement_available"] for pair in dev_pairs) else None,
                        "evaluation_pairs": len(eval_pairs) if full and all(pair["measurement_available"] for pair in eval_pairs) else None,
                        "evaluation_strict_min_max_pairs": sum(pair["strict_min_max"] for pair in eval_pairs) if full and all(pair["measurement_available"] for pair in eval_pairs) else None,
                        "bounded_A_or_M_pilot": bounded,
                        "same_strict_proof_path_observed": same_path},
            "usage": {field: sum(row["usage"][field] for row in rows if row["usage"][field] is not None)
                      if full and all(row["usage"][field] is not None for row in rows) else None for field in _USAGE_FIELDS},
            "limits": {"A": "not_measured", "M": "not_measured", "neutral": "diagnostic_only",
                       "evaluation_scope": plan["protocol"]["evaluation_scope"], "repeated_seeds_are_independent_problems": False,
                       "metadata_is_not_cache_reset": True,
                       "parse_or_envelope_failures": sum(row["status"] in {"invalid_json", "invalid_schema", "incomplete_response"} for row in rows),
                       "logical_failures": sum(row["status"] == "ok" and row["strict_valid"] is False for row in rows)}}


def _render(summary: dict) -> str:
    decision = summary["overall"]["bounded_A_or_M_pilot"]
    text = "미판정" if decision is None else ("통과" if decision else "불통과")
    lines = ["# v064 직접 D 대조 결과", "",
             f"실행 상태: {summary['state']} / 관측 호출: {summary['observed_calls']}/{summary['assigned_calls']} / 완결 분모: {summary['full_complete']}",
             f"기록 성격(provenance): {summary['provenance']}",
             f"주판정(여섯 directed 대응쌍 모두 strict·최소/최대 실제 D): {text}", "",
             "|문제|directed 쌍|strict 최소/최대 쌍|모든 directed 규칙·부모 경로 동일|", "|---|---:|---:|---:|"]
    for item in summary["problem_summaries"]:
        lines.append("|{problem_id}|{assigned_directed_pairs}|{strict_min_max_pairs}|{all_directed_same_strict_proof_path}|".format(**item))
    lines.extend(["", "neutral 조건은 진단용이며 주 성공 지표에 포함하지 않는다.",
                  "파싱·envelope 실패와 논리적 증명 실패는 별도로 기록한다. 미관측(not_observed)은 완료 event에 결속된 관측 기록이 없다는 뜻이며 호출 미발생을 보증하지 않는다. 중단 당시 미확정 원문은 독립 검산의 pending_action에 보존하고 성과로 채점하지 않는다. 미관측 또는 비완결 실행에서는 전체 비율을 제시하지 않는다.",
                  "T02는 개발 기준선이고 E01_shared_fork·E02_two_vs_four는 설계자가 정한 사전 미관측 구조다. 구조적 평가문제 두 개이지만 무작위 모집단이나 외부 독립 holdout은 아니다.",
                  "A와 M은 이번 D-only 대조에서 측정하지 않는다. 실제 D는 모든 노드가 유효하고 최종 조상 closure를 만족할 때만 기록한다."])
    return "\n".join(lines) + "\n"


def _verify_status(files: dict[str, bytes], plan: dict, actions: list[dict], events: list[dict]) -> tuple[dict, list[dict]]:
    if "status.json" not in files:
        _fail("status.json missing")
    status = _object(files["status.json"], "status.json")
    _expect_keys(status, {"state", "reason", "completed_actions", "started_actions", "inference_calls", "plan_sha256"}, "status")
    if status["state"] not in {"complete", "stopped", "crashed"} or status["plan_sha256"] != plan["plan_sha256"]:
        _fail("status identity")
    for key in ("completed_actions", "started_actions", "inference_calls"):
        _nonnegative(status[key], "status " + key)
    completed, started = status["completed_actions"], status["started_actions"]
    if completed != len(events) or started > len(actions) or completed > started:
        _fail("status action counts")
    started_actions = _started_markers(files, plan, actions, status)
    inference = sum(action["kind"] == "call" for action in started_actions)
    if status["inference_calls"] != inference or inference > plan["protocol"]["max_inference_calls"]:
        _fail("status inference count")
    if status["state"] == "complete":
        if status["reason"] is not None or completed != len(actions) or started != len(actions) or inference != plan["protocol"]["max_inference_calls"]:
            _fail("complete status")
    elif status["state"] == "stopped":
        if status["reason"] not in _STOP_REASONS or completed != started or not events:
            _fail("stopped status")
    else:
        if status["reason"] != "interrupted_action" or started not in {completed, completed + 1}:
            _fail("crashed status")
    _require_exact_raw(files, "status.json", status)
    return status, started_actions


def _verify_manifest(files: dict[str, bytes]) -> None:
    if "MANIFEST.json" not in files:
        _fail("MANIFEST.json missing")
    manifest = _object(files["MANIFEST.json"], "MANIFEST.json")
    _expect_keys(manifest, {"contract", "file_hashes"}, "manifest")
    if manifest["contract"] != EVIDENCE_CONTRACT or not isinstance(manifest["file_hashes"], dict):
        _fail("manifest contract")
    expected = {name: common.sha(raw) for name, raw in files.items() if name != "MANIFEST.json"}
    if not common.exact(manifest["file_hashes"], expected):
        _fail("manifest file hashes")
    if files["MANIFEST.json"] != common.wire(manifest):
        _fail("manifest bytes")


def _pending_artifacts(files: dict[str, bytes], plan: dict, action: dict) -> tuple[set[str], dict]:
    """Bind only the single interrupted action's write prefix, without scoring it."""
    names = set()
    if action["kind"] == "call":
        slot = next(slot for slot in plan["slots"] if slot["id"] == action["id"])
        sequence = [("wire/" + action["id"] + "/request.wire.json", _request_for(plan, slot)),
                    ("wire/" + action["id"] + "/response.raw.json", None)]
    else:
        sequence = []
        for index in range(3):
            prefix = "metadata/" + action["id"] + "/" + str(index)
            request = common.wire({"model": plan["identity"]["model"]}) if index == 2 else b""
            sequence.extend([(prefix + ".request.json", request), (prefix + ".response.raw.json", None)])
    missing_or_partial = False
    for name, expected in sequence:
        if name not in files:
            missing_or_partial = True
            continue
        if missing_or_partial:
            _fail("pending artifacts are not a write prefix")
        raw = files[name]
        if expected is not None:
            if not expected.startswith(raw):
                _fail("pending request differs from frozen byte prefix")
            if raw != expected:
                missing_or_partial = True
        elif len(raw) > 1024 ** 2 + 1:
            _fail("pending response size limit")
        names.add(name)
    record_name = "records/" + action["id"] + ".json"
    if record_name in files:
        # A record may be partially written when interrupted. It is retained as
        # uncommitted opaque evidence, never fed to semantic measurement.
        if not names or len(files[record_name]) > common.MAX_JSON:
            _fail("pending record lacks wire or exceeds size limit")
        names.add(record_name)
    return names, {"id": action["id"], "kind": action["kind"], "artifact_names": sorted(names),
                   "record_committed": False, "semantic_measurement": "not_measured"}


def verify_bundle(bundle: Path) -> dict:
    """Verify one frozen evidence ZIP and return a successful independent receipt.

    A contract violation raises :class:`VerificationError`; no producer module or
    source snapshot is imported or executed during verification.
    """
    try:
        raw_bundle = Path(bundle).read_bytes()
        files = common.unzip(raw_bundle)
    except (OSError, ValueError) as exc:
        raise VerificationError("bundle cannot be read safely") from exc
    _verify_manifest(files)
    plan, _slots, actions, _protocol = _verify_plan(files)
    _verify_runtime(files, plan)
    expected_names = {"plan.json", "runtime.json", "baseline/v058_evidence.zip", "records/events.jsonl", "status.json", "summary.json", "summary.ko.md", "MANIFEST.json"}
    expected_names |= _verify_sources(files, plan)
    events, completed_actions = _parse_events(files, plan, actions)
    status, _started = _verify_status(files, plan, actions, events)
    records, calls = [], []
    for event, action in zip(events, completed_actions):
        record_name = "records/" + action["id"] + ".json"
        if action["kind"] == "call":
            record, names = _validate_call(files, plan, action)
            calls.append(record)
        else:
            record, names = _validate_metadata(files, plan, action)
        if event["record_sha256"] != common.sha(files[record_name]):
            _fail("event record SHA binding")
        expected_names.add(record_name)
        expected_names.update(names)
        records.append(record)
    expected_names |= {"records/" + action["id"] + ".started.json" for action in actions[:status["started_actions"]]}
    pending_action = None
    if status["started_actions"] == len(events) + 1:
        pending_names, pending_action = _pending_artifacts(files, plan, actions[len(events)])
        expected_names.update(pending_names)
    if set(files) != expected_names:
        extras = sorted(set(files) - expected_names)
        missing = sorted(expected_names - set(files))
        _fail("bundle layout extras=" + repr(extras) + " missing=" + repr(missing))
    terminal_reason = None
    for index, (action, record) in enumerate(zip(completed_actions, records)):
        reason = (_call_stop_reason(record, plan["identity"]["model"], plan["protocol"]["num_predict"])
                  if action["kind"] == "call" else (None if record["identity_ok"] else "metadata_identity_error"))
        if reason is not None:
            if index != len(events) - 1 or status["started_actions"] != len(events):
                _fail("action after mandatory stop")
            terminal_reason = reason
    if status["state"] == "stopped" and terminal_reason != status["reason"]:
        _fail("stopped reason does not bind terminal action")
    if status["state"] == "complete" and terminal_reason is not None:
        _fail("complete run has terminal failure")
    if sum(record["kind"] == "call" for record in records) > plan["protocol"]["max_inference_calls"]:
        _fail("observed inference budget")
    if status["inference_calls"] * plan["protocol"]["num_predict"] > plan["protocol"]["generation_token_upper_bound"]:
        _fail("generation token upper bound")
    summary = _summary(plan, calls, status["state"])
    if "summary.json" not in files or _object(files["summary.json"], "summary.json") != summary or files["summary.json"] != _saved(summary):
        _fail("summary independent reproduction")
    rendered = _render(summary).encode("utf-8")
    if files.get("summary.ko.md") != rendered:
        _fail("Korean report independent reproduction")
    return {"contract": VERIFY_CONTRACT, "bundle_sha256": common.sha(raw_bundle), "plan_sha256": plan["plan_sha256"],
            "provenance": plan["provenance"],
            "state": status["state"], "completed_actions": status["completed_actions"], "started_actions": status["started_actions"],
            "inference_calls": status["inference_calls"], "observed_calls": len(calls),
            "pending_action": pending_action,
            "compared_groups": ["manifest_and_layout", "plan_baseline_source", "runtime_and_action_schedule",
                                "start_markers_events_records", "metadata_and_identity", "call_requests_and_responses",
                                "stop_budget_and_status", "independent_semantics", "summary_and_korean_report"],
            "differences": [], "production_imports": False,
            "limitation": "번들 내부 일관성 검산이며 외부 실행 사실을 인증하지 않는다. 중단 실행의 inference_calls는 시작 표지 기준이며 모델 수신은 별도 인증되지 않는다.",
            "verified": True}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        receipt = verify_bundle(args.bundle)
        output = _saved(receipt)
        if args.out is None:
            sys.stdout.buffer.write(output)
        else:
            common.write(args.out, output)
        return 0
    except (VerificationError, OSError, ValueError, KeyError, TypeError) as exc:
        print(type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
