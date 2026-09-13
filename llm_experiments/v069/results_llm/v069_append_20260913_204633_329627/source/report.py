"""Frozen v069 result aggregation and Korean report rendering."""
from __future__ import annotations

import base64
from collections import defaultdict
from copy import deepcopy

import common
import measure


CONTRACT = "v069-report-r1"
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


def _call(plan,slot,record):
    import stages
    row={**deepcopy(slot),'status':'not_observed','format_valid':None,'usage':_usage(None),'response_sha256':None,'done_reason':None}
    if record is None:return row,None
    raw=_decode_raw(record)
    status,payload=measure.parse_response(raw,record['http_status'],record['error'],plan['identity']['model'])
    if isinstance(raw,dict) and type(raw.get('eval_count')) is int and raw['eval_count']>plan['protocol']['num_predict']:
        status,payload='generation_budget_exceeded',None
    row.update(status=status,usage=_usage(raw),response_sha256=record['response_sha256'],done_reason=raw.get('done_reason') if isinstance(raw,dict) else None)
    if status=='ok':row['format_valid']=stages.format_valid(slot['stage'],payload)
    elif status in ('invalid_json','invalid_schema'):row['format_valid']=False
    return row,payload

def summarize(plan,records,state):
    import stages
    if plan['contract']!='v069-plan-r1':raise ValueError('plan')
    state=_run_state(state);problems=_problem_index(plan)
    index=_record_index(records,{s['id'] for s in plan['slots']});rows=[];payloads={}
    for slot in plan['slots']:
        row,obj=_call(plan,slot,index.get(slot['id']));rows.append(row);payloads[slot['id']]=obj
    ready_ids={r['id'] for r in rows if r['status']=='ok' and r['format_valid'] is True};trials=[]
    for terminal in [r for r in rows if r['stage']=='final']:
        slots=[s for s in plan['slots'] if s['trial_id']==terminal['trial_id']]
        problem=problems[terminal['problem_id']]
        graph=stages.assemble(slots,payloads) if all(s['id'] in ready_ids for s in slots) else None
        sem=measure.assess(problem,graph) if graph is not None else _empty_semantics()
        emitted=[n['rule'] for n in graph['nodes'] if n['rule'] is not None] if graph is not None else None
        follows=None if emitted is None else emitted==terminal['reference_rule_ids']
        checks=stages.audit_steps(problem,slots,payloads,ready_ids)
        contracts=all(c['valid'] for c in checks) if all(c['valid'] is not None for c in checks) else None
        depth=plan['protocol']['depth_ranges'][problem['id']][terminal['condition']=='reference_long']
        success=None if graph is None or sem['format_valid'] is not True else bool(sem['strict_valid'] and follows and contracts and sem['actual_D']==depth)
        trial={k:deepcopy(terminal[k]) for k in ('trial_id','problem_id','seed','condition','arm','reference_rule_ids')}
        trial.update(**sem,reference_input_D=depth,emitted_rule_ids=emitted,reference_order_followed=follows,
            stage_checks=checks,stage_contract_valid=contracts,reconstruction_success=success,D_instruction_control_success=None,
            assembled_graph_sha256=common.sha(common.wire(graph)) if graph is not None else None)
        trials.append(trial)
    observed=sum(r['status']!='not_observed' for r in rows)
    full=state=='complete' and observed==plan['protocol']['max_inference_calls']
    measured=sum(t['reconstruction_success'] is not None for t in trials);count=sum(t['reconstruction_success'] is True for t in trials)
    known=full and measured==12;flag=count==12 if known else None
    decision=('measurement_incomplete_no_retry' if not known else 'append_reference_constructor_available_stop' if count==12 else 'append_zero_close_branch' if count==0 else 'append_partial_close_branch')
    groups=[]
    for problem in plan['protocol']['problems']:
        for cond in plan['protocol']['conditions']:
            ts=[t for t in trials if t['problem_id']==problem['id'] and t['condition']==cond]
            groups.append({'problem_id':problem['id'],'condition':cond,'assigned':len(ts),
              'measured':sum(t['reconstruction_success'] is not None for t in ts),'strict_valid':sum(t['strict_valid'] is True for t in ts),
              'stage_contract_valid':sum(t['stage_contract_valid'] is True for t in ts),'successes':sum(t['reconstruction_success'] is True for t in ts)})
    usage={}
    for stage in ('facts','rule','final'):
        rr=[r for r in rows if r['stage']==stage]
        usage[stage]={k:sum(r['usage'][k] for r in rr) if full and all(r['usage'][k] is not None for r in rr) else None for k in _USAGE_FIELDS}
    return {'contract':'v069-report-r1','run_name':plan['run_name'],'provenance':plan['provenance'],'plan_sha256':plan['plan_sha256'],
      'state':state,'full_complete':full,'assigned_calls':54,'observed_calls':observed,'rows':rows,'trials':trials,'groups':groups,
      'overall':{'assigned':12,'measured':measured,'successes':count,'unmeasured':12-measured,'positive_control_ready':flag,
         'rate':count/12 if known else None,'next_decision':decision,'D_instruction_control':None,'A_or_M_gate':None,
         'v068_direct_successes_unchanged':4,'v068_staged_successes_unchanged':8},
      'usage_by_stage':usage,'limits':{'solution_path_given':True,'per_step_rule_given':True,'host_repair':False,
        'contemporaneous_comparison':False,'budget_matched':False,'internal_cause_identified':False,'independent_holdout':False}}

def render(r):
    lines=['# v069 지정 규칙 append-only 참조 구성 검사','',
       f"상태: {r['state']} / 관측 {r['observed_calls']}/54 / provenance: {r['provenance']}",
       '정답 참조 경로와 단계별 적용 규칙을 제공한 양성 대조다. 자율 D 제어·A/M 성공이 아니다.',
       'v068 direct 4/12, staged 8/12와 두 arm의 전체 기준선 미달 판정을 그대로 보존한다.',
       '사실 nodes → 규칙별 node 하나 → final_node_id를 모델이 작성한다. 원응답 전달·무보정 연결만 허용한다.','',
       '|문제|참조|성공/배정|측정|strict|단계 계약|','|---|---|---:|---:|---:|---:|']
    for g in r['groups']:
        lines.append(f"|{g['problem_id']}|{g['condition']}|{g['successes']}/{g['assigned']}|{g['measured']}|{g['strict_valid']}|{g['stage_contract_valid']}|")
    a=r['overall'];label='미판정' if a['positive_control_ready'] is None else '통과' if a['positive_control_ready'] else '불통과'
    lines+=['','## 전체 판정',f"append_only: {a['successes']}/12, 미측정 {a['unmeasured']}, 기준선 {label}.",
       f"다음 결정: {a['next_decision']}",
       '12/12인 경우에도 이 지정 경로·단계별 지시 계약과 이미 본 문제·seed의 구성 기준선만 확보된다.',
       '일부 또는 전부 실패하면 이 배치는 종료한다. 문구·seed 변경, 자동 재시도나 다음 실험 자동 실행은 없다.',
       '형식 오류·길이 종료·미실행은 논리 오답이나 D=0으로 채우지 않는다. 미완료/미측정이 있으면 전체 gate는 null이다.',
       'v068과 동시 대조하지 않은 단일 조건 실험이다. 성공률 차이를 인과 효과·동일 비용 우월성으로 해석하지 않는다.',
       '',f"단계별 원응답 비용 계수: {r['usage_by_stage']}",f"계획 SHA-256: {r['plan_sha256']}"]
    return '\n'.join(lines)+'\n'
