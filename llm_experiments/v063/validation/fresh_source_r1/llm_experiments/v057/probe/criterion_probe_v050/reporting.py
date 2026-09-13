"""경로의 최종값·전체 증거·공유 호출 비용을 구분하여 보고한다."""
from __future__ import annotations
import csv,statistics
from collections import Counter,defaultdict
from .contracts import write_json
from .plan import ARMS
from .scoring import path_stages

def counted(rows,key):return sum(r[key] is True for r in rows)
def total_known(rows,key):
    vals=[r.get(key) for r in rows]
    return sum(vals) if all(type(v) is int for v in vals) else None

def metrics(rows):
    return {'assigned':len(rows),'observed':counted(rows,'observed'),'payload_valid':counted(rows,'payload_valid'),
        **{k:counted(rows,k) for k in ('observed_correct','primitives_correct','finding_correct','gap_correct','witness_correct','strict_trace_correct')},
        'positive_assigned':sum(r['gap_positive'] for r in rows),
        'positive_gap_observed':sum(r['gap_positive'] and r['gap_correct'] is not None for r in rows),
        'measured':{k:sum(r[k] is not None for r in rows) for k in ('observed_correct','primitives_correct','finding_correct','gap_correct','witness_correct','strict_trace_correct')},
        'positive_gap_correct':sum(r['gap_positive'] and r['gap_correct'] is True for r in rows),
        'first_failures':dict(Counter(r['first_failed_stage'] for r in rows if r['first_failed_stage'] is not None))}

def summarize(plan,trials,calls,observations,complete):
    keys=('prompt_eval_count','prompt_eval_cached_count','eval_count','total_duration','load_duration','prompt_eval_duration','eval_duration')
    arms={};byid={c['id']:c for c in calls}
    for arm in ARMS:
        rows=[r for r in trials if r['arm']==arm];stat=metrics(rows)
        refs=[b['id']+'__'+s for b in plan['blocks'] for s in path_stages(arm)]
        rc=[byid[k] for k in refs if k in byid];times=[]
        for b in plan['blocks']:
            ids=[b['id']+'__'+s for s in path_stages(arm)]
            if all(k in byid for k in ids):times.append(sum(byid[k]['elapsed_ns'] for k in ids))
        stat['path_usage']={'actual_referenced_calls':len(rc),**{k:total_known(rc,k) for k in keys},
            'http_median_ms':statistics.median(times)/1e6 if times else None,
            'shared_with_other_path':arm.startswith('staged'),'time_basis':'경로 내 실측 HTTP시간 합. 호스트 전체시간/독립 재실행 측정 아님'}
        arms[arm]=stat
    perseed=[]
    for seed in plan['seeds']:
        perseed.append({'seed':seed,'arms':{arm:metrics([r for r in trials if r['arm']==arm and r['seed']==seed]) for arm in ARMS}})
    paired={}
    for left,right in [('oneshot_commuted','oneshot_original'),('staged_commuted','oneshot_commuted'),('staged_pipeline','staged_commuted')]:
        results={}
        for measure in ('finding_correct','strict_trace_correct'):
            if not complete:results[measure]=None;continue
            diffs=[];wins=losses=ties=0;onlyleft=onlyright=0
            for s in plan['seeds']:
                l={r['block_id']:r[measure] for r in trials if r['arm']==left and r['seed']==s}
                rr={r['block_id']:r[measure] for r in trials if r['arm']==right and r['seed']==s}
                d=sum(l[k] for k in l)-sum(rr[k] for k in l);diffs.append(d/len(l))
                wins+=d>0;losses+=d<0;ties+=d==0
                onlyleft+=sum(l[k] and not rr[k] for k in l);onlyright+=sum(rr[k] and not l[k] for k in l)
            results[measure]={'left_only_correct':onlyleft,'right_only_correct':onlyright,'seed_win_tie_loss':[wins,ties,losses],'mean_seed_accuracy_difference':sum(diffs)/len(diffs)}
        paired[left+'-'+right]=results
    repeats=defaultdict(list)
    for c in calls:repeats[c['request_sha256']].append(c['content_sha256'])
    return {'contract':'v050-report-r1','model':plan['baseline']['config']['model'],'temperature':plan['baseline']['config']['options'].get('temperature'),
        'seeds':plan['seeds'],'cycles':plan['cycles'],'arms':arms,'per_seed':perseed,'paired':paired,
        'call_status_counts':dict(Counter(o['status'] for o in observations.values())),
        'unique_execution_usage':{'calls':len(calls),**{k:total_known(calls,k) for k in keys}},
        'request_groups':len(repeats),'unstable_request_groups':sum(len(set(v))>1 for v in repeats.values()),
        'policy':plan['policy']}

def markdown(r):
    lines=['# v050 원래 기준 판정 과제 재통합 결과','',
        f'- 무결성: **{r["data_integrity"]}** / 수집 완료: **{r["data_complete"]}** / 비교 가능: **{r["comparative_analysis_ready"]}**',
        f'- 출처: **{r["evidence_kind"]}** / 실제 기록 호출: **{r["inference_calls"]}/{r["max_inference_calls"]}**',
        f'- 모델: `{r["model"]}` / temperature: `{r["temperature"]}` / seed 수: {len(r["seeds"])} / 반복: {r["cycles"]}',
        '', '자료 무결성 PASS와 모델 정답률은 다르다. 아래 분모는 각 항목의 관측 수이며 배정은 경로당 80건이다. 뒤 단계 미실행/오류가 앞 단계의 정답을 지우지 않는다.','',
        '| 경로 | 입력 읽기 | 원자 판정 | finding 세 값 | gap 단독 | 양성 gap | 전체 경로 |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for arm,a in r['arms'].items():
        ratio=lambda k: str(a[k])+'/'+str(a['measured'][k]) if a['measured'][k] else '미관측'
        lines.append('| '+arm+' | '+' | '.join(ratio(k) for k in ('observed_correct','primitives_correct','finding_correct','gap_correct'))+' | '+str(a['positive_gap_correct'])+'/'+str(a['positive_gap_observed'])+' | '+ratio('strict_trace_correct')+' |')
    lines+=['','## Seed별 전체 경로 정답','', '| seed | oneshot 원식 | oneshot 교환식 | staged 교환식 | staged pipeline |','|---:|---:|---:|---:|---:|']
    for s in r['per_seed']:lines.append('| '+str(s['seed'])+' | '+' | '.join(f'{s["arms"][a]["strict_trace_correct"]}/{s["arms"][a]["assigned"]}' for a in ARMS)+' |')
    lines+=['','## 비용 해석','',f'실제 유일 호출은 {r["unique_execution_usage"]["calls"]}회다. 두 staged 경로는 추출과 proof AND 호출을 공유한다.',
        '경로별 비용에는 공유 호출을 각 경로에 한 번씩 포함한다. 경로별 비용을 더해서 실제 총비용으로 부르면 안 된다.','',
        '| 경로 | 참조한 실제 호출 | 입력 토큰 | 출력 토큰 | 경로 HTTP 중앙값 ms |','|---|---:|---:|---:|---:|']
    for arm,a in r['arms'].items():
        u=a['path_usage'];v=u['http_median_ms'];lines.append(f'| {arm} | {u["actual_referenced_calls"]} | {u["prompt_eval_count"]} | {u["eval_count"]} | {round(v,3) if v is not None else "null"} |')
    lines+=['','## 해석 범위','',
        '원래 단독 사실 주장 criterion_witness의 observed/primitives/세 finding 재통합이다. rules로 증명 경로를 새로 만드는 과제가 아니며 A/D/M 축 조작 실험은 아니다.',
        'oneshot 두 조건은 gap 식의 순서만 다르다. oneshot 대 staged는 prompt/출력 schema/호출 구성의 묶음 비교다.',
        'staged의 answer_only_accepts는 모델이 추출한 same_as_goal을 그대로 연결한다. proof/gap은 실제 호출 응답이다.',
        'v049의 10 seed 전체를 재사용한다. 성공 seed 선별·자동 수정·자동 재시도는 없다. 동일 seed 반복은 새 문제 표본이 아니다.',
        '실행이 미완료면 미관측을 오답으로 확정하지 않으며 대응 정확도 차이를 계산하지 않는다.',
        '',f'계획 SHA-256: `{r["plan_sha256"]}`',f'마지막 event: `{r["event_tip"]}`',
        '해시는 동봉 외부 계획/원문의 일관성 검사이며 외부 실행 전자서명은 아니다.','']
    return '\n'.join(lines)

def save_report(out,r):
    write_json(out/'summary.json',r)
    (out/'summary.ko.md').write_text(markdown(r),encoding='utf-8')
    write_json(out/'audit.json',{k:r[k] for k in ('data_integrity','data_complete','comparative_analysis_ready','plan_sha256','event_tip')})
    for n,rows in [('calls.csv',r['calls']),('trials.csv',[{k:v for k,v in row.items() if k!='actual'} for row in r['trials']])]:
        if rows:
            with (out/n).open('w',newline='',encoding='utf-8-sig') as f:
                w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    write_json(out/'seed_results.json',r['per_seed'])
