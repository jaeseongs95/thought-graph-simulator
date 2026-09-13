"""실제 모델과 구분하여 표시하는 로컬 HTTP 시험 서버."""
from __future__ import annotations
import atexit,contextlib,copy,io,json,shutil,tempfile,threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from tests_v048.fixtures import MODEL,MODEL_DIGEST,SHOW,SERVER,envelope,build_v047
from criterion_probe_v050.contracts import wire,strict_json

@contextlib.contextmanager
def fake_server():
    class State:
        mode='perfect';requests=[];show_calls=0;metadata_boundary=0
    state=State();state.requests=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def send(self,body,status=200):
            raw=wire(body);self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        def do_GET(self):
            if self.path=='/api/version':self.send(SERVER)
            elif self.path=='/api/tags':self.send({'models':[{'name':MODEL,'model':MODEL,'digest':'x'*64 if state.mode=='before_identity_error' else MODEL_DIGEST,'details':SHOW['details']}]})
            else:self.send({'error':'not_found'},404)
        def do_POST(self):
            body=strict_json(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path=='/api/show':
                state.show_calls+=1;show=copy.deepcopy(SHOW)
                if state.mode=='runtime_drift' and state.show_calls>state.metadata_boundary+1:show['template']='changed'
                self.send(show);return
            if self.path!='/api/chat':self.send({'error':'not_found'},404);return
            state.requests.append(body)
            if state.mode=='http_error':self.send({'error':'synthetic failure'},503);return
            text=body['messages'][1]['content'];system=body['messages'][0]['content']
            if text.startswith('input: '):
                v=strict_json(text[7:]);a,b,e=v['a'],v['b'],v['expression']
                if e=='(NOT b)':value=not b
                elif e=='(a AND b)':value=a and b
                else:value=a and not b
                payload={'value':value}
                if state.mode=='wrong_not' and e=='(NOT b)':payload={'value':b}
                if state.mode=='invalid_not' and e=='(NOT b)':payload={'value':'false'}
                if state.mode=='wrong_proof' and e=='(a AND b)':payload={'value':not value}
            else:
                first,second=text.split('\nprobe: ',1);p=strict_json(first[len('problem: '):]);probe=strict_json(second)['atom']
                aa=probe==p['goal'];bb=probe in p['facts']
                payload={'observed':{'probe_atom':probe,'goal_atom':p['goal'],'facts':copy.deepcopy(p['facts'])},
                    'primitives':{'same_as_goal':aa,'in_facts':bb}}
                full='finding' in body['format']['properties']
                if state.mode=='wrong_extract' and not full:payload['primitives']['in_facts']=not bb
                if state.mode=='wrong_observed' and not full:payload['observed']['goal_atom']='WRONG'
                if full:
                    payload['finding']={'answer_only_accepts':aa,'proof_and_goal_accepts':aa and bb,'gap_detected':aa and not bb}
                    if state.mode=='original_false' and 'same_as_goal AND NOT in_facts' in system:payload['finding']['gap_detected']=False
                elif state.mode=='invalid_extract':payload['primitives']['in_facts']='false'
            env=envelope(content=wire(payload).decode())
            if state.mode=='wrong_model':env['model']='wrong-model'
            if state.mode=='missing_usage':env.pop('prompt_eval_count');env.pop('prompt_eval_cached_count')
            if state.mode=='truncated':env['done_reason']='length'
            self.send(env)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    t=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':0.01},daemon=True);t.start()
    try:yield state,f'http://127.0.0.1:{server.server_port}'
    finally:server.shutdown();server.server_close();t.join(timeout=2)

_shared=None

def shared():
    global _shared
    if _shared is not None:return _shared
    from paired_probe_v048.plan import prepare as p48
    from paired_probe_v048.runner import execute as e48
    from paired_probe_v048.__main__ import bundle as b48
    from paired_probe_v049.plan import prepare as p49
    from paired_probe_v049.runner import execute as e49
    from paired_probe_v049.evidence import bundle_run as b49
    from criterion_probe_v050.plan import prepare
    from criterion_probe_v050.runner import execute
    temp=tempfile.TemporaryDirectory(prefix='v050_fixture_');root=Path(temp.name)
    ctx=fake_server();state,endpoint=ctx.__enter__()
    with contextlib.redirect_stdout(io.StringIO()):
        pp,rr=build_v047(root,endpoint);p48(rr,root/'v48.plan',baseline_plan=pp);e48(root/'v48.plan',root/'v48.run');b48(root/'v48.plan',root/'v48.run',root/'v48.zip')
        p49(root/'v48.zip',root/'v49.plan');e49(root/'v49.plan',root/'v49.run');b49(root/'v49.plan',root/'v49.run',root/'v49.zip')
        plan=prepare(root/'v49.zip',root/'v50.plan');state.requests.clear()
        report=execute(root/'v50.plan',root/'v50.run')
    _shared={'root':root,'state':state,'endpoint':endpoint,'bundle':root/'v49.zip','plan':plan,'report':report}
    def cleanup():ctx.__exit__(None,None,None);temp.cleanup()
    atexit.register(cleanup);return _shared

@contextlib.contextmanager
def copied():
    f=shared()
    with tempfile.TemporaryDirectory(prefix='v050_copy_') as td:
        root=Path(td);p=root/'external.plan.json';run=root/'run'
        shutil.copyfile(f['root']/'v50.plan',p);shutil.copytree(f['root']/'v50.run',run)
        yield root,p,run,f

@contextlib.contextmanager
def executed(mode='perfect'):
    from criterion_probe_v050.plan import prepare
    from criterion_probe_v050.runner import execute
    f=shared();s=f['state'];s.mode=mode;s.requests.clear();s.metadata_boundary=s.show_calls
    try:
        with tempfile.TemporaryDirectory(prefix='v050_execute_') as td:
            root=Path(td);p=root/'external.plan.json';run=root/'run';plan=prepare(f['bundle'],p)
            with contextlib.redirect_stdout(io.StringIO()):r=execute(p,run)
            yield root,p,run,plan,r,s
    finally:s.mode='perfect'
