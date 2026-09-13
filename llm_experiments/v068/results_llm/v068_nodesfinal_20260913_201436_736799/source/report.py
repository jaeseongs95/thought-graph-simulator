"""Frozen v068 result aggregation and Korean report rendering."""
from __future__ import annotations

import base64
from collections import defaultdict
from copy import deepcopy

import common
import measure


CONTRACT = "v068-report-r1"
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


def _call(plan, slot, record):
    from stages import nodes_valid, final_valid
    row={**deepcopy(slot),'status':'not_observed','format_valid':None,'usage':_usage(None),'response_sha256':None,'done_reason':None}
    if record is None:return row,None
    raw=_decode_raw(record)
    status,payload=measure.parse_response(raw,record['http_status'],record['error'],plan['identity']['model'])
    if isinstance(raw,dict) and type(raw.get('eval_count')) is int and raw['eval_count']>plan['protocol']['num_predict']:
        status,payload='generation_budget_exceeded',None
    row.update(status=status,usage=_usage(raw),response_sha256=record['response_sha256'],done_reason=raw.get('done_reason') if isinstance(raw,dict) else None)
    if status=='ok':
        valid=(measure._schema_valid(payload) if slot['stage']=='direct' else nodes_valid(payload) if slot['stage']=='nodes' else final_valid(payload))
        row['format_valid']=valid
    elif status in ('invalid_json','invalid_schema'):row['format_valid']=False
    return row,payload


def summarize(plan,records,state):
    from stages import assemble
    if plan['contract']!='v068-plan-r1':raise ValueError('plan')
    state=_run_state(state);problems=_problem_index(plan)
    index=_record_index(records,{s['id'] for s in plan['slots']})
    rows=[];payloads={}
    for s in plan['slots']:
        r,p=_call(plan,s,index.get(s['id']));rows.append(r);payloads[s['id']]=p
    by_id={r['id']:r for r in rows};trials=[]
    for r in rows:
        if r['stage']=='nodes':continue
        source=by_id.get(r['parent_nodes_id']) if r['stage']=='final' else None
        ready=r['status']=='ok' and r['format_valid'] is True
        if source is not None:ready=ready and source['status']=='ok' and source['format_valid'] is True
        graph=None
        if ready:
            graph=payloads[r['id']] if r['stage']=='direct' else assemble(payloads[source['id']],payloads[r['id']])
        semantic=measure.assess(problems[r['problem_id']],graph) if graph is not None else _empty_semantics()
        emitted=[n['rule'] for n in graph['nodes'] if n['rule'] is not None] if graph is not None else None
        follows=None if emitted is None else emitted==r['reference_rule_ids']
        ref_D=plan['protocol']['depth_ranges'][r['problem_id']][r['condition']=='reference_long']
        success=None if graph is None else bool(semantic['strict_valid'] and follows and semantic['actual_D']==ref_D)
        t={k:deepcopy(r[k]) for k in ('id','problem_id','seed','condition','arm','reference_rule_ids','parent_nodes_id')}
        t.update(**semantic,reference_input_D=ref_D,emitted_rule_ids=emitted,reference_order_followed=follows,
                 reconstruction_success=success,D_instruction_control_success=None,
                 assembled_graph_sha256=common.sha(common.wire(graph)) if graph is not None else None)
        trials.append(t)
    observed=sum(r['status']!='not_observed' for r in rows)
    full=state=='complete' and observed==36
    arms=[]
    for arm in ('direct','staged'):
        ts=[t for t in trials if t['arm']==arm];measured=sum(t['reconstruction_success'] is not None for t in ts)
        count=sum(t['reconstruction_success'] is True for t in ts)
        flag=count==12 if full and measured==12 else None
        arms.append({'arm':arm,'assigned':12,'measured':measured,'successes':count,'unmeasured':12-measured,
                     'positive_control_ready':flag,'rate':count/12 if flag is not None else None})
    groups=[]
    for problem in plan['protocol']['problems']:
        for cond in plan['protocol']['conditions']:
            for arm in ('direct','staged'):
                ts=[t for t in trials if t['problem_id']==problem['id'] and t['condition']==cond and t['arm']==arm]
                groups.append({'problem_id':problem['id'],'condition':cond,'arm':arm,'assigned':len(ts),
                  'measured':sum(t['reconstruction_success'] is not None for t in ts),'strict_valid':sum(t['strict_valid'] is True for t in ts),
                  'reference_order_followed':sum(t['reference_order_followed'] is True for t in ts),'successes':sum(t['reconstruction_success'] is True for t in ts)})
    pairs=[]
    for d in [t for t in trials if t['arm']=='direct']:
        s=next(t for t in trials if t['arm']=='staged' and (t['problem_id'],t['seed'],t['condition'])==(d['problem_id'],d['seed'],d['condition']))
        dv,sv=d['reconstruction_success'],s['reconstruction_success']
        category='unmeasured' if dv is None or sv is None else 'both_success' if dv and sv else 'staged_only' if sv else 'direct_only' if dv else 'both_failure'
        pairs.append({'problem_id':d['problem_id'],'seed':d['seed'],'condition':d['condition'],'category':category})
    known=full and all(a['unmeasured']==0 for a in arms)
    if not known:decision='measurement_incomplete_no_retry'
    elif all(a['successes']==12 for a in arms):decision='both_reference_constructors_available_close_diagnostic'
    elif arms[1]['successes']==12:decision='staged_reference_constructor_available_close_diagnostic'
    elif arms[0]['successes']==12:decision='direct_reference_constructor_available_close_diagnostic'
    elif arms[1]['successes']==0:decision='staged_zero_close_diagnostic'
    else:decision='partial_scope_preserved_close_diagnostic'
    usage={}
    for stage in ('direct','nodes','final'):
        rr=[r for r in rows if r['stage']==stage]
        usage[stage]={k:sum(r['usage'][k] for r in rr) if full and all(r['usage'][k] is not None for r in rr) else None for k in _USAGE_FIELDS}
    return {'contract':'v068-report-r1','run_name':plan['run_name'],'provenance':plan['provenance'],'plan_sha256':plan['plan_sha256'],
      'state':state,'full_complete':full,'assigned_calls':36,'observed_calls':observed,'rows':rows,'trials':trials,'groups':groups,
      'arms':arms,'pairs':pairs,'pair_counts':{k:sum(p['category']==k for p in pairs) for k in ('both_success','staged_only','direct_only','both_failure','unmeasured')},
      'overall':{'comparison_measured':known,'next_decision':decision,'D_instruction_control':None,'A_or_M_gate':None,'v067_successes_unchanged':4},
      'usage_by_stage':usage,'limits':{'solution_path_given':True,'host_repair':False,'budget_matched':False,'internal_cause_identified':False,'independent_holdout':False}}


def render(r):
    lines=['# v068 전체 graph vs nodes→final 참조 재구성 대조','',
       f"상태: {r['state']} / 관측 {r['observed_calls']}/36 / provenance: {r['provenance']}",
       '정답 규칙 경로를 제공한 양성 대조다. D 자율 제어·A/M 성공이 아니다. v067은 4/12 그대로 보존한다.',
       'staged는 첫 모델의 nodes와 둘째 모델의 final_node_id를 그대로 결합한다. 노드/부모/ID 수정·후보 추출·사후 가지치기 없음.','',
       '|문제|참조|구조|성공/배정|측정|strict|순서 이행|','|---|---|---|---:|---:|---:|---:|']
    for g in r['groups']:
        lines.append(f"|{g['problem_id']}|{g['condition']}|{g['arm']}|{g['successes']}/{g['assigned']}|{g['measured']}|{g['strict_valid']}|{g['reference_order_followed']}|")
    lines+=['','## 전체 판정']
    for a in r['arms']:
        label='미판정' if a['positive_control_ready'] is None else '통과' if a['positive_control_ready'] else '불통과'
        lines.append(f"{a['arm']}: {a['successes']}/12, 미측정 {a['unmeasured']}, 기준선 {label}.")
    lines += ['',f"짝지은 결과: {r['pair_counts']}",f"다음 결정: {r['overall']['next_decision']}",
       '이번 한정 진단은 이 배치에서 종료한다. 부분 성공의 문제/경로/seed 범위를 보존하고 문구 변경·새 seed로 자동 재실행하지 않는다.',
       '미실행/파싱 실패/예산 초과를 논리 오답이나 D=0으로 채우지 않는다. 중단 배치의 전체 gate는 미판정이다.',
       'staged는 2회 호출하므로 동일 예산 대조가 아니다. 차이는 출력 계약+호출 분리의 결과이며 JSON 키 순서나 내부 원인을 단독 입증하지 않는다.',
       '',f"단계별 원응답 비용 계수: {r['usage_by_stage']}",f"계획 SHA-256: {r['plan_sha256']}"]
    return '\n'.join(lines)+'\n'
