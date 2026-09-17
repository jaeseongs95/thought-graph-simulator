"""원문 바이트와 각 검산기가 산출한 행의 보조 집계.

선택·graph 채점, 응답 보정, 모델 호출은 하지 않는다. 생산과 독립 검산기가
각각 만든 rows를 받아 동일한 바이트/표시 집계를 사용한다. 의미 채점은 공유하지 않는다.
"""
from collections import Counter
from copy import deepcopy
from audit_bytes086 import load, dump, digest

USAGE_KEYS=('prompt_eval_count','eval_count','total_duration','prompt_eval_duration','eval_duration')


def collect(plan, requests, responses, rows):
    by_trial={t['id']:t for t in plan['trials']};row_by={r['trial_id']:r for r in rows}
    buckets={};totals={}
    for slot in plan['slots']:
        t=by_trial[slot['trial_id']];sid=slot['id'];key=(t['selector_variant'],t['metric'],slot['stage'])
        b=buckets.setdefault(key,{'assigned':0,'saved_requests':0,'saved_responses':0,'hashes':set(),'noseed':set()})
        b['assigned']+=1
        raw=requests.get(sid)
        if raw is not None:
            b['saved_requests']+=1;b['hashes'].add(digest(raw))
            body=load(raw);body['options'].pop('seed',None);b['noseed'].add(digest(dump(body)))
        if sid not in responses:continue
        b['saved_responses']+=1
        total=totals.setdefault((t['selector_variant'],t['metric']),{'saved_responses':0,'usage':{k:{'sum_observed':0,'missing':0} for k in USAGE_KEYS}})
        total['saved_responses']+=1
        try:outer=load(responses[sid])
        except (ValueError,UnicodeError):outer={}
        for k in USAGE_KEYS:
            value=outer.get(k) if type(outer) is dict else None
            if type(value) is int and value>=0:total['usage'][k]['sum_observed']+=value
            else:total['usage'][k]['missing']+=1
    unique=[]
    for key,b in sorted(buckets.items()):
        unique.append({'variant':key[0],'metric':key[1],'stage':key[2],
            'assigned_slots':b['assigned'],'request_files':b['saved_requests'],'response_files':b['saved_responses'],
            'distinct_requests_with_seed':len(b['hashes']),'distinct_requests_without_seed':len(b['noseed'])})
    models=[t for t in plan['trials'] if t['arm']=='model']
    units={}
    for t in models:units.setdefault(t['unit_id'],{})[t['selector_variant']]=t
    oracle=[];same_route=[]
    for unit,ts in sorted(units.items()):
        left=ts['two_stage_values'];right=ts['oracle_lookup']
        ls,rs=left['selection_slot_id'],right['selection_slot_id']
        a,b=requests.get(ls),requests.get(rs)
        oracle.append({'unit_id':unit,'metric':left['metric'],'request_comparable':a is not None and b is not None,
                       'identical_request':a==b if a is not None and b is not None else None})
        left,right=ts['correct_values'],ts['two_stage_values']
        if not(left['generate'] and right['generate']):continue
        ar,br=row_by[left['id']],row_by[right['id']]
        paths=(ar['selected_rule_ids'],br['selected_rule_ids'])
        if paths[0] is None or paths[1] is None or paths[0]!=paths[1]:continue
        aa=requests.get(left['id']+'_facts');bb=requests.get(right['id']+'_facts')
        ga,gb=ar['generator_success'],br['generator_success']
        same_route.append({'unit_id':unit,'problem_id':left['problem_id'],'seed':left['seed'],
            'left_generator_success':ga,'right_generator_success':gb,
            'facts_request_comparable':aa is not None and bb is not None,
            'facts_request_byte_equal':aa==bb if aa is not None and bb is not None else None,
            'generator_outcome_differs':ga!=gb if ga is not None and gb is not None else None})
    # 동일 표·원문 목표값에서 metric 필드만 다른 경우를 추린다. 입력이 다르면 비교에서 제외한다.
    lookup_groups={}
    for t in models:
        if t['selector_variant'] not in ('two_stage_values','oracle_lookup'):continue
        if (t['metric'],t['condition']) not in (('D','deep'),('W','shallow')):continue
        key=(t['selector_variant'],t['problem_id'],t['seed'],t['candidate_order_index'],t['id_assignment_index'])
        lookup_groups.setdefault(key,{})[t['metric']]=t
    def without_metric(raw):
        body=load(raw);prefix,data=body['messages'][0]['content'].split('\n\ninput: ',1)
        obj=load(data);obj.pop('metric');body['messages'][0]['content']=prefix+'\n\ninput: '+dump(obj).decode()
        return dump(body)
    metric_pairs=[]
    for key,ts in sorted(lookup_groups.items()):
        if set(ts)!= {'D','W'}:continue
        d,w=ts['D'],ts['W'];dr,wr=row_by[d['id']],row_by[w['id']]
        a,b=requests.get(d['selection_slot_id']),requests.get(w['selection_slot_id'])
        comparable=a is not None and b is not None and without_metric(a)==without_metric(b)
        metric_pairs.append({'variant':key[0],'problem_id':key[1],'seed':key[2],'order':key[3],'labels':key[4],
            'only_metric_differs':comparable,'D_final_choice':dr['final_choice_success'],'W_final_choice':wr['final_choice_success'],
            'candidate_changed':dr['candidate_id']!=wr['candidate_id'] if comparable and dr['candidate_id'] is not None and wr['candidate_id'] is not None else None})
    failures=[]
    for r in rows:
        if r['generator_success'] is not False:continue
        result=r['graph_result'] or {}
        # 오류를 서로 배타적인 원인으로 만들지 않고 원래의 겹치는 코드 목록을 보존한다.
        failures.append({'trial_id':r['trial_id'],'problem_id':r['problem_id'],'variant':r['selector_variant'],
            'metric':r['metric'],'condition':r['condition'],'generator_status':r['generator_status'],
            'graph_errors':deepcopy(result.get('error_codes',[])),'failed_steps':[x for x in r['step_checks'] if x.get('valid') is False]})
    return {'contract':'v086-byte-and-failure-diagnostics-r1','provenance':plan['provenance'],
        'distinct_request_counts':unique,'usage_by_variant_metric':[dict(variant=k[0],metric=k[1],**v) for k,v in sorted(totals.items())],
        'same_route_correct_vs_two_stage':same_route,'oracle_request_equivalence':oracle,'metric_only_lookup_pairs':metric_pairs,
        'generation_failures':failures,'interpretation':
        '고유 요청 수는 독립 구조/새 산술 문제 수가 아니다. 수치 하위 과제가 중복되어도 graph는 시행마다 별도 측정한다. '
        '동일 경로의 생성기 코드가 같아도 selection_original의 공백/개행이 다르면 생성 입력 바이트가 다르다. '
        'oracle 동일 요청은 독립 문제로 가산하지 않는다. usage 누락을 0으로 채우지 않으며 duration 합계는 벽시계 시간이 아니다.'}


def render(data):
    out=['# v086 보조 원문 진단','',data['interpretation'],'',
         '## 숫자 비교·조회 고유 입력','',
         '| 군 | 지표 | 단계 | 저장 요청 | seed 포함 고유 | seed 제외 고유 |','|---|---|---|---:|---:|---:|']
    for r in data['distinct_request_counts']:
        if r['stage'] in ('compare','select'):
            out.append(f"| {r['variant']} | {r['metric']} | {r['stage']} | {r['request_files']} | {r['distinct_requests_with_seed']} | {r['distinct_requests_without_seed']} |")
    same=data['same_route_correct_vs_two_stage'];eq=data['oracle_request_equivalence'];metric=data['metric_only_lookup_pairs']
    out+=['','## 동일 경로 생성·조회 중복','',
        f"같은 경로를 선택한 D 쌍: {len(same)}. facts 요청 바이트 동일: {sum(x['facts_request_byte_equal'] is True for x in same)}. 생성 성패가 달라진 쌍: {sum(x['generator_outcome_differs'] is True for x in same)}.",
        f"두 단계/oracle 조회의 같은 요청: {sum(x['identical_request'] is True for x in eq)}/{len(eq)} 배정쌍. 미관측은 동일 요청으로 세지 않는다.",
        f"metric만 다른 조회 대조: {sum(x['only_metric_differs'] for x in metric)}. 그중 후보가 바뀐 쌍: {sum(x['candidate_changed'] is True for x in metric)}. oracle 대조는 실제 두 단계 대조와 중복될 수 있다.",
        '',f"생성 실패 시행: {len(data['generation_failures'])}. 겹치는 오류 코드와 실패 단계 원문은 diagnostics.json에 보존한다.",'',
        '## D 본실험 사용량 — 참조·W·oracle 제외','',
        '| 군 | 보존 응답 | 관측 입력 토큰 합 | 관측 생성 토큰 합 | 입력/생성 토큰 누락 응답 |','|---|---:|---:|---:|---|']
    for r in data['usage_by_variant_metric']:
        if r['metric']!='D' or r['variant'] in ('reference','oracle_lookup'):continue
        u=r['usage'];out.append(f"| {r['variant']} | {r['saved_responses']} | {u['prompt_eval_count']['sum_observed']} | {u['eval_count']['sum_observed']} | {u['prompt_eval_count']['missing']} / {u['eval_count']['missing']} |")
    return '\n'.join(out)+'\n'
