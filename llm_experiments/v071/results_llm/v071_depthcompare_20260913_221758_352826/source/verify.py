"""독립적인 v071 증거 번들 검산기.

이 모듈은 ``design``, ``measure``, ``report``, ``run``을 import하지 않는다.
공유하는 것은 바이트/JSON/ZIP 계약, 동결 protocol, 직전 증거의 고정 검산 래퍼다.
"""
from __future__ import annotations

import argparse
import base64
import copy
import json
import sys
import urllib.parse
from pathlib import Path

import common
import previous


PLAN_CONTRACT = "v071-plan-r1"
EVIDENCE_CONTRACT = "v071-evidence-r1"
REPORT_CONTRACT = "v071-report-r1"
VERIFY_CONTRACT = "v071-independent-verify-r1"
_USAGE_FIELDS = ("prompt_eval_count", "eval_count", "total_duration", "prompt_eval_cached_count")
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
    records=[]
    for block in range(protocol['assigned_blocks']):
        pi,remainder=divmod(block,4);si,order=divmod(remainder,2)
        unit='b%02d'%block
        if (si+order)%2:
            seq=(('estimate',None),('model_depth','shallow'),('model_depth','deep'),('oracle_depth','deep'),('oracle_depth','shallow'))
        else:
            seq=(('oracle_depth','shallow'),('oracle_depth','deep'),('estimate',None),('model_depth','deep'),('model_depth','shallow'))
        for position,(arm,condition) in enumerate(seq):
            estimate=arm=='estimate'
            records.append({'id':unit+'_estimate' if estimate else unit+'_'+arm+'_'+condition,
                'unit_id':unit,'pair_id':None if estimate else unit+'_'+arm,'block':block,'period':position,
                'problem_id':protocol['problems'][pi]['id'],'seed':protocol['seeds'][si],'seed_index':si,
                'candidate_order_index':order,'stage':'estimate' if estimate else 'select','arm':arm,'condition':condition,
                'history_ids':[unit+'_estimate'] if arm=='model_depth' else [],
                'problem_role':'seen_constructor_task' if pi<3 else 'seen_authored_diagnostic'})
    if len(records)!=100:_fail('depth comparison schedule')
    return records

def _actions(slots,blocks):
    result=[]
    for block in range(blocks):
        calls=[s for s in slots if s['block']==block]
        if len(calls)!=5:_fail('five calls per block')
        result.append({'kind':'metadata','id':'b%02d_before'%block})
        for s in calls:result.append({'kind':'call','id':s['id']})
        result.append({'kind':'metadata','id':'b%02d_after'%block})
    return result

def _baseline(files,protocol):
    raw=files.get('baseline/v070_evidence.zip')
    if raw is None or common.sha(raw)!=protocol['baseline_sha256']:_fail('v070 baseline SHA')
    _,source_plan,request,receipt=previous.inspect_prior(raw)
    if not receipt['verified'] or receipt['state']!='complete':_fail('prior complete')
    return request,copy.deepcopy(source_plan['identity'])


def _reference_depth(problem,ids):
    # atom -> producer 관계를 만든 뒤 goal에서 역방향으로 depth/ancestry를 계산한다.
    if not isinstance(ids,list) or not ids or any(not isinstance(x,str) for x in ids) or len(set(ids))!=len(ids):raise ValueError('route ids')
    rules={r['id']:r for r in problem['rules']};producers={f:None for f in problem['facts']}
    for rid in ids:
        r=rules.get(rid)
        if r is None or any(a not in producers for a in r['premises']) or r['conclusion'] in producers:raise ValueError('route unavailable/redeclaration')
        producers[r['conclusion']]=rid
    if rules[ids[-1]]['conclusion']!=problem['goal']:raise ValueError('route final goal')
    used=set()
    def visit(atom):
        rid=producers[atom]
        if rid is None:return 0
        used.add(rid)
        return 1+max((visit(a) for a in rules[rid]['premises']),default=-1)
    d=visit(problem['goal'])
    if used!=set(ids):raise ValueError('route unused rules')
    return d

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
    for problem in protocol['problems']:
        for i,condition in enumerate(protocol['reference_conditions']):
            if _reference_depth(problem,protocol['reference_plans'][problem['id']][condition])!=protocol['depth_ranges'][problem['id']][i]:_fail('reference expected depth')
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
    actions = _actions(slots, protocol["assigned_blocks"])
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
    protocol=plan['protocol'];body=copy.deepcopy(plan['baseline_request'])
    if len(body['messages'])!=1 or body['messages'][0]['role']!='user':_fail('baseline messages')
    if slot['stage']=='estimate':
        problem=next(p for p in protocol['problems'] if p['id']==slot['problem_id'])
        order=protocol['candidate_orders'][slot['candidate_order_index']]
        routes=[protocol['reference_plans'][problem['id']][protocol['reference_conditions'][j]] for j in order]
        schema={'type':'object','properties':{'depths':{'type':'array','minItems':2,'maxItems':2,
            'items':{'type':'integer','minimum':0,'maximum':64}}},'required':['depths'],'additionalProperties':False}
        payload={'problem':{k:problem[k] for k in ('facts','rules','goal')},'candidate_rule_ids':routes}
        header=protocol['headers']['depth']
    else:
        schema={'type':'object','properties':{'candidate_index':{'type':'integer','enum':[0,1]}},
            'required':['candidate_index'],'additionalProperties':False}
        text=None
        if slot['arm']=='oracle_depth':
            order=protocol['candidate_orders'][slot['candidate_order_index']]
            text=common.wire({'depths':[protocol['depth_ranges'][slot['problem_id']][j] for j in order]}).decode('utf-8')
        else:
            name='wire/'+slot['history_ids'][0]+'/response.raw.json'
            if name not in files:_fail('depth history raw missing')
            try:
                envelope=common.load(files[name]);message=envelope.get('message') if isinstance(envelope,dict) else None
                if isinstance(message,dict) and isinstance(message.get('content'),str):text=message['content']
            except (ValueError,UnicodeError):pass
        payload={'depth_report':text,'requested_depth':protocol['headers'][slot['condition']]}
        header=protocol['headers']['compare']
    body['format']=schema
    body['messages'][0]['content']=header+'\nJSON 객체 하나만 출력한다. 출력 형식(JSON Schema):\n'+common.wire(schema).decode('utf-8')+'\n\ninput: '+common.wire(payload).decode('utf-8')
    body['options']['seed']=slot['seed']
    encoded=common.wire(body)
    if len(encoded)>protocol['request_utf8_byte_limit']:_fail('request byte limit')
    return encoded

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


def _depth_payload(value):
    if not isinstance(value,dict) or set(value)!={'depths'}:return False
    values=value['depths']
    return isinstance(values,list) and len(values)==2 and all(_is_int(x) and 0<=x<=64 for x in values)

def _choice_payload(value):
    return isinstance(value,dict) and set(value)=={'candidate_index'} and _is_int(value['candidate_index']) and 0<=value['candidate_index']<=1

def _count(rows,field):
    values=[r[field] for r in rows]
    return {'assigned':len(values),'measured':sum(type(v) is bool for v in values),'successes':sum(v is True for v in values)}

def _summary(plan,calls,state):
    protocol=plan['protocol'];records={r['id']:r for r in calls};rows=[];seen={}
    fields=('format_valid','reported_depths','depth_report_success','candidate_index','selected_rule_ids','selected_D','selection_success','numeric_choice_success','pipeline_success','error_codes')
    for slot in plan['slots']:
        problem=next(p for p in protocol['problems'] if p['id']==slot['problem_id'])
        routes=[protocol['reference_plans'][problem['id']][protocol['reference_conditions'][i]] for i in protocol['candidate_orders'][slot['candidate_order_index']]]
        ds=[_reference_depth(problem,ids) for ids in routes]
        target=None if slot['stage']=='estimate' else sorted(ds)[0 if slot['condition']=='shallow' else -1]
        row=copy.deepcopy(slot)
        row.update(status='not_observed',expected_depths=ds,target_D=target,usage=_usage(None),response_sha256=None,done_reason=None)
        row.update({field:None for field in fields})
        annotation=seen.get(slot['unit_id']+'_estimate')
        if slot['id'] in records:
            rec=records[slot['id']]
            try:envelope=common.load(_base64(rec['response_b64'],'response'))
            except (ValueError,UnicodeError):envelope=None
            status,obj=_parse_response(envelope,rec['http_status'],rec['error'],plan['identity']['model'])
            if isinstance(envelope,dict) and _is_int(envelope.get('eval_count')) and envelope['eval_count']>protocol['num_predict']:
                status,obj='generation_budget_exceeded',None
            row.update(status=status,usage=_usage(envelope),response_sha256=rec['response_sha256'],done_reason=envelope.get('done_reason') if isinstance(envelope,dict) else None)
            if status=='ok':
                row['error_codes']=[]
                if slot['stage']=='estimate':
                    row['format_valid']=_depth_payload(obj)
                    if row['format_valid']:
                        row['reported_depths']=list(obj['depths'])
                        row['depth_report_success']=all(a==b for a,b in zip(obj['depths'],ds))
                        if not row['depth_report_success']:row['error_codes']=['wrong_candidate_depths']
                    else:row['error_codes']=['invalid_depth_schema']
                else:
                    row['format_valid']=_choice_payload(obj)
                    if row['format_valid']:
                        index=obj['candidate_index'];row['candidate_index']=index
                        row['selected_rule_ids']=list(routes[index]);row['selected_D']=ds[index]
                        row['selection_success']=ds[index]==target
                        given=ds if slot['arm']=='oracle_depth' else annotation['reported_depths'] if annotation else None
                        if given is not None and given[0]!=given[1]:
                            other=1-index
                            row['numeric_choice_success']=(given[index]<given[other]) if slot['condition']=='shallow' else (given[index]>given[other])
                            if not row['numeric_choice_success']:row['error_codes'].append('wrong_numeric_direction')
                        if not row['selection_success']:row['error_codes'].append('wrong_actual_depth_direction')
                        row['error_codes'].sort()
                    else:row['error_codes']=['invalid_choice_schema']
                if row['format_valid'] is False:row['status']='invalid_schema'
            elif status in ('invalid_json','invalid_schema'):row['format_valid']=False
        if slot['arm']=='model_depth' and annotation and type(annotation['depth_report_success']) is bool and type(row['selection_success']) is bool:
            row['pipeline_success']=all((annotation['depth_report_success'],row['selection_success']))
        rows.append(row);seen[slot['id']]=row
    pairs=[]
    for slot in plan['slots']:
        if slot['condition']!='shallow':continue
        group=[row for row in rows if row['pair_id']==slot['pair_id']]
        shallow=next(row for row in group if row['condition']=='shallow')
        deep=next(row for row in group if row['condition']=='deep')
        choice_known=all(type(row['selection_success']) is bool for row in group)
        path_known=all(type(row['pipeline_success']) is bool for row in group)
        pairs.append({'pair_id':slot['pair_id'],'unit_id':slot['unit_id'],'problem_id':slot['problem_id'],'seed':slot['seed'],
            'candidate_order_index':slot['candidate_order_index'],'arm':slot['arm'],'shallow_D':shallow['selected_D'],'deep_D':deep['selected_D'],
            'same_selected_route':shallow['selected_rule_ids']==deep['selected_rule_ids'] if shallow['selected_rule_ids'] is not None and deep['selected_rule_ids'] is not None else None,
            'selective_pair_success':all(row['selection_success'] for row in group) if choice_known else None,
            'pipeline_pair_success':all(row['pipeline_success'] for row in group) if path_known else None})
    ec=_count([r for r in rows if r['stage']=='estimate'],'depth_report_success')
    oc=_count([r for r in rows if r['arm']=='oracle_depth'],'selection_success')
    mc=_count([r for r in rows if r['arm']=='model_depth'],'selection_success')
    pc=_count([r for r in rows if r['arm']=='model_depth'],'pipeline_success')
    op=len([p for p in pairs if p['arm']=='oracle_depth' and p['selective_pair_success'] is True])
    mp=len([p for p in pairs if p['arm']=='model_depth' and p['selective_pair_success'] is True])
    pp=len([p for p in pairs if p['arm']=='model_depth' and p['pipeline_pair_success'] is True])
    full=state=='complete' and len(calls)==100
    complete=full and [ec['measured'],oc['measured'],mc['measured']]==[20,40,40]
    oracle=(oc['successes']==40 and op==20) if full and oc['measured']==40 else None
    estimator=(ec['successes']==20) if full and ec['measured']==20 else None
    pipeline=(oracle and estimator and pc['successes']==40 and pp==20) if complete else None
    if not complete:decision='measurement_incomplete_no_retry'
    elif oracle is not True:decision='numeric_positive_control_failed_close_contract'
    elif estimator is not True:decision='depth_estimation_failed_close_contract'
    elif pipeline is not True:decision='model_report_selection_failed_close_contract'
    else:decision='components_ready_design_separate_graph_composition'
    groups=[]
    for problem in protocol['problems']:
        subset=[r for r in rows if r['problem_id']==problem['id']]
        groups.append({'problem_id':problem['id'],'estimates':_count([r for r in subset if r['stage']=='estimate'],'depth_report_success'),
            'oracle_selection':_count([r for r in subset if r['arm']=='oracle_depth'],'selection_success'),
            'model_selection':_count([r for r in subset if r['arm']=='model_depth'],'selection_success'),
            'model_pipeline':_count([r for r in subset if r['arm']=='model_depth'],'pipeline_success')})
    result={'contract':'v071-report-r1','run_name':plan['run_name'],'provenance':plan['provenance'],'plan_sha256':plan['plan_sha256'],
        'state':state,'full_complete':full,'assigned_calls':100,'observed_calls':len(calls),'rows':rows,'pairs':pairs,'groups':groups,
        'overall':{'depth_reports':ec,'oracle_selection':oc,'model_selection':mc,'model_pipeline':pc,
            'oracle_pair_successes':op,'model_selection_pair_successes':mp,'model_pipeline_pair_successes':pp,'pairs_per_arm':20,
            'unmeasured_calls':100-ec['measured']-oc['measured']-mc['measured'],
            'oracle_ready':oracle,'depth_estimator_ready':estimator,'pipeline_ready':pipeline,'next_decision':decision,
            'end_to_end_graph_D_control':None,'A_or_M_gate':None,'v069_constructor_successes_unchanged':12,
            'v070_selection_successes_unchanged':20,'v070_paired_successes_unchanged':0},
        'usage':{k:sum(r['usage'][k] for r in rows) if full and all(r['usage'][k] is not None for r in rows) else None for k in _USAGE_FIELDS},
        'limits':{'model_depths_repaired':False,'oracle_depths_given':True,'constructor_executed':False,
            'independent_holdout':False,'v070_concurrent_comparison':False,'shared_estimates':20,'choices_per_shared_estimate':2,'internal_cause_identified':False}}
    return common.load(json.dumps(result,ensure_ascii=False,sort_keys=True))

def _render(r):
    a=r['overall'];label='미판정' if a['pipeline_ready'] is None else '통과' if a['pipeline_ready'] else '불통과'
    lines=['# v071 깊이 계산 원문 → 수치 선택 / 정답 깊이 양성 대조','',
        f"상태: {r['state']} / 관측 {r['observed_calls']}/100 / provenance: {r['provenance']}",
        'v070은 선택 20/40, 선택적 pair 0/20으로 종료했다. 기존 실패를 수정하거나 재채점하지 않는다.',
        '깊이 계산 20회, 모델 계산 원문 선택 40회, 정답 깊이 입력 선택 40회다. 정답입력군은 모델의 깊이 계산 성공으로 세지 않는다.',
        '모델의 깊이가 틀리면 뒤의 경로 선택이 우연히 맞아도 계산→선택 전체 성공이 아니다. 잘못된 중간값도 원문 그대로 전달한다.','',
        '|문제|깊이 계산|정답 깊이 선택|모델 원문 경로 선택|계산→선택 전체|',
        '|---|---:|---:|---:|---:|']
    for g in r['groups']:
        values=[g[k] for k in ('estimates','oracle_selection','model_selection','model_pipeline')]
        lines.append('|'+g['problem_id']+'|'+'|'.join(str(v['successes'])+'/'+str(v['assigned']) for v in values)+'|')
    lines+=['','## 전체 판정',
        f"깊이 계산 {a['depth_reports']['successes']}/20, 정답 깊이 선택 {a['oracle_selection']['successes']}/40, 모델 원문 경로 선택 {a['model_selection']['successes']}/40, 계산→선택 전체 {a['model_pipeline']['successes']}/40.",
        f"선택적 pair: 정답 깊이 {a['oracle_pair_successes']}/20, 모델 원문 경로 선택 {a['model_selection_pair_successes']}/20, 계산→선택 전체 {a['model_pipeline_pair_successes']}/20.",
        f"미측정 호출 {a['unmeasured_calls']}, gate {label}. 다음 결정: {a['next_decision']}",
        '두 D 선택은 같은 깊이 계산 한 번을 공유한다. 40개 선택을 40개의 독립적인 깊이 계산으로 세지 않는다.',
        '성공해도 후보 목록 내 계산·수치 선택 기준선이다. 전체 graph 생성, 자율 계획, A/M, hidden-layer 제어, 비용 우월성으로 확대하지 않는다.',
        '이번 한 배치 이후 이 계약은 종료한다. 실패를 문구/seed 변경으로 자동 반복하지 않는다. 미완료·미측정이면 전체 gate는 null이다.',
        'v069의 지정 graph 구성 12/12는 보존하지만 이번 실험에서 generator를 호출하지 않는다. v070과 동시 대조가 아니며 독립 holdout도 아니다.',
        '',f"원응답 사용량 계수: {r['usage']}",f"계획 SHA-256: {r['plan_sha256']}"]
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
        request_name="wire/" + action["id"] + "/request.wire.json"
        expected_request=_request_for(plan, slot, files) if request_name in files else b""
        sequence = [(request_name, expected_request),
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
    expected_names = {"plan.json", "runtime.json", "baseline/v070_evidence.zip", "records/events.jsonl", "status.json", "summary.json", "summary.ko.md", "MANIFEST.json"}
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
