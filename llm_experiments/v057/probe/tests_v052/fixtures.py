"""실제 모델과 구분하여 표시하는 로컬 HTTP 시험 서버."""
from __future__ import annotations
import atexit,contextlib,copy,io,json,shutil,tempfile,threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from tests_v048.fixtures import MODEL,MODEL_DIGEST,SHOW,SERVER,envelope,build_v047
from criterion_probe_v050.contracts import wire,strict_json
from tests_v051.fixtures import sample_trace,bare_goal_trace

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
            if 'final_node_id' in body['format'].get('properties',{}):
                payload=explicit_answer(body,state.mode)
            elif 'nodes' in body['format'].get('properties',{}):
                a='schema' if '각 노드의 views는 보편' in system else 'instance'
                d='deep' if '최종 지지 깊이가 가장 큰 경로' in system else 'shallow'
                m=2 if '평가 기준을 대상으로 acceptance_criterion/counterexample_probe 검토 하나만' in system else (1 if '최종 증명을 대상으로 argument/support_replay 검토 하나만' in system else 0)
                payload=sample_trace(a,d,m)
                if state.mode=='ignore_roles':payload=sample_trace('instance','shallow',0)
                if state.mode=='wrong_m2' and m==2:payload['reviews'][0]['finding']['gap_detected']=False
                if state.mode=='invalid_m2_format' and m==2:payload['reviews'][0]['finding']['gap_detected']='false'
                if state.mode=='false_goal_fact':payload=bare_goal_trace()
                if state.mode=='wrong_schema' and a=='schema':payload['views'][payload['final']]['assumptions'].append({'if':[],'then':payload['views'][payload['final']]['conclusion']})
                if state.mode=='invalid_json':payload={'unknown':'synthetic malformed output'}
            elif text.startswith('input: '):
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





def generic_trace(problem,a='instance',d='shallow',m=0):
    # 시험 서버만 사용하는 생성기. 실행기에는 import되지 않는다.
    nodes=[];seen={}
    def plans(atom,visited):
        if atom in visited:return []
        choices=[(0,None,[])] if atom in problem['facts'] else []
        import itertools
        for rule in problem['rules']:
            if rule['conclusion']!=atom:continue
            for children in itertools.product(*(plans(v,visited|{atom}) for v in rule['premises'])):
                choices.append((1+max(x[0] for x in children),rule,list(children)))
        return choices
    choices=plans(problem['goal'],set());chosen=sorted(choices,key=lambda x:x[0])[0 if d=='shallow' else -1]
    def emit(atom,p):
        key=str((atom,p))
        if key in seen:return seen[key]
        rid=p[1];parents=[] if rid is None else [emit(v,child) for v,child in zip(rid['premises'],p[2])]
        nid='n'+str(len(nodes));nodes.append({'id':nid,'atom':atom,'rule':rid['id'] if rid else None,'parents':parents});seen[key]=nid;return nid
    final=emit(problem['goal'],chosen);views={};lookup={n['id']:n for n in nodes};closure={}
    for n in nodes:
        key=n['id'];closure[key]={key}.union(*(closure[x] for x in n['parents']))
        if a=='instance':views[key]={'kind':'instance','atom':n['atom']};continue
        used=[q for q in nodes if q['id'] in closure[key]];atoms=sorted({q['atom'] for q in used});binding={'Q'+str(i):v for i,v in enumerate(atoms)};rev={v:k for k,v in binding.items()}
        views[key]={'kind':'universal_schema','quantifier':'forall_boolean_valuations','binding':binding,
            'assumptions':[{'if':[rev[lookup[x]['atom']] for x in q['parents']],'then':rev[q['atom']]} for q in used],'conclusion':rev[n['atom']]}
    reviews=[]
    if m==1:reviews=[{'id':'rv','target_kind':'argument','target':final,'check':'support_replay','evidence':[n['id'] for n in nodes],
                     'finding':{'grounded':True,'used_rules':sorted({n['rule'] for n in nodes if n['rule']}),'conclusion':problem['goal']}}]
    if m==2:reviews=[{'id':'rv','target_kind':'acceptance_criterion','target':'valid_proof_and_goal','check':'counterexample_probe',
                     'probe':{'atom':problem['goal'],'rule':None,'parents':[]},'finding':{'answer_only_accepts':True,'proof_and_goal_accepts':False,'gap_detected':True}}]
    return {'nodes':nodes,'final':final,'views':views,'reviews':reviews}

def to_explicit(trace):
    result={'nodes':copy.deepcopy(trace['nodes']),'final_node_id':trace['final'],'node_views':[],'reviews':copy.deepcopy(trace['reviews'])}
    for key,view in trace['views'].items():
        v=copy.deepcopy(view)
        if v['kind']=='universal_schema':v['bindings']=[{'variable':x,'atom':y} for x,y in v.pop('binding').items()]
        result['node_views'].append({'node_id':key,'representation':v})
    return result

def explicit_answer(body,mode):
    text=body['messages'][1]['content'];system=body['messages'][0]['content']
    if '\nreference_record: ' in text:
        return strict_json(text.split('\nreference_record: ',1)[1])
    problem=strict_json(text[len('problem: '):])
    a='schema' if '각 노드의 node_views는 보편' in system else 'instance'
    d='deep' if '최종 지지 깊이가 가장 큰 경로' in system else 'shallow'
    m=2 if '평가 기준을 대상으로 acceptance_criterion/counterexample_probe 검토 하나만' in system else (1 if '최종 증명을 대상으로 argument/support_replay 검토 하나만' in system else 0)
    if mode=='ignore_roles':a,d,m='instance','shallow',0
    trace=generic_trace(problem,a,d,m)
    if mode=='wrong_m2' and m==2:trace['reviews'][0]['finding']['gap_detected']=False
    if mode=='bad_final':trace['final']=problem['goal']
    if mode=='false_goal_fact':trace={'nodes':[{'id':'n0','atom':problem['goal'],'rule':None,'parents':[]}],'final':'n0','views':{'n0':{'kind':'instance','atom':problem['goal']}},'reviews':[]}
    result=to_explicit(trace)
    if set(body['format']['properties'])=={'nodes','final_node_id'}:result={k:result[k] for k in ('nodes','final_node_id')}
    if mode=='invalid_json':return {'bad':'invalid payload'}
    return result

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
    from criterion_probe_v050.plan import prepare as p50
    from criterion_probe_v050.runner import execute as e50
    from criterion_probe_v050.evidence import bundle_run as b50
    from adm_pilot_v051.plan import prepare as p51
    from adm_pilot_v051.runner import execute as e51
    from adm_pilot_v051.evidence import bundle_run as b51
    from adm_diagnostic_v052.plan import prepare
    from adm_diagnostic_v052.runner import execute
    temp=tempfile.TemporaryDirectory(prefix='v052_fixture_');root=Path(temp.name)
    ctx=fake_server();state,endpoint=ctx.__enter__()
    with contextlib.redirect_stdout(io.StringIO()):
        pp,rr=build_v047(root,endpoint)
        p48(rr,root/'v48.plan',baseline_plan=pp);e48(root/'v48.plan',root/'v48.run');b48(root/'v48.plan',root/'v48.run',root/'v48.zip')
        p49(root/'v48.zip',root/'v49.plan');e49(root/'v49.plan',root/'v49.run');b49(root/'v49.plan',root/'v49.run',root/'v49.zip')
        p50(root/'v49.zip',root/'v50.plan');e50(root/'v50.plan',root/'v50.run');b50(root/'v50.plan',root/'v50.run',root/'v50.zip')
        p51(root/'v50.zip',root/'v51.plan');e51(root/'v51.plan',root/'v51.run');b51(root/'v51.plan',root/'v51.run',root/'v51.zip')
        plan=prepare(root/'v51.zip',root/'v52.plan');state.requests.clear();report=execute(root/'v52.plan',root/'v52.run')
    _shared={'root':root,'state':state,'endpoint':endpoint,'bundle':root/'v51.zip','plan':plan,'report':report}
    def cleanup():ctx.__exit__(None,None,None);temp.cleanup()
    atexit.register(cleanup);return _shared

@contextlib.contextmanager
def copied():
    f=shared()
    with tempfile.TemporaryDirectory(prefix='v052_copy_') as td:
        root=Path(td);p=root/'external.plan.json';run=root/'run'
        shutil.copyfile(f['root']/'v52.plan',p);shutil.copytree(f['root']/'v52.run',run)
        yield root,p,run,f

@contextlib.contextmanager
def executed(mode='perfect'):
    from adm_diagnostic_v052.plan import prepare
    from adm_diagnostic_v052.runner import execute
    f=shared();s=f['state'];s.mode=mode;s.requests.clear();s.metadata_boundary=s.show_calls
    try:
        with tempfile.TemporaryDirectory(prefix='v052_execute_') as td:
            root=Path(td);p=root/'external.plan.json';run=root/'run';plan=prepare(f['bundle'],p)
            with contextlib.redirect_stdout(io.StringIO()):r=execute(p,run)
            yield root,p,run,plan,r,s
    finally:s.mode='perfect'
