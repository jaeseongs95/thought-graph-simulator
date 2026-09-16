"""이미 계산된 원응답 판정의 집계·표시. 생산/독립 의미 판정과 분리된 공통 보고 함수."""
from collections import Counter,defaultdict


def counts(v):
    return {'assigned':len(v),'measured':sum(x is not None for x in v),'successes':sum(x is True for x in v),
            'failures':sum(x is False for x in v),'unmeasured':sum(x is None for x in v)}


def conj(v):return None if not v or any(x is None for x in v)else all(v)


def contrast(a,b):
    c={'both_success':0,'left_only':0,'right_only':0,'both_failure':0,'not_comparable':0}
    for x,y in zip(a,b):c['not_comparable'if x is None or y is None else'both_success'if x and y else'left_only'if x else'right_only'if y else'both_failure']+=1
    return c


def aggregate(plan,rows,statuses,usages,state):
    s=plan['protocol'];arms=list(s['factors']);main=[r for r in rows if r['phase']=='end_to_end'];local=[r for r in rows if r['phase']=='rule_probe']
    pairs=[];robust=[];groups={}
    for key in sorted({r['pair_id']for r in main}):
        rr=sorted([r for r in main if r['pair_id']==key],key=lambda r:r['condition']!='shallow');lo=rr[0]
        if len(rr)!=2:raise ValueError('pair assignment')
        pairs.append({k:lo[k]for k in ('pair_id','base_pair_id','problem_id','seed','generator_arm','order','labels')}|
                     {'selection_success':conj([r['selection_success']for r in rr]),
                      'end_to_end_success':conj([r['end_to_end_success']for r in rr])})
    for arm in arms:
        for p in s['problems']:
            for seed in s['seeds']:
                rr=[r for r in pairs if r['generator_arm']==arm and r['problem_id']==p['id']and r['seed']==seed]
                if len(rr)!=4:raise ValueError('robust assignment')
                robust.append({'generator_arm':arm,'problem_id':p['id'],'seed':seed,
                               'selection_success':conj([r['selection_success']for r in rr]),'end_to_end_success':conj([r['end_to_end_success']for r in rr])})
        mr=[r for r in main if r['generator_arm']==arm];lr=[r for r in local if r['generator_arm']==arm];pr=[r for r in pairs if r['generator_arm']==arm];rb=[r for r in robust if r['generator_arm']==arm]
        groups[arm]={'selection':counts([r['selection_success']for r in mr]),'generation_semantic':counts([r['generator_semantic_success']for r in mr]),
                     'generation_with_support_contract':counts([r['generator_success']for r in mr]),'D_end_to_end':counts([r['end_to_end_success']for r in mr]),
                     'D_bidirectional':counts([r['end_to_end_success']for r in pr]),'all_presentations':counts([r['end_to_end_success']for r in rb]),
                     'rule_probe_semantic':counts([r['node_semantic_success']for r in lr]),'rule_probe_strict':counts([r['probe_success']for r in lr])}
    structural=[]
    for p in s['problems']:
        row={'problem_id':p['id'],'arms':{},'contrasts':{}}
        for arm in arms:
            pp=[r['end_to_end_success']for r in pairs if r['problem_id']==p['id']and r['generator_arm']==arm]
            row['arms'][arm]=counts(pp)
        def rate(arm):
            c=row['arms'][arm];return None if c['unmeasured'] else c['successes']/c['assigned']
        b,i,n,both=[rate(a)for a in arms]
        for arm in arms[1:]:row['contrasts'][arm+'_minus_baseline']=None if b is None or rate(arm)is None else rate(arm)-b
        row['inventory_main_effect']=None if any(v is None for v in (b,i,n,both))else((i-b)+(both-n))/2
        row['id_main_effect']=None if any(v is None for v in (b,i,n,both))else((n-b)+(both-i))/2
        row['interaction']=None if any(v is None for v in (b,i,n,both))else both-i-n+b
        structural.append(row)
    effects={}
    for key in [a+'_minus_baseline'for a in arms[1:]]+['inventory_main_effect','id_main_effect','interaction']:
        values=[r['contrasts'].get(key)if key in r['contrasts']else r[key]for r in structural]
        effects[key]={'equal_structure_mean':None if any(v is None for v in values)else sum(values)/len(values),
                      'positive_structures':sum(v is not None and v>0 for v in values),'negative_structures':sum(v is not None and v<0 for v in values),
                      'zero_structures':sum(v==0 for v in values),'unmeasured_structures':sum(v is None for v in values)}
    gains={}
    for arm in arms[1:]:
        left=sorted([r for r in main if r['generator_arm']=='baseline'],key=lambda r:r['unit_id']);right=sorted([r for r in main if r['generator_arm']==arm],key=lambda r:r['unit_id'])
        pp=sorted([r for r in pairs if r['generator_arm']=='baseline'],key=lambda r:r['base_pair_id']);qq=sorted([r for r in pairs if r['generator_arm']==arm],key=lambda r:r['base_pair_id'])
        aa=sorted([r for r in local if r['generator_arm']=='baseline'],key=lambda r:r['unit_id']);bb=sorted([r for r in local if r['generator_arm']==arm],key=lambda r:r['unit_id'])
        gains[arm]={'D_end_to_end':contrast([r['end_to_end_success']for r in left],[r['end_to_end_success']for r in right]),
                    'D_bidirectional':contrast([r['end_to_end_success']for r in pp],[r['end_to_end_success']for r in qq]),
                    'rule_probe':contrast([r['probe_success']for r in aa],[r['probe_success']for r in bb])}
    # 선택 호출 공유: 같은 128개 원문을 네 배의 선택 표본/비용으로 세지 않는다.
    selections=[r for r in main if r['generator_arm']=='baseline']
    usagegroup=defaultdict(list);slotmap={o['id']:o for o in plan['slots']};trialmap={t['id']:t for t in plan['trials']}
    for sid,u in usages.items():
        o=slotmap[sid];t=trialmap[o['trial_id']]
        k='shared_selection'if o['stage']in ('compare','select')else t['phase']+'_'+t['generator_arm'];usagegroup[k].append(u)
    usage={k:{'observed_calls':len(v),'fields':{f:{'sum_observed':sum(u[f]for u in v if u.get(f)is not None),'missing':sum(u.get(f)is None for u in v)}for f in ('prompt_eval_count','eval_count','total_duration','prompt_eval_duration','eval_duration')}}for k,v in sorted(usagegroup.items())}
    features={}
    for arm in arms:
        for arity in (1,2,3):
            for reuse in (False,True):
                rr=[r for r in local if r['generator_arm']==arm and r['features']=={'premise_count':arity,'has_ancestor_among_direct_premises':reuse}]
                features[f'{arm}/arity_{arity}/ancestor_{int(reuse)}']=counts([r['probe_success']for r in rr])
    return {'contract':'v087-summary-r1','provenance':plan['provenance'],'state':state,'groups':groups,
            'primary_effect':effects['inventory_allocated_minus_baseline'],'factorial_effects':effects,'structural_rows':structural,
            'paired_contrasts':gains,'shared_selection':counts([r['selection_success']for r in selections]),
            'shared_selection_calls_assigned':256,'distinct_observed_structures':8,'new_holdout_structures':0,
            'rule_probe_is_not_end_to_end':True,'rule_probe_feature_strata_observational':features,
            'response_statuses':dict(sorted(Counter(statuses.values()).items())),'usage_by_phase_and_arm':usage,
            'trials':main,'rule_probes':local,'pairs':pairs,'robust':robust,
            'decision':'사전 고정한 2×2 절차 효과를 기존 관측 구조에서 비교한다. 진단과 종단, 노드 지원 계약과 실제 graph를 분리한다. 이 배치 결과로 소급 수정·군 선택·자동 재실행하지 않는다.'}


def render(s):
    text=['# v087 — 부모 노드 정보 × 새 ID 지원 대조','',f"출처: {s['provenance']} / 상태: {s['state']}",'',
          '**합성 실행은 모델 연구 결과가 아니다. U01~U08은 기존 관측 진단 집합이며 새 holdout이 아니다.**','',
          '| 생성군 | 규칙 진단(계약 포함) | 유효 생성 | D 종단 | 양방향 D | 네 표시 전체 |','|---|---:|---:|---:|---:|---:|']
    def c(x):return f"{x['successes']}/{x['assigned']} (미관측 {x['unmeasured']})"
    for arm,g in s['groups'].items():text.append('| '+arm+' | '+' | '.join(c(g[k])for k in ('rule_probe_strict','generation_with_support_contract','D_end_to_end','D_bidirectional','all_presentations'))+' |')
    e=s['primary_effect']['equal_structure_mean'];text+=['',f"주평가: inventory_allocated − baseline, 구조 동일 가중치 = {'미산출'if e is None else f'{100*e:+.4f}%p'}",'',
        '선택은 128조건에서 비교·조회 256호출을 한 번씩 수행해 네 군이 원문을 공유한다. 선택 512독립 표본으로 합산하지 않는다.',
        '규칙 진단은 과거의 동일한 유효 직전 이력 위에서 한 규칙만 새로 실행한다. 전체 종단 결과에 합산하지 않는다.',
        '노드 표는 정답 부모가 아니라 실제 이력의 모든 id/atom 행이다. 잘못된 원자·중복 id도 보존한다.',
        '새 ID 군은 실행기가 새 식별자만 지원하며 모델의 자력 식별자 관리 성과로 표현하지 않는다.',
        '군 간 원문 이력이 달라질 수 있어 종단 차이는 지원 절차 전체의 효과다. 정확한 구조별 메커니즘은 진단 집계와 대조한다.','',
        '| 구조 | baseline | node_inventory | allocated_id | inventory_allocated |','|---|---:|---:|---:|---:|']
    for r in s['structural_rows']:text.append('| '+r['problem_id']+' | '+' | '.join(c(x)for x in r['arms'].values())+' |')
    text+=['','## 판정 범위','새로운 깊이 대조·선택기 ablation·W 수정·자력 D 계산·새 holdout은 이 배치에서 수행하지 않는다.','자동 반복·사후 보정·성공 사례만 선택은 하지 않는다.']
    return '\n'.join(text)+'\n'
