"""깊이 계산과 수치 선택을 각각 재채점한다. 원응답을 수정하거나 실패를 소급 복구하지 않는다."""
import base64, json
from copy import deepcopy
import common, measure, reference, depths
_USAGE_FIELDS=('prompt_eval_count','eval_count','total_duration','prompt_eval_cached_count')
_FIELDS=('format_valid','reported_depths','depth_report_success','candidate_index','selected_rule_ids',
         'selected_D','selection_success','numeric_choice_success','pipeline_success','error_codes')

def _usage(raw):
    return {k:raw.get(k) if isinstance(raw,dict) and type(raw.get(k)) is int and raw[k]>=0 else None for k in _USAGE_FIELDS}

def _counts(rows,key):
    return {'assigned':len(rows),'measured':sum(type(r[key]) is bool for r in rows),'successes':sum(r[key] is True for r in rows)}

def summarize(plan,records,state):
    if plan['contract']!='v071-plan-r1' or state not in ('complete','stopped','crashed'):raise ValueError('plan/state')
    index={r['id']:r for r in records}
    if len(index)!=len(records) or not set(index)<={s['id'] for s in plan['slots']}:raise ValueError('duplicate/unknown record')
    spec=plan['protocol'];ps={p['id']:p for p in spec['problems']};rows=[];by_id={}
    for s in plan['slots']:
        p=ps[s['problem_id']]
        order=spec['candidate_orders'][s['candidate_order_index']]
        candidates=[spec['reference_plans'][p['id']][spec['reference_conditions'][i]] for i in order]
        truth=[reference.validate(p,c) for c in candidates]
        target=None if s['stage']=='estimate' else (min(truth) if s['condition']=='shallow' else max(truth))
        row={**deepcopy(s),'status':'not_observed','expected_depths':truth,'target_D':target,'usage':_usage(None),
            'response_sha256':None,'done_reason':None,**{k:None for k in _FIELDS}}
        prior=by_id.get(s['unit_id']+'_estimate') if s['arm']=='model_depth' else None
        if s['id'] in index:
            rec=index[s['id']]
            try:env=common.load(base64.b64decode(rec['response_b64'],validate=True))
            except (UnicodeError,ValueError):env=None
            status,obj=measure.parse_response(env,rec['http_status'],rec['error'],plan['identity']['model'])
            if isinstance(env,dict) and type(env.get('eval_count')) is int and env['eval_count']>spec['num_predict']:
                status,obj='generation_budget_exceeded',None
            row.update(status=status,usage=_usage(env),response_sha256=rec['response_sha256'],done_reason=env.get('done_reason') if isinstance(env,dict) else None)
            if status=='ok':
                if s['stage']=='estimate':row.update(depths.assess_depth(obj,truth))
                else:
                    incoming=truth if s['arm']=='oracle_depth' else prior['reported_depths'] if prior else None
                    row.update(depths.assess_choice(obj,candidates,truth,target,incoming))
                if row['format_valid'] is False:row['status']='invalid_schema'
            elif status in ('invalid_schema','invalid_json'):row['format_valid']=False
        if s['arm']=='model_depth' and prior and type(prior['depth_report_success']) is bool and type(row['selection_success']) is bool:
            row['pipeline_success']=prior['depth_report_success'] and row['selection_success']
        rows.append(row);by_id[s['id']]=row
    pairs=[]
    for s in plan['slots']:
        if s['condition']!='shallow':continue
        rr=[r for r in rows if r['pair_id']==s['pair_id']]
        sh=next(r for r in rr if r['condition']=='shallow');de=next(r for r in rr if r['condition']=='deep')
        known=all(type(r['selection_success']) is bool for r in rr)
        path_known=all(type(r['pipeline_success']) is bool for r in rr)
        pairs.append({'pair_id':s['pair_id'],'unit_id':s['unit_id'],'problem_id':s['problem_id'],'seed':s['seed'],
            'candidate_order_index':s['candidate_order_index'],'arm':s['arm'],
            'shallow_D':sh['selected_D'],'deep_D':de['selected_D'],
            'same_selected_route':sh['selected_rule_ids']==de['selected_rule_ids'] if all(r['selected_rule_ids'] is not None for r in rr) else None,
            'selective_pair_success':all(r['selection_success'] for r in rr) if known else None,
            'pipeline_pair_success':all(r['pipeline_success'] for r in rr) if path_known else None})
    full=state=='complete' and len(records)==spec['max_inference_calls']
    estimates=[r for r in rows if r['stage']=='estimate'];oracle=[r for r in rows if r['arm']=='oracle_depth'];model=[r for r in rows if r['arm']=='model_depth']
    ec=_counts(estimates,'depth_report_success');oc=_counts(oracle,'selection_success');mc=_counts(model,'selection_success');pc=_counts(model,'pipeline_success')
    op=sum(p['arm']=='oracle_depth' and p['selective_pair_success'] is True for p in pairs)
    mp=sum(p['arm']=='model_depth' and p['selective_pair_success'] is True for p in pairs)
    pp=sum(p['arm']=='model_depth' and p['pipeline_pair_success'] is True for p in pairs)
    complete=full and ec['measured']==20 and oc['measured']==40 and mc['measured']==40
    oracle_gate=oc['successes']==40 and op==20 if full and oc['measured']==40 else None
    depth_gate=ec['successes']==20 if full and ec['measured']==20 else None
    gate=(oracle_gate and depth_gate and pc['successes']==40 and pp==20) if complete else None
    if not complete:decision='measurement_incomplete_no_retry'
    elif not oracle_gate:decision='numeric_positive_control_failed_close_contract'
    elif not depth_gate:decision='depth_estimation_failed_close_contract'
    elif not gate:decision='model_report_selection_failed_close_contract'
    else:decision='components_ready_design_separate_graph_composition'
    groups=[]
    for p in spec['problems']:
        rr=[r for r in rows if r['problem_id']==p['id']]
        groups.append({'problem_id':p['id'],'estimates':_counts([r for r in rr if r['stage']=='estimate'],'depth_report_success'),
            'oracle_selection':_counts([r for r in rr if r['arm']=='oracle_depth'],'selection_success'),
            'model_selection':_counts([r for r in rr if r['arm']=='model_depth'],'selection_success'),
            'model_pipeline':_counts([r for r in rr if r['arm']=='model_depth'],'pipeline_success')})
    result={'contract':'v071-report-r1','run_name':plan['run_name'],'provenance':plan['provenance'],'plan_sha256':plan['plan_sha256'],
        'state':state,'full_complete':full,'assigned_calls':100,'observed_calls':len(records),'rows':rows,'pairs':pairs,'groups':groups,
        'overall':{'depth_reports':ec,'oracle_selection':oc,'model_selection':mc,'model_pipeline':pc,
            'oracle_pair_successes':op,'model_selection_pair_successes':mp,'model_pipeline_pair_successes':pp,'pairs_per_arm':20,
            'unmeasured_calls':100-ec['measured']-oc['measured']-mc['measured'],
            'oracle_ready':oracle_gate,'depth_estimator_ready':depth_gate,'pipeline_ready':gate,'next_decision':decision,
            'end_to_end_graph_D_control':None,'A_or_M_gate':None,'v069_constructor_successes_unchanged':12,
            'v070_selection_successes_unchanged':20,'v070_paired_successes_unchanged':0},
        'usage':{k:sum(r['usage'][k] for r in rows) if full and all(r['usage'][k] is not None for r in rows) else None for k in _USAGE_FIELDS},
        'limits':{'model_depths_repaired':False,'oracle_depths_given':True,'constructor_executed':False,
            'independent_holdout':False,'v070_concurrent_comparison':False,'shared_estimates':20,'choices_per_shared_estimate':2,'internal_cause_identified':False}}
    return common.load(json.dumps(result,ensure_ascii=False,sort_keys=True))

def render(r):
    a=r['overall'];label='미판정' if a['pipeline_ready'] is None else '통과' if a['pipeline_ready'] else '불통과'
    lines=['# v071 깊이 계산 원문 → 수치 선택 / 정답 깊이 양성 대조','',
        f"상태: {r['state']} / 관측 {r['observed_calls']}/100 / provenance: {r['provenance']}",
        'v070은 선택 20/40, 선택적 pair 0/20으로 종료했다. 기존 실패를 수정하거나 재채점하지 않는다.',
        '깊이 계산 20회, 모델 계산 원문 선택 40회, 정답 깊이 입력 선택 40회다. 정답입력군은 모델의 깊이 계산 성공으로 세지 않는다.',
        '모델의 깊이가 틀리면 뒤의 경로 선택이 우연히 맞아도 계산→선택 전체 성공이 아니다. 잘못된 중간값도 원문 그대로 전달한다.','',
        '|문제|깊이 계산|정답 깊이 선택|모델 원문 경로 선택|계산→선택 전체|',
        '|---|---:|---:|---:|---:|']
    for g in r['groups']:
        values=[g[k] for k in ('estimates','oracle_selection','model_selection','model_pipeline')]
        lines.append('|'+g['problem_id']+'|'+'|'.join(str(v['successes'])+'/'+str(v['assigned']) for v in values)+'|')
    lines+=['','## 전체 판정',
        f"깊이 계산 {a['depth_reports']['successes']}/20, 정답 깊이 선택 {a['oracle_selection']['successes']}/40, 모델 원문 경로 선택 {a['model_selection']['successes']}/40, 계산→선택 전체 {a['model_pipeline']['successes']}/40.",
        f"선택적 pair: 정답 깊이 {a['oracle_pair_successes']}/20, 모델 원문 경로 선택 {a['model_selection_pair_successes']}/20, 계산→선택 전체 {a['model_pipeline_pair_successes']}/20.",
        f"미측정 호출 {a['unmeasured_calls']}, gate {label}. 다음 결정: {a['next_decision']}",
        '두 D 선택은 같은 깊이 계산 한 번을 공유한다. 40개 선택을 40개의 독립적인 깊이 계산으로 세지 않는다.',
        '성공해도 후보 목록 내 계산·수치 선택 기준선이다. 전체 graph 생성, 자율 계획, A/M, hidden-layer 제어, 비용 우월성으로 확대하지 않는다.',
        '이번 한 배치 이후 이 계약은 종료한다. 실패를 문구/seed 변경으로 자동 반복하지 않는다. 미완료·미측정이면 전체 gate는 null이다.',
        'v069의 지정 graph 구성 12/12는 보존하지만 이번 실험에서 generator를 호출하지 않는다. v070과 동시 대조가 아니며 독립 holdout도 아니다.',
        '',f"원응답 사용량 계수: {r['usage']}",f"계획 SHA-256: {r['plan_sha256']}"]
    return '\n'.join(lines)+'\n'
