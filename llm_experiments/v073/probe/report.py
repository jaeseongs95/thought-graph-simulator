"""원응답을 그대로 채점한다. 형식 실패와 미실행을 오답/0으로 채우지 않는다."""
import base64, json
from copy import deepcopy
import common
_USAGE_FIELDS=('prompt_eval_count','eval_count','total_duration','prompt_eval_cached_count')

def _usage(value):
    return {k:value.get(k) if isinstance(value,dict) and type(value.get(k)) is int and value[k]>=0 else None for k in _USAGE_FIELDS}

def _parse(env,http,error,model,cap):
    if error is not None or http is None:return 'transport_error',None
    if http!=200:return 'http_error',None
    if not isinstance(env,dict):return 'invalid_json',None
    if env.get('model')!=model:return 'identity_error',None
    if type(env.get('eval_count')) is int and env['eval_count']>cap:return 'generation_budget_exceeded',None
    if env.get('done_reason')=='length':return 'generation_length',None
    if env.get('done') is not True or env.get('done_reason')!='stop':return 'incomplete_response',None
    msg=env.get('message')
    if not isinstance(msg,dict) or msg.get('role')!='assistant' or msg.get('tool_calls') or not isinstance(msg.get('content'),str):return 'invalid_schema',None
    try:obj=common.load(msg['content'])
    except (ValueError,UnicodeError):return 'invalid_json',None
    if not isinstance(obj,dict) or set(obj)!={'candidate_index'} or type(obj['candidate_index']) is not int or obj['candidate_index'] not in (0,1):return 'invalid_schema',None
    return 'ok',obj['candidate_index']

def _counts(rows,key):
    return {'assigned':len(rows),'measured':sum(type(r[key]) is bool for r in rows),'successes':sum(r[key] is True for r in rows)}

def summarize(plan,records,state):
    if plan['contract']!='v073-plan-r1' or state not in ('complete','stopped','crashed'):raise ValueError('plan/state')
    spec=plan['protocol'];index={r['id']:r for r in records}
    if len(index)!=len(records) or not set(index)<={s['id'] for s in plan['slots']}:raise ValueError('unknown/duplicate record')
    by_pair={p['id']:p['values'] for p in spec['numeric_pairs']};rows=[]
    for slot in plan['slots']:
        values=[by_pair[slot['numeric_pair_id']][i] for i in spec['candidate_orders'][slot['candidate_order_index']]]
        target=min(values) if slot['condition']=='shallow' else max(values)
        expected=values.index(target)
        row={**deepcopy(slot),'input_values':values,'expected_index':expected,'status':'not_observed','format_valid':None,
            'candidate_index':None,'selection_success':None,'error_codes':None,'usage':_usage(None),'response_sha256':None,'done_reason':None}
        if slot['id'] in index:
            rec=index[slot['id']]
            try:env=common.load(base64.b64decode(rec['response_b64'],validate=True))
            except (ValueError,UnicodeError):env=None
            status,choice=_parse(env,rec['http_status'],rec['error'],plan['identity']['model'],spec['num_predict'])
            row.update(status=status,usage=_usage(env),response_sha256=rec['response_sha256'],done_reason=env.get('done_reason') if isinstance(env,dict) else None)
            if status=='ok':row.update(format_valid=True,candidate_index=choice,selection_success=choice==expected,error_codes=[] if choice==expected else ['wrong_numeric_direction'])
            elif status in ('invalid_json','invalid_schema'):row.update(format_valid=False,error_codes=[status])
            else:row['error_codes']=[status]
        rows.append(row)
    pairs=[]
    for s in plan['slots']:
        if s['condition']!='shallow':continue
        group=[r for r in rows if r['pair_id']==s['pair_id']]
        sh=next(r for r in group if r['condition']=='shallow');de=next(r for r in group if r['condition']=='deep')
        known=all(type(r['selection_success']) is bool for r in group)
        pairs.append({'pair_id':s['pair_id'],'unit_id':s['unit_id'],'numeric_pair_id':s['numeric_pair_id'],'seed':s['seed'],
            'candidate_order_index':s['candidate_order_index'],'format':s['format'],
            'shallow_index':sh['candidate_index'],'deep_index':de['candidate_index'],
            'same_index':sh['candidate_index']==de['candidate_index'] if known else None,
            'pair_success':sh['selection_success'] and de['selection_success'] if known else None})
    contrasts=[]
    for b in range(spec['assigned_blocks']):
        for condition in ('shallow','deep'):
            rr=[r for r in rows if r['block']==b and r['condition']==condition]
            c=next(r for r in rr if r['format']=='compact');s=next(r for r in rr if r['format']=='comma_space')
            known=type(c['selection_success']) is bool and type(s['selection_success']) is bool
            label='unmeasured'
            if known:label=('both_correct' if c['selection_success'] else 'spaced_only') if s['selection_success'] else ('compact_only' if c['selection_success'] else 'both_wrong')
            contrasts.append({'unit_id':c['unit_id'],'numeric_pair_id':c['numeric_pair_id'],'seed':c['seed'],'candidate_order_index':c['candidate_order_index'],
                'condition':condition,'compact_index':c['candidate_index'],'comma_space_index':s['candidate_index'],
                'index_changed':c['candidate_index']!=s['candidate_index'] if known else None,
                'spaced_minus_compact_correct':int(s['selection_success'])-int(c['selection_success']) if known else None,'classification':label})
    full=state=='complete' and len(records)==64
    all_counts=_counts(rows,'selection_success');measurable=full and all_counts['measured']==64
    formats=[]
    for fmt in spec['formats']:
        selection=_counts([r for r in rows if r['format']==fmt],'selection_success')
        ps=_counts([p for p in pairs if p['format']==fmt],'pair_success')
        qualified=selection['successes']==32 and ps['successes']==16 if full and selection['measured']==32 else None
        formats.append({'format':fmt,'selection':selection,'pairs':ps,'qualified':qualified})
    qualifying=[f['format'] for f in formats if f['qualified'] is True] if measurable else []
    preferred=next((f for f in spec['qualifying_format_priority'] if f in qualifying),None)
    ready=bool(qualifying) if measurable else None
    if not measurable:decision='measurement_incomplete_close_without_retry'
    elif len(qualifying)==2:decision='tested_formats_qualified_return_to_end_to_end_design'
    elif len(qualifying)==1:decision='format_specific_qualified_return_to_end_to_end_design'
    else:decision='no_interface_qualified_close_diagnostic_branch'
    cells=[]
    for fmt in spec['formats']:
        for oi in range(2):
            group=[r for r in rows if r['format']==fmt and r['candidate_order_index']==oi]
            cells.append({'format':fmt,'candidate_order_index':oi,'selection':_counts(group,'selection_success'),
                'index_0':sum(r['candidate_index']==0 for r in group),'index_1':sum(r['candidate_index']==1 for r in group)})
    groups=[]
    for pair in spec['numeric_pairs']:
        for fmt in spec['formats']:
            group=[r for r in rows if r['numeric_pair_id']==pair['id'] and r['format']==fmt]
            groups.append({'numeric_pair_id':pair['id'],'format':fmt,'selection':_counts(group,'selection_success')})
    result={'contract':'v073-report-r1','run_name':plan['run_name'],'provenance':plan['provenance'],'plan_sha256':plan['plan_sha256'],
        'model':plan['identity']['model'],'state':state,'full_complete':full,'assigned_calls':64,'observed_calls':len(records),
        'rows':rows,'pairs':pairs,'formats':formats,'format_order_cells':cells,'numeric_pair_groups':groups,'format_contrasts':contrasts,
        'overall':{'selection':all_counts,'pairs':_counts(pairs,'pair_success'),'unmeasured_calls':64-all_counts['measured'],
            'all_measured':measurable,'interface_ready':ready,'qualified_formats':qualifying,'preferred_format_for_new_contract':preferred,
            'robust_across_two_tested_formats':len(qualifying)==2 if measurable else None,'next_decision':decision,
            'automatic_next_experiment':False,'end_to_end_graph_D_control':None,'A_or_M_gate':None},
        'contrast_counts':{label:sum(c['classification']==label for c in contrasts) for label in ('both_correct','both_wrong','compact_only','spaced_only','unmeasured')},
        'request_repetition':{'observed':len(records),'unique_request_bytes':len({r['request_sha256'] for r in records}),
            'observed_conditions_without_seed':len({(r['numeric_pair_id'],r['candidate_order_index'],r['format'],r['condition']) for r in rows if r['id'] in index}),
            'unique_numeric_pairs':4,'assigned_conditions_without_seed':32},
        'usage':{k:sum(r['usage'][k] for r in rows) if full and all(r['usage'][k] is not None for r in rows) else None for k in _USAGE_FIELDS},
        'v072_frozen_result':deepcopy(spec['v072_frozen_result']),
        'limits':{'experimenter_numbers_provided':True,'model_output_repaired':False,'depth_estimation_executed':False,'constructor_executed':False,
            'new_graph_holdout':False,'output_schema_changed':False,'native_model_package_changed':False,'internal_cause_identified':False,
            'previous_failures_rescored':False,'new_run_automatically_repeated':False}}

    return common.load(json.dumps(result,ensure_ascii=False,sort_keys=True))

def render(result):
    a=result['overall'];label='미판정' if a['interface_ready'] is None else '기준 충족' if a['interface_ready'] else '기준 미달'
    lines=['# v073 공백 × 후보 순서 인터페이스 양성 대조','',
        f"상태: {result['state']} / 관측 {result['observed_calls']}/64 / provenance: {result['provenance']}",
        '실험자가 제공한 숫자쌍 4개 × 공백 형식 2개 × 후보 순서 2개 × 방향 2개 × seed 2개다.',
        '값·지시·모델·출력 스키마·생성 옵션은 고정했다. 비교 형식은 쉼표 뒤 공백 한 글자만 다르다.',
        '기존 v072의 응답과 점수는 변경하지 않았다. 이 검사는 깊이 계산이나 최종 graph의 D 제어를 측정하지 않는다.','',
        '|형식|후보 순서|수치 선택 성공/배정|측정|인덱스 0 / 1|','|---|---|---:|---:|---:|']
    for cell in result['format_order_cells']:
        c=cell['selection'];ordering='작은 값 먼저' if cell['candidate_order_index']==0 else '큰 값 먼저'
        lines.append(f"|{cell['format']}|{ordering}|{c['successes']}/{c['assigned']}|{c['measured']}|{cell['index_0']} / {cell['index_1']}|")
    lines+=['','## 형식별 공학적 기준','|형식|선택|양방향 비교 쌍|판정|','|---|---:|---:|---|']
    for f in result['formats']:
        q='미판정' if f['qualified'] is None else '충족' if f['qualified'] else '미달'
        lines.append(f"|{f['format']}|{f['selection']['successes']}/32|{f['pairs']['successes']}/16|{q}|")
    lines+=['',f"전체 선택 {a['selection']['successes']}/64, 양방향 쌍 {a['pairs']['successes']}/32, 미측정 {a['unmeasured_calls']}.",
        f"인터페이스 gate: {label}. 후속 결정: {a['next_decision']}",
        f"충족 형식: {a['qualified_formats']}; 새 계약 설계 시 우선 형식: {a['preferred_format_for_new_contract']}",
        '한 형식만 통과하면 그 형식에 한정한 결과다. 양쪽 통과도 이 4개 숫자쌍·2개 seed 범위의 기준이지 보편적 능력 인증이 아니다.',
        '통과하면 다음 작업은 종단 D 실험 설계다. 정밀한 숫자 보고를 본실험의 새로운 필수조건으로 추가하지 않는다.',
        '실패하면 이 제한 진단을 닫는다. 형식/seed/숫자쌍 추가 탐색이나 새 모델 호출을 자동 실행하지 않는다.',
        '미완료·파싱·스키마·생성 예산 문제는 전체 gate null로 남긴다. 미측정을 오답이나 0으로 채우지 않는다.',
        '', '## 공백만 다른 요청의 짝비교',str(result['contrast_counts']),
        '짝비교와 개별 성공 수는 같은 원응답의 서로 다른 집계다. 독립 실험 표본으로 중복 계산하지 않는다.',
        '', '## 요청 반복 및 사용량',str(result['request_repetition']),str(result['usage']),
        'seed 반복과 같은 숫자쌍을 새로운 독립 과제로 세지 않는다. 누락된 사용량은 0으로 대체하지 않는다.',
        '', 'v072 결과 동결: '+str(result['v072_frozen_result']),
        '종단 graph 생성, A/M, 모델 내부 원인, 출력 스키마의 효과는 이번 검사로 확인하지 않는다.',
        f"계획 SHA-256: {result['plan_sha256']}"]
    return '\n'.join(lines)+'\n'
