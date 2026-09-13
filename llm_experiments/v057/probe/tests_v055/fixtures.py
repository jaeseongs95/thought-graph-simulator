"""시험 전용 두 모델 HTTP 서버. 실제 Qwen/Gemma 추론 성과로 사용하지 않는다."""
from __future__ import annotations
import atexit, contextlib, copy, importlib, io, json, shutil, tempfile, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tests_v048.fixtures import MODEL, MODEL_DIGEST, SHOW, SERVER, envelope, build_v047
from tests_v052.fixtures import explicit_answer, generic_trace, to_explicit
from tests_v051.fixtures import sample_trace
from tests_v054.fixtures import first_path
from model_probe_v055.contracts import wire, strict_json
from model_probe_v055.design import CANDIDATE
GSHOW={'details':{'family':'gemma3','parameter_size':'4.3B','quantization_level':'Q4_K_M'},
    'template':'SYNTHETIC GEMMA TEMPLATE','parameters':'temperature 1','model_info':{'general.architecture':'gemma3'}}
G_DIGEST='c'*64

def graph_answer(body,mode):
    if mode=='perfect':return explicit_answer(body,'perfect')
    problem=strict_json(body['messages'][1]['content'][9:])
    is_reference=body['model']==MODEL
    if mode in ('first_branch','candidate_first','reference_first'):
        if mode=='first_branch' or (mode=='candidate_first')!=is_reference:return first_path(problem)
        return explicit_answer(body,'perfect')
    if mode=='same_depth':return explicit_answer(body,'ignore_roles')
    if mode=='inverse':
        direction='shallow' if '최종 지지 깊이가 가장 큰 경로' in body['messages'][0]['content'] else 'deep'
        p=to_explicit(generic_trace(problem,'instance',direction,0));return {k:p[k] for k in ('nodes','final_node_id')}
    if mode=='v054_vs_perfect':
        if not is_reference:return explicit_answer(body,'perfect')
        p=first_path(problem)
        if problem['id']=='T02' and problem['rules'][0]['id']=='r21':
            p['nodes'][-1]['parents']=[n['id'] for n in p['nodes'] if n['rule'] is None]
        return p
    if mode=='invalid_rule':
        p=explicit_answer(body,'perfect');p['nodes'][-1]['rule']='unknown';return p
    if mode=='duplicate_node':
        p=explicit_answer(body,'perfect');p['nodes'].append(copy.deepcopy(p['nodes'][0]));return p
    if mode in ('bad_final','invalid_json'):return explicit_answer(body,mode)
    return explicit_answer(body,'perfect')

@contextlib.contextmanager
def fake_server():
    class State:
        mode='perfect';show_calls=0;metadata_boundary=0
        def __init__(self):self.requests=[];self.http_requests=[]
    state=State()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def sendraw(self,raw,status=200):
            self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        def send(self,body,status=200):self.sendraw(wire(body),status)
        def do_GET(self):
            state.http_requests.append(('GET',self.path))
            if self.path=='/api/version':
                if state.mode=='metadata_http':self.send({'error':'synthetic metadata unavailable'},503)
                elif state.mode=='metadata_json':self.sendraw(b'{')
                else:self.send(SERVER)
            elif self.path=='/api/tags':
                g={'name':CANDIDATE,'model':CANDIDATE,'digest':MODEL_DIGEST if state.mode=='same_digest' else G_DIGEST,'details':GSHOW['details']}
                q={'name':MODEL,'model':MODEL,'digest':'e'*64 if state.mode=='before_identity' else MODEL_DIGEST,'details':SHOW['details']}
                self.send({'models':[q] if state.mode=='missing_candidate' else [q,g]})
            else:self.send({'error':'unknown endpoint'},404)
        def do_POST(self):
            state.http_requests.append(('POST',self.path))
            body=strict_json(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path=='/api/show':
                state.show_calls+=1;show=copy.deepcopy(GSHOW if body['model']==CANDIDATE else SHOW)
                if state.mode=='drift' and state.show_calls>state.metadata_boundary+1:show['template']='CHANGED AFTER BLOCK'
                if state.mode=='bad_family' and body['model']==CANDIDATE:show['details']['family']='qwen3'
                if state.mode=='bad_quant' and body['model']==CANDIDATE:show['details']['quantization_level']='Q8_0'
                if state.mode=='bad_size' and body['model']==CANDIDATE:show['details']['parameter_size']='12.0B'
                self.send(show);return
            if self.path!='/api/chat':self.send({'error':'unknown endpoint'},404);return
            state.requests.append(body)
            if state.mode=='http_error' or (state.mode=='candidate_http' and body['model']==CANDIDATE):self.send({'error':'synthetic failure'},503);return
            text=body['messages'][1]['content'];system=body['messages'][0]['content'];props=body['format'].get('properties',{})
            if 'final_node_id' in props:
                payload=graph_answer(body,state.mode) if set(props)=={'nodes','final_node_id'} else explicit_answer(body,'perfect')
            elif 'nodes' in props:
                aa='schema' if '각 노드의 views는 보편' in system else 'instance'
                dd='deep' if '최종 지지 깊이가 가장 큰 경로' in system else 'shallow'
                mm=2 if '평가 기준을 대상으로 acceptance_criterion/counterexample_probe 검토 하나만' in system else (1 if '최종 증명을 대상으로 argument/support_replay 검토 하나만' in system else 0)
                payload=sample_trace(aa,dd,mm)
            elif text.startswith('input: '):
                v=strict_json(text[7:]);a,b,e=v['a'],v['b'],v['expression']
                payload={'value':not b if e=='(NOT b)' else (a and b if e=='(a AND b)' else a and not b)}
            else:
                first,second=text.split('\nprobe: ',1);p=strict_json(first[9:]);atom=strict_json(second)['atom'];a=atom==p['goal'];b=atom in p['facts']
                payload={'observed':{'probe_atom':atom,'goal_atom':p['goal'],'facts':copy.deepcopy(p['facts'])},'primitives':{'same_as_goal':a,'in_facts':b}}
                if 'finding' in props:payload['finding']={'answer_only_accepts':a,'proof_and_goal_accepts':a and b,'gap_detected':a and not b}
            env=envelope(content=wire(payload).decode(),model=body['model'])
            if state.mode=='wrong_model':env['model']='wrong:tag'
            if state.mode=='truncated':env['done_reason']='length'
            if state.mode=='syntax_error':env['message']['content']='{'
            if state.mode=='missing_usage':env.pop('prompt_eval_count');env.pop('prompt_eval_cached_count')
            self.send(env)
    http=ThreadingHTTPServer(('127.0.0.1',0),Handler);t=threading.Thread(target=http.serve_forever,kwargs={'poll_interval':0.01},daemon=True);t.start()
    try:yield state,f'http://127.0.0.1:{http.server_port}'
    finally:http.shutdown();http.server_close();t.join(timeout=2)

_cached=None

def shared():
    global _cached
    if _cached is not None:return _cached
    temp=tempfile.TemporaryDirectory(prefix='v055_fixture_');root=Path(temp.name);context=fake_server();state,endpoint=context.__enter__()
    from paired_probe_v048.plan import prepare as p48
    from paired_probe_v048.runner import execute as e48
    from paired_probe_v048.__main__ import bundle as b48
    from model_probe_v055.metadata import capture
    from model_probe_v055.plan import prepare
    from model_probe_v055.runner import execute
    with contextlib.redirect_stdout(io.StringIO()):
        pp,rr=build_v047(root,endpoint)
        p48(rr,root/'v48.plan',baseline_plan=pp);e48(root/'v48.plan',root/'v48.run');b48(root/'v48.plan',root/'v48.run',root/'v48.zip')
        for number,name in [(49,'paired_probe_v049'),(50,'criterion_probe_v050'),(51,'adm_pilot_v051'),(52,'adm_diagnostic_v052'),(53,'depth_probe_v053'),(54,'order_probe_v054')]:
            p=importlib.import_module(name+'.plan').prepare;e=importlib.import_module(name+'.runner').execute;b=importlib.import_module(name+'.evidence').bundle_run
            p(root/f'v{number-1}.zip',root/f'v{number}.plan');e(root/f'v{number}.plan',root/f'v{number}.run');b(root/f'v{number}.plan',root/f'v{number}.run',root/f'v{number}.zip')
        state.requests.clear();cap=capture(root/'v54.zip',root/'capture')
        assert len(state.requests)==0
        plan=prepare(root/'v54.zip',root/'capture/capture.json',root/'v55.plan')
        state.metadata_boundary=state.show_calls;report=execute(root/'v55.plan',root/'v55.run')
    _cached={'root':root,'state':state,'endpoint':endpoint,'plan':plan,'report':report,'bundle':root/'v54.zip','capture':cap}
    def cleanup():context.__exit__(None,None,None);temp.cleanup()
    atexit.register(cleanup);return _cached

@contextlib.contextmanager
def copied():
    base=shared()
    with tempfile.TemporaryDirectory(prefix='v055_copy_') as td:
        root=Path(td);p=root/'external.plan.json';r=root/'run'
        shutil.copyfile(base['root']/'v55.plan',p);shutil.copytree(base['root']/'v55.run',r)
        yield root,p,r,base

@contextlib.contextmanager
def executed(mode):
    from model_probe_v055.runner import execute
    base=shared();state=base['state'];state.mode=mode;state.requests.clear();state.http_requests.clear();state.metadata_boundary=state.show_calls
    try:
        with tempfile.TemporaryDirectory(prefix='v055_exec_') as td:
            root=Path(td);p=root/'external.plan.json';run=root/'run';shutil.copyfile(base['root']/'v55.plan',p)
            with contextlib.redirect_stdout(io.StringIO()):report=execute(p,run)
            yield root,p,run,report,state
    finally:state.mode='perfect'
