"""정답 제공 복사 진단에만 쓰는 공개 표본. 본 가설 실험의 입력에는 절대 넣지 않는다."""
from copy import deepcopy

def reference_record(problem_id):
    if problem_id=='K01':
        nodes=[{'id':'x0','atom':'Ca','rule':None,'parents':[]},
               {'id':'x1','atom':'Cb','rule':'k10','parents':['x0']},
               {'id':'x2','atom':'Cc','rule':'k17','parents':['x1']}]
    else:
        nodes=[{'id':'x0','atom':'Lp','rule':None,'parents':[]},
               {'id':'x1','atom':'Ls','rule':None,'parents':[]},
               {'id':'x2','atom':'Lq','rule':'r21','parents':['x0']},
               {'id':'x3','atom':'Lr','rule':'r57','parents':['x2','x1']},
               {'id':'x4','atom':'Lt','rule':'r04','parents':['x3']},
               {'id':'x5','atom':'Lg','rule':'r69','parents':['x4']}]
    views=[];lookup={};closure={}
    for n in nodes:
        key=n['id'];lookup[key]=n;closure[key]={key}.union(*(closure[p] for p in n['parents']))
        used=[x for x in nodes if x['id'] in closure[key]]
        atoms=sorted({x['atom'] for x in used});reverse={atom:'V'+str(i) for i,atom in enumerate(atoms)}
        views.append({'node_id':key,'representation':{'kind':'universal_schema',
            'quantifier':'forall_boolean_valuations','bindings':[{'variable':reverse[a],'atom':a} for a in atoms],
            'assumptions':[{'if':[reverse[lookup[p]['atom']] for p in x['parents']], 'then':reverse[x['atom']]} for x in used],
            'conclusion':reverse[n['atom']]}})
    return {'nodes':deepcopy(nodes),'final_node_id':nodes[-1]['id'],'node_views':views,
        'reviews':[{'id':'z0','target_kind':'acceptance_criterion','target':'valid_proof_and_goal',
                    'check':'counterexample_probe','probe':{'atom':nodes[-1]['atom'],'rule':None,'parents':[]},
                    'finding':{'answer_only_accepts':True,'proof_and_goal_accepts':False,'gap_detected':True}}]}
