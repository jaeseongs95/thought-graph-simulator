"""시험용 HTTP 응답. 실제 모델 요청은 생성기에 있는 참조 목록 외 정답을 받지 않는다."""
from pathlib import Path
from copy import deepcopy
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import contextlib,io,json,os,sys,tempfile,threading,base64
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import common,design,run,report,verify,measure,reference

def baseline_path():
    p=os.environ.get('V067_BASELINE')
    if not p:raise FileNotFoundError('V067_BASELINE must be the exact live v066 evidence ZIP')
    return Path(p)
ROUTES={'T02':(['r83'],['r21','r57','r04','r69']),'E01_shared_fork':(['n52'],['n08','n91','n37']),'E02_two_vs_four':(['m18','m76'],['m33','m05','m84','m41'])}

def proof(problem,long=False):
    ids=ROUTES[problem['id']][int(long)];rules={r['id']:r for r in problem['rules']};nodes=[{'id':a,'atom':a,'rule':None,'parents':[]} for a in problem['facts']]
    for rid in ids:
        r=rules[rid];nodes.append({'id':r['conclusion'],'atom':r['conclusion'],'rule':rid,'parents':r['premises'][:]})
    return {'nodes':nodes,'final_node_id':problem['goal']}

def envelope(payload,model):return {'model':model,'message':{'role':'assistant','content':json.dumps(payload,ensure_ascii=False)},'done':True,'done_reason':'stop','prompt_eval_count':100,'eval_count':50,'total_duration':1000000,'prompt_eval_cached_count':0}

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
                digest='0'*64 if mode=='bad_metadata' or mode=='late_metadata' and state['calls']>=2 else identity['digest']
                self.send({'models':[{'name':identity['model'],'digest':digest,'details':identity['details']}]});return
            self.send({},404)
        def do_POST(self):
            q=common.load(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path=='/api/show':self.send({k:identity[k] for k in ('details','template','parameters','model_info')});return
            if self.path!='/api/chat':self.send({},404);return
            state['calls']+=1;state['requests'].append(q)
            if mode=='http_error' or mode=='late_http' and state['calls']==4:self.send({'error':'synthetic'},503);return
            text=q['messages'][0]['content'];p=json.JSONDecoder().raw_decode(text.split('\n\nproblem: ',1)[1])[0]
            ref=common.load(text.split('\nprovided_route_plan: ',1)[1]);long=ref['rule_ids']==ROUTES[p['id']][1]
            actual=not long if mode=='reversed' else (False if mode in ('fixed_short','name_only') else long)
            payload=proof(p,actual)
            if mode=='extra':payload['nodes'].append({'id':'unused','atom':p['facts'][0],'rule':None,'parents':[]})
            if mode=='bad_parent':payload['nodes'][-1]['parents']=[]
            if mode=='wrong_final':payload['final_node_id']='missing'
            if mode=='name_only':payload['nodes'][-1]['rule']=ref['rule_ids'][-1]
            if mode=='reverse_nodes':payload['nodes'].reverse()
            if mode=='reorder_independent' and p['id']=='E01_shared_fork' and long:payload['nodes'][2],payload['nodes'][3]=payload['nodes'][3],payload['nodes'][2]
            if mode=='invalid_schema':payload={'rule_ids':ref['rule_ids']}
            obj=envelope(payload,identity['model'])
            if mode=='parse_error':obj['message']['content']='{ broken JSON'
            if mode=='wrong_model':obj['model']='wrong:tag'
            if mode=='over_budget':obj['eval_count']=4097
            if mode=='missing_usage':obj.pop('eval_count');obj.pop('prompt_eval_count')
            if mode=='incomplete':obj['done_reason']='length'
            self.send(obj)
    http=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=http.serve_forever,kwargs={'poll_interval':.01},daemon=True);thread.start()
    try:yield 'http://127.0.0.1:'+str(http.server_port),state
    finally:http.shutdown();http.server_close();thread.join()

@contextlib.contextmanager
def executed(mode='perfect',patcher=None):
    with tempfile.TemporaryDirectory(prefix='v067 한글 space ') as td:
        root=Path(td);p=design.build_plan(baseline_path(),'v067_fixture','synthetic');pp=root/'plan.json';common.save(pp,p)
        with server(p,mode) as (endpoint,state),contextlib.redirect_stdout(io.StringIO()):
            with patcher if patcher else contextlib.nullcontext():res=run.execute(pp,baseline_path(),root/'v067_fixture',endpoint)
        files=common.unzip(Path(res['evidence_zip']).read_bytes());summary=common.load(files['summary.json']);yield root,pp,p,files,summary,res,state

def resign(files):
    f={n:b for n,b in files.items() if n!='MANIFEST.json'};f['MANIFEST.json']=common.wire({'contract':'v067-evidence-r1','file_hashes':{n:common.sha(b) for n,b in f.items()}});return common.zip_bytes(f)

def rechains(files):
    f=dict(files);p=common.load(f['plan.json']);events=[common.load(line) for line in f['records/events.jsonl'].splitlines()];tip=p['plan_sha256']
    for e in events:
        e['record_sha256']=common.sha(f['records/'+e['action']['id']+'.json']);e['previous_hash']=tip;e.pop('event_hash');e['event_hash']=common.sha(common.wire(e));tip=e['event_hash']
    f['records/events.jsonl']=b''.join(common.wire(e)+b'\n' for e in events);return f
