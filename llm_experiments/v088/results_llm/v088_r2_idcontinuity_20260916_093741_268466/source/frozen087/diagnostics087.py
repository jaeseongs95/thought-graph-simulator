"""공통 바이트·오류 보고. 새 의미 채점을 하지 않고 각 검산기의 판정 행만 사용한다."""
import json,hashlib
from collections import Counter,defaultdict


def collect(plan,requests,responses,rows):
    ts={t['id']:t for t in plan['trials']};groups=defaultdict(list)
    for op in plan['slots']:
        sid=op['id']
        if sid not in requests:continue
        t=ts[op['trial_id']];key='shared_'+op['stage']if op['stage']in ('compare','select')else t['phase']+'/'+t['generator_arm']+'/'+op['stage']
        groups[key].append(requests[sid])
    unique={}
    for key,raws in sorted(groups.items()):
        reduced=[]
        for raw in raws:
            obj=json.loads(raw);obj['options'].pop('seed',None);reduced.append(json.dumps(obj,ensure_ascii=False,separators=(',',':')).encode())
        unique[key]={'calls':len(raws),'unique_with_seed':len(set(raws)),'unique_without_seed':len(set(reduced)),
                     'request_bytes_sum':sum(map(len,raws)),'request_bytes_max':max(map(len,raws))}
    failures=[];types=Counter()
    for row in rows:
        if row['phase']=='rule_probe':
            if row['probe_success']is not False:continue
            codes=(row['rule_check']or{}).get('error_codes',[]);steps=[]
        else:
            if row['generator_success']is not False:continue
            codes=(row['graph_result']or{}).get('error_codes',[])
            steps=[dict(step)for step in row['step_checks']if step['valid']is False or step['support_contract_success']is False]
        types.update((row['phase'],row['generator_arm'],code)for code in codes)
        failures.append({'trial_id':row['trial_id'],'phase':row['phase'],'problem_id':row['problem_id'],'arm':row['generator_arm'],
                         'graph_or_rule_errors':codes,'support_contract_success':row['support_contract_success'],'failed_steps':steps})
    comparisons=[]
    main=[r for r in rows if r['phase']=='end_to_end'];bykey={(r['unit_id'],r['generator_arm']):r for r in main}
    for unit in plan['protocol']['units']:
        uid=unit['unit_id'];base=bykey[uid,'baseline'];key=uid+'_baseline_facts'
        for arm in list(plan['protocol']['factors'])[1:]:
            other=bykey[uid,arm];oid=uid+'_'+arm+'_facts'
            comparisons.append({'unit_id':uid,'arm':arm,'same_selected_route':base['selected_rule_ids']==other['selected_rule_ids']if base['selected_rule_ids']is not None and other['selected_rule_ids']is not None else None,
                                'facts_request_equal':requests[key]==requests[oid]if key in requests and oid in requests else None,
                                'facts_response_equal':responses[key]==responses[oid]if key in responses and oid in responses else None,
                                'baseline_generation':base['generator_success'],'other_generation':other['generator_success']})
    return {'contract':'v087-diagnostics-r1','request_uniqueness':unique,'generation_input_pairs':comparisons,'failures':failures,
            'overlapping_error_counts':[{'phase':k[0],'arm':k[1],'error':k[2],'count':v}for k,v in sorted(types.items())],
            'limitation':'같은 원문 입력과 반복 seed는 독립 문제 수를 늘리지 않는다. 오류코드는 한 graph에서 겹칠 수 있다. facts 요청이 같아도 모델 출력이 반드시 같다는 가정은 하지 않는다.'}


def render(d):
    out=['# v087 바이트·실패 진단','',d['limitation'],'','| 구분 | 호출 | seed 포함 고유 | seed 제외 고유 |','|---|---:|---:|---:|']
    for k,v in d['request_uniqueness'].items():out.append(f"| {k} | {v['calls']} | {v['unique_with_seed']} | {v['unique_without_seed']} |")
    out+=['','## 관측 실패',f"실패 행 수: {len(d['failures'])}. 규칙 진단과 전체 graph 실패는 분리한다."]
    for r in d['failures']:out.append(f"- {r['trial_id']}: {','.join(r['graph_or_rule_errors']) or '형식/지원 계약/단계 검사 실패'}")
    return '\n'.join(out)+'\n'
