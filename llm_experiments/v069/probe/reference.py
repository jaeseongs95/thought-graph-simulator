"""고정 정답입력의 사전 검증. 모델 요청 중 정답을 선택/수정하는 도구가 아니다."""
def validate(problem,ids):
    if not isinstance(ids,list) or not ids or len(ids)!=len(set(ids)):raise ValueError('reference list unique/nonempty')
    rules={r['id']:r for r in problem['rules']};state={f:(0,set()) for f in problem['facts']}
    for rid in ids:
        if rid not in rules:raise ValueError('unregistered reference rule')
        r=rules[rid]
        if any(p not in state for p in r['premises']):raise ValueError('reference premises unavailable')
        if r['conclusion'] in state:raise ValueError('reference redeclaration')
        dep=1+max((state[p][0] for p in r['premises']),default=-1)
        support={rid}.union(*(state[p][1] for p in r['premises']));state[r['conclusion']]=(dep,support)
    if rules[ids[-1]]['conclusion']!=problem['goal'] or state[problem['goal']][1]!=set(ids):raise ValueError('reference not exact goal support')
    return state[problem['goal']][0]
