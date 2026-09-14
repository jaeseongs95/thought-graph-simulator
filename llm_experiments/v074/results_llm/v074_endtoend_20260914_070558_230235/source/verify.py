"""v074 독립 번들 검산. 외부 실행 사실을 인증하지 않고 내부 일관성을 검산한다."""
from __future__ import annotations
import argparse,json,re,sys,urllib.parse
from pathlib import Path
from audit_io import archive,b64,digest,dump,load,need,same
from audit_model import reconstruct_schedule,expected_request,independent_summary,independent_report
ROOT=Path(__file__).resolve().parent


def local_sources():
    result={}
    for p in ROOT.rglob('*'):
        if '__pycache__' in p.parts:continue
        need(not p.is_symlink(),'local source symlink')
        if p.is_file():result[p.relative_to(ROOT).as_posix()]=p.read_bytes()
    return result


def metadata_ok(items,expected):
    try:
        if len(items)!=3 or any(x['http_status']!=200 or x['error'] is not None for x in items):return False
        version,tags,show=[load(b64(i['response_b64'])) for i in items]
        ms=[m for m in tags['models'] if m.get('model')==expected['model'] or m.get('name')==expected['model']]
        if len(ms)!=1 or ms[0].get('digest')!=expected['digest'] or not same(ms[0].get('details'),expected['tag_details']) or not same(version,expected['server']):return False
        ns={k:show.get(k) for k in ('template','system','parameters','model_info','details','capabilities','projector_info')}
        if ns['parameters'] is not None:
            if type(ns['parameters']) is not str:return False
            ns['parameters']=sorted(ns['parameters'].split('\n'))
        return same(ns,expected['native'])
    except (KeyError,TypeError,ValueError,UnicodeError):return False


def fatal(r,raw,s):
    if r['error'] is not None:return 'transport_error'
    if r['http_status']!=200:return 'http_error'
    try:x=load(raw)
    except (ValueError,UnicodeError):return None
    if not isinstance(x,dict) or x.get('model')!=s['model']:return 'identity_error'
    if type(x.get('eval_count')) is int and x['eval_count']>s['num_predict']:return 'generation_budget_exceeded'
    return None


def validate_record(fs,p,a,record,raws,allowed):
    sid=a['id'];s=p['protocol']
    need(record.get('id')==sid,'record id')
    if a['kind']=='metadata':
        need(set(record)=={'id','kind','items','identity_ok'} and record['kind']=='metadata','metadata record schema')
        items=record['items'];need(isinstance(items,list) and 1<=len(items)<=3,'metadata items')
        for i,item in enumerate(items):
            need(set(item)=={'path','http_status','error','elapsed_ns','request_b64','response_b64'},'metadata item schema')
            path=('/api/version','/api/tags','/api/show')[i];request=None if i<2 else dump({'model':s['model']})
            need(item['path']==path and (item['request_b64'] is None if request is None else b64(item['request_b64'])==request),'metadata request')
            names=[f'metadata/{sid}/{i}.request.json',f'metadata/{sid}/{i}.response.raw.json'];allowed.update(names)
            need(fs[names[0]]==(request or b'') and fs[names[1]]==b64(item['response_b64']),'metadata wire')
            need(type(item['elapsed_ns']) is int and item['elapsed_ns']>=0,'metadata duration')
            need(item['http_status'] is None or type(item['http_status']) is int and 100<=item['http_status']<=599,'metadata HTTP status')
            need(item['error'] is None or type(item['error']) is str,'metadata error')
            if item['http_status']!=200 or item['error'] is not None:need(i==len(items)-1,'metadata continues after error')
        if len(items)<3:need(items[-1]['http_status']!=200 or items[-1]['error'] is not None,'metadata truncated')
        okay=metadata_ok(items,s['identity']);need(same(record['identity_ok'],okay),'metadata identity claim')
        return None if okay else 'metadata_identity_error'
    slot=next(x for x in p['slots'] if x['id']==sid);skip,request=expected_request(p,slot,raws)
    if skip:
        need(same(record,{'id':sid,'kind':'skip','reason':skip}),'conditional skip or selection mapping')
        return None
    need(set(record)=={'id','kind','http_status','error','elapsed_ns','request_sha256','response_sha256','response_b64'} and record['kind']=='call','call record schema')
    need(type(record['elapsed_ns']) is int and record['elapsed_ns']>=0,'duration')
    need(record['http_status'] is None or type(record['http_status']) is int and 100<=record['http_status']<=599,'HTTP status')
    need(record['error'] is None or type(record['error']) is str,'transport error')
    prefix='wire/'+sid+'/'
    allowed.update(prefix+x for x in ('request.wire.json','response.raw.json','dispatch.started.json'))
    need(fs[prefix+'request.wire.json']==request,'request drift: '+sid)
    need(len(request)<=s['request_utf8_byte_limit'],'request byte limit')
    raw=fs[prefix+'response.raw.json'];need(raw==b64(record['response_b64']),'response bytes')
    need(record['request_sha256']==digest(request) and record['response_sha256']==digest(raw),'wire hashes')
    need(same(load(fs[prefix+'dispatch.started.json']),{'id':sid,'request_sha256':digest(request),'plan_sha256':p['plan_sha256']}),'dispatch marker')
    stop=fatal(record,raw,s);raws[sid]=raw
    return stop


def verify_bundle(path):
    raw=Path(path).read_bytes();fs=archive(raw);manifest=load(fs['MANIFEST.json'])
    need(same(manifest,{'contract':'v074-evidence-r1','file_hashes':{n:digest(b) for n,b in fs.items() if n!='MANIFEST.json'}}),'manifest/layout')
    src=local_sources();s=load(src['data/protocol.json']);plan=load(fs['plan.json'])
    expected_keys={'contract','run_name','provenance','protocol','protocol_sha256','baseline_sha256','source_hashes','trials','slots','actions','plan_sha256'}
    need(set(plan)==expected_keys,'plan schema');need(plan['contract']=='v074-plan-r1','plan contract')
    need(re.fullmatch(r'v074_[A-Za-z0-9_-]{1,70}',plan['run_name']) is not None,'run name')
    need(plan['provenance'] in ('live','synthetic'),'provenance')
    need(same(plan['protocol'],s) and plan['protocol_sha256']==digest(src['data/protocol.json']),'frozen protocol')
    need(plan['baseline_sha256']==s['baseline_sha256']==digest(fs['baseline/v073_evidence.zip']),'baseline hash')
    need(plan['source_hashes']=={n:digest(b) for n,b in src.items()},'local source frozen hash')
    for n,b in src.items():need(fs.get('source/'+n)==b,'source snapshot '+n)
    ts,ss,aa=reconstruct_schedule(s)
    need(same(plan['trials'],ts) and same(plan['slots'],ss) and same(plan['actions'],aa),'frozen schedule')
    need(plan['plan_sha256']==digest(dump({k:v for k,v in plan.items() if k!='plan_sha256'})),'plan digest')
    runtime=load(fs['runtime.json']);need(set(runtime)=={'endpoint','provenance'} and runtime['provenance']==plan['provenance'],'runtime')
    ep=urllib.parse.urlsplit(runtime['endpoint'])
    need(ep.scheme=='http' and ep.hostname in ('localhost','127.0.0.1','::1') and not (ep.username or ep.password or ep.query or ep.fragment) and ep.path in ('','/'),'endpoint')
    st=load(fs['status.json']);need(set(st)=={'state','reason','completed_actions','started_actions','inference_calls','observed_calls','plan_sha256'},'status schema')
    need(st['state'] in ('complete','stopped','crashed') and st['plan_sha256']==plan['plan_sha256'],'state/plan')
    for k in ('completed_actions','started_actions','inference_calls','observed_calls'):need(type(st[k]) is int and st[k]>=0,'status integer')
    events=[load(line) for line in fs['records/events.jsonl'].splitlines()]
    need(len(events)==st['completed_actions']<=len(aa),'completed prefix')
    allowed={'MANIFEST.json','plan.json','runtime.json','status.json','records/events.jsonl','summary.json','summary.ko.md','baseline/v073_evidence.zip'}|{'source/'+n for n in src}
    records={};responses={};tip=plan['plan_sha256'];lastfatal=None
    for i,e in enumerate(events):
        action=aa[i];sid=action['id'];need(set(e)=={'action','record_sha256','previous_hash','event_hash'} and same(e['action'],action),'event action prefix')
        need(e['previous_hash']==tip and e['event_hash']==digest(dump({k:v for k,v in e.items() if k!='event_hash'})),'event chain')
        tip=e['event_hash'];name=f'records/{sid}.json';allowed.add(name)
        need(digest(fs[name])==e['record_sha256'],'record event hash')
        record=load(fs[name]);lastfatal=validate_record(fs,plan,action,record,responses,allowed);records[sid]=record
        if lastfatal:need(i==len(events)-1,'execution continued after fatal')
    starts=[n for n in fs if n.startswith('records/') and n.endswith('.started.json')]
    need(len(starts)==st['started_actions'] and len(events)<=len(starts)<=min(len(events)+1,len(aa)),'started prefix')
    for a in aa[:len(starts)]:
        name='records/'+a['id']+'.started.json';allowed.add(name)
        need(same(load(fs[name]),{'action':a,'plan_sha256':plan['plan_sha256']}),'action start marker')
    pending=None
    if len(starts)>len(events):
        need(st['state']=='crashed','pending requires crash')
        a=aa[len(events)];sid=a['id'];pending={'action':a,'request_saved':False,'dispatch_marked':False,'response_saved':False}
        recordname=f'records/{sid}.json'
        if recordname in fs:
            allowed.add(recordname);validate_record(fs,plan,a,load(fs[recordname]),dict(responses),allowed)
        elif a['kind']=='slot':
            slot=next(x for x in ss if x['id']==sid);skip,request=expected_request(plan,slot,responses)
            for ending in ('request.wire.json','dispatch.started.json','response.raw.json'):
                n=f'wire/{sid}/{ending}'
                if n in fs:allowed.add(n);need(skip is None,'skipped slot dispatched')
            requestname=f'wire/{sid}/request.wire.json';dispatchname=f'wire/{sid}/dispatch.started.json';responsename=f'wire/{sid}/response.raw.json'
            if requestname in fs:need(fs[requestname]==request,'pending request drift')
            if dispatchname in fs:
                need(requestname in fs,'dispatch without request');need(same(load(fs[dispatchname]),{'id':sid,'request_sha256':digest(request),'plan_sha256':plan['plan_sha256']}),'pending dispatch')
            if responsename in fs:need(dispatchname in fs,'response without dispatch')
        else:
            for j in range(3):
                rn=f'metadata/{sid}/{j}.request.json';on=f'metadata/{sid}/{j}.response.raw.json'
                if rn in fs:
                    allowed.add(rn);need(fs[rn]==(b'' if j<2 else dump({'model':s['model']})),'pending metadata request')
                    if j:need(f'metadata/{sid}/{j-1}.response.raw.json' in fs,'pending metadata sequence')
                if on in fs:allowed.add(on);need(rn in fs,'pending metadata response')
        pending.update(request_saved=f'wire/{sid}/request.wire.json' in fs,dispatch_marked=f'wire/{sid}/dispatch.started.json' in fs,response_saved=f'wire/{sid}/response.raw.json' in fs)
    dispatches=[n for n in fs if n.startswith('wire/') and n.endswith('/dispatch.started.json')]
    observations=[n for n in fs if n.startswith('wire/') and n.endswith('/response.raw.json')]
    need(st['inference_calls']==len(dispatches)<=s['max_inference_calls'],'inference dispatch count')
    need(st['observed_calls']==len(observations)<=len(dispatches),'observed count')
    if st['state']=='complete':need(len(events)==len(aa) and st['reason'] is None and pending is None and lastfatal is None,'complete state')
    elif st['state']=='stopped':need(lastfatal==st['reason'] and lastfatal is not None and pending is None,'fatal stopped state')
    else:need(st['reason']=='interrupted_action' and lastfatal is None,'crash status')
    summary=independent_summary(plan,records,responses,st['state'])
    need(same(load(fs['summary.json']),summary),'independent summary/semantics mismatch')
    need(fs['summary.ko.md']==independent_report(summary).encode('utf-8'),'Korean report mismatch')
    need(set(fs)==allowed,'unexpected/unaccounted files: '+repr(sorted(set(fs)^allowed)))
    return {'contract':'v074-independent-verify-r1','bundle_sha256':digest(raw),'plan_sha256':plan['plan_sha256'],
            'provenance':plan['provenance'],'state':st['state'],'completed_actions':st['completed_actions'],'started_actions':st['started_actions'],
            'inference_calls':len(dispatches),'observed_calls':len(observations),'pending_action':pending,
            'compared_groups':['manifest_and_source','frozen_schedule','conditional_skip_and_dispatch','native_identity','raw_requests_and_history','independent_graph_and_steps','target_D_and_trace','summary_and_korean_report'],
            'differences':[],'production_imports':False,
            'limitation':'번들 내부 일관성 검산이며 외부 실행 사실을 인증하지 않는다. 추론 수는 dispatch 시작 표지, 관측 수는 보존한 HTTP 응답 기준이다. 부분 실행의 미관측 답을 보완하지 않는다.',
            'verified':True}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('bundle',type=Path);a=p.parse_args(argv)
    try:print(json.dumps(verify_bundle(a.bundle),ensure_ascii=False,indent=2));return 0
    except (ValueError,OSError,KeyError,TypeError) as e:print('검산 거부: '+str(e),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
