"""시험 전용 합성 HTTP. 정답 작성 함수는 실제 실행기에서 import하지 않는다."""
from pathlib import Path
from copy import deepcopy
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import contextlib,io,json,os,sys,tempfile,threading,base64
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import common,design,run,report,verify,previous

def baseline_path():
    value=os.environ.get('V073_BASELINE')
    if not value:raise FileNotFoundError('V073_BASELINE에 동결된 v072 evidence ZIP 경로를 지정하세요.')
    return Path(value)

def envelope(payload,model):
    return {'model':model,'message':{'role':'assistant','content':common.wire(payload).decode()},'done':True,'done_reason':'stop',
        'prompt_eval_count':100,'eval_count':8,'total_duration':1000000,'prompt_eval_cached_count':0}

def synthetic_value(plan,slot,request,mode='perfect'):
    data=common.load(request['messages'][0]['content'].split('\n\ninput: ')[1]);values=common.load(data['depth_report'])['depths']
    index=values.index(min(values) if slot['condition']=='shallow' else max(values))
    if mode=='first':index=0
    if mode=='last':index=1
    if mode=='wrong':index=1-index
    if mode=='only_space' and slot['format']=='compact':index=0
    if mode=='only_compact' and slot['format']=='comma_space':index=1
    if mode=='ascending_only' and slot['candidate_order_index']==1:index=1-index
    payload={'candidate_index':index}
    if mode=='bool_choice':payload['candidate_index']=False
    if mode=='float_choice':payload['candidate_index']=float(index)
    if mode=='out_of_range':payload['candidate_index']=2
    if mode=='negative':payload['candidate_index']=-1
    if mode=='extra_field':payload['explanation']='not allowed'
    env=envelope(payload,plan['identity']['model'])
    if mode=='parse_error':env['message']['content']=' \n {broken JSON\t '
    if mode=='duplicate_json':env['message']['content']='{"candidate_index":0,"candidate_index":1}'
    if mode=='nonfinite':env['message']['content']='{"candidate_index":NaN}'
    if mode=='array':env['message']['content']='[0]'
    if mode=='whitespace':env['message']['content']=' \n\t'+json.dumps(payload,indent=2)+' \t\n'
    if mode=='missing_content':env['message'].pop('content')
    if mode=='wrong_model':env['model']='wrong:tag'
    if mode=='over_budget':env['eval_count']=plan['protocol']['num_predict']+1
    if mode=='length':env['done_reason']='length'
    if mode=='not_done':env['done']=False
    if mode=='missing_usage':env.pop('eval_count');env.pop('prompt_eval_count')
    if mode=='bool_usage':env['eval_count']=True
    if mode=='tool_calls':env['message']['tool_calls']=[{}]
    return env

@contextlib.contextmanager
def server(plan,mode='perfect'):
    state={'calls':0,'requests':[],'http_paths':[]};identity=plan['identity'];native=deepcopy(identity['native'])
    if native['parameters'] is not None:native['parameters']='\n'.join(native['parameters'])
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def send(self,value,status=200):
            raw=common.wire(value);self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        def do_GET(self):
            state['http_paths'].append(self.path)
            if self.path=='/api/version':self.send(identity['server']);return
            if self.path=='/api/tags':
                digest='0'*64 if mode=='bad_metadata' or (mode=='late_metadata' and state['calls']>=4) else identity['digest']
                self.send({'models':[{'name':identity['model'],'digest':digest,'details':identity['tag_details']}]});return
            self.send({},404)
        def do_POST(self):
            state['http_paths'].append(self.path);q=common.load(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path=='/api/show':
                value=deepcopy(native)
                if mode=='bad_native' or (mode=='late_native' and state['calls']>=4):value['template']='changed-template'
                self.send(value);return
            if self.path!='/api/chat':self.send({},404);return
            slot=plan['slots'][state['calls']];state['calls']+=1;state['requests'].append(q)
            if mode=='http_error' or (mode=='late_http' and state['calls']==4):self.send({'error':'synthetic'},503);return
            self.send(synthetic_value(plan,slot,q,mode))
    http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=http.serve_forever,kwargs={'poll_interval':.01},daemon=True);thread.start()
    try:yield 'http://127.0.0.1:'+str(http.server_port),state
    finally:http.shutdown();http.server_close();thread.join()

@contextlib.contextmanager
def executed(mode='perfect',patcher=None):
    with tempfile.TemporaryDirectory(prefix='v073 한글 space ') as td:
        root=Path(td);p=design.build_plan(baseline_path(),'v073_fixture','synthetic');pp=root/'plan.json';common.save(pp,p)
        with server(p,mode) as (endpoint,state),contextlib.redirect_stdout(io.StringIO()):
            with patcher if patcher else contextlib.nullcontext():res=run.execute(pp,baseline_path(),root/'v073_fixture',endpoint)
        files=common.unzip(Path(res['evidence_zip']).read_bytes());summary=common.load(files['summary.json'])
        yield root,pp,p,files,summary,res,state

def resign(files):
    f={n:b for n,b in files.items() if n!='MANIFEST.json'}
    f['MANIFEST.json']=common.wire({'contract':'v073-evidence-r1','file_hashes':{n:common.sha(b) for n,b in f.items()}})
    return common.zip_bytes(f)

def rechains(files):
    f=dict(files);plan=common.load(f['plan.json']);events=[common.load(line) for line in f['records/events.jsonl'].splitlines()];tip=plan['plan_sha256']
    for e in events:
        e['record_sha256']=common.sha(f['records/'+e['action']['id']+'.json']);e['previous_hash']=tip
        e.pop('event_hash');e['event_hash']=common.sha(common.wire(e));tip=e['event_hash']
    f['records/events.jsonl']=b''.join(common.wire(e)+b'\n' for e in events);return f

def records_for(plan,mode='perfect'):
    records=[];files={}
    for slot in plan['slots']:
        request=design.request_for(plan,slot);raw=common.wire(synthetic_value(plan,slot,request,mode));wire=common.wire(request)
        assert verify._request_for(plan,slot,files)==wire
        files['wire/'+slot['id']+'/request.wire.json']=wire;files['wire/'+slot['id']+'/response.raw.json']=raw
        records.append({'id':slot['id'],'http_status':200,'error':None,'elapsed_ns':1,'request_sha256':common.sha(wire),
            'response_sha256':common.sha(raw),'response_b64':base64.b64encode(raw).decode()})
    return records,files
