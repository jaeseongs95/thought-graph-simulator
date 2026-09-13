"""생산 코드 import 없는 원문 교차검사. 그래프·도식·M 판정을 별도로 재계산한다."""
from __future__ import annotations
import argparse,collections,hashlib,itertools,json,zipfile
from pathlib import Path


def sha(b):return hashlib.sha256(b).hexdigest()
def canon(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def load(x):
    def pairs(xs):
        d={}
        for k,v in xs:
            if k in d:raise ValueError('duplicate key')
            d[k]=v
        return d
    return json.loads(x,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))


def calc(problem,t):
    by={};levels={};reach={};rd={r['id']:r for r in problem['rules']}
    for n in t['nodes']:
        i=n['id'];assert i not in by;assert len(n['parents'])==len(set(n['parents']));assert all(k in by for k in n['parents'])
        if n['rule'] is None:
            assert n['atom'] in problem['facts'] and n['parents']==[];levels[i]=0
        else:
            rr=rd[n['rule']];assert n['atom']==rr['conclusion'];assert sorted(by[k]['atom'] for k in n['parents'])==sorted(rr['premises']);levels[i]=max(levels[k] for k in n['parents'])+1
        reach[i]={i}.union(*(reach[k] for k in n['parents']));by[i]=n
    final=t['final'];assert by[final]['atom']==problem['goal'];assert reach[final]==set(by)
    assert set(t['views'])==set(by);a=set()
    for i,v in t['views'].items():
        if v['kind']=='instance':assert set(v)=={'kind','atom'} and v['atom']==by[i]['atom'];a.add('instance');continue
        assert v['kind']=='universal_schema' and v['quantifier']=='forall_boolean_valuations';b=v['binding'];used=[by[k] for k in reach[i]];atoms={n['atom'] for n in used}
        assert len(b)==len(atoms) and set(b.values())==atoms and b[v['conclusion']]==by[i]['atom']
        expected=[]
        for n in used:
            c=((),n['atom']) if n['rule'] is None else (tuple(sorted(rd[n['rule']]['premises'])),rd[n['rule']]['conclusion'])
            if c not in expected:expected.append(c)
        actual=[]
        for c in v['assumptions']:
            assert len(c['if'])==len(set(c['if']));actual.append((tuple(sorted(b[x] for x in c['if'])),b[c['then']]))
        assert len(actual)==len(set(actual)) and set(actual)==set(expected)
        for bits in itertools.product([0,1],repeat=len(b)):
            truth=dict(zip(b,bits));premise=all(any(not truth[x] for x in c['if']) or truth[c['then']] for c in v['assumptions'])
            assert not premise or truth[v['conclusion']]
        a.add('schema')
    assert len({r['id'] for r in t['reviews']})==len(t['reviews'])
    m=0;review_ok=True;kinds=[]
    for r in t['reviews']:
        f=r['finding'];kinds.append(r['target_kind'])
        if r['target_kind']=='argument':
            assert r['check']=='support_replay' and r['target']==final;m=max(m,1)
            valid=(set(r['evidence'])==set(by) and len(r['evidence'])==len(set(r['evidence']))
                  and f['grounded'] is True and f['conclusion']==problem['goal']
                  and sorted(f['used_rules'])==sorted({n['rule'] for n in by.values() if n['rule']}))
        else:
            assert r['target_kind']=='acceptance_criterion' and r['target']=='valid_proof_and_goal' and r['check']=='counterexample_probe';m=max(m,2)
            pp=r['probe'];inside=pp['atom'] in problem['facts'];same=pp['atom']==problem['goal']
            valid=(pp=={'atom':problem['goal'],'rule':None,'parents':[]} and
                   f['answer_only_accepts'] is same and f['proof_and_goal_accepts'] is (same and inside) and f['gap_detected'] is (same and not inside))
        review_ok=review_ok and valid
    return {'A':next(iter(a)) if len(a)==1 else 'mixed','D':levels[final],'M':m,'strict_valid':review_ok,'kinds':kinds}


def check(archive,out=None):
    with zipfile.ZipFile(archive) as z:
        names=z.namelist();assert len(names)==len(set(names));mf=load(z.read('BUNDLE_MANIFEST.json'));hashes=mf['file_hashes']
        assert set(hashes)==set(names)-{'BUNDLE_MANIFEST.json'}
        for name,h in hashes.items():assert sha(z.read(name))==h,name
        p=load(z.read('external_plan/v051.plan.json'));assert p==load(z.read('run/plan.snapshot.json'))
        assert p['plan_sha256']==sha(canon({k:v for k,v in p.items() if k!='plan_sha256'}))
        assert p['problem_sha256']==sha(canon(p['problem']))
        events=[load(line) for line in z.read('run/events.jsonl').splitlines()];assert len(events)==len(p['slots'])
        prev=p['plan_sha256'];rows=[]
        for s,e in zip(p['slots'],events):
            assert s==e['slot'] and e['parents']==[] and e['kind']=='call';assert e['previous_hash']==prev
            assert e['event_hash']==sha(canon({k:v for k,v in e.items() if k!='event_hash'}));prev=e['event_hash']
            prefix='run/calls/'+s['id']+'/';req=z.read(prefix+'request.wire.json');raw=z.read(prefix+'response.raw.json')
            assert sha(req)==e['request_sha256'] and sha(raw)==e['response_sha256']
            q=load(req);cfg=p['baseline']['config'];assert q['model']==cfg['model'];assert q['options']==dict(cfg['options'],seed=s['seed'])
            assert load(q['messages'][1]['content'][len('problem: '):])==p['problem']
            env=load(raw);assert env['model']==cfg['model'] and env['done'] is True and env['done_reason']=='stop';assert env['message']['role']=='assistant'
            t=load(env['message']['content']);m=calc(p['problem'],t);role=next(r for r in p['roles'] if r['id']==s['role_id'])
            expected_kinds=[] if role['M']==0 else (['argument'] if role['M']==1 else ['acceptance_criterion'])
            match=m['strict_valid'] and m['A']==role['A'] and m['D']==(1 if role['D']=='shallow' else 2) and m['M']==role['M'] and m['kinds']==expected_kinds
            rows.append({**s,**m,'role_match':match})
        stored=load(z.read('run/summary.json'));counts={r['id']:sum(row['role_match'] for row in rows if row['role_id']==r['id']) for r in p['roles']}
        assert all(counts[rid]==stored['roles'][rid]['role_match'] for rid in counts)
        assert sum(row['strict_valid'] for row in rows)==sum(x['strict_valid'] for x in stored['roles'].values())
        result={'bundle_sha256':sha(Path(archive).read_bytes()),'manifest_files_checked':len(hashes),'http_calls_checked':len(rows),
                'fixed_problem_and_goal':True,'event_tip':prev,'role_matches':counts,
                'strict_valid_total':sum(row['strict_valid'] for row in rows),
                'production_imports':False,'scores_match_saved_report':True,'evidence_kind':stored['evidence_kind']}
    if out:Path(out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2));return result
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('archive',type=Path);ap.add_argument('--out',type=Path);a=ap.parse_args();check(a.archive,a.out)
