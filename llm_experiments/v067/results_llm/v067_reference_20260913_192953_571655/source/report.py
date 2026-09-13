"""Frozen v067 result aggregation and Korean report rendering."""
from __future__ import annotations

import base64
from collections import defaultdict
from copy import deepcopy

import common
import measure


CONTRACT = "v067-report-r1"
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




def summarize(plan,records,state):
    """주어진 정답 경로를 재구성하는 기능을 측정한다. 경로 선택의 성과가 아니다."""
    if plan['contract']!='v067-plan-r1':raise ValueError('plan')
    state=_run_state(state);problems=_problem_index(plan);index=_record_index(records,{s['id'] for s in plan['slots']})
    rows=[_row(plan,s,index.get(s['id']),problems) for s in plan['slots']]
    for r in rows:
        supplied=r['reference_rule_ids'];ref_D=plan['protocol']['depth_ranges'][r['problem_id']][r['condition']=='reference_long']
        envelope=_decode_raw(index[r['id']]) if r['id'] in index else None
        payload=measure.parse_response(envelope,r['http_status'],r['error'],plan['identity']['model'])[1] if r['id'] in index else None
        ids=[n['rule'] for n in payload['nodes'] if n['rule'] is not None] if r['format_valid'] is True else None
        follows=None if ids is None else ids==supplied
        success=None if r['strict_valid'] is None or follows is None else bool(r['strict_valid'] and follows and r['actual_D']==ref_D)
        r.update(reference_input_D=ref_D,emitted_rule_ids=ids,reference_order_followed=follows,reference_reconstruction_success=success,D_instruction_control_success=None)
    observed=sum(r['status']!='not_observed' for r in rows);complete=state=='complete' and observed==len(rows)
    measured=sum(r['reference_reconstruction_success'] is not None for r in rows);success=sum(r['reference_reconstruction_success'] is True for r in rows)
    groups=[]
    for p in plan['protocol']['problems']:
        for cond in plan['protocol']['conditions']:
            rr=[r for r in rows if r['problem_id']==p['id'] and r['condition']==cond]
            known=all(r['reference_reconstruction_success'] is not None for r in rr)
            groups.append({'problem_id':p['id'],'condition':cond,'reference_rule_ids':plan['protocol']['reference_plans'][p['id']][cond],
              'assigned':len(rr),'observed':sum(r['status']!='not_observed' for r in rr),'logical_valid':sum(r['proof_valid'] is True for r in rr),'strict_valid':sum(r['strict_valid'] is True for r in rr),'reference_order_followed':sum(r['reference_order_followed'] is True for r in rr),'reconstruction_successes':sum(r['reference_reconstruction_success'] is True for r in rr),'unmeasured':sum(r['reference_reconstruction_success'] is None for r in rr),'rate':sum(r['reference_reconstruction_success'] is True for r in rr)/len(rr) if complete and known else None})
    ready=success==len(rows) if complete and measured==len(rows) else None
    return {'contract':'v067-report-r1','run_name':plan['run_name'],'provenance':plan['provenance'],'plan_sha256':plan['plan_sha256'],
      'state':state,'full_complete':complete,'assigned_calls':len(rows),'observed_calls':observed,'rows':rows,'groups':groups,
      'overall':{'measured_graphs':measured,'reconstruction_successes':success,'positive_control_ready':ready,'reconstruction_rate':success/len(rows) if ready is not None else None,'D_instruction_control':'not_measured','A_or_M_gate':None,'v066_failure_preserved':True,'next_decision':('measurement_incomplete' if ready is None else ('reference_constructor_available_not_D' if ready else ('close_current_graph_task_branch' if success==0 else 'preserve_partial_scope_no_automatic_extension')))},
      'failure_layers':{'proof_failures':sum(r['proof_valid'] is False for r in rows),'strict_only_failures':sum(r['proof_valid'] is True and r['strict_valid'] is False for r in rows),'reference_order_mismatch':sum(r['reference_order_followed'] is False for r in rows),'unmeasured':len(rows)-measured,'not_observed':sum(r['status']=='not_observed' for r in rows)},
      'usage':{k:sum(r['usage'][k] for r in rows) if complete and all(r['usage'][k] is not None for r in rows) else None for k in _USAGE_FIELDS},
      'limits':{'reference_origin':'experimenter_verified_reference','solution_rule_path_provided':True,'output_graph_host_repair':False,'model_chose_reference_path':False,'A':'not_measured','M':'not_measured','not_holdout':True,'historical_comparison_not_causal_effect':True}}

def render(r):
    flag=r['overall']['positive_control_ready'];label='미판정' if flag is None else ('통과' if flag else '불통과')
    lines=['# v067 정상 참조 계획 재구성 양성 대조','',f"실행 상태: {r['state']} / 관측: {r['observed_calls']}/{r['assigned_calls']} / provenance: {r['provenance']}",
      '**실험자가 정답 규칙 경로를 입력으로 제공했다. 모델의 자율적인 D 제어나 모델 계획→생성의 종단 성공이 아니다.**',
      f"참조 입력 재구성: {r['overall']['reconstruction_successes']}/12, 미측정 {12-r['overall']['measured_graphs']}, 양성 대조 기준: {label}.",'',
      '|문제|참조 종류|제공된 규칙 경로|관측/배정|논리 유효|엄격 증명|순서 이행|재구성 성공|미측정|',
      '|---|---|---|---:|---:|---:|---:|---:|---:|']
    for g in r['groups']:
        lines.append(f"|{g['problem_id']}|{g['condition']}|{','.join(g['reference_rule_ids'])}|{g['observed']}/{g['assigned']}|{g['logical_valid']}|{g['strict_valid']}|{g['reference_order_followed']}|{g['reconstruction_successes']}|{g['unmeasured']}|")
    lines+=['','## 해석과 종료',
      '12/12이면 정상 계획을 입력했을 때 이 생성 인터페이스가 재구성할 수 있다는 기준선만 얻는다. 과거 v066의 실패를 취소하거나 원인이 계획기 하나뿐이었다고 단정하지 않는다.',
      '12건이 모두 측정됐는데 성공이 0/12이면 이 모델과 현재 전체-DAG 출력 계약의 양성 대조도 종료한다. 부분 성공은 해당 문제·참조 경로·seed에 한정한다. 같은 문구를 바꾸며 자동 반복하지 않는다.',
      '미관측·파싱 불가이면 전부 오답으로 채우지 않고 전체 기준은 미판정이다. A/M·내부 사고·비용 우월성·새 문제 일반화는 측정하지 않았다.',
      '이 대조의 정답 입력은 명시적 조건이다. 모델의 출력 노드·부모·final 참조는 추가·삭제·수선하지 않는다.',
      '',f"다음 결정 코드: {r['overall']['next_decision']}",f"실패 계층: {r['failure_layers']}",f"원응답 비용 계수: {r['usage']}",f"계획 SHA-256: {r['plan_sha256']}"]
    return '\n'.join(lines)+'\n'
