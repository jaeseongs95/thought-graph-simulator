"""네트워크 없는 시험 영수증. 실제 실행의 기준선 승인에는 사용하지 않는다."""
from copy import deepcopy
from tests_v056.quick_fixture import reference as old_reference
from layout_probe_v056.plan import make_plan as old_make
from layout_probe_v056.requests import request_bytes as old_request
from selection_probe_v057.contracts import b64,digest,strict_json
from selection_probe_v057.plan import make_plan

def reference():
    p=old_make(old_reference());slots=[s for s in p['slots'] if s['layout']=='merged']
    r={'contract':'audited-v056-compact-r1','bundle_sha256':'f'*64,'plan_sha256':p['plan_sha256'],'event_tip':'e'*64,
       'recorded_calls':480,'selected_calls':240,'selected_layout':'merged','evidence_kind':'synthetic_fixture',
       'config':deepcopy(p['baseline']['config']),'identities':deepcopy(p['identities']),'seeds':p['seeds'],'slots':slots,
       'request_bank':{s['id']:b64(old_request(p,s)) for s in slots}}
    r['receipt_sha256']=digest(r);return r

def plan():return make_plan(reference())

def trials(p,mode='perfect'):
    from selection_probe_v057.requests import request_bytes
    from selection_probe_v057.measure import measure,match
    from order_probe_v054.design import problem_for
    from tests_v054.fixtures import first_path
    from tests_v052.fixtures import explicit_answer
    rows=[]
    for s in p['slots']:
        row=s|{'observed':mode!='unobserved','measurement':None,'role_match':None,'status':'unexecuted','parse_error':None}
        if mode=='unobserved':rows.append(row);continue
        q=strict_json(request_bytes(p,s));pr=problem_for(s);want_long=s['direction']=='deep'
        rid=({'K01':'k17','T02':'r69'} if want_long else {'K01':'k03','T02':'r83'})[s['problem_id']]
        if s['mode']=='graph':
            system,user=q['messages'][0]['content'].rsplit('\n\nproblem: ',1)
            q['messages']=[{'role':'system','content':system},{'role':'user','content':'problem: '+user}]
            answer=first_path(pr) if mode in ('first_branch','choice_only') else explicit_answer(q,'perfect')
            if mode=='invalid':answer['nodes'][-1]['rule']='unknown'
        else:
            if mode in ('first_branch','graph_only'):rid=next(r['id'] for r in pr['rules'] if r['conclusion']==pr['goal'])
            if mode=='invalid':rid='unknown'
            answer={'final_rule_id':rid}
        m=measure(pr,answer,s);row.update(measurement=m,role_match=match(pr,m,s),status='valid_payload');rows.append(row)
    return rows
