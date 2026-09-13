"""시험용 로컬 HTTP 모델. 정답/반례 생성은 실제 실행기와 분리되어 있다."""
import base64,contextlib,io,json,os,sys,tempfile,threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import common,design,run,report,verify,measure
ROUTES={'T02':(['r83'],['r21','r57','r04','r69']),'E01_shared_fork':(['n52'],['n08','n91','n37']),'E02_two_vs_four':(['m18','m76'],['m33','m05','m84','m41'])}
def baseline_path():
    p=os.environ.get('V066_BASELINE')
    if not p:raise FileNotFoundError('V066_BASELINE must be actual v065 evidence')
    return Path(p)
def proof(problem,long=False,route=None):
    route=route if route is not None else ROUTES[problem['id']][int(long)];rs={r['id']:r for r in problem['rules']}
    ns=[{'id':a,'atom':a,'rule':None,'parents':[]} for a in problem['facts']]
    for rid in route:
        r=rs[rid];ns.append({'id':r['conclusion'],'atom':r['conclusion'],'rule':rid,'parents':r['premises'][:]})
    return {'nodes':ns,'final_node_id':problem['goal']}
def envelope(payload,model):return {'model':model,'message':{'role':'assistant','content':json.dumps(payload,ensure_ascii=False,indent=2)},'done':True,'done_reason':'stop','prompt_eval_count':100,'eval_count':50,'total_duration':1000000,'prompt_eval_cached_count':0}
@contextlib.contextmanager
def server(plan,mode='perfect'):
    state={'chats':0,'requests':[],'metadata':0};identity=plan['identity']
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def respond(self,value,code=200):
            raw=common.wire(value);self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        def do_GET(self):
            state['metadata']+=1
            if self.path=='/api/version':self.respond(identity['server']);return
            if self.path=='/api/tags':
                digest='0'*64 if mode=='metadata_error' or mode=='late_metadata' and state['chats']>=6 else identity['digest'];self.respond({'models':[{'name':identity['model'],'digest':digest,'details':identity['details']}]});return
            self.respond({'error':'unknown'},404)
        def do_POST(self):
            q=common.load(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path=='/api/show':self.respond({k:identity[k] for k in ('details','template','parameters','model_info')});return
            if self.path!='/api/chat':self.respond({'error':'unknown'},404);return
            state['chats']+=1;state['requests'].append(q);text=q['messages'][0]['content'];pr=json.JSONDecoder().raw_decode(text.split('\n\nproblem: ',1)[1])[0]
            stage='plan' if 'rule_ids' in q['format']['properties'] else ('construct' if '\nroute_plan_response: ' in text else 'direct')
            if mode=='http_error' or mode=='construct_http' and stage=='construct':self.respond({'error':'test transport'},503);return
            deep='최종 지지 깊이가 가장 큰 경로' in text;ids=ROUTES[pr['id']][int(deep)]
            wrong_plan=mode in ('bad_plan_correct_graph','wrong_direction_correct_graph','wrong_plan_preserved')
            if stage=='plan':
                picked=ROUTES[pr['id']][int(not deep)] if wrong_plan else ids
                if mode in ('same_path','direct_only'):picked=ROUTES[pr['id']][0]
                payload={'rule_ids':picked[:]}
                if mode=='bad_plan_correct_graph':payload={'rule_ids':['unknown_rule']}
            else:
                route=ids
                if stage=='direct' and mode in ('staged_only','same_path'):route=ROUTES[pr['id']][0]
                if stage=='construct':
                    transferred=json.loads(text.split('\nroute_plan_response: ',1)[1]);state.setdefault('transfers',[]).append(transferred)
                    if mode in ('same_path','wrong_plan_preserved','direct_only'):route=json.loads(transferred['content'])['rule_ids']
                payload=proof(pr,route=route)
                if mode=='bad_parent' or mode=='plan_only' and stage=='construct':payload['nodes'][-1]['parents']=[]
                if mode=='extra_nodes':payload['nodes'].append({'id':'unused','atom':pr['facts'][0],'rule':None,'parents':[]})
                if mode=='reverse_nodes':payload['nodes'].reverse()
            obj=envelope(payload,identity['model'])
            if mode=='parse_plan_correct_graph' and stage=='plan':obj['message']['content']='{잘못된 JSON\n그대로 보존'
            if mode=='missing_plan_content' and stage=='plan':obj['message'].pop('content')
            if mode=='parse_error':obj['message']['content']='{invalid'
            if mode=='length':obj['done_reason']='length'
            if mode=='wrong_model':obj['model']='wrong'
            if mode=='over_budget':obj['eval_count']=4097
            if mode=='missing_usage':obj.pop('eval_count');obj.pop('prompt_eval_count')
            self.respond(obj)
    http=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=http.serve_forever,kwargs={'poll_interval':.01},daemon=True);thread.start()
    try:yield 'http://127.0.0.1:'+str(http.server_port),state
    finally:http.shutdown();http.server_close();thread.join()
@contextlib.contextmanager
def executed(mode='perfect'):
    with tempfile.TemporaryDirectory(prefix='v066 한글 space ') as td:
        root=Path(td);plan=design.build_plan(baseline_path(),'v066_test','synthetic');p=root/'plan.json';common.save(p,plan)
        with server(plan,mode) as (endpoint,state),contextlib.redirect_stdout(io.StringIO()):result=run.execute(p,baseline_path(),root/'v066_test',endpoint)
        files=common.unzip(Path(result['evidence_zip']).read_bytes());s=common.load(files['summary.json']);yield root,p,plan,files,s,result,state

def resign(files):
    files={n:b for n,b in files.items() if n!='MANIFEST.json'};files['MANIFEST.json']=common.wire({'contract':'v066-evidence-r1','file_hashes':{n:common.sha(b) for n,b in files.items()}});return common.zip_bytes(files)
def rebuild_event_report(files,plan):
    files=dict(files);events=[common.load(line) for line in files['records/events.jsonl'].splitlines()];tip=plan['plan_sha256'];calls=[]
    for e in events:
        name='records/'+e['action']['id']+'.json';rec=common.load(files[name]);e['record_sha256']=common.sha(files[name]);e['previous_hash']=tip;e.pop('event_hash');e['event_hash']=common.sha(common.wire(e));tip=e['event_hash']
        if rec['kind']=='call':calls.append({k:v for k,v in rec.items() if k!='kind'})
    files['records/events.jsonl']=b''.join(common.wire(e)+b'\n' for e in events);s=report.summarize(plan,calls,common.load(files['status.json'])['state']);files['summary.json']=(json.dumps(s,ensure_ascii=False,indent=2)+'\n').encode();files['summary.ko.md']=report.render(s).encode();return files
