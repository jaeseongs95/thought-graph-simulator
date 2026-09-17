"""v091 문제은행 재현기. 모델을 호출하지 않고 사전 규칙만으로 첫 적격 구조를 채택한다."""
from pathlib import Path
from copy import deepcopy
from itertools import combinations
import io,json,zipfile,random,hashlib
from topology091 import route_profile,signature
ROOT=Path(__file__).resolve().parent
CORPUS_SEED=9101601
RENAME_SEED=9101602


def prior_bank():
    bank={};seen_bytes=set();origins=[];rejected=0
    def inspect(name,raw,depth=0):
        nonlocal rejected
        if depth>5:return
        if name.endswith('.zip'):
            h=hashlib.sha256(raw).hexdigest()
            if h in seen_bytes:return
            seen_bytes.add(h)
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                for n in sorted(z.namelist()):
                    if n.endswith(('.json','.zip')):inspect(name+'!'+n,z.read(n),depth+1)
            return
        if not name.endswith('.json'):return
        try:s=json.loads(raw)
        except (ValueError,UnicodeError):return
        if not isinstance(s,dict) or not isinstance(s.get('problems'),list) or not isinstance(s.get('reference_plans'),dict):return
        origins.append(dict(source=name,sha256=hashlib.sha256(raw).hexdigest()))
        for p in s['problems']:
            if not isinstance(p,dict) or p.get('id') not in s['reference_plans']:continue
            routes=s['reference_plans'][p['id']]
            if not isinstance(routes,dict):continue
            for label,path in routes.items():
                try:
                    if not isinstance(path,list) or not 1<=len(path)<=5:continue
                    sig=signature(p,path)
                    bank.setdefault(sig,dict(signature=sig,problem=p,route=path,origin=name,route_label=label))
                except (KeyError,ValueError,TypeError):rejected+=1
    for f in sorted((ROOT/'frozen090').rglob('*')):
        if f.is_file() and f.suffix in ('.json','.zip'):inspect(f.relative_to(ROOT).as_posix(),f.read_bytes())
    return dict(contract='v091-audited-prior-topology-bank-r1',route_signatures=list(sorted(bank)),
                routes=[bank[k] for k in sorted(bank)],source_protocols=origins,excluded_invalid_routes=rejected,
                scope='첨부·보존 소스의 읽을 수 있는 reference_plans, 최대 5규칙. 모델 사전학습 corpus 비노출을 뜻하지 않음.')


def derive_path(template,route,rng,used):
    rp=route_profile(template,route)
    facts=['f0','f1','f2'];N=len(route)
    for attempt in range(1,200001):
        rules=[];available=list(facts)
        arities=[rng.randint(1,3) for _ in range(N)]
        for i,k in enumerate(arities):
            pool=list(combinations(available,k));parents=list(rng.choice(pool))
            atom='g' if i==N-1 else 'x'+str(i)
            rules.append(dict(id='r'+str(i),premises=parents,conclusion=atom));available.append(atom)
        p=dict(id='draft',facts=facts,rules=rules,goal='g');ids=[r['id'] for r in rules]
        try:
            profile=route_profile(p,ids)
            if profile['goal_depth']!=rp['goal_depth']:continue
            # 세 facts 모두 goal support에 들어오게 하여 숨은 유효 facts 수 변화 방지.
            if not set(facts)<=set(v for r in rules for v in r['premises']):continue
            sig=signature(p,ids)
            if sig in used:continue
        except ValueError:continue
        used.add(sig)
        return p,ids,attempt,sig
    raise ValueError('사전 탐색 한도 내 적격 구조 없음: '+template['id'])


def build():
    old=json.loads((ROOT/'data/protocol_v090_snapshot.json').read_text(encoding='utf-8'))
    bank=prior_bank();used=set(bank['route_signatures']);rng=random.Random(CORPUS_SEED);rr=random.Random(RENAME_SEED)
    problems=[];routes={};profiles={};depths={};members=[];rename_maps=[];acceptance=[]
    def add(p,paths,cohort,topology,source,renaming,render_id):
        problems.append(p);routes[p['id']]=paths
        profiles[p['id']]=[route_profile(p,paths[k]) for k in old['reference_conditions']]
        depths[p['id']]=[x['goal_depth'] for x in profiles[p['id']]]
        members.append(dict(problem_id=p['id'],cohort=cohort,topology_id=topology,source_problem_id=source,
            renaming_id=renaming,render_problem_id=render_id,
            route_signatures=[signature(p,paths[k]) for k in old['reference_conditions']]))
    for index,p0 in enumerate(old['problems']):
        pid=p0['id'];paths0=deepcopy(old['reference_plans'][pid]);add(deepcopy(p0),paths0,'known_original',pid,pid,'original',pid)
        atoms=list(dict.fromkeys(p0['facts']+[x['conclusion'] for x in p0['rules']]))
        ap=atoms[0][0];rp=p0['rules'][0]['id'][0]
        nums=[x for x in range(1,100) if f'{ap}{x:02d}' not in atoms]
        am={a:f'{ap}{x:02d}' for a,x in zip(atoms,rr.sample(nums,len(atoms)))}
        rnums=[x for x in range(1,100) if f'{rp}{x:02d}' not in {r['id'] for r in p0['rules']}]
        rm={r['id']:f'{rp}{x:02d}' for r,x in zip(p0['rules'],rr.sample(rnums,len(p0['rules'])))}
        p1=dict(id=pid+'_R1',facts=[am[x] for x in p0['facts']],rules=[dict(id=rm[r['id']],premises=[am[x] for x in r['premises']],conclusion=am[r['conclusion']]) for r in p0['rules']],goal=am[p0['goal']])
        r1={k:[rm[x] for x in v] for k,v in paths0.items()};add(p1,r1,'known_renamed',pid,pid,'R1',pid)
        rename_maps.append(dict(original=pid,renamed=p1['id'],atom_map=am,rule_map=rm,
            preserve=['facts order','rule display order','premise order','D','W','topology','rendered problem id','logical source ids']))
        drafts=[]
        for label in old['reference_conditions']:
            pp,rs,attempt,sig=derive_path(p0,paths0[label],rng,used)
            drafts.append((pp,rs))
            acceptance.append(dict(problem_id=f'V{index+1:02d}',matched_stratum=pid,route=label,attempts=attempt,signature=sig,
               acceptance='first valid candidate: matched D, W, facts=3 and arity range 1..3, all rules support goal, novel canonical route'))
        # 두 경로는 facts와 goal만 공유하며 도출 원자를 따로 갖는다.
        abstract=['f0','f1','f2','g']+[f'{j}_{r["conclusion"]}' for j,(pp,_) in enumerate(drafts) for r in pp['rules'] if r['conclusion']!='g']
        amap={a:f'{ap}{x:02d}' for a,x in zip(abstract,rng.sample(range(1,100),len(abstract)))}
        nr=sum(len(pp['rules']) for pp,_ in drafts);ridnums=iter(rng.sample(range(1,100),nr));rules=[];paths={}
        for j,(pp,rs) in enumerate(drafts):
            conv=lambda a:amap[a if a in ('f0','f1','f2','g') else f'{j}_{a}']
            ids=[]
            for r in pp['rules']:
                rid=f'{rp}{next(ridnums):02d}';ids.append(rid)
                rules.append(dict(id=rid,premises=[conv(a) for a in r['premises']],conclusion=conv(r['conclusion'])))
            paths[old['reference_conditions'][j]]=ids
        rng.shuffle(rules)
        p2=dict(id=f'V{index+1:02d}',facts=[amap[a] for a in ('f0','f1','f2')],rules=rules,goal=amap['g'])
        add(p2,paths,'new_topology',p2['id'],pid,'N0',p2['id'])
    # 기존 block의 표시 순서 유지. 세 cohort는 unit마다 순환 배정한다.
    units=[]
    mm={m['problem_id']:m for m in members}
    for block in range(16):
        oldunits=[u for u in old['units'] if u['block']==block]
        for ui,u0 in enumerate(oldunits):
            idx=int(u0['problem_id'][1:]);ids=[u0['problem_id'],u0['problem_id']+'_R1',f'V{idx:02d}']
            shift=(block+ui)%3;ids=ids[shift:]+ids[:shift]
            for pid in ids:
                m=mm[pid];u=deepcopy(u0);u['problem_id']=pid
                tag={'known_original':'o','known_renamed':'r','new_topology':'n'}[m['cohort']]
                u['unit_id']=tag+'_'+u0['unit_id'];u['input_unit_id']=u0['unit_id'] if tag in ('o','r') else 'h'+u0['unit_id'][1:]
                u['base_pair_id']=tag+'_'+u0['base_pair_id'];u['topology_id']=m['topology_id'];u['renaming_id']=m['renaming_id'];u['cohort']=m['cohort']
                u['render_problem_id']=m['render_problem_id'];u['presentation_id']=f'o{u["candidate_order_index"]}_l{u["id_assignment_index"]}'
                u['sampling_seed']=u['seed'];u['replicate_id']='fixed_seed_once';units.append(u)
    return dict(contract='v091-topology-and-renaming-corpus-r1',corpus_seed=CORPUS_SEED,renaming_seed=RENAME_SEED,
        problems=problems,reference_plans=routes,depth_ranges=depths,frozen_profiles=profiles,units=units,
        members=members,renamings=rename_maps,novel_acceptance=acceptance,prior_bank=bank,
        model_inference_calls=0,selection_basis='D/W/arity/validity/topology only; no target-model outcome filtering')


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',required=True,type=Path);a=parser.parse_args()
    value=build()
    a.out.parent.mkdir(parents=True,exist_ok=True)
    with a.out.open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps(dict(members=len(value['members']),new_topologies=8,renamed_topologies=0,prior_routes=len(value['prior_bank']['routes']),actual_model_calls=0)))
