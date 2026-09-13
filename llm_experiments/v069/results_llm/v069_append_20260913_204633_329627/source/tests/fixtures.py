"""합성 HTTP 대역과 테스트 전용 정답 생성. 실제 모델 성능 증거로 사용하지 않는다."""
from pathlib import Path
from copy import deepcopy
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import contextlib,io,json,os,sys,tempfile,threading,base64
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import common,design,run,report,verify,measure,reference,stages

def baseline_path():
    value=os.environ.get('V069_BASELINE')
    if not value:raise FileNotFoundError('V069_BASELINE에 이번 실제 v068 evidence ZIP 경로가 필요합니다.')
    return Path(value)
ROUTES={'T02':(['r83'],['r21','r57','r04','r69']),'E01_shared_fork':(['n52'],['n08','n91','n37']),'E02_two_vs_four':(['m18','m76'],['m33','m05','m84','m41'])}

def proof(problem,long=False):
    ids=ROUTES[problem['id']][int(long)];rules={r['id']:r for r in problem['rules']}
    nodes=[{'id':'node_'+a,'atom':a,'rule':None,'parents':[]} for a in problem['facts']]
    for rid in ids:
        rule=rules[rid];nodes.append({'id':'node_'+rule['conclusion'],'atom':rule['conclusion'],'rule':rid,'parents':['node_'+a for a in rule['premises']]})
    return {'nodes':nodes,'final_node_id':'node_'+problem['goal']}

def envelope(payload,model):
    return {'model':model,'message':{'role':'assistant','content':json.dumps(payload,ensure_ascii=False)},'done':True,'done_reason':'stop',
        'prompt_eval_count':100,'eval_count':50,'total_duration':1000000,'prompt_eval_cached_count':0}

def synthetic_value(plan,slot,mode='perfect'):
    p=next(p for p in plan['protocol']['problems'] if p['id']==slot['problem_id']);long=slot['condition']=='reference_long'
    graph=proof(p,not long if mode=='reversed' else False if mode=='fixed_short' else long)
    fact_count=len(p['facts']);stage=slot['stage']
    if stage=='facts':payload={'nodes':deepcopy(graph['nodes'][:fact_count])}
    elif stage=='rule':payload={'node':deepcopy(graph['nodes'][min(fact_count+slot['rule_position'],len(graph['nodes'])-1)])}
    else:payload={'final_node_id':graph['final_node_id']}
    if stage=='facts':
        if mode=='extra_fact':payload['nodes'].append({'id':'unused','atom':p['facts'][0],'rule':None,'parents':[]})
        if mode=='missing_fact':payload['nodes'].pop()
        if mode=='all_in_facts':payload={'nodes':deepcopy(graph['nodes'])}
        if mode=='facts_extra_field':payload['final_node_id']='made_up'
        if mode=='wrong_fact':payload['nodes'][0]['atom']='WRONG'
        if mode=='duplicate_fact_id':payload['nodes'][-1]['id']=payload['nodes'][0]['id']
    if stage=='rule':
        n=payload['node']
        if mode=='bad_parent' or mode=='bad_early_rule' and slot['rule_position']==0:n['parents']=[]
        if mode=='wrong_atom':n['atom']='WRONG'
        if mode=='wrong_rule':n['rule']='unknown'
        if mode=='duplicate_rule_id':n['id']='node_'+p['facts'][0]
        if mode=='rule_extra_field':payload['final_node_id']='extra'
        if mode=='self_cycle':n['parents']=[n['id']]
        if mode=='stage_swap' and p['id']=='E01_shared_fork' and long and slot['rule_position'] in (0,1):payload={'node':deepcopy(graph['nodes'][3-slot['rule_position']])}
    if mode=='wrong_final' and stage=='final':payload['final_node_id']='missing'
    # 최종 graph는 유효하지만 facts/rule의 사전 계약을 어기는 반례.
    if mode=='cross_stage_smuggling' and p['id']=='E01_shared_fork' and long:
        if stage=='facts':payload={'nodes':[deepcopy(graph['nodes'][0]),deepcopy(graph['nodes'][2])]}
        if stage=='rule' and slot['rule_position']==0:payload={'node':deepcopy(graph['nodes'][1])}
    if mode=='invalid_schema':payload={'unknown':1}
    env=envelope(payload,plan['identity']['model'])
    if mode=='parse_error' or mode=='facts_parse_error' and stage=='facts' or mode=='rule_parse_error' and stage=='rule':env['message']['content']=' { broken JSON\n '
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
            raw=common.wire(value);self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        def do_GET(self):
            if self.path=='/api/version':self.send(identity['server']);return
            if self.path=='/api/tags':
                digest='0'*64 if mode=='bad_metadata' or mode=='late_metadata' and state['calls']>=9 else identity['digest']
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
    with tempfile.TemporaryDirectory(prefix='v069 한글 space ') as td:
        root=Path(td);p=design.build_plan(baseline_path(),'v069_fixture','synthetic');pp=root/'plan.json';common.save(pp,p)
        with server(p,mode) as (endpoint,state),contextlib.redirect_stdout(io.StringIO()):
            with patcher if patcher else contextlib.nullcontext():res=run.execute(pp,baseline_path(),root/'v069_fixture',endpoint)
        files=common.unzip(Path(res['evidence_zip']).read_bytes());summary=common.load(files['summary.json']);yield root,pp,p,files,summary,res,state

def resign(files):
    f={n:b for n,b in files.items() if n!='MANIFEST.json'};f['MANIFEST.json']=common.wire({'contract':'v069-evidence-r1','file_hashes':{n:common.sha(b) for n,b in f.items()}});return common.zip_bytes(f)

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
