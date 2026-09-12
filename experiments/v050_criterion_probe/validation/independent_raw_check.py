"""v050 raw 증거 교차검사. production 감사기·요청 생성기·oracle를 import하지 않는다."""
from __future__ import annotations
import argparse,hashlib,json,zipfile
from pathlib import Path

def digest(raw):return hashlib.sha256(raw).hexdigest()
def canonical(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def load(raw):
    def pairs(seq):
        out={}
        for k,v in seq:
            if k in out:raise ValueError('duplicate JSON key')
            out[k]=v
        return out
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))

def payload_valid(x,stage):
    if not isinstance(x,dict):return False
    if stage not in ('extract','oneshot_original','oneshot_commuted'):
        return set(x)=={'value'} and type(x['value']) is bool
    keys={'observed','primitives'} if stage=='extract' else {'observed','primitives','finding'}
    if set(x)!=keys:return False
    o=x['observed'];p=x['primitives']
    if not isinstance(o,dict) or set(o)!={'probe_atom','goal_atom','facts'}:return False
    if not all(isinstance(o[k],str) and 1<=len(o[k])<=128 for k in ('probe_atom','goal_atom')):return False
    if not isinstance(o['facts'],list) or not 1<=len(o['facts'])<=10 or not all(isinstance(v,str) and 1<=len(v)<=128 for v in o['facts']):return False
    if not isinstance(p,dict) or set(p)!={'same_as_goal','in_facts'} or not all(type(v) is bool for v in p.values()):return False
    if stage=='extract':return True
    f=x['finding'];return isinstance(f,dict) and set(f)=={'answer_only_accepts','proof_and_goal_accepts','gap_detected'} and all(type(v) is bool for v in f.values())

def check(archive,out=None):
    with zipfile.ZipFile(archive) as z:
        names=z.namelist();assert len(names)==len(set(names))
        manifest=load(z.read('BUNDLE_MANIFEST.json'));hashes=manifest['file_hashes']
        assert set(hashes)==set(names)-{'BUNDLE_MANIFEST.json'}
        for n,h in hashes.items():assert digest(z.read(n))==h,n
        p=load(z.read('external_plan/v050.plan.json'));assert p==load(z.read('run/plan.snapshot.json'))
        assert p['plan_sha256']==digest(canonical({k:v for k,v in p.items() if k!='plan_sha256'}))
        cases={c['id']:c for c in p['cases']};events=[load(l) for l in z.read('run/events.jsonl').splitlines()]
        previous=p['plan_sha256'];payloads={};records={};count=0;edges=0;blocked=0
        for e in events:
            assert e['previous_hash']==previous and e['event_hash']==digest(canonical({k:v for k,v in e.items() if k!='event_hash'}));previous=e['event_hash']
            s=e['slot'];sid=s['id'];stage=s['stage'];stem=s['block_id']+'__'
            deps=[] if stage in ('extract','oneshot_original','oneshot_commuted') else [stem+'extract']
            if stage=='gap_and':deps.append(stem+'not')
            assert e['parents']==[{'id':d,'response_sha256':records[d].get('response_sha256')} for d in deps];edges+=len(deps)
            actual=None
            if e['kind']=='blocked':
                assert any(payloads.get(d) is None for d in deps);blocked+=1
            else:
                assert all(payloads.get(d) is not None for d in deps)
                req=z.read('run/calls/'+sid+'/request.wire.json');raw=z.read('run/calls/'+sid+'/response.raw.json')
                assert digest(req)==e['request_sha256'] and digest(raw)==e['response_sha256']
                q=load(req);cfg=p['baseline']['config'];assert q['model']==cfg['model'];assert q['options']==dict(cfg['options'],seed=s['seed'])
                text=q['messages'][1]['content']
                if deps:
                    v=load(text[7:]);prim=payloads[stem+'extract']['primitives'];expected_expr={'proof':'(a AND b)','gap_direct':'((NOT b) AND a)','not':'(NOT b)','gap_and':'(a AND b)'}[stage]
                    assert v['a'] is prim['same_as_goal']
                    assert v['b'] is (payloads[stem+'not']['value'] if stage=='gap_and' else prim['in_facts'])
                    assert v['expression']==expected_expr
                else:
                    problem,probe=text.split('\nprobe: ',1);case=cases[s['case_id']]
                    assert load(problem[len('problem: '):])==case['problem'] and load(probe)==case['probe']
                try:
                    env=load(raw);msg=env['message'];value=load(msg['content'])
                    valid=(env.get('done') is True and env.get('done_reason')=='stop' and env.get('model')==cfg['model'] and msg.get('role')=='assistant' and not msg.get('thinking') and not msg.get('tool_calls') and payload_valid(value,stage))
                    if valid and e['http_status']==200 and e['transport_error'] is None:actual=value
                except (ValueError,KeyError,TypeError,UnicodeError):pass
                count+=1
            payloads[sid]=actual;records[sid]=e
        result={'bundle_sha256':digest(Path(archive).read_bytes()),'manifest_files_checked':len(hashes),'http_calls':count,'blocked_slots':blocked,
                'parent_edges_checked':edges,'event_tip':previous,'arms':{},'independent_of_production_imports':True}
        for arm in ('oneshot_original','oneshot_commuted','staged_commuted','staged_pipeline'):
            finding_ok=trace_ok=gap_ok=0
            for b in p['blocks']:
                c=cases[b['case_id']];pr=c['problem'];probe=c['probe']['atom'];aa=probe==pr['goal'];bb=probe in pr['facts']
                target={'answer_only_accepts':aa,'proof_and_goal_accepts':aa and bb,'gap_detected':aa and not bb}
                obs={'probe_atom':probe,'goal_atom':pr['goal'],'facts':pr['facts']};prim={'same_as_goal':aa,'in_facts':bb};stem=b['id']+'__'
                middle_ok=True
                if arm.startswith('oneshot'):
                    w=payloads.get(stem+arm);finding=w['finding'] if w else None
                    gap_ok+=bool(finding and finding['gap_detected'] is target['gap_detected'])
                else:
                    ext=payloads.get(stem+'extract');proof=payloads.get(stem+'proof');gap=payloads.get(stem+('gap_direct' if arm=='staged_commuted' else 'gap_and'))
                    gap_ok+=bool(gap is not None and gap['value'] is target['gap_detected'])
                    w=None;finding=None
                    if ext is not None and proof is not None and gap is not None:
                        finding={'answer_only_accepts':ext['primitives']['same_as_goal'],'proof_and_goal_accepts':proof['value'],'gap_detected':gap['value']}
                        w={'observed':ext['observed'],'primitives':ext['primitives'],'finding':finding}
                        if arm=='staged_pipeline':
                            n=payloads.get(stem+'not');middle_ok=n is not None and n['value'] is (not ext['primitives']['in_facts'])
                good=finding is not None and finding==target;finding_ok+=good
                trace_ok+=bool(w is not None and good and w['observed']==obs and w['primitives']==prim and middle_ok)
            result['arms'][arm]={'finding_correct':finding_ok,'gap_correct':gap_ok,'strict_trace_correct':trace_ok,'assigned':len(p['blocks'])}
        stored=load(z.read('run/summary.json'))
        result['matches_saved_scores']=all(all(stored['arms'][a][k]==v for k,v in row.items()) for a,row in result['arms'].items())
        assert result['matches_saved_scores']
    if out:Path(out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2));return result
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('archive',type=Path);ap.add_argument('--out',type=Path);args=ap.parse_args();check(args.archive,args.out)
