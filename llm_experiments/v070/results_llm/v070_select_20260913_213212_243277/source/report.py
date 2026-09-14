"""v070 원응답의 생산 채점과 한국어 보고서. 선택 성공과 graph 생성 성공을 구분한다."""
import base64
from copy import deepcopy
import common, measure, selection
_USAGE_FIELDS=('prompt_eval_count','eval_count','total_duration','prompt_eval_cached_count')
_FIELDS=('format_valid','candidate_member','selected_position','selected_rule_ids','route_valid','route_D','selection_success','error_codes')

def _usage(raw):
    return {k:raw.get(k) if isinstance(raw,dict) and type(raw.get(k)) is int and raw[k]>=0 else None for k in _USAGE_FIELDS}

def summarize(plan,records,state):
    if plan['contract']!='v070-plan-r1' or state not in ('complete','stopped','crashed'):raise ValueError('plan/state')
    index={};allowed={s['id'] for s in plan['slots']}
    for r in records:
        if r['id'] not in allowed or r['id'] in index:raise ValueError('duplicate/unknown record')
        index[r['id']]=r
    spec=plan['protocol'];ps={p['id']:p for p in spec['problems']};rows=[]
    for s in plan['slots']:
        p=ps[s['problem_id']];target=spec['depth_ranges'][p['id']][int(s['condition']=='deep')]
        candidates=[spec['reference_plans'][p['id']][spec['reference_conditions'][i]] for i in spec['candidate_orders'][s['candidate_order_index']]]
        row={**deepcopy(s),'status':'not_observed','target_D':target,'usage':_usage(None),'response_sha256':None,'done_reason':None,**{k:None for k in _FIELDS}}
        if s['id'] in index:
            r=index[s['id']]
            try:env=common.load(base64.b64decode(r['response_b64'],validate=True))
            except (ValueError,UnicodeError):env=None
            status,obj=measure.parse_response(env,r['http_status'],r['error'],plan['identity']['model'])
            if isinstance(env,dict) and type(env.get('eval_count')) is int and env['eval_count']>spec['num_predict']:status,obj='generation_budget_exceeded',None
            row.update(status=status,usage=_usage(env),response_sha256=r['response_sha256'],done_reason=env.get('done_reason') if isinstance(env,dict) else None)
            if status=='ok':
                row.update(selection.assess(p,obj,candidates,target))
                if row['format_valid'] is False:row['status']='invalid_schema'
            elif status in ('invalid_json','invalid_schema'):row['format_valid']=False
        rows.append(row)
    pairs=[]
    for s in plan['slots']:
        if s['condition']!='shallow':continue
        rr=[r for r in rows if r['pair_id']==s['pair_id']];sh=next(r for r in rr if r['condition']=='shallow');de=next(r for r in rr if r['condition']=='deep')
        known=all(type(r['selection_success']) is bool for r in rr)
        pairs.append({'pair_id':s['pair_id'],'problem_id':s['problem_id'],'seed':s['seed'],
            'candidate_order_index':s['candidate_order_index'],'shallow_D':sh['route_D'],'deep_D':de['route_D'],
            'same_selected_route':sh['selected_rule_ids']==de['selected_rule_ids'] if all(r['selected_rule_ids'] is not None for r in rr) else None,
            'selective_pair_success':all(r['selection_success'] for r in rr) if known else None})
    measured=sum(type(r['selection_success']) is bool for r in rows);success=sum(r['selection_success'] is True for r in rows)
    paircount=sum(p['selective_pair_success'] is True for p in pairs);full=state=='complete' and len(records)==40
    complete=full and measured==40;gate=(success==40 and paircount==20) if complete else None
    decision='measurement_incomplete_no_retry' if not complete else 'selector_ready_design_separate_composition' if gate else 'selector_failed_preserve_ranges_close_formulation'
    groups=[]
    for p in spec['problems']:
        for c in spec['conditions']:
            rr=[r for r in rows if r['problem_id']==p['id'] and r['condition']==c]
            groups.append({'problem_id':p['id'],'condition':c,'assigned':len(rr),'measured':sum(type(r['selection_success']) is bool for r in rr),'successes':sum(r['selection_success'] is True for r in rr),'valid_routes':sum(r['route_valid'] is True for r in rr)})
    return {'contract':'v070-report-r1','run_name':plan['run_name'],'provenance':plan['provenance'],'plan_sha256':plan['plan_sha256'],
        'state':state,'full_complete':full,'assigned_calls':40,'observed_calls':len(records),'rows':rows,'pairs':pairs,'groups':groups,
        'overall':{'assigned':40,'measured':measured,'successes':success,'unmeasured':40-measured,'paired_successes':paircount,'assigned_pairs':20,
            'selector_ready':gate,'rate':success/40 if complete else None,'next_decision':decision,'end_to_end_graph_D_control':None,'A_or_M_gate':None,'v069_successes_unchanged':12},
        'usage':{k:sum(r['usage'][k] for r in rows) if full and all(r['usage'][k] is not None for r in rows) else None for k in _USAGE_FIELDS},
        'limits':{'candidate_routes_given':True,'candidate_depth_labels_given':False,'host_repair':False,'constructor_executed':False,'independent_holdout':False,'internal_cause_identified':False}}

def render(r):
    a=r['overall'];label='미판정' if a['selector_ready'] is None else '통과' if a['selector_ready'] else '불통과'
    lines=['# v070 D 지시 기반 후보 경로 선택','',f"상태: {r['state']} / 관측 {r['observed_calls']}/40 / provenance: {r['provenance']}",
        'v069의 지정 append-only 구성 12/12는 그대로 보존한다. 이번에는 경로 선택만 측정하며 generator를 호출하지 않는다.',
        '두 정상 후보를 주지만 short/long 정답 라벨이나 기대 D는 모델에게 주지 않는다. shallow/deep 요구와 후보 순서를 교차한다.',
        'C01은 규칙 개수가 같고 D가 다르다. C02는 얕은 후보의 규칙이 더 많다. 두 문제는 직접 만든 진단 대조이며 독립 holdout이 아니다.','',
        '|문제|D 요구|성공/배정|측정|유효 경로|','|---|---|---:|---:|---:|']
    for g in r['groups']:lines.append(f"|{g['problem_id']}|{g['condition']}|{g['successes']}/{g['assigned']}|{g['measured']}|{g['valid_routes']}|")
    lines+=['','## 전체 판정',f"선택 성공 {a['successes']}/40, 선택적 pair {a['paired_successes']}/20, 미측정 {a['unmeasured']}, gate {label}.",
        f"다음 결정: {a['next_decision']}",
        '40/40 및 20/20이어도 후보 목록 내 D 선택 기준선이다. 자유 계획 생성·전체 graph D 제어·A/M 성공으로 바꾸지 않는다.',
        '실패/부분 성공은 원범위를 보존하고 이 선택 계약을 종료한다. 자동 재시도·seed 변경·다음 단계 자동 실행은 없다.',
        '형식 오류·미실행·중단·길이 종료는 논리 오답 또는 D=0으로 채우지 않는다. 미완료/미측정이면 전체 gate는 null이다.',
        '규칙 목록의 D는 입력 규칙 의존 관계에서 검산한 값이며 모델이 작성한 parent ID를 검증한 graph D가 아니다.',
        '',f"원응답 사용량 계수: {r['usage']}",f"계획 SHA-256: {r['plan_sha256']}"]
    return '\n'.join(lines)+'\n'
