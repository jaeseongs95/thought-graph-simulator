"""v054 원문 독립 재검산. 생산 모듈·첨부 snapshot·기존 독립 채점기를 import하지 않는다."""
from __future__ import annotations
import argparse, collections, csv, hashlib, itertools, json, zipfile
from pathlib import Path, PurePosixPath

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def canonical(v):
    return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()

def load(raw):
    def pairs(items):
        d={}
        for k,v in items:
            if k in d: raise ValueError('duplicate key '+k)
            d[k]=v
        return d
    def reject(x): raise ValueError('nonfinite '+x)
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=reject)

def checked_zip(path):
    with zipfile.ZipFile(path) as z:
        infos=z.infolist();names=[i.filename for i in infos]
        assert len(names)==len(set(names))
        assert sum(i.file_size for i in infos)<200_000_000
        for i in infos:
            p=PurePosixPath(i.filename)
            assert not p.is_absolute() and '..' not in p.parts and '\\' not in i.filename
            assert ((i.external_attr>>16)&0o170000)!=0o120000
        data={i.filename:z.read(i) for i in infos if not i.is_dir()}
    m=load(data['BUNDLE_MANIFEST.json'])
    assert set(data)==set(m['file_hashes'])|{'BUNDLE_MANIFEST.json'}
    assert all(sha(data[n])==h for n,h in m['file_hashes'].items())
    return data,m

def measure(problem,payload):
    result={'format_valid':False,'proof_valid':None,'strict_valid':False,'D':None,'final_ref_valid':None,'errors':[]}
    if payload is None: return result
    nodes=payload.get('nodes') if isinstance(payload,dict) else None
    final=payload.get('final_node_id') if isinstance(payload,dict) else None
    if isinstance(nodes,list):
        result['final_ref_valid']=isinstance(final,str) and bool(final) and sum(isinstance(n,dict) and n.get('id')==final for n in nodes)==1
    def text(v): return isinstance(v,str) and 1<=len(v)<=128
    shape=isinstance(payload,dict) and set(payload)=={'nodes','final_node_id'} and text(final) and isinstance(nodes,list) and 1<=len(nodes)<=16
    if shape:
        for n in nodes:
            if not (isinstance(n,dict) and set(n)=={'id','atom','rule','parents'} and text(n['id']) and text(n['atom']) and (n['rule'] is None or text(n['rule'])) and isinstance(n['parents'],list) and len(n['parents'])<=16 and all(text(p) for p in n['parents'])):
                shape=False;break
    result['format_valid']=shape
    if not shape:
        result['proof_valid']=False;result['errors']=['format'];return result
    byid={}; depths={};ancestors={};terms={};rules={r['id']:r for r in problem['rules']}
    try:
        for n in nodes:
            ident=n['id'];parents=n['parents'];rid=n['rule']
            if ident in byid: raise ValueError('duplicate_id')
            if len(set(parents))!=len(parents): raise ValueError('duplicate_parent')
            if any(p not in byid for p in parents): raise ValueError('missing_or_forward_parent')
            if rid is None:
                if parents or n['atom'] not in problem['facts']: raise ValueError('unsupported_fact')
                depth=0
            else:
                if rid not in rules: raise ValueError('unknown_rule')
                if n['atom']!=rules[rid]['conclusion']: raise ValueError('rule_conclusion')
                if sorted(byid[p]['atom'] for p in parents)!=sorted(rules[rid]['premises']): raise ValueError('wrong_premises')
                depth=1+max(depths[p] for p in parents)
            byid[ident]=n;depths[ident]=depth
            ancestors[ident]={ident}.union(*(ancestors[p] for p in parents))
            terms[ident]=sha(canonical([n['atom'],rid,sorted(terms[p] for p in parents)]))
        if final not in byid: raise ValueError('missing_final')
        if byid[final]['atom']!=problem['goal']: raise ValueError('wrong_goal')
        if ancestors[final]!=set(byid): raise ValueError('unused_nodes')
        result.update(proof_valid=True,strict_valid=True,D=depths[final],structure=terms[final])
    except ValueError as exc:
        result['proof_valid']=False;result['errors']=[str(exc)]
    return result

def envelope(raw,model):
    e=load(raw)
    if not (e.get('model')==model and e.get('done') is True and e.get('done_reason')=='stop'):return None
    m=e.get('message')
    if not (isinstance(m,dict) and m.get('role')=='assistant' and isinstance(m.get('content'),str)):return None
    if m.get('tool_calls') or m.get('images') or (m.get('thinking') is not None and (not isinstance(m['thinking'],str) or m['thinking'].strip())):return None
    if '<think>' in m['content'] or '</think>' in m['content']:return None
    try:return load(m['content'])
    except (ValueError,UnicodeError):return None

def bounds(problem):
    def walk(atom,seen):
        if atom in seen:return set()
        ds={0} if atom in problem['facts'] else set()
        for r in problem['rules']:
            if r['conclusion']==atom:
                for parents in itertools.product(*(walk(p,seen|{atom}) for p in r['premises'])):
                    ds.add(1+max(parents))
        return ds
    values=walk(problem['goal'],set());return min(values),max(values)

def write_csv(path,rows):
    if not rows:return
    keys=list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,keys);w.writeheader()
        for r in rows:w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v for k,v in r.items()})

def verify(bundle,out,previous=None):
    out.mkdir(parents=True,exist_ok=True);data,manifest=checked_zip(bundle)
    plan=load(data['external_plan/v054.plan.json']);report=load(data['run/summary.json']);status=load(data['run/status.json'])
    assert plan['plan_sha256']==sha(canonical({k:v for k,v in plan.items() if k!='plan_sha256'}))
    assert plan==load(data['run/plan.snapshot.json'])
    events=[load(x) for x in data['run/events.jsonl'].splitlines()]
    assert len(events)==len(plan['slots'])==120 and status['complete'] is True
    stored={x['id']:x for x in report['trials']};mismatches=[];fields=0;tip=plan['plan_sha256'];rows=[];payloads={};requests={}
    def compare(where,a,b):
        nonlocal fields
        fields+=1
        if type(a)!=type(b) or a!=b:mismatches.append({'field':where,'stored':a,'independent':b})
    for slot,event in zip(plan['slots'],events):
        sid=slot['id']; assert slot==event['slot'] and event['previous_hash']==tip
        assert event['event_hash']==sha(canonical({k:v for k,v in event.items() if k!='event_hash'}));tip=event['event_hash']
        req=data[f'run/calls/{sid}/request.wire.json'];raw=data[f'run/calls/{sid}/response.raw.json']
        assert sha(req)==event['request_sha256'] and sha(raw)==event['response_sha256']
        assert event['http_status']==200 and event['transport_error'] is None
        request=load(req);problem=load(request['messages'][1]['content'][len('problem: '):]); payload=envelope(raw,request['model'])
        m=measure(problem,payload);b=bounds(problem)
        role=None if slot['direction']=='neutral' else bool(m['strict_valid'] and m['D']==b[slot['direction']=='deep'])
        for f in ('format_valid','proof_valid','strict_valid','D','final_ref_valid'):compare(sid+'/'+f,stored[sid]['measurement'][f],m[f])
        if role is not None:compare(sid+'/role_match',stored[sid]['role_match'],role)
        rows.append({**slot,**m,'role_match':role,'response_sha256':sha(raw),'request_sha256':sha(req)})
        payloads[sid]=payload;requests[sid]=request
    assert tip==report['event_tip']==status['event_tip']
    lookup={(r['problem_id'],r['arm'],r['seed'],r['direction']):r for r in rows}
    pairs=[];oldpairs={(r['problem_id'],r['arm'],r['seed']):r for r in report['pairs']}
    for pid,arm,seed in itertools.product(plan['problems'],plan['arms'],plan['seeds']):
        a,b=(lookup[pid,arm,seed,d] for d in ('shallow','deep')); val=bool(a['role_match'] and b['role_match'] and a['D']!=b['D'])
        compare(f'{pid}/{arm}/{seed}/selective',oldpairs[pid,arm,seed]['direction_selective_success'],val)
        pairs.append({'problem_id':pid,'arm':arm,'seed':seed,'shallow_depth':a['D'],'deep_depth':b['D'],'both_valid':a['strict_valid'] and b['strict_valid'],'selective_success':val})
    orders=[];oldorder={(r['problem_id'],r['direction'],r['seed']):r for r in report['order_contrasts']}
    for pid,direction,seed in itertools.product(plan['problems'],plan['directions'],plan['seeds']):
        a,b=(lookup[pid,arm,seed,direction] for arm in plan['arms']);valid=a['strict_valid'] and b['strict_valid'];change=a['D']!=b['D'] if valid else None;structure=a.get('structure')!=b.get('structure') if valid else None
        compare(f'{pid}/{direction}/{seed}/order_depth',oldorder[pid,direction,seed]['depth_changed'],change);compare(f'{pid}/{direction}/{seed}/order_structure',oldorder[pid,direction,seed]['structure_changed'],structure)
        qa,qb=requests[a['id']],requests[b['id']];pa,pb=(load(q['messages'][1]['content'][9:]) for q in (qa,qb))
        assert {k:v for k,v in qa.items() if k!='messages'}=={k:v for k,v in qb.items() if k!='messages'} and qa['messages'][0]==qb['messages'][0]
        assert {k:v for k,v in pa.items() if k!='rules'}=={k:v for k,v in pb.items() if k!='rules'}
        assert sorted(pa['rules'],key=lambda r:r['id'])==sorted(pb['rules'],key=lambda r:r['id'])
        orders.append({'problem_id':pid,'direction':direction,'seed':seed,'original_depth':a['D'],'swapped_depth':b['D'],'both_valid':valid,'depth_changed':change})
    oldrobust={(r['problem_id'],r['seed']):r for r in report['robust_pairs']}
    for pid,seed in itertools.product(plan['problems'],plan['seeds']):
        val=all(p['selective_success'] for p in pairs if p['problem_id']==pid and p['seed']==seed)
        compare(f'{pid}/{seed}/robust',oldrobust[pid,seed]['both_orders_selective_success'],val)
    bad=[]
    for row in rows:
        if row['strict_valid']:continue
        p=payloads[row['id']];byid={n['id']:n for n in p['nodes']};final=byid[p['final_node_id']];problem=plan['problems'][row['problem_id']];rules={r['id']:r for r in problem['rules']}
        bad.append({'id':row['id'],'first_failure':row['errors'],'final_id':p['final_node_id'],'final_rule':final['rule'],'expected_final_premises':rules[final['rule']]['premises'],'actual_final_parent_ids':final['parents'],'actual_final_parent_atoms':[byid[x]['atom'] if x in byid else None for x in final['parents']],'missing_parent_refs':[{'node':n['id'],'parent':x} for n in p['nodes'] for x in n['parents'] if x not in byid]})
    rep=[]
    if previous:
        old,_=checked_zip(previous)
        for row in rows:
            if row['arm']!='original':continue
            sid=row['id'];req=old[f'run/calls/{sid}/request.wire.json'];assert req==data[f'run/calls/{sid}/request.wire.json']
            q=load(req);problem=load(q['messages'][1]['content'][9:]);m=measure(problem,envelope(old[f'run/calls/{sid}/response.raw.json'],q['model']))
            rep.append({'id':sid,'request_bytes_equal':True,'depth_equal':m['D']==row['D'],'valid_equal':m['strict_valid']==row['strict_valid'],'structure_equal':m.get('structure')==row.get('structure')})
    groups=[]
    for pid,arm,d in itertools.product(plan['problems'],plan['arms'],plan['directions']):
        rs=[r for r in rows if (r['problem_id'],r['arm'],r['direction'])==(pid,arm,d)]
        groups.append({'problem_id':pid,'arm':arm,'direction':d,'assigned':len(rs),'valid':sum(r['strict_valid'] for r in rs),'direction_match':None if d=='neutral' else sum(r['role_match'] for r in rs),'depths':dict(collections.Counter(str(r['D']) for r in rs))})
    result={'bundle_sha256':sha(bundle.read_bytes()),'manifest_files':len(manifest['file_hashes']),'raw_responses':len(rows),'semantic_fields_compared':fields,'discrepancies':mismatches,'valid_proofs':sum(r['strict_valid'] for r in rows),'selective_pairs':sum(p['selective_success'] for p in pairs),'order_changes':sum(p['depth_changed'] is True for p in orders),'order_unmeasured':sum(p['depth_changed'] is None for p in orders),'only_rule_order_changed_pairs':len(orders),'all_bad_final_parents_are_Lp_Ls':all(sorted(r['actual_final_parent_atoms'])==['Lp','Ls'] for r in bad),'bad_missing_reference_responses':sum(bool(r['missing_parent_refs']) for r in bad),'v053_replication_requests':len(rep),'v053_replication_equal':all(r['depth_equal'] and r['valid_equal'] and r['structure_equal'] for r in rep),'groups':groups,'scope':'완료된 v054 원문 검사. source/runtime 동결은 생산 감사와 별도로 검사. 내부 사고 메커니즘 추정 아님'}
    for name,rs in [('trials',rows),('D_pairs',pairs),('order_pairs',orders),('invalid_graphs',bad),('v053_v054_replication',rep),('groups',groups)]:write_csv(out/(name+'.csv'),rs)
    (out/'forensic_results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    assert not mismatches
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('bundle',type=Path);p.add_argument('--out',type=Path,required=True);p.add_argument('--previous',type=Path);a=p.parse_args();print(json.dumps(verify(a.bundle,a.out,a.previous),ensure_ascii=False,indent=2))
