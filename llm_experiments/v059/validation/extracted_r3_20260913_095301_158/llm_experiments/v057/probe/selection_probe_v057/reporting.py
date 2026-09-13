"""완전한 증명 제어와 축소된 규칙 선택 제어의 성공을 구분한다."""
from itertools import product
from collections import Counter
from .contracts import write_json
from .design import MODELS,MODES,PROBLEMS,ARMS,DIRECTIONS
from adm_pilot_v051.reporting import cost as execution_usage
from .measure import terminal_depths

def success_value(t):
    if not t['observed'] or t['measurement'] is None:return None
    m=t['measurement'];return m['strict_valid'] if t['mode']=='graph' else m['choice_valid']

def depth(t):
    if not t['observed'] or t['measurement'] is None:return None
    m=t['measurement'];return m['D'] if t['mode']=='graph' else m['implied_depth']

def summarize(plan,trials,calls,complete):
    lookup={(t['mode'],t['model_key'],t['problem_id'],t['arm'],t['seed'],t['direction']):t for t in trials}
    groups={};pairs=[];robust=[];neutrals=[];contrasts=[]
    for mode,key,pid,arm,d in product(MODES,MODELS,PROBLEMS,ARMS,DIRECTIONS):
        rows=[lookup[mode,key,pid,arm,seed,d] for seed in plan['seeds']];seen=[t for t in rows if t['observed']]
        groups['/'.join((mode,key,pid,arm,d))]={'mode':mode,'model_key':key,'assigned':len(rows),'observed':len(seen),
            'format_valid':sum(t['measurement']['format_valid'] for t in seen),'task_valid':sum(success_value(t) is True for t in seen),
            'task_unmeasured':sum(success_value(t) is None for t in seen),'direction_success':None if d=='neutral' else sum(t['role_match'] is True for t in seen),
            'depth_distribution':dict(Counter(str(depth(t)) if depth(t) is not None else 'unmeasured' for t in seen)),
            'depth_meaning':'generated_proof_D' if mode=='graph' else 'problem_implied_choice_depth_not_generated_proof'}
    for mode,key,pid,arm,seed in product(MODES,MODELS,PROBLEMS,ARMS,plan['seeds']):
        sh,de,ne=(lookup[mode,key,pid,arm,seed,d] for d in DIRECTIONS)
        observed=sh['observed'] and de['observed'];ok=bool(observed and sh['role_match'] is True and de['role_match'] is True and depth(sh)!=depth(de))
        pairs.append({'mode':mode,'model_key':key,'problem_id':pid,'arm':arm,'seed':seed,'both_observed':observed,
            'both_task_valid':success_value(sh) is True and success_value(de) is True,'shallow_depth':depth(sh),'deep_depth':depth(de),
            'selective_success':ok if observed else None,'full_proof_D_control_success':(ok if observed else None) if mode=='graph' else None})
        seen=observed and ne['observed'];ds=[v[0] for v in terminal_depths(PROBLEMS[pid]).values()];lo,hi=min(ds),max(ds)
        neutral_score=(int(success_value(ne) is True and depth(ne)==lo)+int(success_value(ne) is True and depth(ne)==hi))/2 if ne['observed'] else None
        directed_score=(int(sh['role_match'] is True)+int(de['role_match'] is True))/2 if observed else None
        neutrals.append({'mode':mode,'model_key':key,'problem_id':pid,'arm':arm,'seed':seed,'three_observed':seen,
            'directed_score':directed_score,'neutral_score':neutral_score,'directed_minus_neutral':directed_score-neutral_score if seen else None})
    pairmap={(p['mode'],p['model_key'],p['problem_id'],p['arm'],p['seed']):p for p in pairs}
    for mode,key,pid,seed in product(MODES,MODELS,PROBLEMS,plan['seeds']):
        x,y=(pairmap[mode,key,pid,a,seed] for a in ARMS);seen=x['both_observed'] and y['both_observed']
        robust.append({'mode':mode,'model_key':key,'problem_id':pid,'seed':seed,'four_observed':seen,
            'both_orders_success':bool(x['selective_success'] and y['selective_success']) if seen else None,
            'all_four_task_valid':x['both_task_valid'] and y['both_task_valid']})
    for key,pid,arm,seed in product(MODELS,PROBLEMS,ARMS,plan['seeds']):
        g,c=(pairmap[mode,key,pid,arm,seed] for mode in MODES);seen=g['both_observed'] and c['both_observed']
        outcome='unobserved'
        if seen:outcome=('both_selective' if g['selective_success'] and c['selective_success'] else ('graph_only' if g['selective_success'] else ('choice_only' if c['selective_success'] else 'neither')))
        contrasts.append({'model_key':key,'problem_id':pid,'arm':arm,'seed':seed,'four_observed':seen,'graph_selective':g['selective_success'],
            'choice_selective':c['selective_success'],'outcome':outcome})
    models={}
    for key in MODELS:
        modes={}
        for mode in MODES:
            ts=[t for t in trials if (t['model_key'],t['mode'])==(key,mode)];ps=[p for p in pairs if (p['model_key'],p['mode'])==(key,mode)]
            cs=[c for c in calls if (c['model_key'],c['mode'])==(key,mode)]
            modes[mode]={'assigned_calls':120,'observed_calls':sum(t['observed'] for t in ts),'format_valid':sum(t['measurement']['format_valid'] for t in ts if t['observed']),
                'task_valid':sum(success_value(t) is True for t in ts),'assigned_pairs':40,'observed_pairs':sum(p['both_observed'] for p in ps),
                'selective_success':sum(p['selective_success'] is True for p in ps),'selective_rate':sum(p['selective_success'] is True for p in ps)/40 if complete else None,
                'full_proof_D_control_success':sum(p['selective_success'] is True for p in ps) if mode=='graph' else None,
                'unique_execution_usage':execution_usage(cs)}
        ct=[c for c in contrasts if c['model_key']==key];counter=Counter(c['outcome'] for c in ct)
        models[key]={'model':plan['identities'][key]['model'],'modes':modes,'task_contrast':{k:counter[k] for k in ('both_selective','graph_only','choice_only','neither','unobserved')},
                     'choice_minus_graph_rate':(counter['choice_only']-counter['graph_only'])/40 if complete else None}
    return {'contract':'v057-selection-report-r1','models':models,'groups':groups,'pairs':pairs,'robust':robust,
            'neutral_comparisons':neutrals,'task_contrasts':contrasts,'policy':plan['policy'],'primary_directed_assigned':320,'neutral_assigned':160}

def save_report(out,r):
    keys=('contract','data_integrity','data_complete','comparative_analysis_ready','inference_calls','max_inference_calls','plan_sha256','event_tip','run_state','failure_stage','failure_kind','failure_slot_id','run_error')
    write_json(out/'audit.json',{k:r[k] for k in keys});write_json(out/'summary.json',r)
    lines=['# v057 전체 증명 생성 / 마지막 규칙 선택 대조','',f"무결성: {r['data_integrity']} / 완료: {r['data_complete']} / 호출: {r['inference_calls']}/480 / 출처: {r['evidence_kind']}",
        '두 모델 모두 merged 배치. graph 240회 + choice 240회. 방향 지정 320회 + 중립 160회.','',
        '**choice 성공은 마지막 규칙을 고른 성공이다. 전체 증명이나 A/D/M 제어 성공이 아니다.**','']
    if not r['data_complete']:lines+=['## 미완료',str(r['run_error']),'미관측은 패배가 아니며 전체 비교율은 null이다.','']
    for key,m in r['models'].items():
        lines += [f"## {m['model']}",'','|과제|관측/배정|과제 유효|선택적 대응 성공|전체 증명 D 제어|','|---|---:|---:|---:|---|']
        for mode,x in m['modes'].items():
            full=x['full_proof_D_control_success'] if mode=='graph' else '측정 안 함'
            lines.append(f"|{mode}|{x['observed_calls']}/120|{x['task_valid']}|{x['selective_success']}/40|{full}|")
        lines += ['',f"과제별 대응 결과: `{m['task_contrast']}`",'choice_only: 축소된 선택 과제만 성공. 같은 생성 내부에서 선택을 이해했다가 잊었다는 판정이 아니다.','']
        for mode in MODES:
            lines += [f'### {mode} 세부 결과','|문제/순서/방향|관측|과제 유효|방향 이행|깊이|','|---|---:|---:|---:|---|']
            for pid,arm,d in product(PROBLEMS,ARMS,DIRECTIONS):
                g=r['groups']['/'.join((mode,key,pid,arm,d))];lines.append(f"|{pid}/{arm}/{d}|{g['observed']}|{g['task_valid']}|{g['direction_success']}|{g['depth_distribution']}|")
            lines += ['choice의 깊이는 문제 명세에서 선택 규칙에 대응하는 값이다. 생성된 증명의 실제 깊이가 아니다.' if mode=='choice' else 'graph의 깊이는 실제 유효한 증명에서만 계산한다.',
                      '',f"중복 없이 원래 호출 비용만 집계: `{m['modes'][mode]['unique_execution_usage']}`",'']
    lines += ['## 중립 대조','중립 응답 하나를 두 방향 기준에 재채점하며 두 독립 표본으로 세지 않는다.',
        '|모델/과제/문제/순서|관측 묶음|방향 지정−중립 평균|','|---|---:|---:|']
    for key,mode,pid,arm in product(MODELS,MODES,PROBLEMS,ARMS):
        xs=[n['directed_minus_neutral'] for n in r['neutral_comparisons'] if (n['model_key'],n['mode'],n['problem_id'],n['arm'])==(key,mode,pid,arm) and n['three_observed']]
        avg=sum(xs)/len(xs) if xs and r['data_complete'] else None;lines.append(f'|{key}/{mode}/{pid}/{arm}|{len(xs)}|{avg}|')
    lines += ['','## 해석 경계','모델 응답의 자동 보정/재시도/정답 경로 주입 없음. 두 과제는 출력 요구가 다르다. 내부 정책·이해·학습 원인 단독 식별 아님.',
        '같은 응답을 여러 표로 재집계해도 새로운 독립 실험으로 합산하지 않는다.',f"계획 SHA-256: {r['plan_sha256']}",f"event tip: {r['event_tip']}"]
    (out/'summary.ko.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
