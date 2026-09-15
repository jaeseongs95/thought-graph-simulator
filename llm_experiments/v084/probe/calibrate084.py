"""측정 도구의 오프라인 교정. 합성 graph만 검사하며 모델을 호출하지 않는다."""
from copy import deepcopy
from itertools import permutations
import argparse,json
from pathlib import Path
import bootstrap
import measure
from audit_graph import _semantic
import core084


def proof(problem,route):
    """사전 규칙으로 만드는 합성 정답. 실행 요청 생성기에서는 사용하지 않는다."""
    nodes=[{'id':f'f{i}','atom':a,'rule':None,'parents':[]} for i,a in enumerate(problem['facts'])]
    known={n['atom']:n['id'] for n in nodes};rules={r['id']:r for r in problem['rules']}
    for i,rid in enumerate(route):
        r=rules[rid];nid=f'n{i}'
        nodes.append({'id':nid,'atom':r['conclusion'],'rule':rid,'parents':[known[a] for a in r['premises']]})
        known[r['conclusion']]=nid
    return {'nodes':nodes,'final_node_id':known[problem['goal']]}


def describe(graph):
    ds={};layer={};max_fanin=0
    for n in graph['nodes']:
        d=0 if n['rule'] is None else 1+max(ds[p] for p in n['parents'])
        ds[n['id']]=d
        if n['rule'] is not None:
            layer[d]=layer.get(d,0)+1;max_fanin=max(max_fanin,len(n['parents']))
    w=sum(n['rule'] is not None for n in graph['nodes'])
    return {'D':ds[graph['final_node_id']],'W':w,'max_derived_layer_width':max(layer.values()),
            'max_rule_premises':max_fanin,'serial_generator_calls':w+2}



def expand_declared_macro(macro_rule, primitive_problem, expansion_ids):
    """명시된 외부 입·출력 계약 아래에서만 macro 전개를 허용한다."""
    if sorted(macro_rule['premises']) != sorted(primitive_problem['facts']):
        raise ValueError('macro input interface mismatch')
    if macro_rule['conclusion'] != primitive_problem['goal']:
        raise ValueError('macro output interface mismatch')
    expanded = proof(primitive_problem, expansion_ids)
    if measure.assess(primitive_problem, expanded)['strict_valid'] is not True:
        raise ValueError('invalid primitive expansion')
    if _semantic(primitive_problem, expanded)['strict_valid'] is not True:
        raise ValueError('independent expansion validation failed')
    return expanded


def calibration():
    s=core084.spec();checks=[];structures=[]
    def check(name,p,g,expected_D,valid=True):
        a=measure.assess(p,g);b=_semantic(p,g)
        if a != b: raise ValueError(repr((name, a, b)))
        if a['strict_valid'] is not valid: raise ValueError(repr((name, a)))
        if a['actual_D'] != expected_D: raise ValueError(repr((name, a)))
        checks.append({'name':name,'passed':True,'actual_D':a['actual_D'],'strict_valid':a['strict_valid']})
    for p in s['problems']:
        for i,key in enumerate(s['reference_conditions']):
            route=s['reference_plans'][p['id']][key];g=proof(p,route);d=s['depth_ranges'][p['id']][i]
            check(p['id']+'/'+key,p,g,d);structures.append({'problem':p['id'],'route':key,**describe(g)})
            # 기호 전단사 재명명: 문제/규칙/실제 연결을 함께 바꾼다.
            p2=deepcopy(p);g2=deepcopy(g)
            for f in range(len(p2['facts'])):p2['facts'][f]='a_'+p2['facts'][f]
            p2['goal']='a_'+p2['goal']
            for r in p2['rules']:
                r['id']='r_'+r['id'];r['premises']=['a_'+x for x in r['premises']];r['conclusion']='a_'+r['conclusion']
            for n in g2['nodes']:
                n['id']='node_'+n['id'];n['atom']='a_'+n['atom'];n['parents']=['node_'+x for x in n['parents']]
                if n['rule'] is not None:n['rule']='r_'+n['rule']
            g2['final_node_id']='node_'+g2['final_node_id']
            check(p['id']+'/'+key+'/rename',p2,g2,d)
            # 규칙 사전 나열을 바꿔도 동일한 graph의 D는 같다.
            p3=deepcopy(p);p3['rules'].reverse();check(p['id']+'/'+key+'/dictionary_order',p3,g,d)
            facts=[n for n in g['nodes'] if n['rule'] is None];derived=[n for n in g['nodes'] if n['rule'] is not None]
            serial=0
            for order in permutations(derived):
                seen={n['id'] for n in facts};okay=True
                for n in order:
                    if not set(n['parents'])<=seen:okay=False;break
                    seen.add(n['id'])
                if not okay:continue
                for fs in (facts,facts[::-1]):
                    serial+=1;reordered={'nodes':fs+list(order),'final_node_id':g['final_node_id']}
                    check(p['id']+'/'+key+f'/legal_linearization_{serial}',p,reordered,d)
            padded=deepcopy(g)
            padded['nodes'].insert(0,{'id':'padding','atom':p['facts'][0],'rule':None,'parents':[]})
            check(p['id']+'/'+key+'/unused_padding_rejected',p,padded,None,False)
            broken=deepcopy(g);broken['nodes'][-1]['parents']=[]
            check(p['id']+'/'+key+'/missing_parent_rejected',p,broken,None,False)
    # 표현 단위를 바꾸는 경우: 허용된 macro와 그 전개를 명시해야 비교가 가능하다.
    primitive={'id':'calibration','facts':['A'],'rules':[{'id':'p','premises':['A'],'conclusion':'B'},{'id':'q','premises':['B'],'conclusion':'G'}],'goal':'G'}
    macro={'id':'macro_calibration','facts':['A'],'rules':[{'id':'m','premises':['A'],'conclusion':'G'}],'goal':'G'}
    gp=proof(primitive,['p','q']);gm=proof(macro,['m'])
    check('primitive_representation',primitive,gp,2);check('macro_representation',macro,gm,1)
    # 고정된 명시적 인증서다. 모델 응답을 재채점하거나 실제 실험의 단위를 바꾸지 않는다.
    certificate={'macro_rule':'m','primitive_expansion':['p','q'],'input':['A'],'output':'G'}
    expanded=expand_declared_macro(macro['rules'][0],primitive,certificate['primitive_expansion'])
    check('declared_macro_expansion',primitive,expanded,2)
    return {'contract':'v084-offline-calibration-r1','provenance':'synthetic_offline_no_model_calls',
            'checks':checks,'passed':len(checks),'failed':0,'structures':structures,
            'macro_example':{'raw_primitive_D':2,'raw_macro_D':1,'expanded_in_fixed_primitive_system_D':2,'certificate':certificate,
                             'interpretation':'D는 선택한 추론 단위에 상대적이다. 인증된 전개 없이 추상 규칙의 내적 깊이를 추측하지 않는다.'},
            'scope':'측정기의 기호/나열 불변성과 단위 의존성을 확인했다. 모델의 재명명/나열 강건성 또는 인간 사고 타당도를 검증한 결과가 아니다.'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path);a=p.parse_args();r=calibration()
    text=json.dumps(r,ensure_ascii=False,indent=2)+'\n'
    if a.out:core084.write(a.out,text.encode('utf-8'))
    print(json.dumps({'passed':r['passed'],'failed':r['failed'],'actual_model_inference':0},ensure_ascii=False))
if __name__=='__main__':main()
