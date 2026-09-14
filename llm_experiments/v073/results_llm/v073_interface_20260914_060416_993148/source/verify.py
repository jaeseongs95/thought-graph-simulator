"""독립적인 v073 증거 번들 검산기.

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


PLAN_CONTRACT = "v073-plan-r1"
EVIDENCE_CONTRACT = "v073-evidence-r1"
REPORT_CONTRACT = "v073-report-r1"
VERIFY_CONTRACT = "v073-independent-verify-r1"
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
    schedule=[]
    # 생산 실행기와 달리 block 번호에서 요인을 역산한다.
    base=(('compact','shallow'),('compact','deep'),('comma_space','shallow'),('comma_space','deep'))
    for block in range(16):
        pi,rest=divmod(block,4);si,oi=divmod(rest,2);unit='b%02d'%block
        for pos in range(4):
            offset=(pi+oi)%4
            treatment=base[(offset+(3-pos if si else pos))%4]
            fmt,condition=treatment
            schedule.append({'id':unit+'_'+fmt+'_'+condition,'unit_id':unit,'pair_id':unit+'_'+fmt,
                'block':block,'period':pos,'numeric_pair_id':protocol['numeric_pairs'][pi]['id'],'seed':protocol['seeds'][si],
                'seed_index':si,'candidate_order_index':oi,'format':fmt,'condition':condition,'stage':'select','history_ids':[]})
    return schedule

def _actions(slots,blocks):
    actions=[]
    for b in range(blocks):
        chosen=[s['id'] for s in slots if s['block']==b]
        if len(chosen)!=4:_fail('four calls per block')
        actions.append({'kind':'metadata','id':'b%02d_before'%b})
        actions += [{'kind':'call','id':sid} for sid in chosen]
        actions.append({'kind':'metadata','id':'b%02d_after'%b})
    return actions

def _baseline(files,protocol):
    raw=files.get('baseline/v072_evidence.zip')
    if raw is None or common.sha(raw)!=protocol['baseline_sha256']:_fail('v072 baseline SHA')
    prior,old,request,receipt=previous.inspect_prior(raw)
    if not receipt['verified'] or receipt['state']!='complete':_fail('prior complete')
    show=_object(prior['metadata/b00_before/2.response.raw.json'],'archived native')
    frozen={}
    for key in ('template','system','parameters','model_info','details','capabilities','projector_info'):
        frozen[key]=show.get(key)
    if frozen['parameters'] is not None:frozen['parameters']=sorted(frozen['parameters'].split('\n'))
    identity={'model':protocol['model'],'digest':protocol['model_digest'],'server':copy.deepcopy(old['identity']['server']),
        'tag_details':copy.deepcopy(old['identity']['tag_details']),'native':frozen,
        'native_fingerprint_source':'baseline/v072_evidence.zip:metadata/b00_before/2.response.raw.json'}
    return request,identity

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
    if protocol['max_inference_calls']!=64 or protocol['assigned_blocks']!=16 or protocol['max_actions']!=96:
        _fail('frozen budget')
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
    values=next(p['values'][:] for p in protocol['numeric_pairs'] if p['id']==slot['numeric_pair_id'])
    if slot['candidate_order_index']==1:values.reverse()
    inner='{"depths":['+str(values[0])+(',' if slot['format']=='compact' else ', ')+str(values[1])+']}'
    payload={'depth_report':inner,'requested_depth':protocol['headers'][slot['condition']]}
    body['messages'][0]['content']=protocol['headers']['compare']+'\nJSON 객체 하나만 출력한다. 출력 형식(JSON Schema):\n'+common.wire(protocol['schema']).decode('utf-8')+'\n\ninput: '+common.wire(payload).decode('utf-8')
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


def _native_snapshot(items, expected):
    if len(items)!=3:
        raise ValueError('incomplete native metadata')
    decoded=[]
    for item in items:
        if item['http_status']!=200 or item['error'] is not None:raise ValueError('native transport')
        decoded.append(_object(_base64(item['response_b64'],'native'),'native metadata'))
    version,tags,show=decoded
    selected=[m for m in tags['models'] if expected['model'] in (m.get('name'),m.get('model'))]
    if len(selected)!=1:raise ValueError('ambiguous native tag')
    model=selected[0]
    if model.get('digest')!=expected['digest'] or not common.exact(model.get('details'),expected['tag_details']):
        raise ValueError('native digest/details not archived target')
    if not common.exact(version,expected['server']):raise ValueError('server drift')
    if not isinstance(show.get('template'),str) or not show['template'].strip():raise ValueError('missing native template')
    if not isinstance(show.get('details'),dict) or not isinstance(show.get('model_info'),dict):raise ValueError('native object types')
    if any(show['details'].get(k)!=expected['tag_details'].get(k) for k in ('family','format','parameter_size','quantization_level')):
        raise ValueError('show identity mismatch')
    values=[show.get(k) for k in ('template','system','parameters','model_info','details','capabilities','projector_info')]
    if values[2] is not None:
        if not isinstance(values[2],str):raise ValueError('parameters type')
        values[2]=sorted(values[2].split('\n'))
    return values


def _identity_matches(items,expected,pinned_items=None):
    try:
        snapshot=_native_snapshot(items,expected)
        archived=[expected['native'][k] for k in ('template','system','parameters','model_info','details','capabilities','projector_info')]
        return common.exact(snapshot,archived) and (pinned_items is None or common.exact(snapshot,_native_snapshot(pinned_items,expected)))
    except (KeyError,TypeError,UnicodeError,ValueError):
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
    pin_items=None if action["id"]=="b00_before" else _object(files["records/b00_before.json"],"native pin")["items"]
    if record["identity_ok"] != _identity_matches(record["items"], plan["identity"],pin_items):
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


def _choice_payload(value):
    return isinstance(value,dict) and set(value)=={'candidate_index'} and _is_int(value['candidate_index']) and 0<=value['candidate_index']<=1

def _count(rows,field):
    values=[r[field] for r in rows]
    return {'assigned':len(values),'measured':sum(type(v) is bool for v in values),'successes':sum(v is True for v in values)}

def _summary(plan,calls,state):
    protocol=plan['protocol'];by_id={r['id']:r for r in calls};rows=[]
    if len(by_id)!=len(calls) or not set(by_id).issubset({s['id'] for s in plan['slots']}):_fail('unknown/duplicate call')
    for slot in plan['slots']:
        source=next(p['values'] for p in protocol['numeric_pairs'] if p['id']==slot['numeric_pair_id'])
        values=source[:] if slot['candidate_order_index']==0 else list(reversed(source))
        smaller=0 if values[0]<values[1] else 1
        expected=smaller if slot['condition']=='shallow' else 1-smaller
        r=copy.deepcopy(slot)
        r.update(input_values=values,expected_index=expected,status='not_observed',format_valid=None,
            candidate_index=None,selection_success=None,error_codes=None,usage=_usage(None),response_sha256=None,done_reason=None)
        if slot['id'] in by_id:
            call=by_id[slot['id']]
            try:env=common.load(_base64(call['response_b64'],'response'))
            except (ValueError,UnicodeError):env=None
            status,payload=_parse_response(env,call['http_status'],call['error'],plan['identity']['model'])
            if call['error'] is not None:status,payload='transport_error',None
            elif call['http_status']!=200:status,payload=('transport_error' if call['http_status'] is None else 'http_error'),None
            elif isinstance(env,dict) and env.get('model')==plan['identity']['model']:
                if _is_int(env.get('eval_count')) and env['eval_count']>protocol['num_predict']:status,payload='generation_budget_exceeded',None
                elif env.get('done_reason')=='length':status,payload='generation_length',None
            if status=='ok' and not _choice_payload(payload):status,payload='invalid_schema',None
            r.update(status=status,usage=_usage(env),response_sha256=call['response_sha256'],done_reason=env.get('done_reason') if isinstance(env,dict) else None)
            if status=='ok':
                chosen=payload['candidate_index'];correct=(values[chosen]<values[1-chosen]) if slot['condition']=='shallow' else (values[chosen]>values[1-chosen])
                r.update(format_valid=True,candidate_index=chosen,selection_success=correct,error_codes=[] if correct else ['wrong_numeric_direction'])
            else:
                r['error_codes']=[status]
                if status in ('invalid_json','invalid_schema'):r['format_valid']=False
        rows.append(r)
    pairs=[]
    for slot in plan['slots']:
        if slot['condition']!='shallow':continue
        sh=next(r for r in rows if r['id']==slot['id'])
        de=next(r for r in rows if r['pair_id']==slot['pair_id'] and r['condition']=='deep')
        valid=isinstance(sh['selection_success'],bool) and isinstance(de['selection_success'],bool)
        pairs.append({'pair_id':slot['pair_id'],'unit_id':slot['unit_id'],'numeric_pair_id':slot['numeric_pair_id'],'seed':slot['seed'],
            'candidate_order_index':slot['candidate_order_index'],'format':slot['format'],
            'shallow_index':sh['candidate_index'],'deep_index':de['candidate_index'],
            'same_index':sh['candidate_index']==de['candidate_index'] if valid else None,
            'pair_success':bool(sh['selection_success'] and de['selection_success']) if valid else None})
    contrasts=[]
    for block in range(16):
        for condition in ['shallow','deep']:
            c=next(r for r in rows if r['block']==block and r['condition']==condition and r['format']=='compact')
            s=next(r for r in rows if r['block']==block and r['condition']==condition and r['format']=='comma_space')
            known=isinstance(c['selection_success'],bool) and isinstance(s['selection_success'],bool)
            classifications={(True,True):'both_correct',(False,False):'both_wrong',(True,False):'compact_only',(False,True):'spaced_only'}
            label=classifications[(c['selection_success'],s['selection_success'])] if known else 'unmeasured'
            contrasts.append({'unit_id':c['unit_id'],'numeric_pair_id':c['numeric_pair_id'],'seed':c['seed'],'candidate_order_index':c['candidate_order_index'],
                'condition':condition,'compact_index':c['candidate_index'],'comma_space_index':s['candidate_index'],
                'index_changed':c['candidate_index']!=s['candidate_index'] if known else None,
                'spaced_minus_compact_correct':(1 if s['selection_success'] else 0)-(1 if c['selection_success'] else 0) if known else None,
                'classification':label})
    full=state=='complete' and len(calls)==64
    total=_count(rows,'selection_success');complete=full and total['measured']==64
    formats=[]
    for fmt in protocol['formats']:
        selection=_count([r for r in rows if r['format']==fmt],'selection_success')
        paired=_count([r for r in pairs if r['format']==fmt],'pair_success')
        gate=(selection['successes'],paired['successes'])==(32,16) if full and selection['measured']==32 else None
        formats.append({'format':fmt,'selection':selection,'pairs':paired,'qualified':gate})
    passed=[] if not complete else [f['format'] for f in formats if f['qualified'] is True]
    preferred=None
    for fmt in protocol['qualifying_format_priority']:
        if fmt in passed:preferred=fmt;break
    if not complete:decision='measurement_incomplete_close_without_retry'
    elif not passed:decision='no_interface_qualified_close_diagnostic_branch'
    elif len(passed)==1:decision='format_specific_qualified_return_to_end_to_end_design'
    else:decision='tested_formats_qualified_return_to_end_to_end_design'
    cells=[];groups=[]
    for fmt in protocol['formats']:
        for order in range(2):
            subset=[r for r in rows if r['format']==fmt and r['candidate_order_index']==order]
            cells.append({'format':fmt,'candidate_order_index':order,'selection':_count(subset,'selection_success'),
                'index_0':len([r for r in subset if r['candidate_index']==0]),'index_1':len([r for r in subset if r['candidate_index']==1])})
    for pair in protocol['numeric_pairs']:
        for fmt in protocol['formats']:
            groups.append({'numeric_pair_id':pair['id'],'format':fmt,'selection':_count([r for r in rows if r['numeric_pair_id']==pair['id'] and r['format']==fmt],'selection_success')})
    result={'contract':'v073-report-r1','run_name':plan['run_name'],'provenance':plan['provenance'],'plan_sha256':plan['plan_sha256'],
        'model':plan['identity']['model'],'state':state,'full_complete':full,'assigned_calls':64,'observed_calls':len(calls),
        'rows':rows,'pairs':pairs,'formats':formats,'format_order_cells':cells,'numeric_pair_groups':groups,'format_contrasts':contrasts,
        'overall':{'selection':total,'pairs':_count(pairs,'pair_success'),'unmeasured_calls':64-total['measured'],
            'all_measured':complete,'interface_ready':bool(passed) if complete else None,'qualified_formats':passed,'preferred_format_for_new_contract':preferred,
            'robust_across_two_tested_formats':len(passed)==2 if complete else None,'next_decision':decision,
            'automatic_next_experiment':False,'end_to_end_graph_D_control':None,'A_or_M_gate':None},
        'contrast_counts':{label:len([r for r in contrasts if r['classification']==label]) for label in ['both_correct','both_wrong','compact_only','spaced_only','unmeasured']},
        'request_repetition':{'observed':len(calls),'unique_request_bytes':len(set(r['request_sha256'] for r in calls)),
            'observed_conditions_without_seed':len(set((r['numeric_pair_id'],r['candidate_order_index'],r['format'],r['condition']) for r in rows if r['id'] in by_id)),
            'unique_numeric_pairs':4,'assigned_conditions_without_seed':32},
        'usage':{key:sum(r['usage'][key] for r in rows) if full and all(r['usage'][key] is not None for r in rows) else None for key in _USAGE_FIELDS},
        'v072_frozen_result':copy.deepcopy(protocol['v072_frozen_result']),
        'limits':{'experimenter_numbers_provided':True,'model_output_repaired':False,'depth_estimation_executed':False,'constructor_executed':False,
            'new_graph_holdout':False,'output_schema_changed':False,'native_model_package_changed':False,'internal_cause_identified':False,
            'previous_failures_rescored':False,'new_run_automatically_repeated':False}}
    return common.load(json.dumps(result,ensure_ascii=False,sort_keys=True))

def _render(result):
    a=result['overall'];label='미판정' if a['interface_ready'] is None else '기준 충족' if a['interface_ready'] else '기준 미달'
    lines=['# v073 공백 × 후보 순서 인터페이스 양성 대조','',
        f"상태: {result['state']} / 관측 {result['observed_calls']}/64 / provenance: {result['provenance']}",
        '실험자가 제공한 숫자쌍 4개 × 공백 형식 2개 × 후보 순서 2개 × 방향 2개 × seed 2개다.',
        '값·지시·모델·출력 스키마·생성 옵션은 고정했다. 비교 형식은 쉼표 뒤 공백 한 글자만 다르다.',
        '기존 v072의 응답과 점수는 변경하지 않았다. 이 검사는 깊이 계산이나 최종 graph의 D 제어를 측정하지 않는다.','',
        '|형식|후보 순서|수치 선택 성공/배정|측정|인덱스 0 / 1|','|---|---|---:|---:|---:|']
    for cell in result['format_order_cells']:
        c=cell['selection'];ordering='작은 값 먼저' if cell['candidate_order_index']==0 else '큰 값 먼저'
        lines.append(f"|{cell['format']}|{ordering}|{c['successes']}/{c['assigned']}|{c['measured']}|{cell['index_0']} / {cell['index_1']}|")
    lines+=['','## 형식별 공학적 기준','|형식|선택|양방향 비교 쌍|판정|','|---|---:|---:|---|']
    for f in result['formats']:
        q='미판정' if f['qualified'] is None else '충족' if f['qualified'] else '미달'
        lines.append(f"|{f['format']}|{f['selection']['successes']}/32|{f['pairs']['successes']}/16|{q}|")
    lines+=['',f"전체 선택 {a['selection']['successes']}/64, 양방향 쌍 {a['pairs']['successes']}/32, 미측정 {a['unmeasured_calls']}.",
        f"인터페이스 gate: {label}. 후속 결정: {a['next_decision']}",
        f"충족 형식: {a['qualified_formats']}; 새 계약 설계 시 우선 형식: {a['preferred_format_for_new_contract']}",
        '한 형식만 통과하면 그 형식에 한정한 결과다. 양쪽 통과도 이 4개 숫자쌍·2개 seed 범위의 기준이지 보편적 능력 인증이 아니다.',
        '통과하면 다음 작업은 종단 D 실험 설계다. 정밀한 숫자 보고를 본실험의 새로운 필수조건으로 추가하지 않는다.',
        '실패하면 이 제한 진단을 닫는다. 형식/seed/숫자쌍 추가 탐색이나 새 모델 호출을 자동 실행하지 않는다.',
        '미완료·파싱·스키마·생성 예산 문제는 전체 gate null로 남긴다. 미측정을 오답이나 0으로 채우지 않는다.',
        '', '## 공백만 다른 요청의 짝비교',str(result['contrast_counts']),
        '짝비교와 개별 성공 수는 같은 원응답의 서로 다른 집계다. 독립 실험 표본으로 중복 계산하지 않는다.',
        '', '## 요청 반복 및 사용량',str(result['request_repetition']),str(result['usage']),
        'seed 반복과 같은 숫자쌍을 새로운 독립 과제로 세지 않는다. 누락된 사용량은 0으로 대체하지 않는다.',
        '', 'v072 결과 동결: '+str(result['v072_frozen_result']),
        '종단 graph 생성, A/M, 모델 내부 원인, 출력 스키마의 효과는 이번 검사로 확인하지 않는다.',
        f"계획 SHA-256: {result['plan_sha256']}"]
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
    expected_names = {"plan.json", "runtime.json", "baseline/v072_evidence.zip", "records/events.jsonl", "status.json", "summary.json", "summary.ko.md", "MANIFEST.json"}
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
