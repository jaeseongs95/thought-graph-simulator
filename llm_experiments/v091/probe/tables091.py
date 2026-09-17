"""공유 집계·한국어 보고. 핵심 수치는 audit_metrics091으로 별도 재계산한다."""
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


def aggregate_cohort(plan,rows,status,usage,state):
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
    return dict(contract='v091-summary-r1',state=state,provenance=plan['provenance'],plan_sha256=plan['plan_sha256'],
        scope='단일 cohort의 새 선택·새 facts 4군 D 종단 대조',
        groups={'end_to_end':groups},primary=primary,secondary=secondary,
        paired_outcomes=[paired(rows,a,b) for a,b in [s['primary_comparison']]+s['secondary_comparisons']],
        shared_selection=selections['end_to_end_selection'],shared_selection_stages=selections,
        pairs=pairs,robust=robust,response_status_counts=dict(sorted(Counter(status.values()).items())),
        observed_call_records=len(usage),rows=rows,
        limitations=['과거 유효 facts/graph는 생성 입력으로 재사용하지 않는다. 네 군 모두 새 facts를 모델이 출력한다.',
            'baseline은 기존 자유 ID 계약이다. 세 지정군은 공개 facts ID 표와 현재 규칙 ID 지원이 추가된다.',
            '의미 명명만의 효과는 같은 지원 수준인 short_uniform과의 보조 대조로 구별한다.',
            '같은 선택 응답 128개를 네 군이 공유하며 선택/호출을 4배로 세지 않는다.',
            '이 cohort의 구조별 결과다. seed·표시 반복을 독립 모집단 표본으로 해석하지 않는다.',
            '부분 배치/미관측에서 전체 주평가를 계산하지 않는다. 원문 ID·전제·경로를 보정하지 않는다.',
            '동일 원자를 중복 도출하지 않는 현재 primitive 경로에서만 의미 ID의 유일성을 보장한다.',
            '일부 보고 집계는 공유한다. 핵심 집계는 audit_metrics091으로 별도 확인한다.'])



def renaming_contrast(rows,pairs,arms,state):
    result=[]
    for arm in arms:
        left=[r for r in rows if r['cohort']=='known_original' and r['generator_arm']==arm]
        right=[r for r in rows if r['cohort']=='known_renamed' and r['generator_arm']==arm]
        key=lambda r:(r['topology_id'],r['seed'],r['order'],r['labels'],r['condition'])
        aa={key(r):r for r in left};bb={key(r):r for r in right}
        if aa.keys()!=bb.keys():raise ValueError('재명명 대응 단위 불일치')
        labels=Counter();transitions=Counter();items=[]
        for k in sorted(aa):
            a,b=aa[k],bb[k];x,y=a['end_to_end_success'],b['end_to_end_success']
            label='unobserved' if x is None or y is None else 'both_success' if x and y else 'original_only' if x else 'renamed_only' if y else 'both_failure'
            labels[label]+=1;transitions[first_error(a),first_error(b)]+=1
            items.append(dict(topology_id=k[0],seed=k[1],order=k[2],labels=k[3],condition=k[4],original=x,renamed=y))
        per=[]
        for topology in sorted({r['topology_id'] for r in left}):
            pp=[]
            for cohort in ('known_original','known_renamed'):
                vals=[q['success'] for q in pairs if q['topology_id']==topology and q['cohort']==cohort and q['generator_arm']==arm]
                pp.append(count(vals))
            a,b=map(rate,pp);per.append(dict(topology_id=topology,original=pp[0],renamed=pp[1],delta=None if a is None or b is None else b-a))
        ds=[q['delta'] for q in per]
        result.append(dict(generator_arm=arm,planned=len(items),outcomes=dict(labels),per_topology=per,
            mean_delta=None if state!='complete' or None in ds else sum(ds)/len(ds),
            paired_trials=items,error_transitions=[dict(original=x,renamed=y,count=n) for (x,y),n in sorted(transitions.items())],
            scope='same topology, one prespecified renamed surface; not new structures or additional independent problems'))
    return result


def aggregate(plan,rows,status,usage,state):
    s=plan['protocol'];cohorts={};pairs=[];robust=[]
    for cohort in s['cohorts']:
        rr=[r for r in rows if r['cohort']==cohort];pids={r['problem_id'] for r in rr}
        trials=[t for t in plan['trials'] if t['cohort']==cohort];tids={t['id'] for t in trials}
        slots=[o for o in plan['slots'] if o['trial_id'] in tids];ids={o['id'] for o in slots}
        view=dict(plan,protocol=dict(s,problems=[p for p in s['problems'] if p['id'] in pids]),trials=trials,slots=slots)
        sub=aggregate_cohort(view,rr,{k:v for k,v in status.items() if k in ids},{k:v for k,v in usage.items() if k in ids},state)
        if cohort!='new_topology':sub['primary']['definition']='보조 확인: '+cohort+' 내 alias − baseline. 신규 구조 주평가와 합산하지 않음.'
        index={r['base_pair_id']:r for r in rr}
        for q in sub['pairs']:
            q.update(cohort=cohort,topology_id=index[q['base_pair_id']]['topology_id'],renaming_id=index[q['base_pair_id']]['renaming_id'])
        for q in sub['robust']:q['cohort']=cohort
        pairs.extend(sub['pairs']);robust.extend(sub['robust'])
        sub['scope']=cohort
        sub['limitations']=[]
        sub.pop('rows');cohorts[cohort]=sub
    primary=dict(cohorts['new_topology']['primary'],cohort='new_topology')
    return dict(contract='v091-summary-r1',state=state,provenance=plan['provenance'],plan_sha256=plan['plan_sha256'],
        scope='동결 v090 생성기: known original / bijective renaming / new topology 별도 평가',
        primary=primary,secondary=cohorts['new_topology']['secondary'],shared_selection=count({r['unit_id']:r['selection_success'] for r in rows}.values()),cohorts=cohorts,renaming_contrasts=renaming_contrast(rows,pairs,s['generator_arms'],state),
        pairs=pairs,robust=robust,rows=rows,observed_call_records=len(usage),response_status_counts=dict(sorted(Counter(status.values()).items())),
        limitations=['주평가는 신규 V01~V08의 alias−baseline만 사용한다. 기존/재명명은 보조 평가다.',
        '원형과 R1은 같은 8개 구조다. 새로운 독립 구조로 더하지 않는다. 새 구조는 별도의 8개다.',
        '구조 생성은 사전 제약하 첫 적격 채택이며 모델 출력에 기초한 선별이 아니다. IID 모집단 추정은 하지 않는다.',
        '새 경로는 D/W/facts 수/전제 수 범위를 맞췄으나 각 규칙의 전제 수나 결합 모양은 달라질 수 있다.',
        '동일 구조 재명명에는 원자명과 규칙명 변화가 모두 포함된다. 토큰화나 특정 필드 단독 효과로 쓰지 않는다.',
        '기존 source_id 입력 정책은 유지하고 재명명 비교의 논리 표지는 맞춘다. 실제 metadata 제거 처치는 하지 않는다.',
        '이전 부모 배열 재사용은 관측 진단이지 내부 복사 기제의 증명 또는 사후 수정 근거가 아니다.',
        '외부 정답 D, 지정 경로/규칙/ID 지원을 유지한다. 부모는 모델이 출력하고 모든 원응답을 무보정으로 전달한다.',
        '합성 시험·검산·재명명/seed/표시 반복을 새 실제 연구 표본으로 합산하지 않는다.',
        '부분 batch는 전체 주평가를 산출하지 않는다. 실행되지 않은 값을 실패나 깊이0으로 대체하지 않는다.'])


def render(s):
    fmt=lambda x:f"{x['success']}/{x['planned']}"
    lines=['# v091 동결 생성기의 구조·재명명 분리 평가','',f"상태: {s['state']} / 출처: {s['provenance']}"]
    for cohort,sub in s['cohorts'].items():
        lines+=['','## '+cohort,'| 군 | 새 facts | ID 계약 | D 종단 | 양방향 | 네 표시 | 미관측 |','|---|---:|---:|---:|---:|---:|---:|']
        for arm,g in sub['groups']['end_to_end'].items():
            lines.append('| '+arm+' | '+' | '.join(fmt(g[k]) for k in ('fresh_facts','support_contract','outcome','bidirectional','four_display'))+f" | {g['outcome']['unobserved']} |")
        delta=sub['primary']['mean_delta'];lines.append('alias − baseline 양방향 차이: '+('미산출' if delta is None else f'{delta*100:.4f}%p'))
        lines.append('공통 선택: '+fmt(sub['shared_selection']))
    p=s['primary'];delta=p['mean_delta']
    lines+=['','## 사전 주평가: 신규 구조만',p['definition'],'결과: '+('부분/미관측으로 산출하지 않음' if delta is None else f'{delta*100:.4f}%p'),'',
        '## 동일 구조 재명명: 원형 대비 차이']
    for row in s['renaming_contrasts']:
        d=row['mean_delta'];lines.append(row['generator_arm']+': '+('미산출' if d is None else f'{d*100:.4f}%p'))
    return '\n'.join(lines+['','## 해석 범위']+s['limitations'])+'\n'
