"""생산 코드를 import하지 않는 v056 원문 검산기. 표준 라이브러리 + 별도 그래프 계산만 사용."""
from __future__ import annotations
import argparse,base64,io,itertools,json,sys
from pathlib import Path
from independent_graph_forensic import need,load,canonical,sha,unpack,inspect,extract_payload


def bounds(problem):
    """응답 채점용 가능한 깊이 열거. 요청 생성에는 사용하지 않는다."""
    memo={}
    def visit(atom,stack):
        need(atom not in stack,'cyclic problem specification')
        if atom in memo:return memo[atom]
        values={0} if atom in problem['facts'] else set()
        for r in problem['rules']:
            if r['conclusion']==atom:
                parents=[visit(p,stack|{atom}) for p in r['premises']]
                for ds in itertools.product(*parents):values.add(1+max(ds,default=-1))
        memo[atom]=values;return values
    ds=visit(problem['goal'],set());need(bool(ds),'unprovable goal');return min(ds),max(ds)


def metadata(record,expected):
    """기록된 metadata 내용으로 각 모델 식별자를 별도 재구성한다. 실패 record도 수용해 중단을 검산한다."""
    items=record['requests'];need(record['model']==expected['model'],'metadata model')
    names=('server','tags','show');paths=('/api/version','/api/tags','/api/show');data={}
    for i,item in enumerate(items):
        need(i<3 and item['name']==names[i] and item['path']==paths[i],'metadata sequence')
        expected_request=base64.b64encode(canonical({'model':expected['model']})).decode() if i==2 else None
        need(item['request_b64']==expected_request,'metadata request')
        raw=base64.b64decode(item['response_b64'],validate=True)
        if item['http_status']!=200 or item['transport_error'] is not None:return 'runtime_metadata_error'
        try:data[names[i]]=load(raw)
        except (ValueError,UnicodeError):return 'runtime_metadata_error'
    if len(items)!=3:return 'runtime_metadata_error'
    tags=[t for t in data['tags']['models'] if t.get('name')==expected['model'] or t.get('model')==expected['model']]
    if len(tags)!=1:return 'runtime_identity_error'
    show=data['show'];got={'model':expected['model'],'digest':tags[0]['digest'],'show_sha256':sha(canonical(show)),
        'server':data['server'],'details':show.get('details',tags[0].get('details',{})),
        'template':show.get('template'),'parameters':show.get('parameters'),'model_info':show.get('model_info',{})}
    return None if canonical(got)==canonical(expected) else 'runtime_identity_error'


def verify(bundle):
    data,manifest=unpack(bundle);need(manifest['contract']=='v056-evidence-bundle-r1','bundle contract')
    p=load(data['external_plan/v056.plan.json']);r=load(data['run/summary.json']);status=load(data['run/status.json'])
    need(p==load(data['run/plan.snapshot.json']),'plan snapshot')
    need(p['plan_sha256']==sha(canonical({k:v for k,v in p.items() if k!='plan_sha256'})),'plan hash')
    baseline=data['run/baseline/v055_evidence.zip'];need(sha(baseline)==p['reference']['bundle_sha256'],'baseline bytes')
    bd,bm=unpack(io.BytesIO(baseline));bp=load(bd['external_plan/v055.plan.json'])
    need(bp['identities']==p['identities'] and bp['seeds']==p['seeds'],'inherited models/seeds')
    for s in bp['slots']:
        need(base64.b64decode(p['reference']['request_bank'][s['id']],validate=True)==bd[f"run/calls/{s['id']}/request.wire.json"],'original request bank')
    for name,h in p['source_fingerprint'].items():
        raw=data['run/source_snapshot/'+name].decode('utf-8-sig').replace('\r\n','\n').replace('\r','\n').encode()
        need(sha(raw)==h,'snapshot source hash')
    events=[load(line) for line in data['run/events.jsonl'].splitlines()];tip=p['plan_sha256'];seen={};fields=0;diffs=[]
    stored={t['id']:t for t in r['trials']};meta_count=0;failures=[]
    def equal(label,a,b):
        nonlocal fields
        fields+=1
        if type(a)!=type(b) or a!=b:diffs.append({'field':label,'stored':a,'independent':b})
    for i,e in enumerate(events):
        a=e['action'];need(a==p['actions'][i],'event sequence');need(e['previous_hash']==tip,'event chain')
        need(e['event_hash']==sha(canonical({k:v for k,v in e.items() if k!='event_hash'})),'event digest');tip=e['event_hash']
        failure=None
        if a['kind']=='metadata':
            raw=data['run/metadata/'+a['id']+'.json'];need(sha(raw)==e['metadata_sha256'],'metadata hash')
            failure=metadata(load(raw),p['identities'][a['model_key']]);meta_count+=1
        else:
            s=a['slot'];sid=s['id'];raw=data[f'run/calls/{sid}/response.raw.json'];req=data[f'run/calls/{sid}/request.wire.json']
            need(sha(req)==e['request_sha256'] and sha(raw)==e['response_sha256'],'request/response digest')
            original=base64.b64decode(p['reference']['request_bank'][s['reference_slot_id']],validate=True);q=load(original)
            need(q['model']==p['identities'][s['model_key']]['model'] and q['options']['seed']==s['seed'],'model/seed')
            problem=load(q['messages'][1]['content'][9:])
            if s['layout']=='split':need(req==original,'split exact original bytes')
            else:
                need(s['layout']=='merged','unknown layout');old=q['messages'];q['messages']=[{'role':'user','content':old[0]['content']+'\n\n'+old[1]['content']}]
                need(req==json.dumps(q,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf-8'),'merged differs outside message packaging')
            payload=None
            if e['http_status']!=200 or e['transport_error'] is not None:failure='transport_error'
            else:
                try:
                    env=load(raw)
                    if isinstance(env,dict) and isinstance(env.get('model'),str) and env['model']!=q['model']:failure='response_identity_error'
                except (ValueError,UnicodeError):pass
                if failure is None:payload=extract_payload(raw,q['model'])
            m=inspect(problem,payload);lo,hi=bounds(problem)
            match=None if s['direction']=='neutral' else bool(m['strict_valid'] and m['D']==(lo if s['direction']=='shallow' else hi))
            for k in ('format_valid','proof_valid','strict_valid','D','final_ref_valid'):equal(sid+'/'+k,stored[sid]['measurement'][k],m[k])
            equal(sid+'/role',stored[sid]['role_match'],match);equal(sid+'/observed',stored[sid]['observed'],True)
            seen[sid]={'slot':s,'measurement':m,'match':match}
        if failure:
            need(i==len(events)-1 and not status['complete'],'continued after failure');failures.append(failure)
    need(tip==status['event_tip']==r['event_tip'],'event tip')
    need(len(events)==status['recorded_actions'],'event count');equal('call count',r['inference_calls'],status['inference_calls'])
    complete=status['complete'];equal('complete',r['data_complete'],complete)
    need(status['inference_calls'] in (len(seen),len(seen)+1),'attempt count')
    if complete:need(len(seen)==480 and len(events)==520,'complete sample dimensions')
    if failures:equal('failure',status['failure_kind'],failures[-1])
    for s in p['slots']:
        if s['id'] not in seen:
            equal(s['id']+'/unobserved',stored[s['id']]['observed'],False);equal(s['id']+'/unmeasured',stored[s['id']]['measurement'],None)
    pair_results={};summary={}
    for layout,key in itertools.product(p['layouts'],p['model_keys']):
        ts={ (x['slot']['problem_id'],x['slot']['arm'],x['slot']['seed'],x['slot']['direction']):x for x in seen.values() if x['slot']['layout']==layout and x['slot']['model_key']==key}
        successes=0;valid_count=sum(x['measurement']['strict_valid'] for x in ts.values());validpairs=0
        mr=r['layouts'][layout]['models'][key]
        for pid,arm,seed in itertools.product(p['problems'],p['arms'],p['seeds']):
            sh,de=(ts.get((pid,arm,seed,d)) for d in ('shallow','deep'))
            observed=sh is not None and de is not None;valid=bool(observed and sh['measurement']['strict_valid'] and de['measurement']['strict_valid'])
            success=bool(valid and sh['match'] and de['match'] and sh['measurement']['D']!=de['measurement']['D'])
            pair_results[layout,key,pid,arm,seed]=(observed,success);successes+=success;validpairs+=valid
            old=next(x for x in mr['pairs'] if (x['problem_id'],x['arm'],x['seed'])==(pid,arm,seed))
            equal(str((layout,key,pid,arm,seed))+'/selective',old['direction_selective_success'],success)
            equal(str((layout,key,pid,arm,seed))+'/observed',old['both_observed'],observed)
        summary[layout+'/'+key]={'observed':len(ts),'valid':valid_count,'both_valid_pairs':validpairs,'selective_pairs':successes}
    for key,pid,arm in itertools.product(p['model_keys'],p['problems'],p['arms']):
        pairs=[(pair_results['split',key,pid,arm,s],pair_results['merged',key,pid,arm,s]) for s in p['seeds']]
        pairs=[(a[1],b[1]) for a,b in pairs if a[0] and b[0]]
        both=sum(a and b for a,b in pairs);s=sum(a and not b for a,b in pairs);m=sum(b and not a for a,b in pairs)
        old=r['layout_results'][f'{key}/{pid}/{arm}']
        expected={'observed_pairs':len(pairs),'unobserved_pairs':10-len(pairs),'both_success':both,'split_only':s,'merged_only':m,'neither_success':len(pairs)-both-s-m,'merged_minus_split_rate':(m-s)/10 if complete else None}
        for k,v in expected.items():equal(f'{key}/{pid}/{arm}/{k}',old[k],v)
    result={'contract':'independent-v056-r1','bundle_sha256':sha(Path(bundle).read_bytes()),'manifest_files':len(data),'observed_calls':len(seen),'metadata_records':meta_count,'complete':complete,'compared_fields':fields,'differences':diffs,'results':summary,'production_imports':False}
    need(not diffs,'independent semantic differences: '+json.dumps(diffs[:3],ensure_ascii=False));return result


def main():
    ap=argparse.ArgumentParser();ap.add_argument('bundle',type=Path);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    try:r=verify(a.bundle)
    except (ValueError,KeyError,TypeError,OSError) as e:
        r={'verified':False,'error':type(e).__name__+': '+str(e)};a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8');print(r,file=sys.stderr);return 2
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(r,ensure_ascii=False,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
