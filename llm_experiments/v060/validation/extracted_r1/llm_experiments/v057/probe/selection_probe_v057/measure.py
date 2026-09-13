"""관측 후의 채점 전용. 마지막 규칙 선택을 완전한 증명 생성으로 승격하지 않는다."""
from itertools import product
from .contracts import require,validate_payload,ContractError
from .requests import CHOICE_SCHEMA
from order_probe_v054.measure import measure as graph_measure, role_match as graph_match
from order_probe_v054.design import role_for

def terminal_depths(problem):
    """facts에서 가능한 비순환 경로 깊이를 열거한다. 현재 문제에서는 마지막 규칙별 깊이가 하나다."""
    rules=problem['rules'];memo={}
    def depths(atom,stack):
        require(atom not in stack,'채점 문제에 순환 존재')
        if atom in memo:return memo[atom]
        ds={0} if atom in problem['facts'] else set()
        for r in rules:
            if r['conclusion']==atom:
                for group in product(*(depths(a,stack|{atom}) for a in r['premises'])):
                    ds.add(1+max(group,default=-1))
        memo[atom]=ds;return ds
    result={}
    for r in rules:
        if r['conclusion']==problem['goal']:
            ds={1+max(group,default=-1) for group in product(*(depths(a,{problem['goal']}) for a in r['premises']))}
            if ds:result[r['id']]=sorted(ds)
    require(result,'목표를 도출하는 규칙 없음')
    require(all(len(ds)==1 for ds in result.values()),'마지막 규칙만으로 깊이를 식별할 수 없는 문제')
    require(len({ds[0] for ds in result.values()})>=2,'최소/최대 깊이가 구별되지 않는 문제')
    return result

def choice_measure(problem,payload,slot):
    out={'kind':'terminal_rule_choice','format_valid':False,'choice_valid':None,'selected_rule_id':None,
         'implied_depth':None,'proof_valid':None,'strict_valid':None,'D':None,'errors':[]}
    if payload is None:return out
    try:validate_payload(payload,CHOICE_SCHEMA)
    except ContractError as e:out['errors']=[str(e)];return out
    out['format_valid']=True;rid=payload['final_rule_id'];out['selected_rule_id']=rid;out['choice_valid']=False
    rules={r['id']:r for r in problem['rules']}
    if rid not in rules:out['errors']=['unknown_rule'];return out
    if rules[rid]['conclusion']!=problem['goal']:out['errors']=['not_goal_concluding_rule'];return out
    possible=terminal_depths(problem)
    if rid not in possible:out['errors']=['unreachable_terminal_rule'];return out
    out['choice_valid']=True;out['implied_depth']=possible[rid][0];return out

def measure(problem,payload,slot):
    return choice_measure(problem,payload,slot) if slot['mode']=='choice' else graph_measure(problem,payload,slot)

def match(problem,measurement,slot):
    if slot['direction']=='neutral':return None
    if slot['mode']=='graph':return graph_match(measurement,role_for(slot),problem)
    ds=[v[0] for v in terminal_depths(problem).values()]
    target=min(ds) if slot['direction']=='shallow' else max(ds)
    return bool(measurement['choice_valid'] is True and measurement['implied_depth']==target)
