"""Frozen v065 result aggregation and Korean report rendering."""
from __future__ import annotations

import base64
from collections import defaultdict
from copy import deepcopy

import common
import measure


CONTRACT = "v065-report-r1"
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
    """지정한 마지막 규칙으로 구성했는지 평가한다. D 지시만으로 선택한 성공과 구분한다."""
    if plan['contract']!='v065-plan-r1':raise ValueError('v065 plan required')
    state=_run_state(state);problems=_problem_index(plan);index=_record_index(records,{s['id'] for s in plan['slots']})
    rows=[_row(plan,s,index.get(s['id']),problems) for s in plan['slots']]
    for row in rows:
        idx=0 if row['condition']=='prescribed_short' else 1
        row['expected_D_for_prescribed_rule']=plan['protocol']['depth_ranges'][row['problem_id']][idx]
        row['required_rule_match']=None if row['final_rule_id'] is None else row['final_rule_id']==row['required_terminal_rule']
        row['construction_success']=None if row['strict_valid'] is None else bool(row['strict_valid'] and row['required_rule_match'] is True and row['actual_D']==row['expected_D_for_prescribed_rule'])
        row['D_instruction_control_success']=None
    observed=sum(r['status']!='not_observed' for r in rows);complete=state=='complete' and observed==len(rows)
    measured=[r for r in rows if r['construction_success'] is not None]
    gate=None if not complete or len(measured)!=len(rows) else all(r['construction_success'] for r in measured)
    groups=[]
    for problem in plan['protocol']['problems']:
        for c in ('prescribed_short','prescribed_long'):
            rs=[r for r in rows if r['problem_id']==problem['id'] and r['condition']==c]
            groups.append({'problem_id':problem['id'],'condition':c,'required_terminal_rule':plan['protocol']['required_terminal_rules'][problem['id']][c],
                'assigned':len(rs),'observed':sum(r['status']!='not_observed' for r in rs),
                'rule_name_matches':sum(r['required_rule_match'] is True for r in rs),'locally_valid':sum(r['proof_valid'] is True for r in rs),
                'strict_valid':sum(r['strict_valid'] is True for r in rs),'construction_successes':sum(r['construction_success'] is True for r in rs),
                'unmeasured':sum(r['construction_success'] is None for r in rs),
                'rate':sum(r['construction_success'] is True for r in rs)/len(rs) if complete and all(r['construction_success'] is not None for r in rs) else None})
    pairs=[]
    for p in plan['protocol']['problems']:
        for seed in plan['protocol']['seeds']:
            a,b=(next(r for r in rows if r['problem_id']==p['id'] and r['seed']==seed and r['condition']==c) for c in ('prescribed_short','prescribed_long'))
            known=a['construction_success'] is not None and b['construction_success'] is not None
            pairs.append({'problem_id':p['id'],'seed':seed,'prescribed_short_success':a['construction_success'],'prescribed_long_success':b['construction_success'],
                'both_prescribed_routes_constructed':bool(a['construction_success'] and b['construction_success']) if known else None,
                'D_instruction_control_success':None})
    failures={'format_or_envelope':sum(r['status'] in ('invalid_json','invalid_schema','incomplete_response') or r['format_valid'] is False for r in rows),
       'proof_failures':sum(r['proof_valid'] is False for r in rows),'strict_only_failures':sum(r['proof_valid'] is True and r['strict_valid'] is False for r in rows),
       'unobserved':sum(r['status']=='not_observed' for r in rows)}
    success=sum(r['construction_success'] is True for r in rows)
    return {'contract':CONTRACT,'run_name':plan['run_name'],'provenance':plan['provenance'],'plan_sha256':plan['plan_sha256'],
       'state':state,'assigned_calls':len(rows),'observed_calls':observed,'full_complete':complete,'rows':rows,'groups':groups,'construction_pairs':pairs,
       'overall':{'measured_construction_calls':len(measured),'construction_successes':success,
          'construction_rate':success/len(rows) if gate is not None else None,'prescribed_construction_ready':gate,
          'D_instruction_control':'not_measured','bounded_A_or_M_pilot':None,'prior_v064_D_gate_remains':False},
       'failure_layers':failures,'usage':{field:sum(r['usage'][field] for r in rows) if complete and all(r['usage'][field] is not None for r in rows) else None for field in _USAGE_FIELDS},
       'limits':{'A':'not_measured','M':'not_measured','last_rule_explicitly_given':True,'historical_vs_new_not_contemporaneous_causal_comparison':True,
          'not_holdout':True,'retry':False,'repair':False}}

def render(r):
    gate=r['overall']['prescribed_construction_ready'];label='미판정' if gate is None else ('통과' if gate else '불통과')
    lines=['# v065 지정 마지막 규칙의 증명 구성 검사','',f"실행 상태: {r['state']} / 관측 호출: {r['observed_calls']}/{r['assigned_calls']} / provenance: {r['provenance']}",
       '마지막 규칙을 직접 알려주는 구성 검사다. D 지시만으로 모델이 경로를 선택한 성과가 아니다.',
       f'12개 지정 구성의 엄격한 이행: {label}. v064의 D 제어 불통과는 변경하지 않는다.','',
       '|문제|조건|지정 규칙|관측/배정|규칙명 이행|국소 논리 유효|엄격한 증명|지정 구성 성공|미측정|',
       '|---|---|---|---:|---:|---:|---:|---:|---:|']
    for g in r['groups']:
        lines.append(f"|{g['problem_id']}|{g['condition']}|{g['required_terminal_rule']}|{g['observed']}/{g['assigned']}|{g['rule_name_matches']}|{g['locally_valid']}|{g['strict_valid']}|{g['construction_successes']}|{g['unmeasured']}|")
    lines+=['','## 실패 계층',f"형식/응답 오류: {r['failure_layers']['format_or_envelope']}; 논리 오류: {r['failure_layers']['proof_failures']}; 논리는 유효하나 엄격 계약 위반: {r['failure_layers']['strict_only_failures']}; 미관측: {r['failure_layers']['unobserved']}",
        '추가 노드나 출력 순서 위반은 실제 논리 오류와 별도로 집계한다. 정답 경로를 골라내거나 참조·규칙을 수정하지 않는다.',
        '', '## 다음 판단',
        '모든 지정 경로가 엄격하게 구성되면 고정 경로 구성 기준선만 확보한 것이다. 이후 D만으로 선택·구성하는 별도 직접/단계형 대조의 필요성을 결정한다.',
        '깊은 지정 경로가 하나도 유효하지 않으면 현재 이 모델·출력 인터페이스의 지정 구성 분기를 종료한다. 문구를 바꿔 자동 반복하지 않는다.',
        '일부만 성공하면 문제·조건별 성과를 보존하고 사후 성공 subset을 전체 성공으로 바꾸지 않는다. 미완료/파싱 불가이면 진입 판정은 보류한다.',
        'A/M·내부 사고·비용 절감·일반화는 이번 검사에서 측정하지 않는다. 미관측 원문은 성과로 채점하지 않는다.',
        '',f"실제 원응답 계수 합계: {r['usage']}",f"계획 SHA-256: {r['plan_sha256']}"]
    return '\n'.join(lines)+'\n'
