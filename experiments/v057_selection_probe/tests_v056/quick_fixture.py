"""네트워크 없는 변환/집계 단위시험용 합성 영수증. 실험 기준선으로 승인하지 않는다."""
import copy
from layout_probe_v056.contracts import b64,digest
from order_probe_v054.design import schedule as order_schedule,problem_for
from model_probe_v055.design import schedule as model_schedule
from adm_diagnostic_v052.requests import GRAPH_COMMON,encode
from adm_pilot_v051.requests import D
from order_probe_v054.schema import schema_for
from layout_probe_v056.plan import make_plan
SEEDS=[580410664,661935755,209422594,1790124989,267101868,752235971,1292559482,223674688,860724506,68285180]

def reference():
    identities={k:{'model':v,'digest':c*64} for k,v,c in [('reference','qwen3:4b-instruct','a'),('candidate','gemma3:4b','c')]}
    slots=model_schedule({'seeds':SEEDS,'slots':order_schedule(SEEDS)});bank={}
    options={'temperature':0.7,'top_p':0.8,'top_k':20,'min_p':0.0,'repeat_penalty':1.0,'num_ctx':8192,'num_predict':4096,'num_thread':6,'num_batch':256}
    for s in slots:
        schema=schema_for(s);system=GRAPH_COMMON
        if s['direction']!='neutral':system+='\n경로 지시:\n'+D[s['direction']]
        system+='\nJSON 객체 하나만 출력한다. 출력 형식(JSON Schema):\n'+encode(schema).decode()
        q={'model':identities[s['model_key']]['model'],'messages':[{'role':'system','content':system},{'role':'user','content':'problem: '+encode(problem_for(s)).decode()}],
           'stream':False,'keep_alive':'10m','options':options|{'seed':s['seed']},'format':schema}
        bank[s['id']]=b64(encode(q))
    r={'contract':'audited-v055-compact-r1','bundle_sha256':'f'*64,'plan_sha256':'a'*64,'event_tip':'e'*64,'recorded_calls':240,'evidence_kind':'synthetic_fixture',
        'config':{'model':identities['reference']['model'],'endpoint':'http://127.0.0.1:1','timeout_seconds':1,'options':options},'identities':identities,'seeds':SEEDS,'slots':slots,'request_bank':bank}
    r['receipt_sha256']=digest(r);return r

def plan():return make_plan(reference())

def trials(p,mode='unobserved'):
    from order_probe_v054.measure import measure,role_match
    from order_probe_v054.design import problem_for,role_for
    from tests_v054.fixtures import first_path
    from tests_v052.fixtures import explicit_answer
    from layout_probe_v056.requests import request_bytes
    from layout_probe_v056.contracts import strict_json
    rows=[]
    for s in p['slots']:
        if mode=='unobserved':rows.append(s|{'observed':False,'measurement':None,'role_match':None,'status':'unexecuted','parse_error':None});continue
        q=strict_json(request_bytes(p,s))
        if len(q['messages'])==1:
            system,user=q['messages'][0]['content'].rsplit('\n\nproblem: ',1);q['messages']=[{'role':'system','content':system},{'role':'user','content':'problem: '+user}]
        pr=problem_for(s)
        payload=first_path(pr) if mode=='first_branch' or (mode=='merged_only' and s['layout']=='split') else explicit_answer(q,'perfect')
        if mode=='invalid':payload['nodes'][-1]['rule']='unknown'
        m=measure(pr,payload,s);r=role_for(s)
        rows.append(s|{'observed':True,'measurement':m,'role_match':role_match(m,r,pr) if r else None,'status':'valid_payload','parse_error':None})
    return rows
