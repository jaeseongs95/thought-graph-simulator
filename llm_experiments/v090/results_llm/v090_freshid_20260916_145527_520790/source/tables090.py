"""공유 집계·한국어 보고. 핵심 수치는 audit_metrics090으로 별도 재계산한다."""
from collections import Counter,defaultdict


def count(values):
    values=list(values)
    return dict(planned=len(values),success=sum(x is True for x in values),
                failure=sum(x is False for x in values),unobserved=sum(x is None for x in values))


def rate(x):
    return None if x['unobserved'] or not x['planned'] else x['success']/x['planned']


def joint(values):
    values=list(values)
    return False if any(x is False for x in values) else None if any(x is None for x in values) else True


def generation_error(row):
    if row['generator_success'] is True:
        return 'success'
    for x in row['step_checks']:
        if x['valid'] is False:
            errors=x.get('error_codes') or []
            for e in ('missing_parent','premise_counter_mismatch','initial_fact_multiset','duplicate_node_id'):
                if e in errors:
                    return e
            return '+'.join(errors) or 'invalid_step'
        if x.get('support_contract_success') is False:
            return 'facts_id_contract' if x['stage']=='facts' else 'rule_id_contract'
        if x['status'] in ('invalid_json','invalid_schema'):
            return x['status']
        if x['status']!='ok':
            return 'unobserved_or_incomplete:'+x['status']
    return 'unobserved' if row['generator_success'] is None else 'graph_or_route_failure'


def first_error(row):
    if row['end_to_end_success'] is True:
        return 'success'
    if row['selection_success'] is False:
        return 'selection_failure'
    if row['selection_success'] is None:
        return 'selection_unobserved'
    return generation_error(row)


def paired(rows,left,right,key='end_to_end_success'):
    a={r['unit_id']:r for r in rows if r['generator_arm']==left}
    b={r['unit_id']:r for r in rows if r['generator_arm']==right}
    if a.keys()!=b.keys():
        raise ValueError('대응 경로 집합 불일치')
    results=Counter()
    transitions=Counter()
    for k in a:
        x,y=a[k][key],b[k][key]
        label='unobserved' if x is None or y is None else 'both_success' if x and y else 'left_only' if x else 'right_only' if y else 'both_failure'
        results[label]+=1
        transitions[first_error(a[k]),first_error(b[k])]+=1
    return dict(left=left,right=right,planned=len(a),
        **{k:results[k] for k in ('both_success','left_only','right_only','both_failure','unobserved')},
        error_transitions=[dict(left_outcome=x,right_outcome=y,count=n) for (x,y),n in sorted(transitions.items())])


def contrast(pairs,problems,left,right,state):
    out=[]
    for p in problems:
        subset=[r for r in pairs if r['problem_id']==p['id']]
        a=count(x['success'] for x in subset if x['generator_arm']==left)
        b=count(x['success'] for x in subset if x['generator_arm']==right)
        ar,br=rate(a),rate(b)
        out.append(dict(problem_id=p['id'],left=a,right=b,delta=None if ar is None or br is None else br-ar))
    ds=[x['delta'] for x in out]
    mean=None if state!='complete' or any(x is None for x in ds) else sum(ds)/len(ds)
    loo=[] if mean is None else [dict(omitted_structure=x['problem_id'],mean_delta=(sum(ds)-x['delta'])/(len(ds)-1)) for x in out]
    return dict(left=left,right=right,per_structure=out,mean_delta=mean,leave_one_structure_out=loo,
                unit='fresh end-to-end bidirectional pairs; equal weight per structure',
                sensitivity_is_not_confidence_interval=True)


def aggregate(plan,rows,status,usage,state):
    s=plan['protocol'];groups={};pairs=[];robust=[]
    for arm in s['generator_arms']:
        rr=[r for r in rows if r['generator_arm']==arm]
        bins=defaultdict(list)
        for r in rr:
            bins[r['pair_id']].append(r)
        aps=[]
        for pid,values in sorted(bins.items()):
            if len(values)!=2 or {r['condition'] for r in values}!={'shallow','deep'}:
                raise ValueError('양방향 배정 불일치')
            sh=next(r['end_to_end_success'] for r in values if r['condition']=='shallow')
            dp=next(r['end_to_end_success'] for r in values if r['condition']=='deep')
            item=dict(pair_id=pid,base_pair_id=values[0]['base_pair_id'],phase='end_to_end',generator_arm=arm,
                problem_id=values[0]['problem_id'],seed=values[0]['seed'],order=values[0]['order'],labels=values[0]['labels'],
                shallow=sh,deep=dp,success=joint([sh,dp]))
            aps.append(item);pairs.append(item)
        bundles=defaultdict(list)
        for p in aps:
            bundles[p['problem_id'],p['seed']].append(p)
        rb=[]
        for (pid,seed),values in sorted(bundles.items()):
            if len(values)!=4 or len({(x['order'],x['labels']) for x in values})!=4:
                raise ValueError('네 표시 bundle 불일치')
            item=dict(problem_id=pid,seed=seed,generator_arm=arm,success=joint(x['success'] for x in values))
            rb.append(item);robust.append(item)
        g=dict(outcome=count(r['end_to_end_success'] for r in rr),
            graph_semantic=count(r['generator_semantic_success'] for r in rr),
            support_contract=count(r['support_contract_success'] for r in rr),
            fresh_facts=count(r['initial_fact_success'] for r in rr),facts_id_contract=count(r['initial_id_contract_success'] for r in rr),
            bidirectional=count(p['success'] for p in aps),four_display=count(p['success'] for p in rb),
            first_errors=dict(sorted(Counter(first_error(r) for r in rr).items())),
            generation_first_errors=dict(sorted(Counter(generation_error(r) for r in rr).items())),
            pair_distribution=dict(both_success=sum(p['shallow'] is True and p['deep'] is True for p in aps),
                only_one_success=sum((p['shallow'] is True and p['deep'] is False) or (p['shallow'] is False and p['deep'] is True) for p in aps),
                both_failed=sum(p['shallow'] is False and p['deep'] is False for p in aps),
                incomplete=sum(p['shallow'] is None or p['deep'] is None for p in aps)),
            per_structure={p['id']:dict(outcome=count(r['end_to_end_success'] for r in rr if r['problem_id']==p['id']),
                bidirectional=count(x['success'] for x in aps if x['problem_id']==p['id'])) for p in s['problems']},
            by_target_depth={str(d):count(r['end_to_end_success'] for r in rr if r['target_D']==d) for d in sorted({r['target_D'] for r in rr})},
            conditional_after_correct_selection=count(r['generator_success'] for r in rr if r['selection_success'] is True))
        groups[arm]=g
    primary=contrast(pairs,s['problems'],*s['primary_comparison'],state)
    primary['definition']=s['primary_definition']
    secondary=[contrast(pairs,s['problems'],a,b,state) for a,b in s['secondary_comparisons']]
    unique={}
    for r in rows:
        vals=tuple(r[k] for k in ('comparison_success','lookup_adherence','final_choice_success','selection_success'))
        if r['unit_id'] in unique and unique[r['unit_id']]!=vals:
            raise ValueError('공유 선택 판정이 생성군마다 다름')
        unique[r['unit_id']]=vals
    selections={k:count(v[i] for v in unique.values()) for i,k in enumerate(('comparison','lookup','choice','end_to_end_selection'))}
    return dict(contract='v090-summary-r1',state=state,provenance=plan['provenance'],plan_sha256=plan['plan_sha256'],
        scope='기존 U01~U08; 새 공통 선택 및 군별 새 facts 생성의 4군 D 종단 대조',
        groups={'end_to_end':groups},primary=primary,secondary=secondary,
        paired_outcomes=[paired(rows,a,b) for a,b in [s['primary_comparison']]+s['secondary_comparisons']],
        shared_selection=selections['end_to_end_selection'],shared_selection_stages=selections,
        pairs=pairs,robust=robust,response_status_counts=dict(sorted(Counter(status.values()).items())),
        observed_call_records=len(usage),rows=rows,
        limitations=['과거 유효 facts/graph는 생성 입력으로 재사용하지 않는다. 네 군 모두 새 facts를 모델이 출력한다.',
            'baseline은 기존 자유 ID 계약이다. 세 지정군은 공개 facts ID 표와 현재 규칙 ID 지원이 추가된다.',
            '의미 명명만의 효과는 같은 지원 수준인 short_uniform과의 보조 대조로 구별한다.',
            '같은 선택 응답 128개를 네 군이 공유하며 선택/호출을 4배로 세지 않는다.',
            '독립 구조는 기존 8개다. seed·표시 반복을 독립 모집단 표본으로 해석하지 않는다.',
            '부분 배치/미관측에서 전체 주평가를 계산하지 않는다. 원문 ID·전제·경로를 보정하지 않는다.',
            '동일 원자를 중복 도출하지 않는 현재 primitive 경로에서만 의미 ID의 유일성을 보장한다.',
            '일부 보고 집계는 공유한다. 핵심 집계는 audit_metrics090으로 별도 확인한다.'])


def render(s):
    lines=['# v090 새 선택·새 facts의 의미 ID D 종단 대조','',
        f"상태: {s['state']} / 출처: {s['provenance']}",'',
        '| 생성군 | 새 facts 의미 성공 | ID 계약 성공 | D 종단 | 양방향 | 네 표시 전체 | 미관측 |',
        '|---|---:|---:|---:|---:|---:|---:|']
    fmt=lambda x:f"{x['success']}/{x['planned']}"
    for arm,g in s['groups']['end_to_end'].items():
        lines.append('| '+arm+' | '+' | '.join(fmt(g[k]) for k in ('fresh_facts','support_contract','outcome','bidirectional','four_display'))+f" | {g['outcome']['unobserved']} |")
    p=s['primary'];d=p['mean_delta']
    lines+=['','## 사전 주평가',p['definition'],'차이: '+('부분 실행/미관측으로 산출하지 않음' if d is None else f'{d*100:.4f}%p'),
        '',f"공통 two-stage 선택: {fmt(s['shared_selection'])}",'','## 보조 대비']
    for x in s['secondary']:
        lines.append(f"{x['right']} − {x['left']}: "+('미산출' if x['mean_delta'] is None else f"{x['mean_delta']*100:.4f}%p"))
    return '\n'.join(lines+['','## 해석 범위']+s['limitations'])+'\n'
