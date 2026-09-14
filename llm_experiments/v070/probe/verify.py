"""독립적인 v070 증거 번들 검산기.

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


PLAN_CONTRACT = "v070-plan-r1"
EVIDENCE_CONTRACT = "v070-evidence-r1"
REPORT_CONTRACT = "v070-report-r1"
VERIFY_CONTRACT = "v070-independent-verify-r1"
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
    result=[];last=None;last_c=None
    for block in range(10):
        pi,si=divmod(block,2);p=protocol['problems'][pi]
        sequence=((0,'shallow'),(0,'deep'),(1,'deep'),(1,'shallow'))
        for period,index in enumerate(range(4) if si==0 else range(3,-1,-1)):
            order,c=sequence[index];sid='b%02d_o%d_%s'%(block,order,c)
            result.append({'id':sid,'pair_id':'b%02d_o%d'%(block,order),'block':block,'period':period,
                'problem_id':p['id'],'seed':protocol['seeds'][si],'seed_index':si,'condition':c,
                'candidate_order_index':order,'stage':'select','history_ids':[],
                'problem_role':'seen_constructor_task' if block<6 else 'authored_discriminating_control',
                'previous_call_id':last,'previous_condition':last_c})
            last=sid;last_c=c
    if len(result)!=40:_fail('selector schedule')
    return result

def _actions(slots,blocks):
    result=[]
    for b in range(blocks):
        group=[s for s in slots if s['block']==b]
        if len(group)!=4:_fail('four calls per block')
        result+=[{'kind':'metadata','id':'b%02d_before'%b}]
        result+=[{'kind':'call','id':s['id']} for s in group]
        result+=[{'kind':'metadata','id':'b%02d_after'%b}]
    return result

def _baseline(files,protocol):
    raw=files.get('baseline/v069_evidence.zip')
    if raw is None or common.sha(raw)!=protocol['baseline_sha256']:_fail('v069 baseline SHA')
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
    spec=plan['protocol'];p=[p for p in spec['problems'] if p['id']==slot['problem_id']][0]
    if slot['history_ids']:_fail('selector history')
    pair=spec['reference_plans'][p['id']]
    ordered=[pair[spec['reference_conditions'][j]] for j in spec['candidate_orders'][slot['candidate_order_index']]]
    body=copy.deepcopy(plan['baseline_request'])
    if len(body['messages'])!=1 or body['messages'][0]['role']!='user':_fail('baseline messages')
    body['format']={'type':'object','properties':{'rule_ids':{'type':'array','minItems':1,'maxItems':16,'items':{'type':'string','minLength':1,'maxLength':128}}},'required':['rule_ids'],'additionalProperties':False}
    data={'problem':{k:p[k] for k in ('facts','rules','goal')},'candidate_rule_ids':ordered,'requested_depth':spec['headers'][slot['condition']]}
    body['messages'][0]['content']=(spec['headers']['common']+'\nJSON 객체 하나만 출력한다. 출력 형식(JSON Schema):\n'+common.wire(body['format']).decode()+'\n\ninput: '+common.wire(data).decode())
    body['options']['seed']=slot['seed'];raw=common.wire(body)
    if len(raw)>spec['request_utf8_byte_limit']:_fail('request budget')
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


def _selection(problem,obj,candidates,depth):
    ok=isinstance(obj,dict) and set(obj)=={'rule_ids'}
    ok=ok and isinstance(obj['rule_ids'],list) and 0<len(obj['rule_ids'])<=16
    ok=ok and all(isinstance(x,str) and 0<len(x)<=128 for x in obj['rule_ids'])
    r={'format_valid':ok,'candidate_member':None,'selected_position':None,'selected_rule_ids':None,
       'route_valid':None,'route_D':None,'selection_success':None,'error_codes':[]}
    if not ok:r['error_codes']=['invalid_selection_schema'];return r
    r['selected_rule_ids']=list(obj['rule_ids']);positions=[i for i in range(len(candidates)) if candidates[i]==obj['rule_ids']]
    r['candidate_member']=len(positions)==1
    if len(positions)==1:r['selected_position']=positions[0]
    else:r['error_codes'].append('not_exact_candidate')
    try:r['route_D']=_reference_depth(problem,obj['rule_ids']);r['route_valid']=True
    except (ValueError,TypeError):r['route_valid']=False;r['error_codes'].append('invalid_goal_support_route')
    if r['route_valid'] and r['route_D']!=depth:r['error_codes'].append('wrong_depth_direction')
    r['selection_success']=r['candidate_member'] and r['route_valid'] and r['route_D']==depth
    r['error_codes']=sorted(r['error_codes']);return r

def _summary(plan,calls,state):
    recs={c['id']:c for c in calls};spec=plan['protocol'];rows=[]
    for slot in plan['slots']:
        p=next(p for p in spec['problems'] if p['id']==slot['problem_id'])
        d=spec['depth_ranges'][p['id']][0 if slot['condition']=='shallow' else 1]
        cs=[spec['reference_plans'][p['id']][spec['reference_conditions'][i]] for i in spec['candidate_orders'][slot['candidate_order_index']]]
        r=copy.deepcopy(slot);r.update(status='not_observed',target_D=d,usage=_usage(None),response_sha256=None,done_reason=None)
        r.update({k:None for k in ('format_valid','candidate_member','selected_position','selected_rule_ids','route_valid','route_D','selection_success','error_codes')})
        rec=recs.get(slot['id'])
        if rec is not None:
            try:env=common.load(_base64(rec['response_b64'],'response'))
            except (UnicodeError,ValueError):env=None
            status,obj=_parse_response(env,rec['http_status'],rec['error'],plan['identity']['model'])
            if isinstance(env,dict) and _is_int(env.get('eval_count')) and env['eval_count']>spec['num_predict']:status,obj='generation_budget_exceeded',None
            r.update(status=status,usage=_usage(env),response_sha256=rec['response_sha256'],done_reason=env.get('done_reason') if isinstance(env,dict) else None)
            if status=='ok':
                r.update(_selection(p,obj,cs,d))
                if not r['format_valid']:r['status']='invalid_schema'
            elif status in ('invalid_json','invalid_schema'):r['format_valid']=False
        rows.append(r)
    pairs=[]
    for shallow in [r for r in rows if r['condition']=='shallow']:
        deep=next(r for r in rows if r['pair_id']==shallow['pair_id'] and r['condition']=='deep')
        both=_is_bool(shallow['selection_success']) and _is_bool(deep['selection_success'])
        pairs.append({'pair_id':shallow['pair_id'],'problem_id':shallow['problem_id'],'seed':shallow['seed'],
            'candidate_order_index':shallow['candidate_order_index'],'shallow_D':shallow['route_D'],'deep_D':deep['route_D'],
            'same_selected_route':shallow['selected_rule_ids']==deep['selected_rule_ids'] if shallow['selected_rule_ids'] is not None and deep['selected_rule_ids'] is not None else None,
            'selective_pair_success':(shallow['selection_success'] and deep['selection_success']) if both else None})
    observed=len(calls);full=state=='complete' and observed==40
    measured=len([r for r in rows if _is_bool(r['selection_success'])]);successes=len([r for r in rows if r['selection_success'] is True])
    count=len([p for p in pairs if p['selective_pair_success'] is True]);ready=full and measured==40
    gate=(successes==40 and count==20) if ready else None
    decision='measurement_incomplete_no_retry'
    if ready:decision='selector_ready_design_separate_composition' if gate else 'selector_failed_preserve_ranges_close_formulation'
    groups=[]
    for p in spec['problems']:
        for cond in spec['conditions']:
            rr=[r for r in rows if (r['problem_id'],r['condition'])==(p['id'],cond)]
            groups.append({'problem_id':p['id'],'condition':cond,'assigned':len(rr),'measured':len([r for r in rr if _is_bool(r['selection_success'])]),'successes':len([r for r in rr if r['selection_success'] is True]),'valid_routes':len([r for r in rr if r['route_valid'] is True])})
    usage={}
    for key in _USAGE_FIELDS:
        values=[r['usage'][key] for r in rows];usage[key]=sum(values) if full and None not in values else None
    return {'contract':'v070-report-r1','run_name':plan['run_name'],'provenance':plan['provenance'],'plan_sha256':plan['plan_sha256'],
        'state':state,'full_complete':full,'assigned_calls':40,'observed_calls':observed,'rows':rows,'pairs':pairs,'groups':groups,
        'overall':{'assigned':40,'measured':measured,'successes':successes,'unmeasured':40-measured,'paired_successes':count,'assigned_pairs':20,
            'selector_ready':gate,'rate':successes/40 if ready else None,'next_decision':decision,'end_to_end_graph_D_control':None,'A_or_M_gate':None,'v069_successes_unchanged':12},
        'usage':usage,'limits':{'candidate_routes_given':True,'candidate_depth_labels_given':False,'host_repair':False,'constructor_executed':False,'independent_holdout':False,'internal_cause_identified':False}}

def _is_bool(value):return type(value) is bool

def _render(r):
    a=r['overall'];label='미판정' if a['selector_ready'] is None else '통과' if a['selector_ready'] else '불통과'
    lines=['# v070 D 지시 기반 후보 경로 선택','',f"상태: {r['state']} / 관측 {r['observed_calls']}/40 / provenance: {r['provenance']}",
        'v069의 지정 append-only 구성 12/12는 그대로 보존한다. 이번에는 경로 선택만 측정하며 generator를 호출하지 않는다.',
        '두 정상 후보를 주지만 short/long 정답 라벨이나 기대 D는 모델에게 주지 않는다. shallow/deep 요구와 후보 순서를 교차한다.',
        'C01은 규칙 개수가 같고 D가 다르다. C02는 얕은 후보의 규칙이 더 많다. 두 문제는 직접 만든 진단 대조이며 독립 holdout이 아니다.','',
        '|문제|D 요구|성공/배정|측정|유효 경로|','|---|---|---:|---:|---:|']
    for g in r['groups']:lines.append(f"|{g['problem_id']}|{g['condition']}|{g['successes']}/{g['assigned']}|{g['measured']}|{g['valid_routes']}|")
    lines+=['','## 전체 판정',f"선택 성공 {a['successes']}/40, 선택적 pair {a['paired_successes']}/20, 미측정 {a['unmeasured']}, gate {label}.",
        f"다음 결정: {a['next_decision']}",
        '40/40 및 20/20이어도 후보 목록 내 D 선택 기준선이다. 자유 계획 생성·전체 graph D 제어·A/M 성공으로 바꾸지 않는다.',
        '실패/부분 성공은 원범위를 보존하고 이 선택 계약을 종료한다. 자동 재시도·seed 변경·다음 단계 자동 실행은 없다.',
        '형식 오류·미실행·중단·길이 종료는 논리 오답 또는 D=0으로 채우지 않는다. 미완료/미측정이면 전체 gate는 null이다.',
        '규칙 목록의 D는 입력 규칙 의존 관계에서 검산한 값이며 모델이 작성한 parent ID를 검증한 graph D가 아니다.',
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
    expected_names = {"plan.json", "runtime.json", "baseline/v069_evidence.zip", "records/events.jsonl", "status.json", "summary.json", "summary.ko.md", "MANIFEST.json"}
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
