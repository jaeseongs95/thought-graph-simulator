"""합성 HTTP 대역과 테스트 전용 정답 생성. 실제 모델 성능 증거로 사용하지 않는다."""
from pathlib import Path
from copy import deepcopy
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import contextlib,io,json,os,sys,tempfile,threading,base64
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import common,design,run,report,verify,measure,reference,selection

def baseline_path():
    value=os.environ.get('V070_BASELINE')
    if not value:raise FileNotFoundError('V070_BASELINE에 이번 실제 v069 evidence ZIP 경로가 필요합니다.')
    return Path(value)
def envelope(payload,model):
    return {'model':model,'message':{'role':'assistant','content':json.dumps(payload,ensure_ascii=False)},'done':True,'done_reason':'stop',
        'prompt_eval_count':100,'eval_count':50,'total_duration':1000000,'prompt_eval_cached_count':0}

def synthetic_value(plan,slot,mode='perfect'):
    spec=plan['protocol'];routes=spec['reference_plans'][slot['problem_id']];long=slot['condition']=='deep'
    candidates=[routes[spec['reference_conditions'][i]] for i in spec['candidate_orders'][slot['candidate_order_index']]]
    correct=routes['reference_long' if long else 'reference_short'];ids=correct[:]
    if mode=='reversed':ids=routes['reference_short' if long else 'reference_long'][:]
    if mode=='fixed_short':ids=routes['reference_short'][:]
    if mode=='first':ids=candidates[0][:]
    if mode=='last':ids=candidates[1][:]
    if mode=='by_count':ids=(max(candidates,key=len) if long else min(candidates,key=len))[:]
    if mode=='reverse_ids':ids=list(reversed(ids))
    if mode=='unknown':ids=['unregistered']
    if mode=='duplicate':ids=ids+ids[-1:]
    if mode=='empty':ids=[]
    if mode=='mixed':ids=candidates[0]+candidates[1]
    if mode=='nonmember_valid' and slot['problem_id']=='E01_shared_fork' and long:ids=['n91','n08','n37']
    payload={'rule_ids':ids}
    if mode=='extra_field':payload['reason']='extra'
    if mode=='bool_payload':payload={'rule_ids':True}
    if mode=='nested':payload={'rule_ids':[ids]}
    env=envelope(payload,plan['identity']['model'])
    if mode=='parse_error':env['message']['content']=' { broken JSON\n '
    if mode=='duplicate_json':env['message']['content']='{"rule_ids":["x"],"rule_ids":["r83"]}'
    if mode=='nonfinite':env['message']['content']='{"rule_ids":NaN}'
    if mode=='wrong_model':env['model']='wrong:tag'
    if mode=='over_budget':env['eval_count']=4097
    if mode=='missing_usage':env.pop('eval_count');env.pop('prompt_eval_count')
    if mode=='incomplete':env['done_reason']='length'
    if mode=='tool_calls':env['message']['tool_calls']=[{}]
    if mode=='bool_usage':env['eval_count']=True
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
                digest='0'*64 if mode=='bad_metadata' or mode=='late_metadata' and state['calls']>=4 else identity['digest']
                self.send({'models':[{'name':identity['model'],'digest':digest,'details':identity['details']}]});return
            self.send({},404)
        def do_POST(self):
            q=common.load(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path=='/api/show':self.send({k:identity[k] for k in ('details','template','parameters','model_info')});return
            if self.path!='/api/chat':self.send({},404);return
            slot=plan['slots'][state['calls']];state['calls']+=1;state['requests'].append(q)
            if mode=='http_error' or mode=='late_http' and state['calls']==4:self.send({'error':'synthetic'},503);return
            self.send(synthetic_value(plan,slot,mode))
    http=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=http.serve_forever,kwargs={'poll_interval':.01},daemon=True);thread.start()
    try:yield 'http://127.0.0.1:'+str(http.server_port),state
    finally:http.shutdown();http.server_close();thread.join()

@contextlib.contextmanager
def executed(mode='perfect',patcher=None):
    with tempfile.TemporaryDirectory(prefix='v070 한글 space ') as td:
        root=Path(td);p=design.build_plan(baseline_path(),'v070_fixture','synthetic');pp=root/'plan.json';common.save(pp,p)
        with server(p,mode) as (endpoint,state),contextlib.redirect_stdout(io.StringIO()):
            with patcher if patcher else contextlib.nullcontext():res=run.execute(pp,baseline_path(),root/'v070_fixture',endpoint)
        files=common.unzip(Path(res['evidence_zip']).read_bytes());summary=common.load(files['summary.json']);yield root,pp,p,files,summary,res,state

def resign(files):
    f={n:b for n,b in files.items() if n!='MANIFEST.json'};f['MANIFEST.json']=common.wire({'contract':'v070-evidence-r1','file_hashes':{n:common.sha(b) for n,b in f.items()}});return common.zip_bytes(f)

def rechains(files):
    f=dict(files);p=common.load(f['plan.json']);events=[common.load(line) for line in f['records/events.jsonl'].splitlines()];tip=p['plan_sha256']
    for e in events:
        e['record_sha256']=common.sha(f['records/'+e['action']['id']+'.json']);e['previous_hash']=tip;e.pop('event_hash');e['event_hash']=common.sha(common.wire(e));tip=e['event_hash']
    f['records/events.jsonl']=b''.join(common.wire(e)+b'\n' for e in events);return f

def records_for(plan,mode='perfect'):
    records=[];wire_files={}
    for slot in plan['slots']:
        raw=common.wire(synthetic_value(plan,slot,mode));hist={sid:wire_files['wire/'+sid+'/response.raw.json'] for sid in slot['history_ids']}
        request=common.wire(design.request_for(plan,slot,hist))
        assert verify._request_for(plan,slot,wire_files)==request
        wire_files['wire/'+slot['id']+'/request.wire.json']=request;wire_files['wire/'+slot['id']+'/response.raw.json']=raw
        records.append({'id':slot['id'],'http_status':200,'error':None,'elapsed_ns':1,
           'request_sha256':common.sha(request),'response_sha256':common.sha(raw),'response_b64':base64.b64encode(raw).decode()})
    return records,wire_files
