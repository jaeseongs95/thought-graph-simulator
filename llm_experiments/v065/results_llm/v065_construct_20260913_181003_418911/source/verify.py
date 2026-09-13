"""독립적인 v065 증거 번들 검산기.

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
import previous


PLAN_CONTRACT = "v065-plan-r1"
EVIDENCE_CONTRACT = "v065-evidence-r1"
REPORT_CONTRACT = "v065-report-r1"
VERIFY_CONTRACT = "v065-independent-verify-r1"
_BASELINE_DIRECTION = '허용된 유효한 증명 중 최종 지지 깊이가 가장 작은 경로를 선택한다.'
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


def _slot_schedule(protocol):
    result=[];prior_id=None;prior_condition=None
    for pi,problem in enumerate(protocol['problems']):
        for si,seed in enumerate(protocol['seeds']):
            if not _is_int(seed):_fail('seed must be integer')
            block=pi*len(protocol['seeds'])+si;order=protocol['orders'][block]
            if len(order)!=2 or set(order)!={'prescribed_short','prescribed_long'}:_fail('construction order')
            for period,condition in enumerate(order):
                rid=protocol['required_terminal_rules'][problem['id']][condition]
                slot={'id':f'b{block:02d}_p{pi}_{condition}','problem_id':problem['id'],'seed':seed,'seed_index':si,
                      'block':block,'period':period,'condition':condition,'required_terminal_rule':rid,
                      'previous_call_id':prior_id,'previous_condition':prior_condition}
                result.append(slot);prior_id=slot['id'];prior_condition=condition
    if len(result)!=protocol['max_inference_calls']:_fail('frozen call budget')
    return result


def _actions(slots,blocks):
    actions=[]
    for b in range(blocks):
        group=[s for s in slots if s['block']==b]
        if len(group)!=2:_fail('two calls in construction block')
        actions+=[{'kind':'metadata','id':f'b{b:02d}_before'}]
        actions += [{'kind':'call','id':s['id']} for s in group]
        actions+=[{'kind':'metadata','id':f'b{b:02d}_after'}]
    return actions


def _baseline(files,protocol):
    raw=files.get('baseline/v064_evidence.zip')
    if raw is None or common.sha(raw)!=protocol['baseline_sha256']:_fail('v064 baseline identity')
    source,source_plan,request,receipt=previous.inspect_prior(raw)
    # 이전 아카이브 감사만 공유한다. 현재 v065의 요청·증명·집계는 이 모듈에서 별도 계산한다.
    if not receipt['verified'] or receipt['state']!='complete':_fail('previous evidence not complete')
    return request,copy.deepcopy(source_plan['identity'])


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


def _request_for(plan,slot):
    request=copy.deepcopy(plan['baseline_request']);ms=request.get('messages');options=request.get('options')
    if not isinstance(ms,list) or len(ms)!=1 or ms[0].get('role')!='user' or not isinstance(options,dict):_fail('baseline request shape')
    text=ms[0]['content'];marker='\n\nproblem: '
    if text.count(marker)!=1 or text.count(_BASELINE_DIRECTION)!=1:_fail('request anchors')
    if slot['condition'] not in {'prescribed_short','prescribed_long'}:_fail('condition')
    pid=slot['problem_id'];rid=plan['protocol']['required_terminal_rules'][pid][slot['condition']]
    if rid!=slot['required_terminal_rule']:_fail('required final rule')
    before=text.partition(marker)[0];problem=next(p for p in plan['protocol']['problems'] if p['id']==pid)
    sentence="최종 goal 노드의 rule은 반드시 '"+rid+"'로 지정한다. 이 규칙을 마지막으로 사용하는 유효한 증명 하나를 구성한다."
    ms[0]['content']=before.replace(_BASELINE_DIRECTION,sentence)+marker+common.wire(problem).decode('utf-8')
    options['seed']=slot['seed'];raw=common.wire(request)
    if len(raw)>plan['protocol']['request_utf8_byte_limit']:_fail('request byte limit')
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











def _summary(plan,calls,state):
    by_id={r['id']:r for r in calls};problems={p['id']:p for p in plan['protocol']['problems']}
    rows=[]
    for slot in plan['slots']:
        r=_row(plan,slot,by_id.get(slot['id']),problems)
        low,high=plan['protocol']['depth_ranges'][slot['problem_id']]
        r['expected_D_for_prescribed_rule']=low if slot['condition']=='prescribed_short' else high
        r['required_rule_match']=(r['final_rule_id']==slot['required_terminal_rule']) if r['final_rule_id'] is not None else None
        r['construction_success']=None if r['strict_valid'] is None else (r['strict_valid'] is True and r['required_rule_match'] is True and r['actual_D']==r['expected_D_for_prescribed_rule'])
        r['D_instruction_control_success']=None;rows.append(r)
    count=sum(r['status']!='not_observed' for r in rows);full=state=='complete' and count==len(plan['slots'])
    measured=sum(r['construction_success'] is not None for r in rows);success=sum(r['construction_success'] is True for r in rows)
    ready=None if not full or measured!=len(rows) else success==len(rows)
    groups=[];pairs=[]
    for problem in plan['protocol']['problems']:
        pid=problem['id']
        for condition in ['prescribed_short','prescribed_long']:
            ids=[s['id'] for s in plan['slots'] if s['problem_id']==pid and s['condition']==condition]
            group=[r for r in rows if r['id'] in ids];ok=sum(r['construction_success'] is True for r in group);unmeasured=sum(r['construction_success'] is None for r in group)
            groups.append({'problem_id':pid,'condition':condition,'required_terminal_rule':plan['protocol']['required_terminal_rules'][pid][condition],
              'assigned':len(ids),'observed':sum(r['status']!='not_observed' for r in group),'rule_name_matches':sum(r['required_rule_match'] is True for r in group),
              'locally_valid':sum(r['proof_valid'] is True for r in group),'strict_valid':sum(r['strict_valid'] is True for r in group),
              'construction_successes':ok,'unmeasured':unmeasured,'rate':ok/len(ids) if full and unmeasured==0 else None})
        for seed in plan['protocol']['seeds']:
            local={r['condition']:r for r in rows if r['problem_id']==pid and r['seed']==seed}
            short,long=local['prescribed_short']['construction_success'],local['prescribed_long']['construction_success']
            pairs.append({'problem_id':pid,'seed':seed,'prescribed_short_success':short,'prescribed_long_success':long,
              'both_prescribed_routes_constructed':(short and long) if short is not None and long is not None else None,'D_instruction_control_success':None})
    usage={}
    for key in _USAGE_FIELDS:
        vals=[r['usage'][key] for r in rows];usage[key]=sum(vals) if full and all(v is not None for v in vals) else None
    failures={'format_or_envelope':sum(r['status'] in ('invalid_json','invalid_schema','incomplete_response') or r['format_valid'] is False for r in rows),
        'proof_failures':sum(r['proof_valid'] is False for r in rows),'strict_only_failures':sum(r['proof_valid'] is True and r['strict_valid'] is False for r in rows),
        'unobserved':sum(r['status']=='not_observed' for r in rows)}
    return {'contract':REPORT_CONTRACT,'run_name':plan['run_name'],'provenance':plan['provenance'],'plan_sha256':plan['plan_sha256'],'state':state,
       'assigned_calls':len(rows),'observed_calls':count,'full_complete':full,'rows':rows,'groups':groups,'construction_pairs':pairs,
       'overall':{'measured_construction_calls':measured,'construction_successes':success,'construction_rate':success/len(rows) if ready is not None else None,
          'prescribed_construction_ready':ready,'D_instruction_control':'not_measured','bounded_A_or_M_pilot':None,'prior_v064_D_gate_remains':False},
       'failure_layers':failures,'usage':usage,'limits':{'A':'not_measured','M':'not_measured','last_rule_explicitly_given':True,
       'historical_vs_new_not_contemporaneous_causal_comparison':True,'not_holdout':True,'retry':False,'repair':False}}


def _render(summary):
    flag=summary['overall']['prescribed_construction_ready'];label='미판정' if flag is None else ('통과' if flag else '불통과')
    text=['# v065 지정 마지막 규칙의 증명 구성 검사','',
      '실행 상태: '+summary['state']+' / 관측 호출: '+str(summary['observed_calls'])+'/'+str(summary['assigned_calls'])+' / provenance: '+summary['provenance'],
      '마지막 규칙을 직접 알려주는 구성 검사다. D 지시만으로 모델이 경로를 선택한 성과가 아니다.',
      '12개 지정 구성의 엄격한 이행: '+label+'. v064의 D 제어 불통과는 변경하지 않는다.','',
      '|문제|조건|지정 규칙|관측/배정|규칙명 이행|국소 논리 유효|엄격한 증명|지정 구성 성공|미측정|',
      '|---|---|---|---:|---:|---:|---:|---:|---:|']
    for g in summary['groups']:
        cells=[g['problem_id'],g['condition'],g['required_terminal_rule'],str(g['observed'])+'/'+str(g['assigned']),g['rule_name_matches'],g['locally_valid'],g['strict_valid'],g['construction_successes'],g['unmeasured']]
        text.append('|'+ '|'.join(str(c) for c in cells)+'|')
    f=summary['failure_layers']
    text+=['','## 실패 계층',f"형식/응답 오류: {f['format_or_envelope']}; 논리 오류: {f['proof_failures']}; 논리는 유효하나 엄격 계약 위반: {f['strict_only_failures']}; 미관측: {f['unobserved']}",
      '추가 노드나 출력 순서 위반은 실제 논리 오류와 별도로 집계한다. 정답 경로를 골라내거나 참조·규칙을 수정하지 않는다.',
      '', '## 다음 판단',
      '모든 지정 경로가 엄격하게 구성되면 고정 경로 구성 기준선만 확보한 것이다. 이후 D만으로 선택·구성하는 별도 직접/단계형 대조의 필요성을 결정한다.',
      '깊은 지정 경로가 하나도 유효하지 않으면 현재 이 모델·출력 인터페이스의 지정 구성 분기를 종료한다. 문구를 바꿔 자동 반복하지 않는다.',
      '일부만 성공하면 문제·조건별 성과를 보존하고 사후 성공 subset을 전체 성공으로 바꾸지 않는다. 미완료/파싱 불가이면 진입 판정은 보류한다.',
      'A/M·내부 사고·비용 절감·일반화는 이번 검사에서 측정하지 않는다. 미관측 원문은 성과로 채점하지 않는다.',
      '', '실제 원응답 계수 합계: '+str(summary['usage']),'계획 SHA-256: '+summary['plan_sha256']]
    return '\n'.join(text)+'\n' 


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
        if len(names) < 2 or len(names) % 2 or len(files[record_name]) > common.MAX_JSON:
            _fail("pending record requires completed request/response pairs and bounded size")
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
    expected_names = {"plan.json", "runtime.json", "baseline/v064_evidence.zip", "records/events.jsonl", "status.json", "summary.json", "summary.ko.md", "MANIFEST.json"}
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
