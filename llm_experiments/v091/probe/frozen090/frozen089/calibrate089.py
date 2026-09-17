"""합성 정상/반례를 두 의미 판정기에 대조한다. 모델 추론은 하지 않는다."""
from pathlib import Path
from copy import deepcopy
from collections import Counter
import argparse
import json
import core089 as c
import design089 as d
import fixtures089 as f
import bridge089
from rows087 import rule_check
from audit_rows087 import step_check
from measure import assess
from audit_graph import _semantic

def calibration():
    plan=f.plan()
    records,raws,requests=f.response_set(plan)
    rules=graphs=0
    by_case=Counter()
    for op in plan['slots']:
        if op['stage']!='rule' or op['id'] not in requests:
            continue
        body=c.load(requests[op['id']])
        data=d.data_from(body)
        before=d.history_nodes(data['history'])
        obj=c.load(c.load(raws[op['id']])['message']['content'])['node']
        p=data['problem'];rid=data['operation']['requested_rule_id']
        cases=[('valid',deepcopy(obj),True)]
        x=deepcopy(obj);x['parents']=['NO_SUCH_NODE'];cases.append(('missing_parent',x,False))
        x=deepcopy(obj);x['parents']=x['parents'][1:];cases.append(('omitted_premise',x,False))
        x=deepcopy(obj);x['id']=before[0]['id'];cases.append(('duplicate_node',x,False))
        x=deepcopy(obj);x['atom']='NOT_THE_CONCLUSION';cases.append(('wrong_atom',x,False))
        x=deepcopy(obj);x['rule']='NOT_THE_RULE';cases.append(('wrong_rule',x,False))
        x=deepcopy(obj);x['parents']+=x['parents'][:1];cases.append(('duplicate_parent',x,False))
        for label,node,expected in cases:
            snapshot=deepcopy(node)
            a=rule_check(p,before,node,rid);b=step_check(p,before,node,rid)
            if a!=b or a['valid'] is not expected or node!=snapshot:
                raise AssertionError('규칙 calibration 불일치: '+op['id']+'/'+label)
            rules+=1;by_case['rule/'+label]+=1
    for t in plan['trials']:
        ops=[o for o in plan['slots'] if o['trial_id']==t['id'] and o['stage'] in ('facts','rule','final') and o['id'] in raws]
        nodes=d.history_nodes(d.continuation_seed(t)[0]) if t['phase']=='continuation' else []
        final=None
        for op in ops:
            obj=c.load(c.load(raws[op['id']])['message']['content'])
            if op['stage']=='facts':nodes.extend(obj['nodes'])
            elif op['stage']=='rule':nodes.append(obj['node'])
            else:final=obj['final_node_id']
        original=dict(nodes=nodes,final_node_id=final)
        cases=[('valid',deepcopy(original),True)]
        x=deepcopy(original);x['final_node_id']='NO_FINAL';cases.append(('missing_final',x,False))
        x=deepcopy(original);x['nodes'][-1]['parents']=[x['nodes'][-1]['id']];cases.append(('cycle',x,False))
        x=deepcopy(original);x['nodes'][-1]['parents']=x['nodes'][-1]['parents'][1:];cases.append(('omitted_premise',x,False))
        problem=next(p for p in plan['protocol']['problems'] if p['id']==t['problem_id'])
        for label,graph,expected in cases:
            snapshot=deepcopy(graph)
            a=assess(problem,graph);b=_semantic(problem,graph)
            if a!=b or a['strict_valid'] is not expected or graph!=snapshot:
                raise AssertionError('graph calibration 불일치: '+t['id']+'/'+label)
            graphs+=1;by_case['graph/'+label]+=1
    return dict(contract='v089-calibration-r1',provenance='synthetic_no_inference',passed=rules+graphs,
                failures=0,actual_qwen_calls=0,rule_cases=rules,graph_cases=graphs,case_counts=dict(sorted(by_case.items())))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    result=calibration();c.save(args.out,result)
    print(json.dumps(result,ensure_ascii=False));return 0
if __name__=='__main__':raise SystemExit(main())
