"""이름·규칙 나열 순서와 무관한 작은 proof DAG의 정확한 정규형.

최대 규칙 5개인 이 실험에 한정해 fact와 비-goal 도출 노드의 모든
일대일 순열을 대조한다. 색은 fact / inference / goal이며 전제는 multiset이다.
모델 호출·정답 복구에 사용하지 않는다.
"""
from itertools import permutations
from collections import Counter
import hashlib,json


def route_profile(problem, route):
    rules={r['id']:r for r in problem['rules']}
    depths={a:0 for a in problem['facts']};steps=[];parents={}
    if len(depths)!=len(problem['facts']):raise ValueError('중복 facts')
    for rid in route:
        r=rules[rid];ps=r['premises'];a=r['conclusion']
        if not ps or len(ps)>3 or len(set(ps))!=len(ps):raise ValueError('primitive 전제 계약')
        if a in depths or any(v not in depths for v in ps):raise ValueError('중복 도출 또는 비위상 순서')
        d=1+max(depths[v] for v in ps)
        steps.append(dict(rule_id=rid,conclusion=a,premises=[dict(atom=v,depth=depths[v]) for v in ps],depth=d))
        depths[a]=d;parents[a]=ps
    if problem['goal'] not in parents:raise ValueError('goal 미도출')
    ancestors=set();todo=[problem['goal']]
    while todo:
        a=todo.pop()
        if a not in ancestors:ancestors.add(a);todo.extend(parents.get(a,[]))
    if not set(parents)<=ancestors:raise ValueError('goal에 기여하지 않는 도출 노드')
    return dict(facts=[dict(atom=a,depth=0) for a in problem['facts']],steps=steps,
                goal_depth=depths[problem['goal']],rule_count=len(route))


def canonical_route(problem,route):
    profile=route_profile(problem,route)
    facts=list(problem['facts']);goal=problem['goal']
    edges={x['conclusion']:[p['atom'] for p in x['premises']] for x in profile['steps']}
    internal=[a for a in edges if a!=goal]
    best=None
    for ff in permutations(facts):
        for nn in permutations(internal):
            nodes=ff+nn+(goal,);ids={a:i for i,a in enumerate(nodes)}
            value=tuple(tuple(sorted(ids[v] for v in edges[a])) for a in nn+(goal,))
            if best is None or value<best:best=value
    return json.dumps([len(facts),best],separators=(',',':'))


def signature(problem,route):
    return hashlib.sha256(canonical_route(problem,route).encode()).hexdigest()


def inverse_rename(problem,atom_map,rule_map):
    """검증용 역변환이다. 실제 응답에는 적용하지 않는다."""
    am={v:k for k,v in atom_map.items()};rm={v:k for k,v in rule_map.items()}
    if len(am)!=len(atom_map) or len(rm)!=len(rule_map):raise ValueError('비전단사 재명명')
    return dict(id=problem['id'],facts=[am[a] for a in problem['facts']],
        rules=[dict(id=rm[r['id']],premises=[am[a] for a in r['premises']],conclusion=am[r['conclusion']]) for r in problem['rules']],
        goal=am[problem['goal']])
