"""오프라인 교차검사용 별도 구현. adm_minimal/local_llm을 import하지 않는다.
원문 노드/부모/규칙을 수정하지 않는다. 정답 생성 코드가 아닌 증거 추출기다.
"""
from __future__ import annotations
from collections import Counter
from itertools import product


def support(problem: dict, payload: dict, *, core_format: bool = False) -> dict:
    ik, rk, pk, fk = ('id','rule','parents','final') if core_format else ('node_id','rule_id','parent_node_ids','selected_final_node_id')
    rules = {r['id']:r for r in problem['rules']}
    nodes = payload.get('nodes')
    if not isinstance(nodes,list) or not nodes:
        return {'shape_valid':False,'full_support_valid':False,'selected_support_valid':False,'reason':'nodes'}
    index, closure, depth, grounded, details = {}, {}, {}, {}, []
    for position,node in enumerate(nodes):
        faults=[]
        if not isinstance(node,dict):
            details.append({'position':position,'faults':['node_not_object']});continue
        key,atom,rule,parents = node.get(ik),node.get('atom'),node.get(rk),node.get(pk)
        if not ({ik, 'atom', rk, pk} <= set(node) and isinstance(key,str) and key and isinstance(atom,str) and isinstance(parents,list)
                and all(isinstance(v,str) for v in parents) and (rule is None or isinstance(rule,str))):
            details.append({'position':position,'faults':['node_shape']});continue
        if key in index: faults.append('duplicate_id')
        if len(parents)!=len(set(parents)): faults.append('duplicate_parent_id')
        missing_refs=[v for v in parents if v not in index]
        if missing_refs: faults.append('missing_or_forward_parent')
        actual=[index[v]['atom'] for v in parents if v in index]
        expected=None; expected_conclusion=None
        if rule is None:
            expected=[]
            if atom not in problem['facts']: faults.append('ungrounded_fact')
            if parents: faults.append('fact_with_parents')
        elif rule not in rules:
            faults.append('unknown_rule')
        else:
            expected=rules[rule]['premises'];expected_conclusion=rules[rule]['conclusion']
            if atom!=expected_conclusion: faults.append('wrong_conclusion')
            if Counter(actual)!=Counter(expected): faults.append('wrong_premises')
        if key not in index:
            index[key]={'atom':atom,'parents':parents,'rule':rule}
            structural_ok=not missing_refs and all(v in depth for v in parents)
            closure[key]={key}.union(*(closure.get(v,set()) for v in parents))
            if structural_ok:
                depth[key]=0 if rule is None else 1+max([depth[v] for v in parents],default=0)
            grounded[key]=not faults and all(grounded.get(v,False) for v in parents)
        detail={'position':position,'node_id':key,'atom':atom,'rule_id':rule,'parent_node_ids':parents,
                'actual_parent_atoms':actual,'expected_parent_atoms':expected,'expected_conclusion':expected_conclusion,
                'missing_premises':list((Counter(expected or [])-Counter(actual)).elements()),
                'extra_premises':list((Counter(actual)-Counter(expected or [])).elements()),
                'faults':faults,'locally_valid':not faults,'grounded':grounded.get(key,False)}
        details.append(detail)
    final=payload.get(fk);exists=isinstance(final,str) and final in index
    selected=closure.get(final,set()) if exists else set()
    unrelated=[k for k in index if k not in selected] if exists else None
    all_local=len(details)==len(nodes) and all(d.get('locally_valid',False) for d in details)
    goal_match=exists and index[final]['atom']==problem['goal']
    selected_valid=bool(len(index)==len(nodes) and exists and grounded.get(final,False) and goal_match)
    return {'shape_valid':len(index)==len(nodes),'node_count':len(nodes),
            'locally_valid_nodes':sum(d.get('locally_valid',False) for d in details),
            'all_local_steps_valid':all_local,'final_reference_exists':exists,'goal_match':bool(goal_match),
            'selected_support_valid':selected_valid,
            'full_support_valid':bool(all_local and selected_valid and not unrelated),
            'selected_depth_when_valid':depth.get(final) if selected_valid else None,
            'structural_depth_not_semantic_D':depth.get(final) if exists else None,
            'unrelated_node_ids':unrelated,
            'first_failure':next((d for d in details if not d.get('locally_valid',False)),None),
            'nodes':details}


def depth_set_forward(problem: dict) -> list[int]:
    """증명별 원자 집합·깊이의 전방 고정점. 기존 후방 탐색 함수를 부르지 않는다."""
    facts=set(problem['facts'])
    states={a:{(frozenset([a]),0)} for a in facts}
    changed=True
    while changed:
        changed=False
        for rule in problem['rules']:
            out=rule['conclusion']
            if out in facts: continue
            choices=[list(states.get(a,())) for a in rule['premises']]
            for items in product(*choices):
                used=frozenset().union(*(x[0] for x in items))
                if out in used: continue
                candidate=(used|{out},1+max(x[1] for x in items))
                target=states.setdefault(out,set())
                if candidate not in target:
                    target.add(candidate);changed=True
    return sorted({d for _,d in states.get(problem['goal'],())})


def reachable_forward(problem: dict) -> bool:
    known=set(problem['facts'])
    while True:
        added={r['conclusion'] for r in problem['rules'] if set(r['premises'])<=known}-known
        if not added: break
        known|=added
    return problem['goal'] in known


def criterion(problem: dict, atom: str) -> dict:
    answer=atom==problem['goal'];strict=answer and atom in problem['facts']
    return {'answer_only_accepts':answer,'proof_and_goal_accepts':strict,'gap_detected':answer!=strict}
