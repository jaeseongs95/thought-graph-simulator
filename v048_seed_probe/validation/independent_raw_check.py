"""본 감사 모듈을 import하지 않는 합성 960회 기록의 수동 진리표 교차검사."""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


def load(raw):
    def pairs(items):
        result={}
        for k,v in items:
            assert k not in result,'duplicate key';result[k]=v
        return result
    return json.loads(raw,object_pairs_hook=pairs)


def sha(raw):return hashlib.sha256(raw).hexdigest()

def digest(obj):return sha(json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode())


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan',type=Path,required=True);p.add_argument('--run',type=Path,required=True)
    args=p.parse_args()
    plan=load(args.plan.read_bytes());events=[load(x) for x in (args.run/'events.jsonl').read_bytes().splitlines()]
    assert plan['baseline']['evidence_kind']=='synthetic_fixture','합성 smoke 검사 전용'
    assert len(events)==plan['max_calls']==960
    truth={(False,False):False,(False,True):False,(True,False):True,(True,True):False}
    and_truth={(False,False):False,(False,True):False,(True,False):False,(True,True):True}
    not_truth={False:True,True:False}
    previous=plan['plan_sha256'];values={};totals=Counter();hashes={};strict=0
    for e in events:
        assert e['kind']=='call' and e['previous_hash']==previous
        assert e['event_hash']==digest({k:v for k,v in e.items() if k!='event_hash'})
        previous=e['event_hash'];slot=e['slot']
        folder=args.run/'calls'/slot['id']
        raw=(folder/'request.wire.json').read_bytes();response=(folder/'response.raw.json').read_bytes()
        assert sha(raw)==e['request_sha256'] and sha(response)==e['response_sha256']
        body=load(raw);inp=load(body['messages'][1]['content'][7:]);env=load(response)
        assert body['options']['seed']==slot['seed'] and slot['seed'] not in [1729]
        assert env['model']==body['model'] and env['done'] is True and env['done_reason']=='stop'
        payload=load(env['message']['content']);assert set(payload)=={'value'} and type(payload['value']) is bool
        value=payload['value'];stage=slot['stage'];a,b=slot['a'],slot['b'];bid=slot['block_id']
        assert type(a) is bool and type(b) is bool and inp['a'] is a
        values[slot['id']]=value;hashes[slot['id']]=e['response_sha256'];totals[stage+'_calls']+=1
        if stage in ('original','commuted'):
            assert inp['b'] is b
            totals[stage+'_correct']+=value is truth[a,b]
        elif stage=='not':
            assert inp['b'] is b
            totals['not_correct']+=value is not_truth[b]
        elif stage=='and':
            parent=bid+'__not';assert inp['b'] is values[parent]
            assert e['parent']=={'id':parent,'response_sha256':hashes[parent]}
            totals['and_local_correct']+=value is and_truth[a,values[parent]]
            totals['pipeline_final_correct']+=value is truth[a,b]
            strict+=values[parent] is not_truth[b] and value is and_truth[a,values[parent]] and value is truth[a,b]
        else:raise AssertionError('unknown stage')
    assert strict==240
    assert totals['original_correct']==180 and totals['commuted_correct']==240
    assert totals['not_correct']==240 and totals['and_local_correct']==240 and totals['pipeline_final_correct']==240
    print(json.dumps({'kind':'independent_synthetic_smoke_only','calls_checked':len(events),
        'new_model_inference':False,'no_import_of_production_evaluator':True,
        'counts':dict(totals),'pipeline_strict':strict,'event_tip':previous},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
