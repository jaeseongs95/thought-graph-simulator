"""사전 정상·반례를 독립 의미 판정기에 대조한다. Qwen 호출 없음."""
from copy import deepcopy
from collections import Counter
from pathlib import Path
import argparse,json
import core090 as c,design090 as d,fixtures090 as f
from rows090 import fact_check,facts_support
from audit_rows090 import initial_check,initial_support
import bridge090
from rows087 import rule_check
from audit_rows087 import step_check
from measure import assess
from audit_graph import _semantic


def calibration():
    p=f.plan();records,raws,requests=f.response_set(p)
    counts=Counter();nf=nr=ng=0
    for op in p['slots']:
        if op['id'] not in requests:continue
        body=c.load(requests[op['id']]);data=d.data_from(body)
        if op['stage']=='facts':
            t=d.trial_for(p,op);arm=t['generator_arm'];problem=data['problem']
            original=c.load(c.load(raws[op['id']])['message']['content'])['nodes']
            cases=[('valid',deepcopy(original),True,True)]
            x=deepcopy(original);x[0]['atom']='WRONG_ATOM';cases.append(('wrong_atom',x,False,arm=='baseline'))
            x=deepcopy(original);x[1]['id']=x[0]['id'];cases.append(('duplicate_id',x,False,arm=='baseline'))
            x=deepcopy(original)[1:];cases.append(('missing_fact',x,False,True))
            x=deepcopy(original);x[0]['parents']=['NO_PARENT'];cases.append(('fact_parent',x,False,True))
            x=deepcopy(original);x[0]['id']='UNEXPECTED_BUT_UNIQUE';cases.append(('id_contract_only',x,True,arm=='baseline'))
            for name,nodes,sem,support in cases:
                saved=deepcopy(nodes)
                a,b=fact_check(problem,nodes),initial_check(problem,nodes)
                if a!=b or a['valid'] is not sem or facts_support(problem,nodes,arm) is not support or initial_support(problem,nodes,arm) is not support or nodes!=saved:
                    raise AssertionError('facts calibration '+op['id']+'/'+name)
                nf+=1;counts['facts/'+name]+=1
        if op['stage']=='rule':
            before=d.history_nodes(data['history']);problem=data['problem'];rid=data['operation']['requested_rule_id']
            original=c.load(c.load(raws[op['id']])['message']['content'])['node']
            cases=[('valid',deepcopy(original),True)]
            x=deepcopy(original);x['parents']=['NO_SUCH_NODE'];cases.append(('missing_parent',x,False))
            x=deepcopy(original);x['parents']=x['parents'][1:];cases.append(('omitted_premise',x,False))
            x=deepcopy(original);x['id']=before[0]['id'];cases.append(('duplicate_node',x,False))
            x=deepcopy(original);x['atom']='WRONG_CONCLUSION';cases.append(('wrong_atom',x,False))
            x=deepcopy(original);x['rule']='NO_SUCH_RULE';cases.append(('wrong_rule',x,False))
            x=deepcopy(original);x['parents']+=x['parents'][:1];cases.append(('duplicate_parent',x,False))
            for label,node,expected in cases:
                saved=deepcopy(node);a=rule_check(problem,before,node,rid);b=step_check(problem,before,node,rid)
                if a!=b or a['valid'] is not expected or node!=saved:raise AssertionError('rule calibration '+op['id']+'/'+label)
                nr+=1;counts['rule/'+label]+=1
    bytrial={t['id']:[] for t in p['trials']}
    for o in p['slots']:
        if o['stage'] in ('facts','rule','final') and o['id'] in raws:bytrial[o['trial_id']].append(o)
    for t in p['trials']:
        nodes=[];final=None
        for op in bytrial[t['id']]:
            obj=c.load(c.load(raws[op['id']])['message']['content'])
            if op['stage']=='facts':nodes+=obj['nodes']
            elif op['stage']=='rule':nodes.append(obj['node'])
            else:final=obj['final_node_id']
        original=dict(nodes=nodes,final_node_id=final);cases=[('valid',deepcopy(original),True)]
        x=deepcopy(original);x['final_node_id']='NO_FINAL';cases.append(('missing_final',x,False))
        x=deepcopy(original);x['nodes'][-1]['parents']=[x['nodes'][-1]['id']];cases.append(('cycle',x,False))
        x=deepcopy(original);x['nodes'][-1]['parents']=x['nodes'][-1]['parents'][1:];cases.append(('omitted_premise',x,False))
        problem=next(x for x in p['protocol']['problems'] if x['id']==t['problem_id'])
        for label,graph,expected in cases:
            saved=deepcopy(graph);a,b=assess(problem,graph),_semantic(problem,graph)
            if a!=b or a['strict_valid'] is not expected or graph!=saved:raise AssertionError('graph calibration '+t['id']+'/'+label)
            ng+=1;counts['graph/'+label]+=1
    return dict(contract='v090-calibration-r1',provenance='synthetic_no_inference',passed=nf+nr+ng,
        failures=0,actual_qwen_calls=0,facts_cases=nf,rule_cases=nr,graph_cases=ng,case_counts=dict(sorted(counts.items())))


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    result=calibration();c.save(a.out,result);print(json.dumps(result,ensure_ascii=False));return 0
if __name__=='__main__':raise SystemExit(main())
