"""합성 응답 fixtures. 실제 모델 결과로 보고하지 않는다."""
from pathlib import Path
from copy import deepcopy
import os,json
import core084 as core
import design084
from calibrate084 import proof

BASELINE=Path(os.environ.get('V084_BASELINE', str(Path.home()/'Downloads/v083_controlcross_20260915_131258_306803_evidence.zip')))


def plan():
    spec=core.spec();ts,ss,aa=design084.schedule(spec)
    p={'contract':'v084-plan-r1','run_name':'v084_synthetic_test','provenance':'synthetic','protocol':spec,
       'protocol_sha256':core.sha((core.ROOT/'data/protocol.json').read_bytes()),'baseline_sha256':spec['baseline_sha256'],
       'source_hashes':core.source_hashes(),'trials':ts,'slots':ss,'actions':aa}
    p['plan_sha256']=core.sha(core.wire(p));return p


def decode_request(body):
    text=body['messages'][0]['content']
    return core.load(text.split('\n\ninput: ',1)[1])


def answer(body,policy='oracle',wrong_rule=False):
    data=decode_request(body)
    if 'candidates' in data:
        cards=data['candidates'];direction='shallow' if '작은' in data.get('requested_depth',data.get('requested_rule_count','')) else 'deep'
        requested='W' if 'requested_rule_count' in data else 'D'
        if policy=='first':chosen=cards[0]
        elif policy=='longest':chosen=max(cards,key=lambda c:len(c['rules']))
        elif policy=='shortest':chosen=min(cards,key=lambda c:len(c['rules']))
        elif policy=='reported' and 'candidate_measurements' in data:
            vals=[core.load(x['content'])['goal_depth' if requested=='D' else 'rule_count'] for x in data['candidate_measurements']]
            chosen=cards[vals.index((min if direction=='shallow' else max)(vals))]
        elif policy=='id0':chosen=next(c for c in cards if c['candidate_id']=='route_0')
        else:
            criterion='W' if policy=='count_only' else 'D' if policy=='depth_only' else requested
            vals=[]
            for c in cards:
                depths={a:0 for a in data['problem']['facts']}
                for r in c['rules']:depths[r['conclusion']]=1+max(depths[x] for x in r['premises'])
                vals.append(len(c['rules']) if criterion=='W' else depths[data['problem']['goal']])
            goal=(min if direction=='shallow' else max)(vals)
            chosen=cards[vals.index(goal)]
            if policy=='reverse':chosen=cards[1-cards.index(chosen)]
        obj={'candidate_id':chosen['candidate_id']}
    else:
        phase=data['operation']['stage']
        if phase=='facts':obj={'nodes':[{'id':f'f{i}','atom':a,'rule':None,'parents':[]} for i,a in enumerate(data['problem']['facts'])]}
        else:
            nodes=[]
            for h in data['history']:
                x=core.load(h['content'])
                if 'nodes' in x:nodes.extend(x['nodes'])
                elif 'node' in x:nodes.append(x['node'])
            if phase=='final':obj={'final_node_id':nodes[-1]['id']}
            else:
                r=data['operation']['requested_rule'];by={n['atom']:n['id'] for n in nodes}
                parents=[by[a] for a in r['premises']]
                if wrong_rule:parents=[]
                obj={'node':{'id':f"n{data['operation']['index']}",'atom':r['conclusion'],'rule':r['id'],'parents':parents}}
    return core.wire({'model':body['model'],'created_at':'synthetic','message':{'role':'assistant','content':core.wire(obj).decode()},
                      'done':True,'done_reason':'stop','prompt_eval_count':1,'eval_count':1,'total_duration':1,'prompt_eval_duration':1,'eval_duration':1})


def response_set(p,policy='oracle',transform=None):
    records={};raws={};requests={}
    for op in p['slots']:
        skip=design084.disposition(p,op,raws)
        if skip:records[op['id']]={'kind':'skip','reason':skip};continue
        body=design084.request_for(p,op,raws);requests[op['id']]=core.wire(body)
        active=policy.get(design084.trial_for(p,op)['selector_variant'],'oracle') if isinstance(policy,dict) else policy
        raw=answer(body,active)
        if transform is not None:raw=transform(op,body,raw)
        raws[op['id']]=raw;records[op['id']]={'kind':'call','http_status':200,'error':None}
    return records,raws,requests


def fake_exchange(policy='oracle',crash_at=None,http_at=None,identity_error=False):
    count={'chat':0,'all':0}
    spec=core.spec();expected=spec['identity']
    def exchange(endpoint,path,body,timeout):
        count['all']+=1
        if path=='/api/version':raw=core.wire({'version':'wrong'} if identity_error else expected['server'])
        elif path=='/api/tags':raw=core.wire({'models':[{'name':expected['model'],'model':expected['model'],'digest':expected['digest'],'details':expected['tag_details']}]})
        elif path=='/api/show':
            show=deepcopy(expected['native'])
            if show['parameters'] is not None:show['parameters']='\n'.join(show['parameters'])
            raw=core.wire(show)
        else:
            count['chat']+=1
            if crash_at==count['chat']:raise KeyboardInterrupt('synthetic crash after dispatch')
            if http_at==count['chat']:return 503,b'error',None,1
            raw=answer(core.load(body),policy)
        return 200,raw,None,1
    exchange.count=count
    return exchange
