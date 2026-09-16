"""합성 검증 응답. 실제 Qwen 결과가 아니며 라이브 실행 경로에서 import하지 않는다."""
from pathlib import Path
from copy import deepcopy
import base64,importlib.util
import core087 as core,design087 as design
import bridge087

spec=importlib.util.spec_from_file_location('_v086_fixtures',core.ROOT/'frozen086/tests/fixtures086.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)


def plan():
    s=core.spec();ts,ops,actions=design.schedule(s)
    p={'contract':'v087-plan-r1','run_name':'v087_synthetic_test','provenance':'synthetic','protocol':s,
       'protocol_sha256':core.sha((core.ROOT/'data/protocol.json').read_bytes()),'baseline_sha256':s['baseline_sha256'],
       'source_hashes':core.source_hashes(),'trials':ts,'slots':ops,'actions':actions}
    p['plan_sha256']=core.sha(core.wire(p));return p


def data(body):return core.load(body['messages'][0]['content'].split('\n\ninput: ',1)[1])


def answer(body,policy='oracle'):
    d=data(body);raw=old.answer(body,policy)
    if d.get('operation',{}).get('stage')=='rule':
        x=core.load(raw);obj=core.load(x['message']['content']);used={r['id']for r in design.history_inventory(d['history'])['rows']}
        k=1
        while f'synthetic_node_{k}'in used:k+=1
        obj['node']['id']=d.get('allocated_node_id',f'synthetic_node_{k}')
        x['message']['content']=core.wire(obj).decode();raw=core.wire(x)
    return raw


def response_set(p,transform=None,policy='oracle'):
    records={};raws={};requests={}
    for op in p['slots']:
        sid=op['id'];skip=design.disposition(p,op,raws)
        if skip:records[sid]={'kind':'skip','reason':skip};continue
        body=design.request_for(p,op,raws);raw=answer(body,policy)
        if transform:raw=transform(op,body,raw)
        requests[sid]=core.wire(body);raws[sid]=raw;records[sid]={'kind':'call','http_status':200,'error':None}
    return records,raws,requests


def fake_exchange(crash_at=None,http_at=None,transport_at=None,identity_error=False,policy='oracle'):
    calls={'chat':0,'all':0};identity=core.spec()['identity']
    def exchange(endpoint,path,body,timeout):
        calls['all']+=1
        if path=='/api/version':raw=core.wire({'version':'bad'}if identity_error else identity['server'])
        elif path=='/api/tags':raw=core.wire({'models':[{'name':identity['model'],'model':identity['model'],'digest':identity['digest'],'details':identity['tag_details']}]})
        elif path=='/api/show':
            obj=deepcopy(identity['native'])
            if obj['parameters']is not None:obj['parameters']='\n'.join(obj['parameters'])
            raw=core.wire(obj)
        else:
            calls['chat']+=1
            if calls['chat']==crash_at:raise KeyboardInterrupt('synthetic after dispatch')
            if calls['chat']==http_at:return 503,b'unavailable',None,1
            if calls['chat']==transport_at:return 200,b'{partial','incomplete_http_body:expected=100,received=8',1
            raw=answer(core.load(body),policy)
        return 200,raw,None,1
    exchange.count=calls
    return exchange
