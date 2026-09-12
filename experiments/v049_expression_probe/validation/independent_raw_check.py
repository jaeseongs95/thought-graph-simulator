"""v049 ZIP의 독립 원문 검사. 배포 실행기/평가기/정답표를 import하지 않는다."""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import re
import zipfile
from pathlib import Path

def decode(data):
    def pairs(xs):
        d={}
        for k,v in xs:
            if k in d:raise ValueError('중복 키: '+k)
            d[k]=v
        return d
    return json.loads(data,object_pairs_hook=pairs)

def sha(x):return hashlib.sha256(x).hexdigest()
def canon(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()

def calculate(expr,a,b):
    # shunting-yard: 본 평가기의 재귀하강 파서와 다른 계산 경로.
    ts=re.findall(r'NOT|AND|a|b|[()]',expr)
    assert ''.join(ts)==re.sub(r'\s+','',expr)
    operators=[];postfix=[];prec={'NOT':2,'AND':1}
    for t in ts:
        if t in ('a','b'):postfix.append(t)
        elif t=='(':operators.append(t)
        elif t==')':
            while operators and operators[-1]!='(':postfix.append(operators.pop())
            assert operators.pop()=='('
        else:
            while operators and operators[-1]!='(' and (prec[operators[-1]]>prec[t] or (prec[operators[-1]]==prec[t] and t=='AND')):postfix.append(operators.pop())
            operators.append(t)
    while operators:postfix.append(operators.pop())
    vals=[]
    for t in postfix:
        if t in ('a','b'):vals.append(a if t=='a' else b)
        elif t=='NOT':vals.append(not vals.pop())
        else:
            r=vals.pop();l=vals.pop();vals.append(l and r)
    assert len(vals)==1
    return vals[0]

def check(path):
    with zipfile.ZipFile(path) as z:
        assert len(z.namelist())==len(set(z.namelist()))
        raw={n:z.read(n) for n in z.namelist()}
    manifest=decode(raw['BUNDLE_MANIFEST.json'])
    assert manifest['file_hashes']=={n:sha(b) for n,b in raw.items() if n!='BUNDLE_MANIFEST.json'}
    plan=decode(raw['external_plan/v049.plan.json']);assert plan==decode(raw['run/plan.snapshot.json'])
    assert plan['plan_sha256']==sha(canon({k:v for k,v in plan.items() if k!='plan_sha256'}))
    expected=[]
    for block in plan['blocks']:
        for arm in block['arms']:
            for stage in (('not','and') if arm=='pipeline' else (arm,)):
                expected.append((block,arm,stage))
    es=[decode(x) for x in raw['run/events.jsonl'].splitlines()]
    assert len(es)==len(expected)==480
    truth={(False,False):False,(False,True):False,(True,False):True,(True,True):False}
    unary={False:True,True:False};conjunction={(False,False):False,(False,True):False,(True,False):False,(True,True):True}
    records={};tip=plan['plan_sha256'];links=0
    for e,(b,arm,stage) in zip(es,expected):
        s=e['slot'];assert s['id']==b['id']+'__'+stage and s['arm']==arm
        assert e['previous_hash']==tip and e['event_hash']==sha(canon({k:v for k,v in e.items() if k!='event_hash'}));tip=e['event_hash']
        assert e['kind']=='call' and e['http_status']==200 and e['transport_error'] is None
        req=raw['run/calls/'+s['id']+'/request.wire.json'];resp=raw['run/calls/'+s['id']+'/response.raw.json']
        assert sha(req)==e['request_sha256'] and sha(resp)==e['response_sha256']
        request=decode(req);response=decode(resp);values=decode(request['messages'][1]['content'][7:]);out=decode(response['message']['content'])
        assert response['done'] is True and response['done_reason']=='stop' and response['model']==plan['baseline']['config']['model']
        assert set(out)=={'value'} and type(out['value']) is bool
        assert request['options']['seed']==b['seed'] and values['a'] is b['a']
        result=calculate(values['expression'],values['a'],values['b'])
        if stage=='and':
            parent=records[b['id']+'__not'];assert values['b'] is parent['value']
            assert e['parent']=={'id':b['id']+'__not','response_sha256':parent['hash']}
            assert result is conjunction[b['a'],parent['value']];links+=1
        else:
            assert values['b'] is b['b'];assert e['parent'] is None
            assert result is (unary[b['b']] if stage=='not' else truth[b['a'],b['b']])
        records[s['id']]={'value':out['value'],'local_correct':out['value'] is result,'hash':sha(resp)}
    arms=collections.defaultdict(lambda:{'assigned':0,'final_correct':0,'trace_correct':None})
    for b in plan['blocks']:
        for arm in b['arms']:
            final=records[b['id']+'__'+('and' if arm=='pipeline' else arm)]
            arms[arm]['assigned']+=1;arms[arm]['final_correct']+=final['value'] is truth[b['a'],b['b']]
            if arm=='pipeline':
                parent=records[b['id']+'__not'];arms[arm]['trace_correct']=(arms[arm]['trace_correct'] or 0)+(parent['local_correct'] and final['local_correct'] and final['value'] is truth[b['a'],b['b']])
    summary=decode(raw['run/summary.json'])
    for arm,r in arms.items():
        assert r['assigned']==summary['arms'][arm]['assigned'] and r['final_correct']==summary['arms'][arm]['final_correct']
        if arm=='pipeline':assert r['trace_correct']==summary['arms'][arm]['strict_trace_correct']
    return {'evidence_kind':plan['baseline']['evidence_kind'],'calls':len(es),'parent_links':links,
            'independent_arms':dict(arms),'agrees_with_summary':True,'event_tip':tip,
            'scope':'이 검사 실행은 정상형식·완결 480회 합성 증거에 대한 별도 계산이다. 새 LLM 성과가 아님'}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--bundle',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    result=check(a.bundle);a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False,indent=2))
