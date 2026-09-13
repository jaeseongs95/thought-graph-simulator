"""사후 규칙 경로 평가. 실행기·요청 생성기는 이 모듈을 호출하지 않는다."""
def assess_plan(problem,payload):
    out={'plan_valid':None,'planned_D':None,'selected_rule_ids':None,'plan_format_valid':False,'plan_error_codes':[]}
    if not isinstance(payload,dict) or set(payload)!={'rule_ids'}:out['plan_error_codes']=['plan_schema'];return out
    ids=payload['rule_ids']
    if not isinstance(ids,list) or not 1<=len(ids)<=16 or not all(isinstance(x,str) and 1<=len(x)<=128 for x in ids):out['plan_error_codes']=['plan_schema'];return out
    out.update(plan_format_valid=True,plan_valid=False,selected_rule_ids=ids[:]);errors=set()
    if len(set(ids))!=len(ids):errors.add('duplicate_rule')
    rules={r['id']:r for r in problem['rules']};available={a:(0,set()) for a in problem['facts']}
    for rid in ids:
        if rid not in rules:errors.add('unregistered_rule');continue
        rule=rules[rid];prem=rule['premises'];con=rule['conclusion']
        if con in available:errors.add('rederived_atom')
        if not all(a in available for a in prem):errors.add('plan_premise_unavailable');continue
        dep=1+max((available[a][0] for a in prem),default=-1)
        ancestors={rid}.union(*(available[a][1] for a in prem));available[con]=(dep,ancestors)
    if ids[-1] not in rules or rules[ids[-1]]['conclusion']!=problem['goal']:errors.add('plan_final_goal')
    goal=available.get(problem['goal'])
    if goal is None:errors.add('plan_goal_unreachable')
    elif goal[1]!=set(ids):errors.add('plan_unused_rule')
    out['plan_error_codes']=sorted(errors)
    if not errors:out.update(plan_valid=True,planned_D=goal[0])
    return out

def follows_plan(plan_payload,graph_payload,graph_format_valid):
    if not isinstance(plan_payload,dict) or set(plan_payload)!={'rule_ids'} or not isinstance(plan_payload['rule_ids'],list):return None
    if not all(isinstance(r,str) for r in plan_payload['rule_ids']) or not graph_format_valid:return None
    return [n['rule'] for n in graph_payload['nodes'] if n['rule'] is not None]==plan_payload['rule_ids']
