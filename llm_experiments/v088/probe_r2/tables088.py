"""의미 판정 이후 공통 집계. 고정 이력 진단과 새 D 종단을 합산하지 않는다."""
from collections import Counter,defaultdict

def count(vals):
    vals=list(vals)
    return dict(planned=len(vals),observed=sum(v is not None for v in vals),success=sum(v is True for v in vals),failure=sum(v is False for v in vals),unobserved=sum(v is None for v in vals))

def joint(vals):
    vals=list(vals)
    if any(v is False for v in vals):return False
    if not vals or any(v is None for v in vals):return None
    return True

def rate(c):return c['success']/c['planned'] if c['planned'] and c['unobserved']==0 else None

def effect(pairs,problems,left,right,phase):
    per=[]
    for p in problems:
        selected=[x for x in pairs if x['problem_id']==p['id'] and x['phase']==phase]
        a=count(x['success']for x in selected if x['generator_arm']==left);b=count(x['success']for x in selected if x['generator_arm']==right)
        ar,br=rate(a),rate(b);delta=None if ar is None or br is None else br-ar
        per.append(dict(problem_id=p['id'],left=a,right=b,delta=delta))
    ds=[x['delta']for x in per];mean=None if any(x is None for x in ds)else sum(ds)/len(ds)
    return dict(phase=phase,left=left,right=right,per_structure=per,mean_delta=mean,
        improved=sum(d is not None and d>0 for d in ds),worse=sum(d is not None and d<0 for d in ds),same=sum(d==0 for d in ds),unobserved=sum(d is None for d in ds))

def aggregate(plan,rows,status,usage,state):
    s=plan['protocol'];groups={};pairs=[];robust=[]
    for phase,arms,key in [('rename_probe',s['probe_arms'],'probe_success'),('continuation',s['continuation_arms'],'continuation_success'),('end_to_end',s['monitor_arms'],'end_to_end_success')]:
        groups[phase]={}
        for arm in arms:
            rr=[r for r in rows if r['phase']==phase and r['generator_arm']==arm]
            g=dict(outcome=count(r[key]for r in rr))
            if phase!='rename_probe':
                g['graph_semantic']=count(r['generator_semantic_success']for r in rr)
                g['support_contract']=count(r['support_contract_success']for r in rr)
                by=defaultdict(list)
                for r in rr:by[r['pair_id']].append(r)
                pp=[]
                for pairid,rs in sorted(by.items()):
                    if len(rs)!=2 or {r['condition']for r in rs}!={'shallow','deep'}:raise ValueError('pair layout')
                    success=joint(r[key]for r in rs)
                    if success is True:
                        ordered=sorted(rs,key=lambda r:r['target_D'])
                        if not ordered[0]['actual_D']<ordered[1]['actual_D']:raise ValueError('pair depth not selective')
                    item=dict(pair_id=pairid,phase=phase,generator_arm=arm,problem_id=rs[0]['problem_id'],seed=rs[0]['seed'],success=success)
                    pairs.append(item);pp.append(item)
                g['bidirectional']=count(x['success']for x in pp)
                if phase=='end_to_end':
                    bundles=defaultdict(list)
                    for x in pp:bundles[(x['problem_id'],x['seed'])].append(x)
                    rb=[]
                    for (pid,seed),xs in sorted(bundles.items()):
                        if len(xs)!=4:raise ValueError('display bundle')
                        item=dict(problem_id=pid,seed=seed,generator_arm=arm,success=joint(x['success']for x in xs));rb.append(item);robust.append(item)
                    g['four_display']=count(x['success']for x in rb)
                    # 선택은 네/두 생성군마다 더하지 않고 아래 공통 필드에 한 번만 보고한다.
            groups[phase][arm]=g
    contrasts=[]
    for left,right in [s['primary_comparison']]+s['secondary_comparisons']:
        contrasts.append(effect(pairs,s['problems'],left,right,'continuation'))
    monitor=effect(pairs,s['problems'],'baseline','allocated_id','end_to_end')
    interactions=[]
    for p in s['problems']:
        rates={arm:rate(count(x['success']for x in pairs if x['phase']=='continuation' and x['generator_arm']==arm and x['problem_id']==p['id']))for arm in s['continuation_arms']}
        delta=None if any(v is None for v in rates.values())else rates['long_uniform']-rates['long_mixed']-rates['short_uniform']+rates['short_mixed']
        interactions.append(dict(problem_id=p['id'],delta=delta))
    mean_interaction=None if any(x['delta']is None for x in interactions)else sum(x['delta']for x in interactions)/len(interactions)
    if state != 'complete':
        for e in contrasts+[monitor]: e['mean_delta']=None
        mean_interaction=None
    selected=[r for r in rows if r['phase']=='end_to_end' and r['generator_arm']=='baseline']
    return dict(contract='v088-summary-r2',state=state,provenance=plan['provenance'],plan_sha256=plan['plan_sha256'],
        scope='기존 8구조 진단; 재명명 입력·과거 사실 prefix는 새 자율 증명 표본이 아님',
        main_question='동일 출력 ID에서 초기 사실 이름 통일이 후속 참조를 개선하는가',groups=groups,
        primary=contrasts[0],secondary=contrasts[1:],interaction=dict(per_structure=interactions,mean_delta=mean_interaction),
        monitor_comparison=monitor,shared_selection=count(r['selection_success']for r in selected),pairs=pairs,robust=robust,
        response_status_counts=dict(sorted(Counter(status.values()).items())),observed_call_records=len(usage),rows=rows,
        limitations=['연속 생성은 고정된 과거 유효 사실에서 시작하며 새 D 종단과 별도 평가한다.',
                    '문제·seed·표시·규칙 반복은 독립 구조 수가 아니다. 미관측을 오답/0깊이로 채우지 않는다.',
                    '이름 계열 대비는 길이만의 효과가 아니며 mixed 군의 원래 이름은 이력에 따라 이미 비슷할 수 있다.'])

def render(s):
    lines=['# v088 — ID 표현과 연속 참조 결과','',f"상태: {s['state']} / 출처: {s['provenance']}",'',
           '## A. 고정 유효 이력의 재명명 진단','', '| 군 | 규칙 성공 | 미관측 |','|---|---:|---:|']
    for a,g in s['groups']['rename_probe'].items():
        x=g['outcome'];lines.append(f"| {a} | {x['success']}/{x['planned']} | {x['unobserved']} |")
    lines+=['','## B. 과거 사실 prefix 이후의 새 연속 생성 — 전체 자율 종단이 아님','',
            '| 군 | 의미 graph | 계약 포함 연속 성공 | 양방향 | 미관측 |','|---|---:|---:|---:|---:|']
    for a,g in s['groups']['continuation'].items():
        v=g['outcome'];b=g['bidirectional'];m=g['graph_semantic'];lines.append(f"| {a} | {m['success']}/{m['planned']} | {v['success']}/{v['planned']} | {b['success']}/{b['planned']} | {v['unobserved']} |")
    d=s['primary']['mean_delta'];lines+=['',f"주평가 long_uniform − long_mixed: {'미관측 구조로 산출하지 않음' if d is None else format(d*100,'.4f')+'%p'}",'',
        '## C. 새 선택·새 facts부터 실행한 기존 D 종단 대조','', '| 군 | 실제 D 종단 | 양방향 | 네 표시 전체 |','|---|---:|---:|---:|']
    for a,g in s['groups']['end_to_end'].items():
        v=g['outcome'];b=g['bidirectional'];r=g['four_display'];lines.append(f"| {a} | {v['success']}/{v['planned']} | {b['success']}/{b['planned']} | {r['success']}/{r['planned']} |")
    q=s['shared_selection'];lines+=['',f"공통 선택: {q['success']}/{q['planned']} (생성군별 중복 합산 없음)",'','## 판정 범위','']+s['limitations']
    return '\n'.join(lines)+'\n'
