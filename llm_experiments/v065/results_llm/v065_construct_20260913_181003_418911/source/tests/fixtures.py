"""합성 서버 전용 정답과 반례. 실행기/요청 생성기는 이 모듈을 import하지 않는다."""
from __future__ import annotations
import base64,contextlib,io,json,os,sys,tempfile,threading
from copy import deepcopy
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import common,design,run,report,verify

def baseline_path():
    name=os.environ.get('V065_BASELINE')
    if not name:raise FileNotFoundError('V065_BASELINE must name the exact v064 evidence ZIP')
    return Path(name)

def proof(problem,long=False):
    routes={'T02':(['r83'],['r21','r57','r04','r69']), 'E01_shared_fork':(['n52'],['n08','n91','n37']),
            'E02_two_vs_four':(['m18','m76'],['m33','m05','m84','m41'])}
    route=routes[problem['id']][int(long)];rs={r['id']:r for r in problem['rules']}
    nodes=[{'id':a,'atom':a,'rule':None,'parents':[]} for a in problem['facts']]
    for rid in route:
        r=rs[rid];nodes.append({'id':r['conclusion'],'atom':r['conclusion'],'rule':rid,'parents':r['premises'][:]})
    return {'nodes':nodes,'final_node_id':problem['goal']}

def envelope(payload,model='qwen3:4b-instruct'):
    return {'model':model,'message':{'role':'assistant','content':json.dumps(payload,ensure_ascii=False)},'done':True,'done_reason':'stop',
            'prompt_eval_count':100,'eval_count':50,'total_duration':1000000,'prompt_eval_cached_count':0}

@contextlib.contextmanager
def server(plan,mode='perfect'):
    state={'chats':0,'requests':[],'metadata':0};identity=plan['identity']
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def respond(self,obj,code=200):
            raw=common.wire(obj);self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        def do_GET(self):
            state['metadata']+=1
            if self.path=='/api/version':self.respond(identity['server']);return
            if self.path=='/api/tags':
                digest='0'*64 if mode=='metadata_error' or mode=='late_metadata' and state['chats']>=2 else identity['digest']
                self.respond({'models':[{'name':identity['model'],'digest':digest,'details':identity['details']}]});return
            self.respond({'error':'unknown'},404)
        def do_POST(self):
            req=common.load(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path=='/api/show':
                self.respond({k:identity[k] for k in ('details','template','parameters','model_info')});return
            if self.path!='/api/chat':self.respond({'error':'unknown'},404);return
            state['chats']+=1;state['requests'].append(req)
            if mode=='http_error' or mode=='late_http' and state['chats']==4:self.respond({'error':'synthetic'},503);return
            text=req['messages'][0]['content'];p=common.load(text.split('\n\nproblem: ')[-1]);rules=common.spec()['required_terminal_rules'][p['id']]
            long=("'"+rules['prescribed_long']+"'") in text
            actual_long=long if mode not in ('fixed','reversed','name_only') else (not long if mode=='reversed' else False)
            payload=proof(p,actual_long)
            if mode=='name_only':payload['nodes'][-1]['rule']=rules['prescribed_long'] if long else rules['prescribed_short']
            if mode=='extra':payload['nodes'].append({'id':'unused_fact','atom':p['facts'][0],'rule':None,'parents':[]})
            if mode=='reverse_nodes':payload['nodes'].reverse()
            if mode=='bad_parent':payload['nodes'][-1]['parents']=[]
            if mode=='unknown_rule':payload['nodes'][-1]['rule']='not_registered'
            obj=envelope(payload,identity['model'])
            if mode=='over_budget':obj['eval_count']=4097
            if mode=='wrong_model':obj['model']='wrong:4b'
            if mode=='parse_error':obj['message']['content']='{invalid'
            if mode=='length':obj['done_reason']='length'
            if mode=='missing_usage':obj.pop('eval_count');obj.pop('prompt_eval_count')
            self.respond(obj)
    http=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=http.serve_forever,kwargs={'poll_interval':.01},daemon=True);thread.start()
    try:yield 'http://127.0.0.1:'+str(http.server_port),state
    finally:http.shutdown();http.server_close();thread.join()

@contextlib.contextmanager
def executed(mode='perfect'):
    with tempfile.TemporaryDirectory(prefix='v065 한글 space ') as td:
        root=Path(td);plan=design.build_plan(baseline_path(),'v065_test','synthetic');p=root/'plan.json';common.save(p,plan)
        with server(plan,mode) as (endpoint,state),contextlib.redirect_stdout(io.StringIO()):result=run.execute(p,baseline_path(),root/'v065_test',endpoint)
        files=common.unzip(Path(result['evidence_zip']).read_bytes());summary=common.load(files['summary.json'])
        yield root,p,plan,files,summary,result,state

def resign(files):
    files={k:v for k,v in files.items() if k!='MANIFEST.json'}
    files['MANIFEST.json']=common.wire({'contract':'v065-evidence-r1','file_hashes':{k:common.sha(v) for k,v in files.items()}})
    return common.zip_bytes(files)

def rebuild_event_report(files,plan):
    files=dict(files);es=[common.load(x) for x in files['records/events.jsonl'].splitlines()];tip=plan['plan_sha256'];calls=[]
    for e in es:
        n='records/'+e['action']['id']+'.json';rec=common.load(files[n]);e['record_sha256']=common.sha(files[n]);e['previous_hash']=tip;e.pop('event_hash');e['event_hash']=common.sha(common.wire(e));tip=e['event_hash']
        if rec['kind']=='call':calls.append({k:v for k,v in rec.items() if k!='kind'})
    files['records/events.jsonl']=b''.join(common.wire(e)+b'\n' for e in es);r=report.summarize(plan,calls,common.load(files['status.json'])['state'])
    files['summary.json']=(json.dumps(r,ensure_ascii=False,indent=2)+'\n').encode();files['summary.ko.md']=report.render(r).encode()
    return files
