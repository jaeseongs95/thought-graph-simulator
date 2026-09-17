"""생산 정규형 함수를 쓰지 않는 구조·재명명 검증: 색/차수 후보를 둔 전단사 탐색."""
from collections import Counter
from copy import deepcopy
from audit_bytes091 import need,same


def graph(problem,route):
    rs={r['id']:r for r in problem['rules']}
    names=list(problem['facts']);edges=set();dep={a:0 for a in names};steps=[]
    need(len(names)>0 and len(set(names))==len(names),'unique facts')
    for rid in route:
        r=rs[rid];a=r['conclusion'];ps=r['premises']
        need(1<=len(ps)<=3 and len(set(ps))==len(ps),'arity/duplicate premise')
        need(a not in dep and all(v in dep for v in ps),'valid unique-atom topological route')
        d=max(dep[x] for x in ps)+1
        steps.append(dict(rule_id=rid,conclusion=a,premises=[dict(atom=x,depth=dep[x]) for x in ps],depth=d))
        names.append(a);dep[a]=d;edges.update((x,a) for x in ps)
    need(problem['goal'] in dep and problem['goal'] not in problem['facts'],'derived goal')
    reached={problem['goal']}
    while True:
        more={a for a,b in edges if b in reached}-reached
        if not more:break
        reached|=more
    need(set(names)-set(problem['facts'])<=reached,'all inference nodes support goal')
    colors={a:0 if a in problem['facts'] else 2 if a==problem['goal'] else 1 for a in names}
    return names,edges,colors,dict(facts=[dict(atom=a,depth=0) for a in problem['facts']],steps=steps,
        goal_depth=dep[problem['goal']],rule_count=len(route))


def isomorphic(p,route,q,other):
    A,E,C,_=graph(p,route);B,F,D,_=graph(q,other)
    if len(A)!=len(B) or len(E)!=len(F):return False
    def key(v,edges,colors):return colors[v],sum(y==v for x,y in edges),sum(x==v for x,y in edges)
    ka={v:key(v,E,C) for v in A};kb={v:key(v,F,D) for v in B}
    if Counter(ka.values())!=Counter(kb.values()):return False
    candidates={a:[b for b in B if ka[a]==kb[b]] for a in A}
    order=sorted(A,key=lambda a:(len(candidates[a]),-ka[a][1]-ka[a][2]))
    mapping={};used=set()
    def visit(i):
        if i==len(A):return True
        a=order[i]
        for b in candidates[a]:
            if b in used:continue
            if any(((a,x) in E)!=((b,y) in F) or ((x,a) in E)!=((y,b) in F) for x,y in mapping.items()):continue
            mapping[a]=b;used.add(b)
            if visit(i+1):return True
            used.remove(b);del mapping[a]
        return False
    return visit(0)


def validate(corpus,old):
    need(corpus['model_inference_calls']==0,'corpus must be model untested')
    ps={p['id']:p for p in corpus['problems']};rs=corpus['reference_plans']
    need(len(ps)==len(corpus['problems'])==24,'24 distinct represented problems')
    need(len(corpus['members'])==24 and {m['problem_id'] for m in corpus['members']}==set(ps),'unique corpus members')
    need(Counter(m['cohort'] for m in corpus['members'])==Counter({'known_original':8,'known_renamed':8,'new_topology':8}),'member cohorts')
    need(len(corpus['renamings'])==8 and {m['original'] for m in corpus['renamings']}=={p['id'] for p in old['problems']},'8 distinct renaming maps')
    for p in old['problems']:
        need(same(ps[p['id']],p),'original problem modified')
        need(same(rs[p['id']],old['reference_plans'][p['id']]),'original route modified')
    for m in corpus['renamings']:
        oldp=ps[m['original']];ren=ps[m['renamed']];am=m['atom_map'];rm=m['rule_map']
        need(len(am)==len(set(am.values())) and len(rm)==len(set(rm.values())),'renaming bijection')
        need(all(len(k)==len(v) and k[0]==v[0] and k!=v for k,v in am.items()),'atom format/changed name')
        need(all(len(k)==len(v) and k[0]==v[0] and k!=v for k,v in rm.items()),'rule format/changed name')
        expected=dict(id=m['renamed'],facts=[am[a] for a in oldp['facts']],goal=am[oldp['goal']],
            rules=[dict(id=rm[r['id']],premises=[am[a] for a in r['premises']],conclusion=am[r['conclusion']]) for r in oldp['rules']])
        need(same(expected,ren),'renaming changes semantics/order')
        for label,route in rs[m['original']].items():
            need(rs[m['renamed']][label]==[rm[a] for a in route],'renamed route')
            need(isomorphic(oldp,route,ren,rs[m['renamed']][label]),'renamed graph not equivalent')
    novel=[];checks=0
    for m in corpus['members']:
        p=ps[m['problem_id']]
        need(len(p['facts'])==3,'current experiment facts=3')
        for label,route in rs[p['id']].items():
            *_,profile=graph(p,route)
            idx=old['reference_conditions'].index(label)
            need(same(profile,corpus['frozen_profiles'][p['id']][idx]),'independent D/W profile')
            need(profile['goal_depth']==corpus['depth_ranges'][p['id']][idx],'depth range')
            if m['cohort']=='new_topology':
                ref=old['frozen_profiles'][m['source_problem_id']][idx]
                need(profile['goal_depth']==ref['goal_depth'] and profile['rule_count']==ref['rule_count'],'matched D/W')
                for b in corpus['prior_bank']['routes']:
                    checks+=1;need(not isomorphic(p,route,b['problem'],b['route']),'old isomorphic route in holdout')
                for q,rr in novel:
                    checks+=1;need(not isomorphic(p,route,q,rr),'duplicate holdout topology')
                novel.append((p,route))
    expected_units=[]
    for block in range(16):
        selected=[u for u in old['units'] if u['block']==block]
        for index,original in enumerate(selected):
            number=int(original['problem_id'][1:]);ids=[original['problem_id'],original['problem_id']+'_R1','V%02d'%number]
            shift=(block+index)%3
            for pid in ids[shift:]+ids[:shift]:
                tag='r' if pid.endswith('_R1') else 'n' if pid.startswith('V') else 'o'
                cohort={'o':'known_original','r':'known_renamed','n':'new_topology'}[tag]
                u=deepcopy(original);u.update(problem_id=pid,unit_id=tag+'_'+original['unit_id'],
                    input_unit_id=original['unit_id'] if tag!='n' else 'h'+original['unit_id'][1:],
                    base_pair_id=tag+'_'+original['base_pair_id'],topology_id=pid if tag=='n' else original['problem_id'],
                    renaming_id={'o':'original','r':'R1','n':'N0'}[tag],cohort=cohort,
                    render_problem_id=pid if tag=='n' else original['problem_id'],
                    presentation_id='o%d_l%d'%(original['candidate_order_index'],original['id_assignment_index']),
                    sampling_seed=original['seed'],replicate_id='fixed_seed_once')
                expected_units.append(u)
    need(same(corpus['units'],expected_units),'independent corpus unit identities/order')
    need(len(novel)==16,'16 new routes')
    return dict(checked=True,independent_isomorphism_comparisons=checks,new_problems=8,new_routes=16,
                renamed_problems=8,renamed_routes=16,old_unique_routes=len(corpus['prior_bank']['routes']))
