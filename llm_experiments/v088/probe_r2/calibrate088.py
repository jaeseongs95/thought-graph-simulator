"""측정기 반례 검산. 모델 추론 없이 기대 정오를 생산/독립 채점에 대조."""
from pathlib import Path
from copy import deepcopy
import argparse,json
import core088 as c,design088 as d,fixtures088 as f
import bridge088
from rows087 import rule_check
from audit_rows087 import step_check
from measure import assess
from audit_graph import _semantic

def correct_graph(problem,path):
    by={};nodes=[]
    for atom in problem['facts']:
        nid='fact_'+atom;by[atom]=nid;nodes.append(dict(id=nid,atom=atom,rule=None,parents=[]))
    for i,rid in enumerate(path):
        r=next(r for r in problem['rules']if r['id']==rid);nid='derived_'+str(i)
        nodes.append(dict(id=nid,atom=r['conclusion'],rule=rid,parents=[by[a]for a in r['premises']]));by[r['conclusion']]=nid
    return dict(nodes=nodes,final_node_id=by[problem['goal']])

def rename_graph(graph,style):
    # 테스트 입력의 일관된 이름 변경이다. 실제 관측 graph에는 적용하지 않는다.
    raw=[dict(source_slot_id='calibration',content=c.wire(dict(nodes=graph['nodes'])).decode())]
    h,m=d.rename_history(raw,style)
    return dict(nodes=c.load(h[0]['content'])['nodes'],final_node_id=m[graph['final_node_id']])

def calibration():
    checked=[]
    for a in d.anchors():
        for style in c.spec()['probe_arms']:
            body=deepcopy(a['request_body']);da=d.data_from(body);da['history'],_=d.rename_history(da['history'],style);body=d.render_body(body,da)
            before=d.history_nodes(da['history']);correct=c.load(c.load(f.answer(body))['message']['content'])['node']
            cases=[('valid',correct,True)]
            n=deepcopy(correct);n['parents']=n['parents'][1:];cases.append(('missing',n,False))
            n=deepcopy(correct);n['id']=before[0]['id'];cases.append(('duplicate',n,False))
            n=deepcopy(correct);n['rule']='unregistered';cases.append(('wrong_rule',n,False))
            for name,n,expected in cases:
                old=deepcopy(n);x=rule_check(da['problem'],before,n,a['rule_id']);y=step_check(da['problem'],before,n,a['rule_id'])
                if x!=y or x['valid']is not expected or n!=old:raise AssertionError((a['id'],style,name,x,y))
                checked.append(dict(kind='rule',case=a['id']+'/'+style+'/'+name,expected=expected))
    for p in c.spec()['problems']:
        for kind,path in c.spec()['reference_plans'][p['id']].items():
            for style in c.spec()['probe_arms']:
                g=rename_graph(correct_graph(p,path),style);cases=[('valid',g,True)]
                x=deepcopy(g);x['nodes'][-1]['parents']=x['nodes'][-1]['parents'][1:];cases.append(('missing_parent',x,False))
                x=deepcopy(g);x['nodes'][-1]['parents'][0]='does_not_exist';cases.append(('nonexistent_parent',x,False))
                x=deepcopy(g);x['nodes'][-1]['id']=x['nodes'][0]['id'];x['final_node_id']=x['nodes'][0]['id'];cases.append(('duplicate_id',x,False))
                x=deepcopy(g);x['nodes'][-1]['atom']='wrong_atom';cases.append(('wrong_atom',x,False))
                x=deepcopy(g);x['final_node_id']=x['nodes'][0]['id'];cases.append(('wrong_final',x,False))
                for name,x,expected in cases:
                    untouched=deepcopy(x);v=assess(p,x);w=_semantic(p,x)
                    if v!=w or v['strict_valid']is not expected or x!=untouched:raise AssertionError((p['id'],kind,style,name,v,w))
                    checked.append(dict(kind='graph',case=p['id']+'/'+kind+'/'+style+'/'+name,expected=expected))
    return dict(contract='v088-calibration-r2',provenance='synthetic_no_inference',passed=len(checked),failures=0,
        actual_qwen_calls=0,rule_cases=sum(x['kind']=='rule'for x in checked),graph_cases=sum(x['kind']=='graph'for x in checked),checks=checked)

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);a=p.parse_args();x=calibration();c.save(a.out,x);print(json.dumps({k:v for k,v in x.items()if k!='checks'},ensure_ascii=False));return 0
if __name__=='__main__':raise SystemExit(main())
