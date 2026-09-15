"""모델 응답을 읽지 않는 결정적 신규 DAG 구조 생성·정규형 검사.

깊이/규칙 수 층화와 기호화 알고리즘을 고정한다. 조건을 만족하는 첫 후보를
사용하며 성과 기반 후보 선택은 없다. SHA-256 순서는 IID 표집 주장이 아니다.
"""
from __future__ import annotations
from copy import deepcopy
from functools import lru_cache
from itertools import combinations, permutations
from pathlib import Path
import hashlib
import json

FROZEN_REQUEST_KEYS = (
    'model','identity','seeds','conditions','reference_conditions','candidate_orders',
    'candidate_ids','selector_schema','generation_schema','headers','api_defaults',
    'num_predict','request_utf8_byte_limit','timeout_seconds','generator_variants',
    'id_assignments','count_select_header','count_conditions','control_select_addendum',
    'support_origin','support_only_in_selector','numeric_compare_header','lookup_header',
    'numeric_compare_schema','lookup_schema',
)
# [얕은 D, 얕은 W, 깊은 D, 깊은 W]. 규칙 수 층화는 유지하고 3개는 새 깊이 조합으로 확장한다.
SHAPES = ((2,4,3,4),(2,4,4,4),(3,5,5,5),(4,5,5,5),
          (2,4,3,3),(3,5,4,4),(3,5,4,4),(3,5,4,4))
GENERATION_SEED = 'ADM-v086-structural-holdout-20260915-r1'


def topology_signature(problem: dict, paths: list[list[str]]) -> str:
    """공통 사실 매핑을 보존한 proof DAG 쌍의 기호 불변 완전 정규형."""
    facts, goal = problem['facts'], problem['goal']
    by_id = {r['id']:r for r in problem['rules']}
    possibilities = []
    for fact_order in permutations(facts):
        fids = {a:i for i,a in enumerate(fact_order)}
        encoded = []
        for path in paths:
            rules = [by_id[r] for r in path]
            inner = [r['conclusion'] for r in rules if r['conclusion'] != goal]
            representations = []
            for order in permutations(inner):
                labels = dict(fids)
                labels.update({a:len(facts)+i for i,a in enumerate(order)})
                labels[goal] = len(facts)+len(inner)
                representations.append(tuple(sorted((labels[r['conclusion']], tuple(sorted(labels[a] for a in r['premises']))) for r in rules)))
            encoded.append(min(representations))
        possibilities.append(tuple(encoded))
    return json.dumps([len(facts),min(possibilities)],separators=(',',':'))


def ranked(items, salt):
    return sorted(items, key=lambda x: (hashlib.sha256((GENERATION_SEED+'/'+salt+'/'+str(x)).encode()).hexdigest(), str(x)))


def prior_cases():
    import core086 as c
    out=[]
    # H01~H04 4개와 T01~T08 8개. v085는 T를 재사용했으므로 중복 가산하지 않는다.
    for name in ('v083_protocol.json','v085_protocol.json'):
        old=c.load((c.ROOT/'data'/name).read_bytes())
        for p in old['problems']:
            paths=[old['reference_plans'][p['id']][k] for k in old['reference_conditions']]
            out.append((p, paths))
    return out


def _profile(problem, path):
    ds={a:0 for a in problem['facts']};by={r['id']:r for r in problem['rules']};steps=[]
    for rid in path:
        r=by[rid];pres=[{'atom':a,'depth':ds[a]} for a in r['premises']]
        d=1+max(x['depth'] for x in pres);ds[r['conclusion']]=d
        steps.append({'rule_id':rid,'conclusion':r['conclusion'],'premises':pres,'depth':d})
    return {'facts':[{'atom':a,'depth':0} for a in problem['facts']], 'steps':steps,
            'goal_depth':ds[problem['goal']],'rule_count':len(path)}


def _route(index, kind, depth, width, forbidden):
    """유효성/구조 중복만으로 거르는 고정 순서. 모델·점수·외부 파일을 읽지 않는다."""
    for attempt in range(200000):
        rows=[];ds={f'f{i}':0 for i in range(3)}
        for i in range(width):
            available=[f'f{j}' for j in range(3)]+[f'x{j}' for j in range(i)]
            options=[cs for n in range(1,min(3,len(available))+1) for cs in combinations(available,n)]
            h=hashlib.sha256(f'{GENERATION_SEED}/{index}/{kind}/{attempt}/{i}'.encode()).digest()
            parents=list(options[int.from_bytes(h,'big')%len(options)])
            name='g' if i==width-1 else f'x{i}'
            ds[name]=1+max(ds[a] for a in parents)
            rows.append({'id':f'r{i}','premises':parents,'conclusion':name})
        if ds['g']!=depth:continue
        parents={r['conclusion']:r['premises'] for r in rows};seen=set()
        def visit(a):
            if a in seen:return
            seen.add(a)
            for b in parents.get(a,[]):visit(b)
        visit('g')
        if seen!=set(ds):continue  # 모든 사실과 규칙이 실제 goal ancestry에 속해야 한다.
        p={'id':'abstract','facts':[f'f{i}' for i in range(3)],'rules':rows,'goal':'g'}
        route=[r['id'] for r in rows];signature=topology_signature(p,[route])
        if signature in forbidden:continue
        forbidden.add(signature)
        return p,route,{'attempt_index':attempt,'candidate_checks':attempt+1,'single_route_signature':signature}
    raise ValueError('사전 생성 후보 한도 소진. seed를 바꿔 자동 우회하지 않는다.')


@lru_cache(maxsize=1)
def _generated():
    old=prior_cases();forbidden={topology_signature(p,[path]) for p,paths in old for path in paths}
    previous={p['id']:topology_signature(p,paths) for p,paths in old}
    cases=[];plans={};profiles={};metadata={};signatures={};recipe={}
    for index,(sd,sw,dd,dw) in enumerate(SHAPES):
        pid=f'U{index+1:02d}';raw_routes=[];notes=[]
        for kind,(d,w) in enumerate(((sd,sw),(dd,dw))):
            p,path,note=_route(index,kind,d,w,forbidden);raw_routes.append(p);notes.append(note)
        symbols=['f0','f1','f2','g']+[f'{k}_x{i}' for k,w in ((0,sw),(1,dw)) for i in range(w-1)]
        atom_numbers=ranked(list(range(100)),pid+'/atoms');rule_numbers=ranked(list(range(100)),pid+'/rules')
        # 1문자+2자리의 기존 기호 길이를 유지한다. 의미를 이름에 부호화하지 않는다.
        atom_prefix='CDEFGHIJ'[index];rule_prefix='jklmnopq'[index]
        names={x:f'{atom_prefix}{atom_numbers[i]:02d}' for i,x in enumerate(symbols)}
        paths=[];rules=[];n=0
        for k,rp in enumerate(raw_routes):
            route=[]
            def atom(a):return names[f'{k}_{a}' if a.startswith('x') else a]
            for r in rp['rules']:
                rid=f'{rule_prefix}{rule_numbers[n]:02d}';n+=1;route.append(rid)
                rules.append({'id':rid,'premises':[atom(a) for a in r['premises']],'conclusion':atom(r['conclusion'])})
            paths.append(route)
        rules=sorted(rules,key=lambda r:hashlib.sha256((GENERATION_SEED+'/'+pid+'/dictionary/'+r['id']).encode()).hexdigest())
        problem={'id':pid,'facts':[names[f'f{i}'] for i in range(3)],'rules':rules,'goal':names['g']}
        signature=topology_signature(problem,paths)
        if signature in set(previous.values())|set(signatures.values()):raise ValueError('pair topology duplicate')
        cases.append(problem);plans[pid]=dict(zip(('reference_short','reference_long'),paths))
        profiles[pid]=[_profile(problem,path) for path in paths]
        signatures[pid]=signature;recipe[pid]=notes
        metadata[pid]={'family':'equal_rule_count' if sw==dw else 'inverted_rule_count',
            'structural_problem_id':pid,'numeric_profile_regime':'new_depth_profile' if index in (1,2,3) else 'previous_depth_profile','shallow_D':sd,'deep_D':dd,'shallow_rule_count':sw,'deep_rule_count':dw,
            'evaluation_role':'response_unseen_prespecified_structural_case','prior_exposure_batches':[],
            'presentation':'SHA-256 고정 기호/규칙 사전 순서; 두 seed와 네 후보 위치/ID 표시 모두 배정'}
    return {'problems':cases,'reference_plans':plans,'frozen_profiles':profiles,'problem_metadata':metadata,
            'structure_signatures':signatures,'prior_structure_signatures':previous,
            'depth_ranges':{p['id']:[profiles[p['id']][i]['goal_depth'] for i in (0,1)] for p in cases},
            'metrics_by_problem':{p['id']:['D'] if i<4 else ['D','W'] for i,p in enumerate(cases)},
            'holdout_generation':{'algorithm':'sha256_parent_subset_first_valid_novel_route_r1','seed':GENERATION_SEED,
                'max_attempts_per_route':200000,'max_primitive_premises':3,'all_nodes_in_goal_ancestry':True,
                'exclude_isomorphic_single_routes':True,'reference_case_count':len(old),
                'reference_route_count':sum(len(paths) for _,paths in old),'cases':recipe}}


def generated_fields():return deepcopy(_generated())


def build_protocol():
    import core086
    s=core086.spec();s.update(generated_fields());return s


def main():
    import argparse
    from audit086 import validate_protocol
    import core086
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',action='store_true',required=True);p.parse_args()
    current=core086.spec();rebuilt=build_protocol()
    if not core086.exact(current,rebuilt):raise ValueError('동결 문제와 결정적 재구성 불일치')
    validate_protocol(current)
    print(json.dumps({'checked':True,'structural_cases':8,'new_holdout_cases':8,'prior_cases_excluded':12,
                      'model_calls':0},ensure_ascii=False))

if __name__=='__main__':main()
