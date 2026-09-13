"""독립적인 v066 증거 번들 검산기.

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


PLAN_CONTRACT = "v066-plan-r1"
EVIDENCE_CONTRACT = "v066-evidence-r1"
REPORT_CONTRACT = "v066-report-r1"
VERIFY_CONTRACT = "v066-independent-verify-r1"
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
    slots=[]
    for pi,pr in enumerate(protocol['problems']):
        for si,seed in enumerate(protocol['seeds']):
            block=pi*2+si
            directions=('shallow','deep') if si==0 else ('deep','shallow')
            period=0
            for di,d in enumerate(directions):
                aa=('direct','staged') if (block+di)%2==0 else ('staged','direct')
                for arm in aa:
                    for stage in (('direct',) if arm=='direct' else ('plan','construct')):
                        sid='b%02d_p%d_%s_%s'%(block,pi,d,stage)
                        parent='b%02d_p%d_%s_plan'%(block,pi,d) if stage=='construct' else None
                        slots.append({'id':sid,'problem_id':pr['id'],'seed':seed,'seed_index':si,'block':block,'period':period,'direction':d,'arm':arm,'stage':stage,'parent_plan_id':parent,'previous_call_id':slots[-1]['id'] if slots else None,'previous_condition':slots[-1]['direction'] if slots else None});period+=1
    if len(slots)!=protocol['max_inference_calls'] or len(slots)!=36:_fail('36-call schedule')
    return slots




def _actions(slots,blocks):
    out=[]
    for b in range(blocks):
        ss=[s for s in slots if s['block']==b]
        if len(ss)!=6:_fail('six calls required')
        out.extend([{'kind':'metadata','id':f'b{b:02d}_before'},*[{'kind':'call','id':s['id']} for s in ss],{'kind':'metadata','id':f'b{b:02d}_after'}])
    return out




def _baseline(files,protocol):
    raw=files.get('baseline/v065_evidence.zip')
    if raw is None or common.sha(raw)!=protocol['baseline_sha256']:_fail('v064 baseline identity')
    source,source_plan,request,receipt=previous.inspect_prior(raw)
    # 이전 아카이브 감사만 공유한다. 현재 v066의 요청·증명·집계는 이 모듈에서 별도 계산한다.
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


def _request_for(plan,slot,files):
    q=copy.deepcopy(plan['baseline_request']);problem=next(p for p in plan['protocol']['problems'] if p['id']==slot['problem_id'])
    ms=q['messages']
    if len(ms)!=1 or ms[0]['role']!='user':_fail('baseline shape')
    text=ms[0]['content'];marker='\n\nproblem: '
    if text.count(marker)!=1 or text.count(_BASELINE_DIRECTION)!=1:_fail('baseline anchor')
    prefix=text.split(marker,1)[0];d='허용된 유효한 증명 중 최종 지지 깊이가 가장 작은 경로를 선택한다.' if slot['direction']=='shallow' else '허용된 유효한 증명 중 최종 지지 깊이가 가장 큰 경로를 선택한다.'
    prefix=prefix.replace(_BASELINE_DIRECTION,d)
    if slot['stage']=='plan':
        schema={'type':'object','properties':{'rule_ids':{'type':'array','items':{'type':'string','minLength':1,'maxLength':128},'minItems':1,'maxItems':16}},'required':['rule_ids'],'additionalProperties':False}
        prefix='facts와 rules만 사용하여 goal을 지지하는 증명 경로 하나를 계획한다.\n전체 노드와 부모 ID를 쓰지 말고, 사용할 규칙 ID를 적용 순서대로 rule_ids에 한 번씩 나열한다.\n각 규칙의 전제는 초기 facts 또는 그 앞에서 선택한 규칙의 결론으로 얻어져야 한다.\n마지막 규칙이 goal을 도출해야 한다. 최종 goal에 필요 없는 다른 경로의 규칙은 포함하지 않는다.\n입력에 등록된 실제 규칙 ID를 사용하고 새 규칙을 만들지 않는다.'+'\n경로 지시:\n'+d+'\nJSON 객체 하나만 출력한다. 출력 형식(JSON Schema):\n'+common.wire(schema).decode('utf-8')
        q['format']=schema
    ms[0]['content']=prefix+marker+common.wire(problem).decode('utf-8')
    if slot['stage']=='construct':
        name='wire/'+slot['parent_plan_id']+'/response.raw.json'
        if name not in files:_fail('parent raw missing')
        raw=files[name]
        try:
            env=common.load(raw);message=env.get('message');content=message.get('content') if isinstance(message,dict) else None
            if not isinstance(content,str):content=None
        except (ValueError,UnicodeError,AttributeError):content=None
        transfer={'source_slot_id':slot['parent_plan_id'],'response_sha256':common.sha(raw),'content':content}
        header='아래 route_plan_response는 앞선 모델 호출의 원응답이다. 그 응답의 rule_ids와 규칙 적용 순서를 그대로 사용하여 전체 증명 DAG를 작성한다.\n규칙 계획을 추가·삭제·치환·재정렬하거나 다른 경로로 다시 선택하지 않는다. 계획이 틀려도 정답 경로로 고쳐 쓰지 않는다.\n각 노드 ID, 초기 사실 노드 및 부모 연결은 직접 작성하되 원래 증명 규칙과 출력 계약을 지킨다.'
        ms[0]['content']+='\n\n'+header+'\nroute_plan_response: '+common.wire(transfer).decode('utf-8')
    if slot['stage'] not in ('direct','plan','construct'):_fail('unknown stage')
    q['options']['seed']=slot['seed'];raw=common.wire(q)
    if len(raw)>plan['protocol']['request_utf8_byte_limit']:_fail('request budget')
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
    if request != _request_for(plan, next(slot for slot in plan["slots"] if slot["id"] == action["id"]), files):
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











def _plan_semantics(problem,payload):
    result={'plan_valid':None,'planned_D':None,'selected_rule_ids':None,'plan_format_valid':False,'plan_error_codes':[]}
    if not isinstance(payload,dict) or set(payload)!= {'rule_ids'}:
        result['plan_error_codes']=['plan_schema'];return result
    seq=payload['rule_ids']
    if not isinstance(seq,list) or not 1<=len(seq)<=16 or any(not _text(v) for v in seq):result['plan_error_codes']=['plan_schema'];return result
    result.update(plan_format_valid=True,plan_valid=False,selected_rule_ids=seq[:])
    known={f:{'depth':0,'trace':set()} for f in problem['facts']};rs={r['id']:r for r in problem['rules']};bad=set()
    if len(seq)!=len(set(seq)):bad.add('duplicate_rule')
    # 별도 구현은 규칙 의존성을 기록한 뒤 전제 지원 깊이를 합성한다.
    trace_nodes={}
    for ix,rid in enumerate(seq):
        r=rs.get(rid)
        if r is None:bad.add('unregistered_rule');continue
        if r['conclusion'] in known:bad.add('rederived_atom')
        parents=[known.get(a) for a in r['premises']]
        if any(x is None for x in parents):bad.add('plan_premise_unavailable');continue
        deps=set([rid]);depth=0
        for entry in parents:deps.update(entry['trace']);depth=max(depth,entry['depth'])
        known[r['conclusion']]={'depth':depth+1 if parents else 0,'trace':deps}
    if seq[-1] not in rs or rs[seq[-1]]['conclusion']!=problem['goal']:bad.add('plan_final_goal')
    g=known.get(problem['goal'])
    if g is None:bad.add('plan_goal_unreachable')
    elif g['trace']!=set(seq):bad.add('plan_unused_rule')
    result['plan_error_codes']=sorted(bad)
    if not bad:result.update(plan_valid=True,planned_D=g['depth'])
    return result


def _summary(plan,calls,state):
    ix={c['id']:c for c in calls};rows=[];decoded={};problems={p['id']:p for p in plan['protocol']['problems']}
    for s in plan['slots']:
        row=copy.deepcopy(s)
        row.update(status='not_observed',response_sha256=None,request_sha256=None,http_status=None,elapsed_ns=None)
        for k in _SEMANTIC_FIELDS:row[k]=None
        row.update(plan_format_valid=None,plan_valid=None,planned_D=None,selected_rule_ids=None,plan_error_codes=None,follows_actual_plan=None,direction_success=None,plan_direction_success=None,usage={k:None for k in _USAGE_FIELDS})
        rec=ix.get(s['id'])
        if rec:
            for k in ('response_sha256','request_sha256','http_status','elapsed_ns'):row[k]=rec[k]
            try:env=common.load(_base64(rec['response_b64'],'response'))
            except (ValueError,UnicodeError):env=None
            row['usage']=_usage(env);status,payload=_parse_response(env,rec['http_status'],rec['error'],plan['identity']['model']);row['status']=status;decoded[s['id']]=payload
            target=plan['protocol']['depth_ranges'][s['problem_id']][0 if s['direction']=='shallow' else 1]
            if status=='ok':
                if s['stage']=='plan':
                    row.update(_plan_semantics(problems[s['problem_id']],payload));row['format_valid']=row['plan_format_valid']
                    row['plan_direction_success']=None if row['plan_valid'] is None else bool(row['plan_valid'] and row['planned_D']==target)
                else:
                    row.update(_semantic(problems[s['problem_id']],payload))
                    row['direction_success']=None if row['strict_valid'] is None else bool(row['strict_valid'] and row['actual_D']==target)
            elif status in ('invalid_json','invalid_schema'):row['format_valid']=False
        rows.append(row)
    for row in rows:
        if row['stage']=='construct' and row['id'] in decoded:
            prior=decoded.get(row['parent_plan_id']);value=decoded[row['id']]
            if isinstance(prior,dict) and set(prior)=={'rule_ids'} and isinstance(prior['rule_ids'],list) and all(isinstance(x,str) for x in prior['rule_ids']) and row['format_valid'] is True:
                row['follows_actual_plan']=[n['rule'] for n in value['nodes'] if n['rule'] is not None]==prior['rule_ids']
    lookup={(r['problem_id'],r['seed'],r['direction'],r['stage']):r for r in rows};units=[]
    for pr in plan['protocol']['problems']:
        for seed in plan['protocol']['seeds']:
            for arm in ('direct','staged'):
                for direction in ('shallow','deep'):
                    final=lookup[pr['id'],seed,direction,'direct' if arm=='direct' else 'construct'];planner=None if arm=='direct' else lookup[pr['id'],seed,direction,'plan']
                    observed=final['status']!='not_observed' and (planner is None or planner['status']!='not_observed')
                    values=[final['direction_success']]
                    if planner:values.extend([planner['plan_direction_success'],final['follows_actual_plan']])
                    ok=all(values) if observed and all(v is not None for v in values) else None
                    units.append({'problem_id':pr['id'],'seed':seed,'arm':arm,'direction':direction,'all_stages_observed':observed,'planner_success':planner['plan_direction_success'] if planner else None,'final_graph_success':final['direction_success'],'actual_D':final['actual_D'],'plan_followed':final['follows_actual_plan'] if planner else None,'end_to_end_success':ok})
    count=len(calls);complete=state=='complete' and count==36;pairs=[];arms={}
    for arm in ('direct','staged'):
        for pr in plan['protocol']['problems']:
            for seed in plan['protocol']['seeds']:
                u={x['direction']:x for x in units if (x['problem_id'],x['seed'],x['arm'])==(pr['id'],seed,arm)};short,long=u['shallow'],u['deep']
                ok=None if short['end_to_end_success'] is None or long['end_to_end_success'] is None else bool(short['end_to_end_success'] and long['end_to_end_success'] and short['actual_D']!=long['actual_D'])
                pairs.append({'arm':arm,'problem_id':pr['id'],'seed':seed,'shallow_end_to_end':short['end_to_end_success'],'deep_end_to_end':long['end_to_end_success'],'selective_D_success':ok})
        ps=[x for x in pairs if x['arm']==arm];ts=[x for x in rows if x['arm']==arm];us=[x for x in units if x['arm']==arm]
        arms[arm]={'assigned_calls':len(ts),'observed_calls':sum(x['status']!='not_observed' for x in ts),'assigned_pairs':len(ps),'measured_pairs':sum(x['selective_D_success'] is not None for x in ps),'selective_successes':sum(x['selective_D_success'] is True for x in ps),'end_to_end_successes':sum(x['end_to_end_success'] is True for x in us),'final_strict_proofs':sum(x['strict_valid'] is True for x in ts),'final_D_only_successes':sum(x['final_graph_success'] is True for x in us),'all_pairs_pass':all(x['selective_D_success'] for x in ps) if complete and all(x['selective_D_success'] is not None for x in ps) else None,'usage':{k:sum(x['usage'][k] for x in ts) if all(x['usage'][k] is not None for x in ts) else None for k in _USAGE_FIELDS}}
    contrasts=[]
    for pr in plan['protocol']['problems']:
        for seed in plan['protocol']['seeds']:
            x={a:next(p['selective_D_success'] for p in pairs if (p['problem_id'],p['seed'],p['arm'])==(pr['id'],seed,a)) for a in ('direct','staged')};a,b=x['direct'],x['staged']
            result='not_comparable' if a is None or b is None else ('both' if a and b else ('direct_only' if a else ('staged_only' if b else 'neither')))
            contrasts.append({'problem_id':pr['id'],'seed':seed,'direct':a,'staged':b,'outcome':result})
    return {'contract':'v066-report-r1','run_name':plan['run_name'],'provenance':plan['provenance'],'plan_sha256':plan['plan_sha256'],'state':state,'full_complete':complete,'assigned_calls':36,'observed_calls':count,'rows':rows,'units':units,'pairs':pairs,'arms':arms,'contrasts':contrasts,'planner':{'observed':sum(x['stage']=='plan' and x['status']!='not_observed' for x in rows),'valid_plans':sum(x['plan_valid'] is True for x in rows),'direction_successes':sum(x['plan_direction_success'] is True for x in rows)},'limits':{'A':'not_measured','M':'not_measured','internal_control':'not_measured','equal_compute_comparison':False,'prior_v065_construction_gate_remains':False,'prior_prescribed_branch_closed':True,'planner_is_not_generated_proof':True,'repair':False,'retry':False}}




def _render(r):
    lines=['# v066 직접 생성 대 모델 원계획 전달 비교','',f"실행 상태: {r['state']} / 관측 호출: {r['observed_calls']}/36 / provenance: {r['provenance']}",
       '이전 v065의 지정 규칙 단일 호출 분기는 종료했다. 이번에는 정답 규칙을 알려주지 않는 다른 실행 구조를 비교한다.',
       'staged 성공에는 모델의 계획이 유효·요구 깊이 이행, 원계획 그대로 전달, 그래프 규칙 순서 일치, 전체 strict 증명·요구 D 이행이 모두 필요하다.','',
       '|방식|호출 관측/배정|최종 strict 증명|최종 D만 일치|종단 이행|선택적 D쌍|6쌍 진입 기준|','|---|---:|---:|---:|---:|---:|---|']
    for name,a in r['arms'].items():lines.append(f"|{name}|{a['observed_calls']}/{a['assigned_calls']}|{a['final_strict_proofs']}|{a['final_D_only_successes']}|{a['end_to_end_successes']}|{a['selective_successes']}/6|{a['all_pairs_pass']}|")
    lines+=['','## 계획과 최종 증명의 분리',f"계획 관측 {r['planner']['observed']}/12, 유효 경로 계획 {r['planner']['valid_plans']}, 방향 이행 {r['planner']['direction_successes']}.",
       'planned_D는 규칙 목록의 사후 진단값이다. actual_D는 모델이 작성한 최종 유효 DAG에서만 계산한다. 잘못된 계획 뒤의 우연한 정답은 종단 성공이 아니다.','',
       '|문제|seed|방식|방향|계획 방향 성공|최종 그래프 방향 성공|계획 준수|종단 성공|실제 D|','|---|---:|---|---|---|---|---|---|---:|']
    for u in r['units']:lines.append(f"|{u['problem_id']}|{u['seed']}|{u['arm']}|{u['direction']}|{u['planner_success']}|{u['final_graph_success']}|{u['plan_followed']}|{u['end_to_end_success']}|{u['actual_D']}|")
    lines+=['','## 비용과 범위','direct는 12호출, staged는 24호출이다. 동일 계산량 비교 또는 토큰 절약 검증이 아니다. 같은 원문 재집계를 독립 표본이나 비용으로 중복 합산하지 않는다.']
    for name,a in r['arms'].items():lines.append(f"{name} 원응답 사용량: {a['usage']}")
    lines+=['','## 다음 판단','staged가 6/6쌍을 충족하면 이 제한된 외부 실행 구조의 D 기준선만 확보한다. 이전 단일 호출 실패를 취소하거나 내부 사고/A/M 성과로 확대하지 않는다.',
       '일부만 성공하면 해당 문제와 방향 범위를 보존한다. staged 종단 성공이 없다면 이 2단계 구조도 종료하며 같은 문구 변형을 자동 반복하지 않는다.',
       '미완료/파싱 불가이면 전체 진입 기준은 미판정이다. 모든 원응답과 중간값을 보존하고 자동 보정·자동 재시도는 하지 않는다.',f"계획 SHA-256: {r['plan_sha256']}"]
    return '\n'.join(lines)+'\n'




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
        sequence = [("wire/" + action["id"] + "/request.wire.json", _request_for(plan, slot, files)),
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
    expected_names = {"plan.json", "runtime.json", "baseline/v065_evidence.zip", "records/events.jsonl", "status.json", "summary.json", "summary.ko.md", "MANIFEST.json"}
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
    if "summary.json" not in files or not common.exact(_object(files["summary.json"], "summary.json"), summary) or files["summary.json"] != _saved(_object(files["summary.json"], "summary.json")):
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
