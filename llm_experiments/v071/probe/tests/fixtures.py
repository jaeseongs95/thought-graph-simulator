"""시험용 합성 대역. 이 정답 생성기는 실험 실행 경로에서 호출되지 않는다."""
from pathlib import Path
from copy import deepcopy
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import contextlib,io,json,os,sys,tempfile,threading,base64
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import common,design,run,report,verify,measure,reference,depths

def baseline_path():
    path=os.environ.get('V071_BASELINE')
    if not path:raise FileNotFoundError('V071_BASELINE에 실제 v070 evidence ZIP 경로를 지정하세요.')
    return Path(path)

def envelope(payload,model):
    return {'model':model,'message':{'role':'assistant','content':common.wire(payload).decode('utf-8')},'done':True,'done_reason':'stop',
        'prompt_eval_count':100,'eval_count':50,'total_duration':1000000,'prompt_eval_cached_count':0}

def synthetic_value(plan,slot,request,mode='perfect'):
    spec=plan['protocol'];pid=slot['problem_id'];order=spec['candidate_orders'][slot['candidate_order_index']]
    truth=[spec['depth_ranges'][pid][i] for i in order]
    data=common.load(request['messages'][0]['content'].split('\n\ninput: ')[1])
    if slot['stage']=='estimate':
        values=truth[:]
        if mode in ('reverse_depths','wrong_depth_correct_choice'):values=list(reversed(values))
        if mode=='offset_depths':values=[d+1 for d in values]
        if mode=='tie_depths':values=[2,2]
        if mode=='by_count':values=[len(c) for c in data['candidate_rule_ids']]
        payload={'depths':values}
        if mode=='bool_depth':payload['depths'][0]=True
        if mode=='float_depth':payload['depths'][0]=float(values[0])
        if mode=='negative_depth':payload['depths'][0]=-1
        if mode=='too_large_depth':payload['depths'][1]=65
        if mode=='extra_depth':payload['depths'].append(4)
    else:
        try:
            incoming=common.load(data['depth_report'])
            values=incoming['depths'] if depths.depth_format(incoming) else None
        except (UnicodeError,ValueError,TypeError):values=None
        if mode=='wrong_depth_correct_choice':values=truth
        if values is None or values[0]==values[1]:index=0
        elif slot['condition']=='shallow':index=0 if values[0]<values[1] else 1
        else:index=0 if values[0]>values[1] else 1
        if mode=='first':index=0
        if mode=='last':index=1
        if mode=='reverse_choice':index=1-index
        if mode=='oracle_wrong' and slot['arm']=='oracle_depth':index=1-index
        if mode=='model_wrong' and slot['arm']=='model_depth':index=1-index
        payload={'candidate_index':index}
        if mode=='bool_choice':payload['candidate_index']=False
        if mode=='float_choice':payload['candidate_index']=float(index)
        if mode=='out_of_range':payload['candidate_index']=2
    if mode=='extra_field':payload['extra']='not allowed'
    env=envelope(payload,plan['identity']['model'])
    if mode=='parse_error' or (mode=='estimate_parse_error' and slot['stage']=='estimate'):
        env['message']['content']=' \n {broken JSON\t '
    if mode=='duplicate_json':env['message']['content']='{"depths":[1,2],"depths":[2,1]}' if slot['stage']=='estimate' else '{"candidate_index":0,"candidate_index":1}'
    if mode=='nonfinite':env['message']['content']='{"depths":[NaN,2]}' if slot['stage']=='estimate' else '{"candidate_index":NaN}'
    if mode=='whitespace':env['message']['content']=' \n\t'+json.dumps(payload,ensure_ascii=False,indent=3)+' \t\n'
    if mode=='missing_content' and slot['stage']=='estimate':env['message'].pop('content')
    if mode=='wrong_model':env['model']='wrong:tag'
    if mode=='over_budget':env['eval_count']=spec['num_predict']+1
    if mode=='incomplete':env['done_reason']='length'
    if mode=='estimate_incomplete' and slot['stage']=='estimate':env['done_reason']='length'
    if mode=='missing_usage':env.pop('eval_count');env.pop('prompt_eval_count')
    if mode=='bool_usage':env['eval_count']=True
    if mode=='tool_calls':env['message']['tool_calls']=[{}]
    return env

@contextlib.contextmanager
def server(plan,mode='perfect'):
    state={'calls':0,'requests':[]};identity=plan['identity']
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def send(self,value,status=200):
            raw=common.wire(value);self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        def do_GET(self):
            if self.path=='/api/version':self.send(identity['server']);return
            if self.path=='/api/tags':
                digest='0'*64 if mode=='bad_metadata' or (mode=='late_metadata' and state['calls']>=5) else identity['digest']
                self.send({'models':[{'name':identity['model'],'digest':digest,'details':identity['details']}]});return
            self.send({},404)
        def do_POST(self):
            q=common.load(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path=='/api/show':self.send({k:identity[k] for k in ('details','template','parameters','model_info')});return
            if self.path!='/api/chat':self.send({},404);return
            slot=plan['slots'][state['calls']];state['calls']+=1;state['requests'].append(q)
            if mode=='http_error' or (mode=='late_http' and state['calls']==5):self.send({'error':'synthetic'},503);return
            self.send(synthetic_value(plan,slot,q,mode))
    http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=http.serve_forever,kwargs={'poll_interval':.01},daemon=True);thread.start()
    try:yield 'http://127.0.0.1:'+str(http.server_port),state
    finally:http.shutdown();http.server_close();thread.join()

@contextlib.contextmanager
def executed(mode='perfect',patcher=None):
    with tempfile.TemporaryDirectory(prefix='v071 한글 space ') as td:
        root=Path(td);p=design.build_plan(baseline_path(),'v071_fixture','synthetic');pp=root/'plan.json';common.save(pp,p)
        with server(p,mode) as (endpoint,state),contextlib.redirect_stdout(io.StringIO()):
            with patcher if patcher else contextlib.nullcontext():res=run.execute(pp,baseline_path(),root/'v071_fixture',endpoint)
        files=common.unzip(Path(res['evidence_zip']).read_bytes());summary=common.load(files['summary.json'])
        yield root,pp,p,files,summary,res,state

def resign(files):
    f={n:b for n,b in files.items() if n!='MANIFEST.json'}
    f['MANIFEST.json']=common.wire({'contract':'v071-evidence-r1','file_hashes':{n:common.sha(b) for n,b in f.items()}})
    return common.zip_bytes(f)

def rechains(files):
    f=dict(files);plan=common.load(f['plan.json']);events=[common.load(line) for line in f['records/events.jsonl'].splitlines()];tip=plan['plan_sha256']
    for e in events:
        e['record_sha256']=common.sha(f['records/'+e['action']['id']+'.json']);e['previous_hash']=tip
        e.pop('event_hash');e['event_hash']=common.sha(common.wire(e));tip=e['event_hash']
    f['records/events.jsonl']=b''.join(common.wire(e)+b'\n' for e in events)
    return f

def records_for(plan,mode='perfect'):
    records=[];files={}
    for slot in plan['slots']:
        history={sid:files['wire/'+sid+'/response.raw.json'] for sid in slot['history_ids']}
        request=design.request_for(plan,slot,history);raw=common.wire(synthetic_value(plan,slot,request,mode));wire=common.wire(request)
        assert verify._request_for(plan,slot,files)==wire
        files['wire/'+slot['id']+'/request.wire.json']=wire;files['wire/'+slot['id']+'/response.raw.json']=raw
        records.append({'id':slot['id'],'http_status':200,'error':None,'elapsed_ns':1,'request_sha256':common.sha(wire),
            'response_sha256':common.sha(raw),'response_b64':base64.b64encode(raw).decode()})
    return records,files
