"""v052 ZIP의 별도 의미 검사. 생산 채점기·fixture 생성기를 import하지 않는다."""
import argparse,hashlib,itertools,json,zipfile
from pathlib import Path

def loads(raw):
    def obj(pairs):
        out={}
        for k,v in pairs:
            if k in out:raise ValueError('duplicate JSON key')
            out[k]=v
        return out
    return json.loads(raw,object_pairs_hook=obj)

def check(problem,payload,arm,task):
    """기록 원문을 검사하며 목표 후보를 선택하거나 값을 보충하지 않는다."""
    try:
        if arm=='legacy':trace=payload
        else:
            trace={'nodes':payload['nodes'],'final':payload['final_node_id'],'reviews':payload.get('reviews',[]),'views':{}}
            for e in payload.get('node_views',[]):
                assert e['node_id'] not in trace['views'];v=dict(e['representation'])
                if v['kind']=='universal_schema':
                    bindings=v.pop('bindings');v['binding']={e['variable']:e['atom'] for e in bindings};assert len(v['binding'])==len(bindings)
                trace['views'][e['node_id']]=v
        ns={};ds={};closures={};rules={r['id']:r for r in problem['rules']}
        for n in trace['nodes']:
            k=n['id'];assert k not in ns and len(n['parents'])==len(set(n['parents']))
            assert all(x in ns for x in n['parents'])
            if n['rule'] is None:assert n['atom'] in problem['facts'] and n['parents']==[];ds[k]=0
            else:
                rule=rules[n['rule']];assert n['atom']==rule['conclusion'];assert sorted(ns[x]['atom'] for x in n['parents'])==sorted(rule['premises']);ds[k]=1+max(ds[x] for x in n['parents'])
            closures[k]={k}.union(*(closures[x] for x in n['parents']));ns[k]=n
        final=trace['final'];assert ns[final]['atom']==problem['goal'];assert closures[final]==set(ns)
        if task=='graph_only':return True,None,ds[final],None
        assert set(trace['views'])==set(ns);modes=[]
        for k,v in trace['views'].items():
            if v['kind']=='instance':assert v['atom']==ns[k]['atom'];modes.append('instance');continue
            assert v['kind']=='universal_schema' and v['quantifier']=='forall_boolean_valuations'
            b=v['binding'];used=[ns[x] for x in closures[k]];atoms={n['atom'] for n in used}
            assert len(b)==len(atoms) and set(b.values())==atoms
            assert b[v['conclusion']]==ns[k]['atom']
            expected=set()
            for n in used:
                if n['rule'] is None:expected.add(((),n['atom']))
                else:r=rules[n['rule']];expected.add((tuple(sorted(r['premises'])),r['conclusion']))
            ground=[]
            for c in v['assumptions']:
                assert len(c['if'])==len(set(c['if']))
                ground.append((tuple(sorted(b[x] for x in c['if'])),b[c['then']]))
            assert len(ground)==len(set(ground)) and set(ground)==expected
            variables=list(b)
            for bits in itertools.product((False,True),repeat=len(variables)):
                val=dict(zip(variables,bits));antecedent=all(not all(val[x] for x in c['if']) or val[c['then']] for c in v['assumptions']);assert not antecedent or val[v['conclusion']]
            modes.append('schema')
        A=modes[0] if len(set(modes))==1 else 'mixed';levels=[]
        for rv in trace['reviews']:
            f=rv['finding']
            if rv['target_kind']=='argument':
                assert rv['target']==final and rv['check']=='support_replay'
                assert len(rv['evidence'])==len(ns) and set(rv['evidence'])==set(ns)
                assert f['grounded'] is True and f['conclusion']==ns[final]['atom']
                assert sorted(f['used_rules'])==sorted({n['rule'] for n in ns.values() if n['rule'] is not None});levels.append(1)
            else:
                assert rv['target_kind']=='acceptance_criterion' and rv['target']=='valid_proof_and_goal' and rv['check']=='counterexample_probe'
                assert rv['probe']=={'atom':problem['goal'],'rule':None,'parents':[]}
                assert type(f['answer_only_accepts']) is bool and type(f['proof_and_goal_accepts']) is bool and type(f['gap_detected']) is bool
                assert f=={'answer_only_accepts':True,'proof_and_goal_accepts':problem['goal'] in problem['facts'],'gap_detected':problem['goal'] not in problem['facts']};levels.append(2)
        return True,A,ds[final],max(levels) if levels else 0
    except (KeyError,TypeError,ValueError,AssertionError):return False,None,None,None

def verify(path):
    with zipfile.ZipFile(path) as z:
        names=z.namelist();assert len(names)==len(set(names));manifest=loads(z.read('BUNDLE_MANIFEST.json'));files=manifest['file_hashes']
        assert set(names)==set(files)|{'BUNDLE_MANIFEST.json'}
        for n,h in files.items():assert hashlib.sha256(z.read(n)).hexdigest()==h
        plan=loads(z.read('external_plan/v052.plan.json'));report=loads(z.read('run/summary.json'))
        lookup={t['id']:t for t in report['trials']};counts={'calls':0,'primary_assigned':0,'primary_valid':0,'primary_role_success':0,'copy_calls':0,'local_result_agreements':0}
        for slot in plan['slots']:
            env=loads(z.read('run/calls/'+slot['id']+'/response.raw.json'));payload=loads(env['message']['content']);counts['calls']+=1
            problem=plan['problems'][slot['problem_id']];ok,A,D,M=check(problem,payload,slot['arm'],slot['task']);stored=lookup[slot['id']]
            assert bool(ok)==bool(stored['measurement']['strict_valid']),(slot['id'],ok,stored['measurement'])
            counts['local_result_agreements']+=1
            if slot['task']=='factorial':
                counts['primary_assigned']+=1;counts['primary_valid']+=ok
                a,d,m=slot['role_id'].split('_');lo,hi=(1,2) if problem['id']=='K01' else (1,4)
                rm=ok and A==a and D==(lo if d=='shallow' else hi) and M==int(m[1:]) and len(payload['reviews'])==(0 if M==0 else 1)
                assert bool(rm)==bool(stored['role_match']);counts['primary_role_success']+=rm
            if slot['task']=='copy_control':counts['copy_calls']+=1
        assert counts['primary_assigned']==240 and counts['copy_calls']==20 and counts['calls']==440
        counts['evidence_kind']=report['evidence_kind'];counts['manifest_files']=len(files)
        return counts
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('bundle',type=Path);parser.add_argument('--out',type=Path);a=parser.parse_args()
    r=verify(a.bundle);text=json.dumps(r,ensure_ascii=False,indent=2);print(text)
    if a.out:a.out.write_text(text,encoding='utf-8')
