"""생산/독립 의미 판정 뒤의 공유 집계. 미관측을 실패로 채우지 않는다."""
from collections import Counter, defaultdict

def count(values):
    values = list(values)
    return dict(planned=len(values), success=sum(x is True for x in values),
                failure=sum(x is False for x in values), unobserved=sum(x is None for x in values))

def rate(summary):
    return None if summary['unobserved'] or not summary['planned'] else summary['success']/summary['planned']

def joint(values):
    values = list(values)
    return False if any(v is False for v in values) else None if any(v is None for v in values) else True

def effect(pairs, problems, left, right):
    per_structure = []
    for problem in problems:
        subset = [x for x in pairs if x['phase'] == 'continuation' and x['problem_id'] == problem['id']]
        a = count(x['success'] for x in subset if x['generator_arm'] == left)
        b = count(x['success'] for x in subset if x['generator_arm'] == right)
        ar, br = rate(a), rate(b)
        per_structure.append(dict(problem_id=problem['id'], left=a, right=b,
            delta=None if ar is None or br is None else br-ar))
    ds = [p['delta'] for p in per_structure]
    mean = None if any(d is None for d in ds) else sum(ds)/len(ds)
    return dict(left=left, right=right, per_structure=per_structure, mean_delta=mean,
                unit='bidirectional supported continuation; equal weight per structure')

def first_error(row):
    key = 'continuation_success' if row['phase'] == 'continuation' else 'end_to_end_success'
    if row[key] is True:
        return 'success'
    for step in row['step_checks']:
        if step['valid'] is False:
            errors = step.get('error_codes') or []
            if 'missing_parent' in errors:
                return 'missing_parent'
            if 'premise_counter_mismatch' in errors:
                return 'premise_counter_mismatch'
            return '+'.join(errors) or 'invalid_step'
        if step.get('support_contract_success') is False:
            return 'allocation_contract'
        if step['status'] in ('invalid_json','invalid_schema','lookup_null'):
            return step['status']
        if step['status'] not in ('ok',):
            return 'unobserved_or_incomplete:'+step['status']
    if row['phase'] == 'end_to_end' and row.get('selection_success') is False:
        return 'selection_failure'
    return 'unobserved' if row[key] is None else 'graph_or_route_failure'

def aggregate(plan, rows, status, usage, state):
    s = plan['protocol']
    groups = {'continuation':{}, 'end_to_end':{}}
    pairs, robust = [], []
    for phase, arms, outcome in (('continuation',s['continuation_arms'],'continuation_success'),
                                 ('end_to_end',s['monitor_arms'],'end_to_end_success')):
        for arm in arms:
            selected = [r for r in rows if r['phase'] == phase and r['generator_arm'] == arm]
            g = dict(outcome=count(r[outcome] for r in selected),
                graph_semantic=count(r['generator_semantic_success'] for r in selected),
                support_contract=count(r['support_contract_success'] for r in selected),
                first_errors=dict(sorted(Counter(first_error(r) for r in selected).items())))
            bins = defaultdict(list)
            for r in selected:
                bins[r['pair_id']].append(r)
            arm_pairs = []
            for pair_id, values in sorted(bins.items()):
                if len(values) != 2 or {r['condition'] for r in values} != {'shallow','deep'}:
                    raise ValueError('양방향 pair 배정 불일치')
                item = dict(pair_id=pair_id, phase=phase, generator_arm=arm,
                    problem_id=values[0]['problem_id'], seed=values[0]['seed'],
                    success=joint(r[outcome] for r in values),
                    shallow=next(r[outcome] for r in values if r['condition']=='shallow'),
                    deep=next(r[outcome] for r in values if r['condition']=='deep'))
                arm_pairs.append(item)
                pairs.append(item)
            g['bidirectional'] = count(x['success'] for x in arm_pairs)
            g['pair_distribution'] = dict(both_success=sum(x['shallow'] is True and x['deep'] is True for x in arm_pairs),
                only_one_success=sum((x['shallow'] is True and x['deep'] is False) or (x['shallow'] is False and x['deep'] is True) for x in arm_pairs),
                both_failed=sum(x['shallow'] is False and x['deep'] is False for x in arm_pairs),
                incomplete=sum(x['shallow'] is None or x['deep'] is None for x in arm_pairs))
            g['per_structure'] = {p['id']:dict(
                outcome=count(r[outcome] for r in selected if r['problem_id']==p['id']),
                bidirectional=count(x['success'] for x in arm_pairs if x['problem_id']==p['id'])) for p in s['problems']}
            g['by_target_depth'] = {str(depth):count(r[outcome] for r in selected if r['target_D']==depth)
                                    for depth in sorted({r['target_D'] for r in selected})}
            if phase == 'continuation':
                g.update(initial_id_style=selected[0]['initial_id_style'], output_id_style=selected[0]['output_id_style'])
            else:
                bundles = defaultdict(list)
                for x in arm_pairs:
                    bundles[x['problem_id'],x['seed']].append(x)
                own = []
                for (pid,seed), values in sorted(bundles.items()):
                    if len(values) != 4:
                        raise ValueError('네 표시 묶음 배정 불일치')
                    item = dict(problem_id=pid, seed=seed, generator_arm=arm, success=joint(x['success'] for x in values))
                    own.append(item)
                    robust.append(item)
                g['four_display'] = count(x['success'] for x in own)
            groups[phase][arm] = g
    components = [effect(pairs,s['problems'],*contrast) for contrast in s['primary_components']]
    by_structure = []
    for index,p in enumerate(s['problems']):
        ds = [e['per_structure'][index]['delta'] for e in components]
        by_structure.append(dict(problem_id=p['id'], family_deltas=ds,
            delta=None if any(v is None for v in ds) else sum(ds)/len(ds)))
    ds = [x['delta'] for x in by_structure]
    overall = None if state != 'complete' or any(v is None for v in ds) else sum(ds)/len(ds)
    loo = []
    if overall is not None:
        loo = [dict(omitted_structure=x['problem_id'],mean_delta=(sum(ds)-x['delta'])/(len(ds)-1)) for x in by_structure]
    secondary = [effect(pairs,s['problems'],*contrast) for contrast in s['secondary_comparisons']]
    if state != 'complete':
        for item in components+secondary:
            item['mean_delta'] = None
    continuations = [r for r in rows if r['phase']=='continuation']
    transitions = []
    for left,right in s['primary_components']+s['secondary_comparisons']:
        aa={r['unit_id']:r for r in continuations if r['generator_arm']==left}
        bb={r['unit_id']:r for r in continuations if r['generator_arm']==right}
        cell_counts=Counter((first_error(aa[k]),first_error(bb[k])) for k in aa)
        transitions.append(dict(left=left,right=right,unit='same structure/route/seed, not additional samples',
            outcomes=[dict(left_outcome=a,right_outcome=b,count=n) for (a,b),n in sorted(cell_counts.items())]))
    selected = [r for r in rows if r['phase']=='end_to_end']
    return dict(contract='v089-summary-r1',state=state,provenance=plan['provenance'],plan_sha256=plan['plan_sha256'],
        scope='기존 8구조의 4×4 지원 연속 생성 진단 + 기존 새 선택/새 facts D 종단 기준선',groups=groups,
        primary=dict(definition=s['primary_definition'],components=components,per_structure=by_structure,
            mean_delta=overall,leave_one_structure_out=loo,sensitivity_is_not_confidence_interval=True),
        secondary=secondary,first_error_transitions=transitions,shared_selection=count(r['selection_success'] for r in selected),
        pairs=pairs,robust=robust,response_status_counts=dict(sorted(Counter(status.values()).items())),
        observed_call_records=len(usage),rows=rows,
        limitations=['교차군은 과거 유효 facts 지원을 받은 연속 생성이며 C의 새 facts 종단과 합산하지 않는다.',
            '4×4는 16개 명명 조건이지 16개의 독립 문제 집합이 아니다. 구조는 8개, seed는 2개다.',
            '의미 ID 처치는 의미 단서를 포함한다. 문자열 길이만의 효과나 모델 내부 기제를 식별하지 않는다.',
            '미관측/부분 실행은 실패 또는 0 깊이로 채우지 않는다. 전체 주효과는 완료 배치에서만 계산한다.',
            '집계와 한국어 렌더링은 독립 채점기와 공유한다. 의미 판정/요청 재구성은 별도 구현이다.'])

def render(s):
    lines=['# v089 초기 ID × 후속 ID 교차 실험','',f"상태: {s['state']} / 출처: {s['provenance']}",'',
        '## A. 초기 유효 facts 지원 후 연속 생성 — 4×4','',
        '| 초기 ID | 후속 ID | 유효 연속 graph | 양방향 | 미관측 |','|---|---|---:|---:|---:|']
    for arm,g in s['groups']['continuation'].items():
        x,y=g['outcome'],g['bidirectional']
        lines.append(f"| {g['initial_id_style']} | {g['output_id_style']} | {x['success']}/{x['planned']} | {y['success']}/{y['planned']} | {x['unobserved']} |")
    delta=s['primary']['mean_delta']
    lines+=['','주평가: 같은 계열의 중립 초기 ID − atom_alias 초기 ID, short/long 동일 가중·구조 동일 가중.',
        '차이: '+('부분 실행 또는 미관측으로 산출하지 않음' if delta is None else f'{delta*100:.4f}%p'),
        '', '## B. 새 선택·새 facts에서 시작한 기존 D 종단 기준선','']
    for arm,g in s['groups']['end_to_end'].items():
        x,y,z=g['outcome'],g['bidirectional'],g['four_display']
        lines.append(f"{arm}: 종단 {x['success']}/{x['planned']}, 양방향 {y['success']}/{y['planned']}, 네 표시 {z['success']}/{z['planned']}")
    q=s['shared_selection'];lines+=['',f"공통 two-stage 선택: {q['success']}/{q['planned']}",'','## 판정 범위','']+s['limitations']
    return '\n'.join(lines)+'\n'
