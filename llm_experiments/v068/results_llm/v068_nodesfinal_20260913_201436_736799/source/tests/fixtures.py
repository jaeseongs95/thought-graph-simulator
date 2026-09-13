"""합성 HTTP 대역. 실제 모델 실행·성능 증거가 아니다. 정답 생성은 이 테스트 파일 안에만 있다."""
from pathlib import Path
from copy import deepcopy
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import contextlib,io,json,os,sys,tempfile,threading,base64
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import common,design,run,report,verify,measure,reference,stages

def baseline_path():
    p=os.environ.get('V068_BASELINE')
    if not p:raise FileNotFoundError('V068_BASELINE에 이번 실제 v067 evidence ZIP 경로가 필요합니다.')
    return Path(p)
ROUTES={'T02':(['r83'],['r21','r57','r04','r69']),'E01_shared_fork':(['n52'],['n08','n91','n37']),'E02_two_vs_four':(['m18','m76'],['m33','m05','m84','m41'])}

def proof(problem,long=False):
    ids=ROUTES[problem['id']][int(long)];rules={r['id']:r for r in problem['rules']}
    nodes=[{'id':'node_'+a,'atom':a,'rule':None,'parents':[]} for a in problem['facts']]
    for rid in ids:
        r=rules[rid];nodes.append({'id':'node_'+r['conclusion'],'atom':r['conclusion'],'rule':rid,'parents':['node_'+a for a in r['premises']]})
    return {'nodes':nodes,'final_node_id':'node_'+problem['goal']}

def envelope(payload,model):
    return {'model':model,'message':{'role':'assistant','content':json.dumps(payload,ensure_ascii=False)},'done':True,'done_reason':'stop',
            'prompt_eval_count':100,'eval_count':50,'total_duration':1000000,'prompt_eval_cached_count':0}

def synthetic_value(plan,slot,mode='perfect'):
    p=next(p for p in plan['protocol']['problems'] if p['id']==slot['problem_id']);long=slot['condition']=='reference_long'
    graph=proof(p,not long if mode=='reversed' else False if mode=='fixed_short' else long)
    if mode in ('extra','nodes_extra'):graph['nodes'].append({'id':'unused','atom':p['facts'][0],'rule':None,'parents':[]})
    if mode in ('bad_parent','nodes_bad_parent'):graph['nodes'][-1]['parents']=[]
    if mode=='wrong_final':graph['final_node_id']='missing'
    if mode=='direct_missing_final' and slot['stage']=='direct':graph['final_node_id']='missing'
    if mode=='staged_missing_final' and slot['stage']=='final':graph['final_node_id']='missing'
    if mode=='reverse_nodes':graph['nodes'].reverse()
    if mode=='reorder_independent' and p['id']=='E01_shared_fork' and long:graph['nodes'][2],graph['nodes'][3]=graph['nodes'][3],graph['nodes'][2]
    if slot['stage']=='nodes':payload={'nodes':graph['nodes']}
    elif slot['stage']=='final':payload={'final_node_id':graph['final_node_id']}
    else:payload=graph
    if mode=='invalid_schema':payload={'unknown':1}
    if mode=='nodes_extra_field' and slot['stage']=='nodes':payload['final_node_id']='node_'+p['goal']
    env=envelope(payload,plan['identity']['model'])
    if mode=='parse_error' or mode=='nodes_parse_error' and slot['stage']=='nodes':env['message']['content']='{ broken JSON'
    if mode=='wrong_model':env['model']='wrong:tag'
    if mode=='over_budget':env['eval_count']=4097
    if mode=='missing_usage':env.pop('eval_count');env.pop('prompt_eval_count')
    if mode=='incomplete':env['done_reason']='length'
    return env

@contextlib.contextmanager
def server(plan,mode='perfect'):
    state={'calls':0,'requests':[]};identity=plan['identity']
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def send(self,value,status=200):
            b=common.wire(value);self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
        def do_GET(self):
            if self.path=='/api/version':self.send(identity['server']);return
            if self.path=='/api/tags':
                digest='0'*64 if mode=='bad_metadata' or mode=='late_metadata' and state['calls']>=6 else identity['digest']
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
    with tempfile.TemporaryDirectory(prefix='v068 한글 space ') as td:
        root=Path(td);p=design.build_plan(baseline_path(),'v068_fixture','synthetic');pp=root/'plan.json';common.save(pp,p)
        with server(p,mode) as (endpoint,state),contextlib.redirect_stdout(io.StringIO()):
            with patcher if patcher else contextlib.nullcontext():res=run.execute(pp,baseline_path(),root/'v068_fixture',endpoint)
        files=common.unzip(Path(res['evidence_zip']).read_bytes());summary=common.load(files['summary.json']);yield root,pp,p,files,summary,res,state

def resign(files):
    f={n:b for n,b in files.items() if n!='MANIFEST.json'};f['MANIFEST.json']=common.wire({'contract':'v068-evidence-r1','file_hashes':{n:common.sha(b) for n,b in f.items()}});return common.zip_bytes(f)

def rechains(files):
    f=dict(files);p=common.load(f['plan.json']);events=[common.load(line) for line in f['records/events.jsonl'].splitlines()];tip=p['plan_sha256']
    for e in events:
        e['record_sha256']=common.sha(f['records/'+e['action']['id']+'.json']);e['previous_hash']=tip;e.pop('event_hash');e['event_hash']=common.sha(common.wire(e));tip=e['event_hash']
    f['records/events.jsonl']=b''.join(common.wire(e)+b'\n' for e in events);return f

def records_for(plan,mode='perfect'):
    records=[];wire_files={}
    for slot in plan['slots']:
        raw=common.wire(synthetic_value(plan,slot,mode))
        parent=wire_files['wire/'+slot['parent_nodes_id']+'/response.raw.json'] if slot['stage']=='final' else None
        request=common.wire(design.request_for(plan,slot,parent))
        assert verify._request_for(plan,slot,wire_files)==request
        wire_files['wire/'+slot['id']+'/response.raw.json']=raw
        records.append({'id':slot['id'],'http_status':200,'error':None,'elapsed_ns':1,
           'request_sha256':common.sha(request),'response_sha256':common.sha(raw),'response_b64':base64.b64encode(raw).decode()})
    return records,wire_files
