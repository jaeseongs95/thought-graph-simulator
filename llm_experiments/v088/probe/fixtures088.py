"""오프라인·합성 검증 전용. 실제 Qwen 응답이 아니다."""
from copy import deepcopy
import core088 as core, design088 as design
import bridge088
import fixtures087 as previous

def plan():
    s=core.spec();ts,ops,actions=design.schedule(s)
    p=dict(contract='v088-plan-r1',run_name='v088_synthetic_test',provenance='synthetic',protocol=s,
        protocol_sha256=core.sha((core.ROOT/'data/protocol.json').read_bytes()),baseline_sha256=s['baseline_sha256'],
        source_hashes=core.source_hashes(),trials=ts,slots=ops,actions=actions)
    p['plan_sha256']=core.sha(core.wire(p));return p

def answer(body,policy='oracle'):return previous.answer(body,policy)

def response_set(p,transform=None,policy='oracle'):
    records={};raws={};requests={}
    for o in p['slots']:
        sid=o['id'];skip=design.disposition(p,o,raws)
        if skip:records[sid]=dict(kind='skip',reason=skip);continue
        body=design.request_for(p,o,raws);raw=answer(body,policy)
        if transform:raw=transform(o,body,raw)
        raws[sid]=raw;requests[sid]=core.wire(body);records[sid]=dict(kind='call',http_status=200,error=None)
    return records,raws,requests

def fake_exchange(crash_at=None,http_at=None,transport_at=None,identity_error=False,policy='oracle'):
    calls=dict(chat=0,all=0);identity=core.spec()['identity']
    def exchange(endpoint,path,body,timeout):
        calls['all']+=1
        if path=='/api/version':raw=core.wire({'version':'bad'}if identity_error else identity['server'])
        elif path=='/api/tags':raw=core.wire({'models':[dict(name=identity['model'],model=identity['model'],digest=identity['digest'],details=identity['tag_details'])]})
        elif path=='/api/show':
            x=deepcopy(identity['native'])
            if x['parameters']is not None:x['parameters']='\n'.join(x['parameters'])
            raw=core.wire(x)
        else:
            calls['chat']+=1
            if calls['chat']==crash_at:raise KeyboardInterrupt('synthetic dispatch interruption')
            if calls['chat']==http_at:return 503,b'unavailable',None,1
            if calls['chat']==transport_at:return 200,b'{partial','incomplete_http_body:expected=100,received=8',1
            raw=answer(core.load(body),policy)
        return 200,raw,None,1
    exchange.count=calls;return exchange
