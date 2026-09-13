"""직접 생성·계획·구성·종단 성과를 분리하고 같은 원응답의 비용은 한 번만 센다."""
import base64
from copy import deepcopy
import common,measure,route
FIELDS=('format_valid','proof_valid','strict_valid','actual_D','final_rule_id','error_codes')
USAGE=('prompt_eval_count','eval_count','total_duration','prompt_eval_cached_count')
def _decode(record):
    if record is None:return None
    try:return common.load(base64.b64decode(record['response_b64'],validate=True))
    except (ValueError,UnicodeError):return None

def summarize(plan,records,state):
    if plan['contract']!='v066-plan-r1' or state not in ('complete','stopped','crashed'):raise ValueError('plan/state')
    index={r['id']:r for r in records}
    if len(index)!=len(records) or not set(index)<={s['id'] for s in plan['slots']}:raise ValueError('duplicate/unplanned record')
    rows=[];payloads={};problems={p['id']:p for p in plan['protocol']['problems']}
    for s in plan['slots']:
        record=index.get(s['id']);env=_decode(record);p=problems[s['problem_id']]
        row=deepcopy(s)|{'status':'not_observed','response_sha256':None,'request_sha256':None,'http_status':None,'elapsed_ns':None,**{k:None for k in FIELDS},'plan_format_valid':None,'plan_valid':None,'planned_D':None,'selected_rule_ids':None,'plan_error_codes':None,'follows_actual_plan':None,'direction_success':None,'plan_direction_success':None,'usage':{k:None for k in USAGE}}
        if record:
            for k in ('response_sha256','request_sha256','http_status','elapsed_ns'):row[k]=record[k]
            row['usage']={k:env.get(k) if isinstance(env,dict) and type(env.get(k)) is int and env[k]>=0 else None for k in USAGE}
            status,payload=measure.parse_response(env,record['http_status'],record['error'],plan['identity']['model']);row['status']=status;payloads[s['id']]=payload
            target=plan['protocol']['depth_ranges'][s['problem_id']][s['direction']=='deep']
            if status=='ok':
                if s['stage']=='plan':
                    row.update(route.assess_plan(p,payload));row['format_valid']=row['plan_format_valid']
                    if row['plan_valid'] is not None:row['plan_direction_success']=bool(row['plan_valid'] and row['planned_D']==target)
                else:
                    row.update(measure.assess(p,payload))
                    if row['strict_valid'] is not None:row['direction_success']=bool(row['strict_valid'] and row['actual_D']==target)
            elif status in ('invalid_json','invalid_schema'):row['format_valid']=False
        rows.append(row)
    byid={r['id']:r for r in rows}
    for row in rows:
        if row['stage']=='construct' and row['id'] in payloads:
            row['follows_actual_plan']=route.follows_plan(payloads.get(row['parent_plan_id']),payloads[row['id']],row['format_valid'] is True)
    observed=len(records);complete=state=='complete' and observed==len(rows);units=[]
    for p in plan['protocol']['problems']:
        for seed in plan['protocol']['seeds']:
            for arm in ('direct','staged'):
                for d in ('shallow','deep'):
                    rs=[r for r in rows if (r['problem_id'],r['seed'],r['arm'],r['direction'])==(p['id'],seed,arm,d)]
                    final=next(r for r in rs if r['stage']!='plan');pr=next((r for r in rs if r['stage']=='plan'),None)
                    seen=all(r['status']!='not_observed' for r in rs)
                    known=seen and final['direction_success'] is not None
                    if pr is not None:known=known and pr['plan_direction_success'] is not None and final['follows_actual_plan'] is not None
                    ok=None
                    if known:ok=bool(final['direction_success'] and (pr is None or pr['plan_direction_success'] and final['follows_actual_plan']))
                    units.append({'problem_id':p['id'],'seed':seed,'arm':arm,'direction':d,'all_stages_observed':seen,'planner_success':pr['plan_direction_success'] if pr else None,'final_graph_success':final['direction_success'],'actual_D':final['actual_D'],'plan_followed':final['follows_actual_plan'] if pr else None,'end_to_end_success':ok})
    pairs=[];arms={}
    for arm in ('direct','staged'):
        for p in plan['protocol']['problems']:
            for seed in plan['protocol']['seeds']:
                a,b=(next(u for u in units if (u['arm'],u['problem_id'],u['seed'],u['direction'])==(arm,p['id'],seed,d)) for d in ('shallow','deep'))
                known=a['end_to_end_success'] is not None and b['end_to_end_success'] is not None
                ok=bool(a['end_to_end_success'] and b['end_to_end_success'] and a['actual_D']!=b['actual_D']) if known else None
                pairs.append({'arm':arm,'problem_id':p['id'],'seed':seed,'shallow_end_to_end':a['end_to_end_success'],'deep_end_to_end':b['end_to_end_success'],'selective_D_success':ok})
        ps=[p for p in pairs if p['arm']==arm];rr=[r for r in rows if r['arm']==arm];us=[u for u in units if u['arm']==arm]
        arms[arm]={'assigned_calls':len(rr),'observed_calls':sum(r['status']!='not_observed' for r in rr),'assigned_pairs':len(ps),'measured_pairs':sum(p['selective_D_success'] is not None for p in ps),'selective_successes':sum(p['selective_D_success'] is True for p in ps),'end_to_end_successes':sum(u['end_to_end_success'] is True for u in us),'final_strict_proofs':sum(r['strict_valid'] is True for r in rr),'final_D_only_successes':sum(u['final_graph_success'] is True for u in us),'all_pairs_pass':all(p['selective_D_success'] for p in ps) if complete and all(p['selective_D_success'] is not None for p in ps) else None,'usage':{k:sum(r['usage'][k] for r in rr) if all(r['usage'][k] is not None for r in rr) else None for k in USAGE}}
    contrasts=[]
    for p in plan['protocol']['problems']:
        for seed in plan['protocol']['seeds']:
            a,b=(next(x for x in pairs if (x['problem_id'],x['seed'],x['arm'])==(p['id'],seed,arm))['selective_D_success'] for arm in ('direct','staged'))
            outcome='not_comparable' if a is None or b is None else ('both' if a and b else ('direct_only' if a else ('staged_only' if b else 'neither')))
            contrasts.append({'problem_id':p['id'],'seed':seed,'direct':a,'staged':b,'outcome':outcome})
    return {'contract':'v066-report-r1','run_name':plan['run_name'],'provenance':plan['provenance'],'plan_sha256':plan['plan_sha256'],'state':state,'full_complete':complete,'assigned_calls':36,'observed_calls':observed,'rows':rows,'units':units,'pairs':pairs,'arms':arms,'contrasts':contrasts,'planner':{'observed':sum(r['stage']=='plan' and r['status']!='not_observed' for r in rows),'valid_plans':sum(r['plan_valid'] is True for r in rows),'direction_successes':sum(r['plan_direction_success'] is True for r in rows)},'limits':{'A':'not_measured','M':'not_measured','internal_control':'not_measured','equal_compute_comparison':False,'prior_v065_construction_gate_remains':False,'prior_prescribed_branch_closed':True,'planner_is_not_generated_proof':True,'repair':False,'retry':False}}

def render(r):
    lines=['# v066 직접 생성 대 모델 원계획 전달 비교','',f"실행 상태: {r['state']} / 관측 호출: {r['observed_calls']}/36 / provenance: {r['provenance']}",
       '이전 v065의 지정 규칙 단일 호출 분기는 종료했다. 이번에는 정답 규칙을 알려주지 않는 다른 실행 구조를 비교한다.',
       'staged 성공에는 모델의 계획이 유효·요구 깊이 이행, 원계획 그대로 전달, 그래프 규칙 순서 일치, 전체 strict 증명·요구 D 이행이 모두 필요하다.','',
       '|방식|호출 관측/배정|최종 strict 증명|최종 D만 일치|종단 이행|선택적 D쌍|6쌍 진입 기준|','|---|---:|---:|---:|---:|---:|---|']
    for name,a in r['arms'].items():lines.append(f"|{name}|{a['observed_calls']}/{a['assigned_calls']}|{a['final_strict_proofs']}|{a['final_D_only_successes']}|{a['end_to_end_successes']}|{a['selective_successes']}/6|{a['all_pairs_pass']}|")
    lines+=['','## 계획과 최종 증명의 분리',f"계획 관측 {r['planner']['observed']}/12, 유효 경로 계획 {r['planner']['valid_plans']}, 방향 이행 {r['planner']['direction_successes']}.",
       'planned_D는 규칙 목록의 사후 진단값이다. actual_D는 모델이 작성한 최종 유효 DAG에서만 계산한다. 잘못된 계획 뒤의 우연한 정답은 종단 성공이 아니다.','',
       '|문제|seed|방식|방향|계획 방향 성공|최종 그래프 방향 성공|계획 준수|종단 성공|실제 D|','|---|---:|---|---|---|---|---|---|---:|']
    for u in r['units']:lines.append(f"|{u['problem_id']}|{u['seed']}|{u['arm']}|{u['direction']}|{u['planner_success']}|{u['final_graph_success']}|{u['plan_followed']}|{u['end_to_end_success']}|{u['actual_D']}|")
    lines+=['','## 비용과 범위','direct는 12호출, staged는 24호출이다. 동일 계산량 비교 또는 토큰 절약 검증이 아니다. 같은 원문 재집계를 독립 표본이나 비용으로 중복 합산하지 않는다.']
    for name,a in r['arms'].items():lines.append(f"{name} 원응답 사용량: {a['usage']}")
    lines+=['','## 다음 판단','staged가 6/6쌍을 충족하면 이 제한된 외부 실행 구조의 D 기준선만 확보한다. 이전 단일 호출 실패를 취소하거나 내부 사고/A/M 성과로 확대하지 않는다.',
       '일부만 성공하면 해당 문제와 방향 범위를 보존한다. staged 종단 성공이 없다면 이 2단계 구조도 종료하며 같은 문구 변형을 자동 반복하지 않는다.',
       '미완료/파싱 불가이면 전체 진입 기준은 미판정이다. 모든 원응답과 중간값을 보존하고 자동 보정·자동 재시도는 하지 않는다.',f"계획 SHA-256: {r['plan_sha256']}"]
    return '\n'.join(lines)+'\n'
