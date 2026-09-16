"""시험 전용 합성 응답. 실제 Qwen 결과가 아니며 production 실행에서 import하지 않는다."""
from copy import deepcopy
import core090 as core
import design090 as design
import bridge090
import fixtures087 as old


def plan():
    s=core.spec();ts,ops,actions=design.schedule(s)
    p=dict(contract='v090-plan-r1',run_name='v090_synthetic_test',provenance='synthetic',protocol=s,
        protocol_sha256=core.sha((core.ROOT/'data/protocol.json').read_bytes()),baseline_sha256=s['baseline_sha256'],
        source_hashes=core.source_hashes(),trials=ts,slots=ops,actions=actions)
    p['plan_sha256']=core.sha(core.wire(p))
    return p


def answer(body,policy='oracle'):
    # oracle는 시험용 정답 생성기일 뿐이다. 모델 응답의 사후 보정에 사용하지 않는다.
    raw=old.answer(body,policy)
    data=design.data_from(body)
    if data.get('operation',{}).get('stage')=='facts' and 'allocated_fact_ids' in data:
        outer=core.load(raw);obj=core.load(outer['message']['content'])
        table={x['atom']:x['id'] for x in data['allocated_fact_ids']}
        for n in obj['nodes']:
            n['id']=table[n['atom']]
        outer['message']['content']=core.wire(obj).decode()
        raw=core.wire(outer)
    return raw


def response_set(p,transform=None,policy='oracle'):
    records,raws,requests={},{},{}
    for op in p['slots']:
        sid=op['id'];skip=design.disposition(p,op,raws)
        if skip:
            records[sid]=dict(kind='skip',reason=skip)
            continue
        body=design.request_for(p,op,raws);raw=answer(body,policy)
        if transform:
            raw=transform(op,body,raw)
        raws[sid]=raw;requests[sid]=core.wire(body)
        records[sid]=dict(kind='call',http_status=200,error=None)
    return records,raws,requests


def fake_exchange(crash_at=None,http_at=None,transport_at=None,identity_error=False,policy='oracle'):
    calls={'chat':0,'all':0};identity=core.spec()['identity']
    def exchange(endpoint,path,body,timeout):
        calls['all']+=1
        if path=='/api/version':
            raw=core.wire({'version':'bad'} if identity_error else identity['server'])
        elif path=='/api/tags':
            raw=core.wire({'models':[{'name':identity['model'],'model':identity['model'],
                'digest':identity['digest'],'details':identity['tag_details']}]})
        elif path=='/api/show':
            value=deepcopy(identity['native'])
            if value['parameters'] is not None:
                value['parameters']='\n'.join(value['parameters'])
            raw=core.wire(value)
        else:
            calls['chat']+=1
            if calls['chat']==crash_at:
                raise KeyboardInterrupt('synthetic interruption after dispatch')
            if calls['chat']==http_at:
                return 503,b'unavailable',None,1
            if calls['chat']==transport_at:
                return 200,b'{partial','incomplete_http_body:expected=100,received=8',1
            raw=answer(core.load(body),policy)
        return 200,raw,None,1
    exchange.count=calls
    return exchange
