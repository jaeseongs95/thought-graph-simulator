"""입력 배치 효과, 증명 유효성, D 선택적 제어를 서로 다른 분모로 보고한다."""
from copy import deepcopy
from .contracts import write_json
from .design import MODELS,LAYOUTS,PROBLEMS,ARMS
from model_probe_v055.reporting import summarize as model_summarize


def summarize(plan,trials,calls,complete):
    layouts={}
    for layout in LAYOUTS:
        ts=[t for t in trials if t['layout']==layout];cs=[c for c in calls if c['layout']==layout]
        layouts[layout]=model_summarize(plan,ts,cs,complete)
    pairmaps={(layout,key):{(p['problem_id'],p['arm'],p['seed']):p for p in layouts[layout]['models'][key]['pairs']} for layout in LAYOUTS for key in MODELS}
    contrasts=[];results={};validity={}
    for key in MODELS:
        for pid in PROBLEMS:
            for arm in ARMS:
                rows=[]
                for seed in plan['seeds']:
                    a,b=(pairmaps[layout,key][pid,arm,seed] for layout in LAYOUTS)
                    rows.append({'model_key':key,'problem_id':pid,'arm':arm,'seed':seed,'both_layouts_observed':a['both_observed'] and b['both_observed'],
                        'split_success':a['direction_selective_success'],'merged_success':b['direction_selective_success']})
                contrasts.extend(rows);seen=[r for r in rows if r['both_layouts_observed']]
                s=sum(r['split_success'] and not r['merged_success'] for r in seen);m=sum(r['merged_success'] and not r['split_success'] for r in seen)
                results[f'{key}/{pid}/{arm}']={'assigned_pairs':10,'observed_pairs':len(seen),'unobserved_pairs':10-len(seen),
                    'both_success':sum(r['split_success'] and r['merged_success'] for r in seen),'split_only':s,'merged_only':m,
                    'neither_success':sum(not r['split_success'] and not r['merged_success'] for r in seen),
                    'merged_minus_split_rate':(m-s)/10 if complete else None}
        ts=[t for t in trials if t['model_key']==key];a={t['reference_slot_id']:t for t in ts if t['layout']=='split'};b={t['reference_slot_id']:t for t in ts if t['layout']=='merged'}
        seen=[(a[k],b[k]) for k in a if a[k]['observed'] and b[k]['observed']]
        both=sum(x['measurement']['strict_valid'] and y['measurement']['strict_valid'] for x,y in seen)
        s=sum(x['measurement']['strict_valid'] and not y['measurement']['strict_valid'] for x,y in seen);m=sum(y['measurement']['strict_valid'] and not x['measurement']['strict_valid'] for x,y in seen)
        validity[key]={'assigned_pairs':120,'observed_pairs':len(seen),'unobserved_pairs':120-len(seen),'both_valid':both,'split_only_valid':s,'merged_only_valid':m,
            'neither_valid':len(seen)-both-s-m,'merged_minus_split_validity_rate':(m-s)/120 if complete else None}
    return {'contract':'v056-layout-report-r1','layouts':layouts,'layout_contrasts':contrasts,'layout_results':results,'validity_contrasts':validity,
        'primary_directed_assigned':320,'neutral_assigned':160,'policy':plan['policy']}


def save_report(out,r):
    keys=('contract','data_integrity','data_complete','comparative_analysis_ready','inference_calls','max_inference_calls','plan_sha256','event_tip','run_state','failure_stage','failure_kind','failure_slot_id','run_error')
    write_json(out/'audit.json',{k:r[k] for k in keys});write_json(out/'summary.json',r)
    lines=['# v056 입력 메시지 배치 대조','',f"무결성: {r['data_integrity']} / 완료: {r['data_complete']} / 호출: {r['inference_calls']}/480 / 출처: {r['evidence_kind']}",
        'split: 기존 system/user 분리. merged: 같은 텍스트를 하나의 user 메시지로 연결. 방향 지정 320 + 중립 160.','']
    if not r['data_complete']:lines+=['## 미완료',str(r['run_error']),'미관측을 패배로 세지 않는다. 전체 비교율은 null.','']
    for layout,x in r['layouts'].items():
        for key,m in x['models'].items():
            lines += [f"## {m['model']} / {layout}",'','|문제/순서/방향|배정|관측|유효 증명|방향 일치|깊이|','|---|---:|---:|---:|---:|---|']
            for name,g in m['groups'].items():lines.append(f"|{name}|{g['assigned']}|{g['observed']}|{g['layers']['strict_valid']['correct']}|{g['direction_success'] if g['direction_success'] is not None else '해당 없음'}|{g['depth_distribution']}|")
            lines+=['','### 선택적 D 제어','|문제/순서|배정 쌍|둘 다 유효|선택적 성공|','|---|---:|---:|---:|']
            for name,g in m['core_results'].items():lines.append(f"|{name}|{g['assigned_pairs']}|{g['both_valid_pairs']}|{g['direction_selective_success']}|")
            lines+=['','### 두 규칙 순서 모두에서 유지되는 제어','|문제|배정 seed 묶음|네 증명 모두 유효|두 순서 모두 선택적 성공|','|---|---:|---:|---:|']
            for name,g in m['robust_results'].items():lines.append(f"|{name}|{g['assigned_seed_groups']}|{g['all_four_valid']}|{g['both_orders_selective_success']}|")
            lines+=['','### 중립 대조','|문제/순서|측정 가능한 seed 묶음|방향 지정 − 중립 평균|','|---|---:|---:|']
            for pid in PROBLEMS:
                for arm in ARMS:
                    ns=[n['directed_minus_neutral'] for n in m['neutral_comparisons'] if n['problem_id']==pid and n['arm']==arm and n['directed_minus_neutral'] is not None]
                    delta=sum(ns)/len(ns) if ns and r['data_complete'] else None
                    lines.append(f"|{pid}/{arm}|{len(ns)}|{delta}|")
            lines+=['중립 응답 한 개를 두 방향 기준에 재채점한 값이며, 두 개의 독립 응답으로 세지 않는다.','',f"원래 호출만 한 번 집계한 비용: `{m['unique_execution_usage']}`"]
    lines+=['','## 증명 유효성의 배치 효과','|모델|배정 쌍|미관측|둘 다 유효|분리만 유효|병합만 유효|둘 다 무효|병합−분리|','|---|---:|---:|---:|---:|---:|---:|---:|']
    for key,v in r['validity_contrasts'].items():lines.append(f"|{key}|{v['assigned_pairs']}|{v['unobserved_pairs']}|{v['both_valid']}|{v['split_only_valid']}|{v['merged_only_valid']}|{v['neither_valid']}|{v['merged_minus_split_validity_rate']}|")
    lines+=['','## 배치별 선택적 제어 비교','|모델/문제/순서|배정|미관측|둘 다 성공|분리만|병합만|둘 다 미성공|병합−분리|','|---|---:|---:|---:|---:|---:|---:|---:|']
    for name,c in r['layout_results'].items():lines.append(f"|{name}|{c['assigned_pairs']}|{c['unobserved_pairs']}|{c['both_success']}|{c['split_only']}|{c['merged_only']}|{c['neither_success']}|{c['merged_minus_split_rate']}|")
    lines+=['','## 해석 경계','증명 유효성 개선만으로 D 제어 성공이 아니다. 중립도 유지한다. 같은 480응답을 관점별 재집계하며 독립 표본으로 합산하지 않는다.',
        '역할·턴 경계·특수 토큰 배치가 함께 달라진 대조다. 내부 정책 우선순위나 학습 원인을 직접 측정하지 않는다.',
        '한국어 내용/규칙/목표/출력 계약은 유지했고 정답 경로를 제공하거나 호스트가 보정하지 않는다.',
        '이전 계획은 재귀 JSON으로 포함하지 않는다. 감사된 기준선 ZIP을 별도 바이트 파일로 보존한다.',
        f"계획 SHA-256: {r['plan_sha256']}",f"event tip: {r['event_tip']}"]
    (out/'summary.ko.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
