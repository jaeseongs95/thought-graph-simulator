"""2×2 대응 차이·상호작용과 파이프라인을 분리해 보고한다."""
from __future__ import annotations
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from paired_probe_v048.reporting import _counts, _costs, write_csv
from .plan import ARMS, DIRECT, input_key
from .contracts import EXPRS

PAIRS = (("original","commuted"),("original_open","commuted_open"),
         ("original_open","original"),("commuted_open","commuted")) + tuple((arm,"pipeline") for arm in DIRECT)

def summarize(plan: dict, trials: list[dict], resources: list[dict], decoded: dict, complete: bool) -> dict:
    arm_reports={};per_seed=[];by_seed={}
    for arm in ARMS:
        rows=[r for r in trials if r['arm']==arm]
        metrics=_counts(rows,complete);tables=[]
        for seed in plan['seeds']:
            sr=[r for r in rows if r['seed']==seed]
            counts=_counts(sr,complete and all(r['observed'] for r in sr))
            by_seed[seed,arm]=counts;per_seed.append({'seed':seed,'arm':arm,**counts})
            for cycle in range(plan['cycles']):
                cells=[r for r in sr if r['cycle']==cycle]
                observed=len(cells)==4 and all(r['observed'] for r in cells)
                tables.append({'seed':seed,'cycle':cycle,'observed':observed,
                    'final_four_of_four':all(r['final_correct'] is True for r in cells) if observed else None,
                    'trace_four_of_four':all(r['trace_correct'] is True for r in cells) if observed and arm=='pipeline' else None})
        metrics.update({'tables':tables,'four_of_four_repeats':sum(t['final_four_of_four'] is True for t in tables),
            'trace_four_of_four_repeats':sum(t['trace_four_of_four'] is True for t in tables) if arm=='pipeline' else None,
            'per_input':{k:{'correct':sum(r['final_correct'] is True for r in rows if input_key(r['a'],r['b'])==k),
                            'assigned':sum(input_key(r['a'],r['b'])==k for r in rows),
                            'observed':sum(r['observed'] for r in rows if input_key(r['a'],r['b'])==k)} for k in ('00','01','10','11')},
            'status_counts':dict(Counter(r['status'] for r in rows)),
            'costs':_costs(rows,[c for c in resources if c['arm']==arm])})
        arm_reports[arm]=metrics
    paired={};tm={(r['block_id'],r['arm']):r for r in trials}
    for reference,contender in PAIRS:
        counts=Counter(both_correct=0,reference_only=0,contender_only=0,neither_correct=0,unobserved_pairs=0)
        deltas=[]
        for block in plan['blocks']:
            l,r=tm[block['id'],reference],tm[block['id'],contender]
            if not l['observed'] or not r['observed']:counts['unobserved_pairs']+=1;continue
            lc,rc=l['final_correct'] is True,r['final_correct'] is True
            counts['both_correct' if lc and rc else 'reference_only' if lc else 'contender_only' if rc else 'neither_correct']+=1
        for seed in plan['seeds']:
            l,r=by_seed[seed,reference],by_seed[seed,contender]
            deltas.append({'seed':seed,'assigned_per_arm':l['assigned'],
                'final_accuracy_delta':(r['final_correct']-l['final_correct'])/l['assigned'] if complete else None,
                'positive_accuracy_delta':(r['positive_correct']-l['positive_correct'])/l['positive_assigned'] if complete else None})
        valid=[d['final_accuracy_delta'] for d in deltas if d['final_accuracy_delta'] is not None]
        paired[contender+'-'+reference]={'reference_arm':reference,'contender_arm':contender,**dict(counts),
            'per_seed':deltas,'final_accuracy_delta':statistics.mean(valid) if complete else None,
            'seed_wins':sum(d>0 for d in valid) if complete else None,'seed_ties':sum(d==0 for d in valid) if complete else None,
            'seed_losses':sum(d<0 for d in valid) if complete else None,'inferential_p_value':None,'confidence_interval':None}
    interactions=[]
    for seed in plan['seeds']:
        r={arm:by_seed[seed,arm]['final_accuracy'] for arm in DIRECT}
        val=(r['commuted']-r['original'])-(r['commuted_open']-r['original_open']) if complete else None
        interactions.append({'seed':seed,'difference_of_differences':val})
    groups=defaultdict(list)
    for c in resources:groups[c['request_sha256']].append(c)
    repeats=[]
    for h,calls in groups.items():
        first=calls[0];signature={(c['status'],c['value']) for c in calls}
        hashes={c['response_content_sha256'] for c in calls if c['response_content_sha256'] is not None}
        repeats.append({'request_sha256':h,'seed':first['seed'],'stage':first['stage'],'recorded_calls':len(calls),
            'unique_content_strings':len(hashes),'unique_semantic_status_values':len(signature),
            'semantic_repeat_instability':len(calls)>=2 and len(signature)>1})
    patterns=[]
    for seed in plan['seeds']:
        r={a:by_seed[seed,a] for a in ARMS}
        patterns.append({'seed':seed,'all_direct_forms_perfect':all(r[a]['final_correct']==r[a]['assigned'] for a in DIRECT) if complete else None,
            'pipeline_trace_perfect':r['pipeline']['strict_trace_correct']==r['pipeline']['assigned'] if complete else None,
            'all_arms_final_perfect':all(r[a]['final_correct']==r[a]['assigned'] for a in ARMS) if complete else None})
    return {'contract':'expression-report-v049-r1','arms':arm_reports,'per_seed':per_seed,
        'paired_final_outcomes':paired,'factorial_interaction':{'definition':plan['analysis_policy']['interaction'],
            'per_seed':interactions,'mean':statistics.mean(x['difference_of_differences'] for x in interactions) if complete else None,
            'note':'등록 표현의 정확도 차이의 차이. 내부 계산 순서를 뜻하지 않음'},
        'behavior_patterns':patterns,'request_repeats':repeats,
        'repeated_request_groups':sum(x['recorded_calls']>=2 for x in repeats),'unstable_request_groups':sum(x['semantic_repeat_instability'] for x in repeats),
        'call_status_counts':dict(Counter(d['status'] for d in decoded.values())),
        'seeds':plan['seeds'],'seed_count':len(plan['seeds']),'cycles':plan['cycles'],
        'temperature':plan['baseline']['config']['options'].get('temperature'),'model':plan['baseline']['config']['model'],
        'reference_only_scores':plan['reference']['reference_only_scores'],
        'seed_interpretation':'v048 seed 10개 전체를 재사용한 표현 대조. 새 seed 검증·새 논리 문제 표본이 아님. 2회는 순서/재현 확인.',
        'scope':plan['analysis_policy']['scope'],'fairness':'모든 직접식과 pipeline의 최종값을 비교. pipeline 중간값은 별도. best-of 표현을 사후 선택해 점수 합성하지 않음.'}

def _s(x):return '측정 없음' if x is None else str(x)
def _ms(x):return '측정 없음' if x is None else f'{x/1e6:.3f}'

def write_markdown(path: Path, r: dict) -> None:
    lines=['# v049 표현 2×2 대조 결과','',
        f'- 출처: **{r["evidence_kind"]}** / 새 모델 추론 표기: **{r["new_model_inference"]}**',
        f'- 자료 무결성: **{r["data_integrity"]}** / 수집 완료: **{r["data_complete"]}** / 비교 가능: **{r["comparative_analysis_ready"]}**',
        f'- 실제 기록 요청: **{r["inference_calls"]}/{r["max_inference_calls"]}**',
        f'- 모델: `{r["model"]}` / temperature: `{r["temperature"]}` / 반복: `{r["cycles"]}`',
        f'- v048 전체 seed 재사용: `{r["seeds"]}`','',
        '자료가 유효한 실행에서도 모델은 틀릴 수 있다. 무결성과 정답률은 다르다.','',
        '| 조건 | 식 | 최종값 정답/배정 | 양성 정답/배정 | 진리표 4/4 | 중간값 포함 |',
        '|---|---|---:|---:|---:|---:|']
    for arm in ARMS:
        a=r['arms'][arm];expression=EXPRS.get(arm,'NOT b → AND(a, 반환값)')
        trace='측정 대상 아님' if arm!='pipeline' else f'{a["strict_trace_correct"]}/{a["assigned"]}'
        lines.append(f'| {arm} | `{expression}` | {a["final_correct"]}/{a["assigned"]} | {a["positive_correct"]}/{a["positive_assigned"]} | {a["four_of_four_repeats"]}/{len(a["tables"])} | {trace} |')
    lines+=['','## Seed별 결과','','| seed | original | commuted | original_open | commuted_open | pipeline 최종 | pipeline 전체 |','|---:|---:|---:|---:|---:|---:|---:|']
    sr={(x['seed'],x['arm']):x for x in r['per_seed']}
    for seed in r['seeds']:
        cells=[f'{sr[seed,a]["final_correct"]}/{sr[seed,a]["assigned"]}' for a in ARMS]
        p=sr[seed,'pipeline'];lines.append(f'| {seed} | '+' | '.join(cells)+f' | {p["strict_trace_correct"]}/{p["assigned"]} |')
    lines+=['','## 등록한 대응 비교','','| 대조(앞−뒤) | 뒤 조건만 정답 | 앞 조건만 정답 | seed 승/무/패 | 정확도 차이 |','|---|---:|---:|---|---:|']
    for name,p in r['paired_final_outcomes'].items():
        lines.append(f'| {name} | {p["reference_only"]} | {p["contender_only"]} | {_s(p["seed_wins"])}/{_s(p["seed_ties"])}/{_s(p["seed_losses"])} | {_s(p["final_accuracy_delta"])} |')
    lines+=['',f'상호작용(차이의 차이): **{_s(r["factorial_interaction"]["mean"])}**',
        '`(commuted-original)-(commuted_open-original_open)`; 단위는 정확도 비율 차이이며 내부 사고 순서를 뜻하지 않는다.',
        '', '## 자원 사용','','| 조건 | 호출 | 입력 토큰 합 | 출력 토큰 합 | 경로 HTTP시간 중앙값 ms | 로딩 합 ms |','|---|---:|---:|---:|---:|---:|']
    for arm in ARMS:
        c=r['arms'][arm]['costs']
        lines.append(f'| {arm} | {c["eval_count"]["actual_calls"]} | {_s(c["prompt_eval_count"]["total"])} | {_s(c["eval_count"]["total"])} | {_ms(c["complete_path_http_sum_ns"]["median"])} | {_ms(c["load_duration"]["total"])} |')
    lines+=['','호출 비용은 실패 포함. pipeline은 두 HTTP시간 합이며 호스트 전체 시간·동일 FLOPs가 아니다. 누락은 null.',
        '',r['seed_interpretation'],r['fairness'],r['scope'],
        f'동일 요청 반복 그룹: {r["repeated_request_groups"]}; 의미/형식 불안정 그룹: {r["unstable_request_groups"]}.',
        '서로 다른 표현별 결과를 모두 보존한다. 새 모델/ADM 축/새 논리식은 이번 실험에서 조작하지 않았다.',
        '',f'계획 SHA-256: `{r["plan_sha256"]}`',f'마지막 event 해시: `{r["event_tip"]}`',
        '해시는 원문·동봉 외부계획의 일관성 검사이며 모든 원문을 함께 바꾸는 공격이나 외부 실행의 전자서명이 아니다.']
    if not r['data_complete']:
        lines[2:2]=['**미완료. 기록된 성공 개수는 부분 관측이며 미실행은 오답이 아니다. 전체 비교차와 상호작용은 null.**','']
        lines+=['','중단 사유: '+str(r['run_error'])]
    path.write_text('\n'.join(lines)+'\n',encoding='utf-8')
