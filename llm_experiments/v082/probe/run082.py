"""v082 로컬 실행기. 조건부 미실행을 기록하고 잘못된 중간값은 보정하지 않는다."""
from __future__ import annotations
import argparse, base64, json, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path
import core082 as common, design082 as design


def endpoint_ok(value):
    p=urllib.parse.urlsplit(value)
    if (p.scheme!='http' or p.hostname not in ('localhost','127.0.0.1','::1') or p.username or p.password
        or p.query or p.fragment or p.path not in ('','/')):raise ValueError('명시적 로컬 HTTP Ollama 주소만 허용')
    return value.rstrip('/')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):return None


def exchange(endpoint,path,body,timeout):
    request=urllib.request.Request(endpoint+path,data=body,headers={'Content-Type':'application/json'},method='GET' if body is None else 'POST')
    start=time.perf_counter_ns()
    try:
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
        with opener.open(request,timeout=timeout) as r:code=r.status;raw=r.read(1024**2+1)
        return code,raw,('response_size_limit' if len(raw)>1024**2 else None),time.perf_counter_ns()-start
    except urllib.error.HTTPError as e:return e.code,e.read(1024**2+1),None,time.perf_counter_ns()-start
    except (OSError,urllib.error.URLError) as e:return None,b'',type(e).__name__,time.perf_counter_ns()-start


def identity_matches(items,expected):
    try:
        if len(items)!=3 or any(i['http_status']!=200 or i['error'] is not None for i in items):return False
        version,tags,show=[common.load(base64.b64decode(i['response_b64'],validate=True)) for i in items]
        matches=[x for x in tags['models'] if x.get('name')==expected['model'] or x.get('model')==expected['model']]
        if len(matches)!=1:return False
        if not common.exact(version,expected['server']) or matches[0]['digest']!=expected['digest'] or not common.exact(matches[0]['details'],expected['tag_details']):return False
        native={k:show.get(k) for k in ('template','system','parameters','model_info','details','capabilities','projector_info')}
        if native['parameters'] is not None:
            if not isinstance(native['parameters'],str):return False
            native['parameters']=sorted(native['parameters'].split('\n'))
        return common.exact(native,expected['native'])
    except (ValueError,KeyError,TypeError,UnicodeError):return False


def metadata(plan,action,endpoint,out):
    items=[]
    for index,path in enumerate(('/api/version','/api/tags','/api/show')):
        body=common.wire({'model':plan['protocol']['model']}) if index==2 else None
        prefix=out/'metadata'/action['id']/str(index)
        common.write(Path(str(prefix)+'.request.json'),body or b'')
        code,raw,error,elapsed=exchange(endpoint,path,body,plan['protocol']['timeout_seconds'])
        common.write(Path(str(prefix)+'.response.raw.json'),raw)
        items.append({'path':path,'http_status':code,'error':error,'elapsed_ns':elapsed,
                      'request_b64':None if body is None else base64.b64encode(body).decode(),
                      'response_b64':base64.b64encode(raw).decode()})
        if code!=200 or error is not None:break
    return {'id':action['id'],'kind':'metadata','items':items,'identity_ok':identity_matches(items,plan['protocol']['identity'])}


def fatal_call(record,raw,spec):
    if record['error'] is not None:return 'transport_error'
    if record['http_status']!=200:return 'http_error'
    try:outer=common.load(raw)
    except (ValueError,UnicodeError):return None
    if not isinstance(outer,dict) or outer.get('model')!=spec['model']:return 'identity_error'
    if type(outer.get('eval_count')) is int and outer['eval_count']>spec['num_predict']:return 'generation_budget_exceeded'
    return None


def put_once_or_equal(path,raw):
    if path.exists():
        if path.read_bytes()!=raw:raise FileExistsError('기존 산출물과 다름: '+str(path))
    else:common.write(path,raw)


def finalize(out):
    import report082 as report
    from verify082 import verify_bundle
    plan=common.load((out/'plan.json').read_bytes())
    if not common.exact(plan['source_hashes'],common.source_hashes()):raise ValueError('실행 소스와 동결 소스 불일치')
    events=[common.load(x) for x in (out/'records/events.jsonl').read_bytes().splitlines()]
    records={e['action']['id']:common.load((out/'records'/(e['action']['id']+'.json')).read_bytes()) for e in events}
    responses={i:(out/'wire'/i/'response.raw.json').read_bytes() for i,r in records.items() if r['kind']=='call'}
    started=list((out/'records').glob('*.started.json'));dispatch=list((out/'wire').glob('*/dispatch.started.json'))
    if not (out/'status.json').exists():
        common.save(out/'status.json',{'state':'crashed','reason':'interrupted_action','completed_actions':len(events),
            'started_actions':len(started),'inference_calls':len(dispatch),'observed_calls':len(list((out/'wire').glob('*/response.raw.json'))),'plan_sha256':plan['plan_sha256']})
    status=common.load((out/'status.json').read_bytes())
    s=report.summarize(plan,records,responses,status['state'])
    put_once_or_equal(out/'summary.json',common.wire(s))
    put_once_or_equal(out/'summary.ko.md',report.render(s).encode('utf-8'))
    files={}
    for p in sorted(out.rglob('*')):
        if p.is_symlink():raise ValueError('run symlink')
        if p.is_file():files[p.relative_to(out).as_posix()]=p.read_bytes()
    files['MANIFEST.json']=common.wire({'contract':'v082-evidence-r1','file_hashes':{n:common.sha(b) for n,b in files.items()}})
    bundle=out.parent/(out.name+'_evidence.zip');put_once_or_equal(bundle,common.zip_bytes(files))
    receipt=verify_bundle(bundle)
    target=out.parent/(out.name+'_independent.json');put_once_or_equal(target,common.wire(receipt))
    return {'state':status['state'],'evidence_zip':str(bundle.resolve()),'independent_json':str(target.resolve()),
            'inference_calls':status['inference_calls'],'observed_calls':status['observed_calls']}


def execute(plan_path,baseline_path,out,endpoint):
    endpoint=endpoint_ok(endpoint);plan=common.load(plan_path.read_bytes())
    expected=design.make_plan(baseline_path,plan['run_name'],plan['provenance'],audit_previous=False)
    if not common.exact(plan,expected):raise ValueError('plan/source/baseline mismatch')
    if out.exists() or out.name!=plan['run_name']:raise FileExistsError('기존 결과 또는 RunName 불일치')
    common.write(out.parent/'frozen_batch.started.json',common.wire({'run_name':plan['run_name'],'plan_sha256':plan['plan_sha256'],'automatic_retry':False}))
    common.write(plan_path.with_name(plan_path.name+'.started'),common.wire({'plan_sha256':plan['plan_sha256']}))
    out.mkdir(parents=True);common.save(out/'plan.json',plan)
    common.save(out/'runtime.json',{'endpoint':endpoint,'provenance':plan['provenance']})
    common.write(out/'baseline/v081_evidence.zip',baseline_path.read_bytes())
    for n,b in common.sources().items():common.write(out/'source'/n,b)
    common.write(out/'records/events.jsonl',b'')
    responses={};tip=plan['plan_sha256'];completed=started=calls=observed=0;state='complete';reason=None
    try:
        for action in plan['actions']:
            common.write(out/'records'/(action['id']+'.started.json'),common.wire({'action':action,'plan_sha256':plan['plan_sha256']}));started+=1
            failure=None
            if action['kind']=='metadata':
                record=metadata(plan,action,endpoint,out)
                if not record['identity_ok']:failure='metadata_identity_error'
            else:
                slot=next(s for s in plan['slots'] if s['id']==action['id'])
                skip=design.disposition(plan,slot,responses)
                if skip:
                    record={'id':slot['id'],'kind':'skip','reason':skip}
                else:
                    request=common.wire(design.request_for(plan,slot,responses));prefix=out/'wire'/slot['id']
                    common.write(prefix/'request.wire.json',request)
                    if calls>=plan['protocol']['max_inference_calls']:raise ValueError('inference budget')
                    common.write(prefix/'dispatch.started.json',common.wire({'id':slot['id'],'request_sha256':common.sha(request),'plan_sha256':plan['plan_sha256']}))
                    calls+=1
                    code,raw,error,elapsed=exchange(endpoint,'/api/chat',request,plan['protocol']['timeout_seconds'])
                    common.write(prefix/'response.raw.json',raw);responses[slot['id']]=raw;observed+=1
                    record={'id':slot['id'],'kind':'call','http_status':code,'error':error,'elapsed_ns':elapsed,
                            'request_sha256':common.sha(request),'response_sha256':common.sha(raw),'response_b64':base64.b64encode(raw).decode()}
                    failure=fatal_call(record,raw,dict(plan['protocol'],num_predict=common.load(request)['options']['num_predict']))
            rraw=common.wire(record);common.write(out/'records'/(action['id']+'.json'),rraw)
            event={'action':action,'record_sha256':common.sha(rraw),'previous_hash':tip}
            event['event_hash']=common.sha(common.wire(event));tip=event['event_hash']
            with (out/'records/events.jsonl').open('ab') as f:f.write(common.wire(event)+b'\n');f.flush()
            completed+=1
            print(f"{completed}/{len(plan['actions'])} {action['id']}: {record['kind']} / 추론 {calls}",flush=True)
            if failure:state='stopped';reason=failure;break
    except BaseException as exc:
        state='crashed';reason='interrupted_action'
        print('중단: '+type(exc).__name__+': '+str(exc),file=sys.stderr,flush=True)
    common.save(out/'status.json',{'state':state,'reason':reason,
         'completed_actions':len((out/'records/events.jsonl').read_bytes().splitlines()),
         'started_actions':len(list((out/'records').glob('*.started.json'))),
         'inference_calls':len(list((out/'wire').glob('*/dispatch.started.json'))),
         'observed_calls':len(list((out/'wire').glob('*/response.raw.json'))),'plan_sha256':plan['plan_sha256']})
    return finalize(out)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);cmd=p.add_subparsers(dest='command',required=True)
    a=cmd.add_parser('prepare');a.add_argument('--baseline',type=Path,required=True);a.add_argument('--run-name',required=True);a.add_argument('--out',type=Path,required=True);a.add_argument('--synthetic',action='store_true')
    a=cmd.add_parser('execute');a.add_argument('--baseline',type=Path,required=True);a.add_argument('--plan',type=Path,required=True);a.add_argument('--out',type=Path,required=True);a.add_argument('--endpoint',default='http://127.0.0.1:11434')
    a=cmd.add_parser('finalize');a.add_argument('--run',type=Path,required=True)
    args=p.parse_args(argv)
    try:
        if args.command=='prepare':
            plan=design.make_plan(args.baseline,args.run_name,'synthetic' if args.synthetic else 'live');common.save(args.out,plan)
            result={'prepared':str(args.out.resolve()),'actual_model_inference':False,'max_inference_calls':plan['protocol']['max_inference_calls'],'plan_sha256':plan['plan_sha256']}
        elif args.command=='execute':
            if common.load(args.plan.read_bytes()).get('provenance') != 'live':
                raise ValueError('합성 계획은 실제 서버 CLI 실행에 사용할 수 없습니다. 합성 실행은 tests의 mock/시험 HTTP 서버에서만 수행합니다.')
            result=execute(args.plan,args.baseline,args.out,args.endpoint)
        else:result=finalize(args.run)
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if result.get('state','complete')=='complete' else 2
    except (OSError,ValueError,TypeError,KeyError) as e:print(type(e).__name__+': '+str(e),file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
