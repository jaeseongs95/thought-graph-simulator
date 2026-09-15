"""관측 anchor와 반례에 대한 생산·독립 규칙/graph 측정기 점검. 모델 호출 0회."""
from pathlib import Path
from copy import deepcopy
import argparse,json
import core087 as core,design087 as design,rows087,audit_rows087,fixtures087
import bridge087
from audit_graph import _semantic
import measure


def calibration():
    total=0;checks=[];by_problem={p['id']:p for p in core.spec()['problems']}
    for a in design.anchors():
        p=by_problem[a['problem_id']];d=fixtures087.data(a['request_body']);nodes=[]
        for h in d['history']:
            x=core.load(h['content']);nodes+=x['nodes']if 'nodes'in x else[x['node']]
        body=deepcopy(a['request_body']);payload=core.load(core.load(fixtures087.answer(body))['message']['content']);valid=payload['node']
        cases=[('valid',valid,True)]
        for name,mut in [('missing_parent',lambda n:n['parents'].pop()),('wrong_atom',lambda n:n.update(atom='INVALID')),
                         ('duplicate_id',lambda n:n.update(id=nodes[0]['id'])),('unregistered_rule',lambda n:n.update(rule='INVALID')),
                         ('unknown_parent',lambda n:n['parents'].append('MISSING'))]:
            n=deepcopy(valid);mut(n);cases.append((name,n,False))
        for label,node,expected in cases:
            left=rows087.rule_check(p,nodes,node,a['rule_id']);right=audit_rows087.step_check(p,nodes,node,a['rule_id'])
            if not core.exact(left,right)or left['valid']is not expected:raise ValueError('calibration failed '+a['id']+' '+label)
            checks.append({'anchor':a['id'],'case':label,'accepted':left['valid']});total+=1
    # 모든 16경로에 대한 전체 graph의 정상/무효 대조.
    from calibrate086 import proof
    graph_checks=0
    for p in core.spec()['problems']:
        for path in core.spec()['reference_plans'][p['id']].values():
            graph=proof(p,path)
            for label in ('valid','duplicate_id','missing_parent','wrong_final','wrong_atom'):
                g=deepcopy(graph)
                if label=='duplicate_id':g['nodes'][-1]['id']=g['nodes'][0]['id']
                if label=='missing_parent':g['nodes'][-1]['parents']=[]
                if label=='wrong_final':g['final_node_id']='absent'
                if label=='wrong_atom':g['nodes'][-1]['atom']='INVALID'
                a=measure.assess(p,g);b=_semantic(p,g)
                if not core.exact(a,b)or a['strict_valid']is not (label=='valid'):raise ValueError('graph calibration '+label)
                graph_checks+=1
    return {'contract':'v087-calibration-r1','provenance':'offline_and_synthetic','actual_qwen_calls':0,'rule_comparisons':total,'graph_comparisons':graph_checks,'passed':total+graph_checks,'failures':0,'checks':checks}


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();r=calibration();core.save(a.out,r);print(json.dumps({k:v for k,v in r.items()if k!='checks'},ensure_ascii=False));return 0
if __name__=='__main__':raise SystemExit(main())
