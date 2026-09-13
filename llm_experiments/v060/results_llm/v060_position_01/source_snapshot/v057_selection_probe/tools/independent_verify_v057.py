"""생산 모듈을 import하지 않는 v057 원문/요청/측정 검산. 표준 라이브러리 및 별도 검산기만 사용."""
from __future__ import annotations
import argparse,base64,collections,itertools,json,io,tempfile
from pathlib import Path
from independent_graph_forensic import need,load,canonical,sha,unpack,inspect,extract_payload
from independent_verify_v056 import metadata,verify as verify_baseline

CHOICE_HEADER=(
 'facts와 rules만 사용하여 goal을 지지하는 비순환 증명 경로 하나를 선택한다.\n'
 '이번에는 전체 증명 DAG를 작성하지 않는다. 선택한 경로에서 goal을 직접 도출하는 마지막 규칙의 id 하나만 출력한다.\n'
 'final_rule_id에는 입력 rules에 등록된 실제 규칙 id를 쓴다. 원자 이름이나 새 노드 id를 쓰지 않는다.\n'
 '선택한 마지막 규칙의 모든 전제는 facts에서 rules를 통해 도출 가능해야 한다.\n'
 '후보 목록, 증명 노드, 설명, 깊이 숫자는 출력하지 않는다.'
)
CS={'type':'object','properties':{'final_rule_id':{'type':'string','minLength':1,'maxLength':128}},'required':['final_rule_id'],'additionalProperties':False}
def encode(x):return json.dumps(x,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()

def problem_depths(problem):
    """전방 깊이 집합 전파로 별도 계산. 생산 채점기의 재귀 함수를 사용하지 않는다."""
    table={f:{0} for f in problem['facts']}
    for _ in range(32):
        before={k:set(v) for k,v in table.items()}
        for r in problem['rules']:
            if all(p in table for p in r['premises']):
                ds={1+max(ds,default=-1) for ds in itertools.product(*(table[p] for p in r['premises']))}
                table.setdefault(r['conclusion'],set()).update(ds)
        if table==before:break
    else:raise ValueError('cyclic/unsupported problem')
    result={}
    for r in problem['rules']:
        if r['conclusion']==problem['goal'] and all(a in table for a in r['premises']):
            ds={1+max(ds,default=-1) for ds in itertools.product(*(table[a] for a in r['premises']))}
            need(len(ds)==1,'terminal rule does not identify depth');result[r['id']]=next(iter(ds))
    need(len(set(result.values()))>=2,'two target depths required');return result

def choice(problem,payload):
    m={'format_valid':False,'choice_valid':None,'selected_rule_id':None,'implied_depth':None,'proof_valid':None,'strict_valid':None,'D':None}
    if not isinstance(payload,dict) or set(payload)!={'final_rule_id'} or not isinstance(payload['final_rule_id'],str) or not 1<=len(payload['final_rule_id'])<=128:return m
    rid=payload['final_rule_id'];ds=problem_depths(problem)
    m.update(format_valid=True,choice_valid=rid in ds,selected_rule_id=rid,implied_depth=ds.get(rid));return m

def expected_request(raw,slot):
    if slot['mode']=='graph':return raw
    need(slot['mode']=='choice','mode');q=load(raw)
    need(len(q['messages'])==1 and q['messages'][0]['role']=='user','merged base')
    prefix,problem=q['messages'][0]['content'].rsplit('\n\nproblem: ',1)
    old=prefix.split('\nJSON 객체 하나만 출력한다. 출력 형식(JSON Schema):\n',1)[0]
    directive='' if slot['direction']=='neutral' else '\n경로 지시:\n'+old.split('\n경로 지시:\n',1)[1]
    q['messages']=[{'role':'user','content':CHOICE_HEADER+directive+'\nJSON 객체 하나만 출력한다. 출력 형식(JSON Schema):\n'+encode(CS).decode()+'\n\nproblem: '+problem}];q['format']=CS
    return encode(q)

def verify(bundle):
    data,manifest=unpack(bundle);need(manifest['contract']=='v057-evidence-bundle-r1','bundle contract')
    p=load(data['external_plan/v057.plan.json']);r=load(data['run/summary.json']);status=load(data['run/status.json']);runm=load(data['run/run_manifest.json'])
    need(p==load(data['run/plan.snapshot.json']),'plan snapshot');need(p['plan_sha256']==sha(canonical({k:v for k,v in p.items() if k!='plan_sha256'})),'plan hash')
    need(p['contract']=='selection-probe-v057-r1' and p['modes']==['graph','choice'] and p['reference_layout']=='merged','frozen experiment')
    baseline=data['run/baseline/v056_evidence.zip'];need(sha(baseline)==p['reference']['bundle_sha256'],'baseline bytes')
    with tempfile.TemporaryDirectory(prefix='independent_v057_') as td:
        previous=Path(td)/'v056.zip';previous.write_bytes(baseline);vr=verify_baseline(previous)
    need(vr['complete'] and not vr['differences'],'baseline independent check')
    bd,bm=unpack(io.BytesIO(baseline));bp=load(bd['external_plan/v056.plan.json']);need(bp['identities']==p['identities'] and bp['seeds']==p['seeds'],'identity/seed inheritance')
    selected=[s for s in bp['slots'] if s['layout']=='merged'];need(selected==p['reference']['slots'],'selected source slots')
    need(p['reference']['recorded_calls']==480 and p['reference']['selected_calls']==240 and p['reference']['selected_layout']=='merged','reference count')
    need(set(p['reference']['request_bank'])=={s['id'] for s in selected},'bank keys')
    for s in selected:need(base64.b64decode(p['reference']['request_bank'][s['id']],validate=True)==bd[f"run/calls/{s['id']}/request.wire.json"],'request bank bytes')
    specs={(s['model_key'],s['seed'],s['problem_id'],s['arm'],s['direction']):s for s in selected};expected=[]
    for i,seed in enumerate(p['seeds']):
        for j,key in enumerate(('reference','candidate') if i%2==0 else ('candidate','reference')):
            cells=sorted(itertools.product(bp['problems'],bp['arms'],bp['directions']))
            for n,(pid,arm,d) in enumerate(cells):
                old=specs[key,seed,pid,arm,d]
                for mode in ('graph','choice') if (i+n)%2==0 else ('choice','graph'):
                    expected.append(old|{'id':mode+'__'+old['id'],'reference_slot_id':old['id'],'mode':mode,'task':'selection_probe','stage':mode,'block':2*i+j,'seed_index':i,'position':len(expected)})
    need(expected==p['slots'],'slot schedule')
    actions=[]
    for b in range(20):
        ss=[s for s in expected if s['block']==b]
        actions.append({'kind':'metadata','id':f'b{b:02d}.before','block':b,'model_key':ss[0]['model_key']})
        actions.extend({'kind':'call','id':s['id'],'slot':s} for s in ss)
        actions.append({'kind':'metadata','id':f'b{b:02d}.after','block':b,'model_key':ss[0]['model_key']})
    for i,a in enumerate(actions):a['index']=i
    need(actions==p['actions'],'action schedule')
    need(runm['source_fingerprint']==p['source_fingerprint'] and runm['plan_sha256']==p['plan_sha256'],'run identity')
    need(runm['evidence_kind']==p['reference']['evidence_kind'],'source label');need(runm['new_model_inference'] is (runm['evidence_kind']!='synthetic_fixture'),'synthetic label')
    actual_snap={n[len('run/source_snapshot/'):] for n in data if n.startswith('run/source_snapshot/')};need(actual_snap==set(p['source_fingerprint']),'source snapshot files')
    for name,h in p['source_fingerprint'].items():
        raw=data['run/source_snapshot/'+name].decode('utf-8-sig').replace('\r\n','\n').replace('\r','\n').encode();need(sha(raw)==h,'source snapshot bytes')
    stored={t['id']:t for t in r['trials']};need(set(stored)=={s['id'] for s in p['slots']},'report trial ids')
    events=[load(line) for line in data['run/events.jsonl'].splitlines()];tip=p['plan_sha256'];observed={};diff=[];fields=0;metadata_count=0;last_fail=None
    def eq(label,a,b):
        nonlocal fields
        fields+=1
        if type(a)!=type(b) or a!=b:diff.append({'field':label,'stored':a,'independent':b})
    for i,e in enumerate(events):
        need(e['action']==actions[i] and e['previous_hash']==tip,'action/order chain');need(e['event_hash']==sha(canonical({k:v for k,v in e.items() if k!='event_hash'})),'event hash');tip=e['event_hash'];a=e['action'];failure=None
        if a['kind']=='metadata':
            raw=data['run/metadata/'+a['id']+'.json'];need(sha(raw)==e['metadata_sha256'],'metadata bytes');failure=metadata(load(raw),p['identities'][a['model_key']]);metadata_count+=1
        else:
            s=a['slot'];sid=s['id'];wire=data[f'run/calls/{sid}/request.wire.json'];raw=data[f'run/calls/{sid}/response.raw.json'];model=p['identities'][s['model_key']]['model']
            old=bd[f"run/calls/{s['reference_slot_id']}/request.wire.json"];need(wire==expected_request(old,s),'request transformation')
            need(sha(wire)==e['request_sha256'] and sha(raw)==e['response_sha256'],'raw hash')
            q=load(wire);problem=load(q['messages'][0]['content'].rsplit('\n\nproblem: ',1)[1]);payload=extract_payload(raw,model)
            if e['http_status']!=200 or e['transport_error'] is not None:failure='transport_error';payload=None
            else:
                try:
                    env=load(raw)
                    if isinstance(env,dict) and isinstance(env.get('model'),str) and env['model']!=model:failure='response_identity_error';payload=None
                except (ValueError,UnicodeError):pass
            m=inspect(problem,payload) if s['mode']=='graph' else choice(problem,payload)
            mm=stored[sid]['measurement'];keys=('format_valid','proof_valid','strict_valid','D','final_ref_valid') if s['mode']=='graph' else ('format_valid','choice_valid','selected_rule_id','implied_depth','proof_valid','strict_valid','D')
            for k in keys:eq(sid+'/'+k,mm[k],m[k])
            valid=m['strict_valid'] if s['mode']=='graph' else m['choice_valid'];dep=m['D'] if s['mode']=='graph' else m['implied_depth'];bounds=problem_depths(problem).values()
            target=min(bounds) if s['direction']=='shallow' else max(bounds)
            match=None if s['direction']=='neutral' else bool(valid is True and dep==target)
            eq(sid+'/role_match',stored[sid]['role_match'],match);eq(sid+'/observed',stored[sid]['observed'],True)
            observed[sid]=s|{'valid':valid,'depth':dep,'match':match,'format_valid':m['format_valid']}
        if failure:
            need(i==len(events)-1 and not status['complete'],'no retry after failure');last_fail=failure
    need(tip==status['event_tip']==r['event_tip'],'tip');need(len(events)==status['recorded_actions'],'event count');eq('observed calls',len(r['calls']),len(observed))
    if status['complete']:need(len(events)==520 and len(observed)==480 and status['inference_calls']==480,'complete counts')
    else:
        need(len(observed)<=status['inference_calls']<=len(observed)+1,'partial counts')
        if last_fail:need(status['failure_kind']==last_fail,'failure diagnosis')
    lookup={(s['mode'],s['model_key'],s['problem_id'],s['arm'],s['seed'],s['direction']):s['id'] for s in p['slots']};pairmap={};result={}
    for pair in r['pairs']:
        mode,key,pid,arm,seed=(pair[k] for k in ('mode','model_key','problem_id','arm','seed'))
        sh,de=(observed.get(lookup[mode,key,pid,arm,seed,d]) for d in ('shallow','deep'));seen=sh is not None and de is not None
        success=bool(sh['match'] and de['match'] and sh['depth']!=de['depth']) if seen else None
        eq('pair observed',pair['both_observed'],seen);eq('pair success',pair['selective_success'],success)
        eq('choice is not proof',pair['full_proof_D_control_success'],success if mode=='graph' else None)
        pairmap[mode,key,pid,arm,seed]=success
    for key in p['model_keys']:
        result[key]={};outs=collections.Counter()
        for mode in p['modes']:
            rs=[s for s in observed.values() if (s['model_key'],s['mode'])==(key,mode)];vals=[x for (mo,ke,*_),x in pairmap.items() if (mo,ke)==(mode,key)];successes=sum(v is True for v in vals)
            got={'observed_calls':len(rs),'format_valid':sum(s['format_valid'] for s in rs),'task_valid':sum(s['valid'] is True for s in rs),
                 'observed_pairs':sum(x is not None for x in vals),'selective_success':successes,'selective_rate':successes/40 if status['complete'] else None,
                 'full_proof_D_control_success':successes if mode=='graph' else None}
            for k,v in got.items():eq(key+'/'+mode+'/'+k,r['models'][key]['modes'][mode][k],v)
            result[key][mode]=got
        for pid,arm,seed in itertools.product(p['problems'],p['arms'],p['seeds']):
            g,c=(pairmap[mo,key,pid,arm,seed] for mo in ('graph','choice'))
            outcome='unobserved' if g is None or c is None else ('both_selective' if g and c else ('graph_only' if g else ('choice_only' if c else 'neither')));outs[outcome]+=1
        for k in ('both_selective','graph_only','choice_only','neither','unobserved'):eq(key+'/contrast/'+k,r['models'][key]['task_contrast'][k],outs[k])
        eq(key+'/rate',r['models'][key]['choice_minus_graph_rate'],(outs['choice_only']-outs['graph_only'])/40 if status['complete'] else None)
    for t in r['trials']:
        if t['id'] not in observed:
            eq('unexecuted observed',t['observed'],False);eq('unexecuted measurement',t['measurement'],None);eq('unexecuted role',t['role_match'],None)
    need(not diff,'independent measurement/report mismatch: '+str(diff[:3]))
    return {'contract':'independent-v057-r1','bundle_sha256':sha(bundle.read_bytes()),'manifest_files':len(data),'observed_calls':len(observed),
            'metadata_records':metadata_count,'complete':status['complete'],'compared_fields':fields,'differences':diff,'results':result,
            'production_imports':False,'baseline_independent_compared_fields':vr['compared_fields']}

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('bundle',type=Path);ap.add_argument('--out',type=Path);a=ap.parse_args()
    try:
        result=verify(a.bundle);text=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
        if a.out:
            with a.out.open('x',encoding='utf-8') as f:f.write(text)
        print(text)
    except (ValueError,OSError,KeyError,TypeError) as e:
        print('독립 검산 실패: '+str(e));raise SystemExit(2)
