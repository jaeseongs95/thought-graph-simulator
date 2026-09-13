"""동일한 v054 지표를 모델별 계산하고, 대응된 제어 성패만 비교한다."""
from copy import deepcopy
from .contracts import write_json
from .design import MODELS, PROBLEMS, ARMS
from order_probe_v054.reporting import summarize as summarize_order

def summarize(plan,trials,calls,complete):
    models={}
    for key in MODELS:
        pp={'seeds':plan['seeds'],'baseline':deepcopy(plan['baseline']),'policy':plan['policy']}
        pp['baseline']['config']['model']=plan['identities'][key]['model']
        ts=[t for t in trials if t['model_key']==key];cs=[c for c in calls if c['model_key']==key]
        models[key]=summarize_order(pp,ts,cs,{},complete)
        models[key]['data_complete']=complete
        models[key]['identity']=plan['identities'][key]
    cross=[];cells={}
    maps={key:{(p['problem_id'],p['arm'],p['seed']):p for p in m['pairs']} for key,m in models.items()}
    for pid in PROBLEMS:
        for arm in ARMS:
            rows=[]
            for seed in plan['seeds']:
                q,g=(maps[key][pid,arm,seed] for key in MODELS)
                rows.append({'problem_id':pid,'arm':arm,'seed':seed,
                    'both_models_observed':q['both_observed'] and g['both_observed'],
                    'reference_selective':q['direction_selective_success'],'candidate_selective':g['direction_selective_success'],
                    'reference_both_valid':q['both_valid'],'candidate_both_valid':g['both_valid']})
            cross.extend(rows)
            # 비교 양쪽이 관측된 쌍만 성패 대비에 포함한다. 미실행은 패배가 아니다.
            observed=[r for r in rows if r['both_models_observed']]
            qonly=sum(r['reference_selective'] and not r['candidate_selective'] for r in observed)
            gonly=sum(r['candidate_selective'] and not r['reference_selective'] for r in observed)
            cells[pid+'/'+arm]={'assigned':10,'observed_pairs':len(observed),'unobserved_pairs':len(rows)-len(observed),
                'both_success':sum(r['candidate_selective'] and r['reference_selective'] for r in observed),
                'reference_only':qonly,'candidate_only':gonly,
                'neither_success':sum(not r['candidate_selective'] and not r['reference_selective'] for r in observed),
                'candidate_minus_reference_rate':(gonly-qonly)/10 if complete else None}
    return {'contract':'v055-model-probe-report-r1','models':models,'cross_model_pairs':cross,'cross_model_results':cells,
        'primary_directed_assigned':160,'neutral_assigned':80,'policy':plan['policy'],
        'statistical_note':'2문제×10 seed의 대응 기술통계. 숫자 seed를 공유해도 모델 사이 동일 난수 표본은 아님. 방향/순서/모델 비교는 같은 240응답 재집계이며 합산하지 않음.'}

def save_report(out,r):
    keys=('contract','data_integrity','data_complete','comparative_analysis_ready','inference_calls','max_inference_calls',
        'plan_sha256','event_tip','run_state','failure_stage','failure_kind','failure_slot_id','run_error')
    write_json(out/'audit.json',{k:r[k] for k in keys});write_json(out/'summary.json',r)
    lines=['# v055 두 소형 모델의 D 제어 비교','',
        f"무결성: {r['data_integrity']} / 완료: {r['data_complete']} / 호출: {r['inference_calls']}/240 / 출처: {r['evidence_kind']}",
        '방향 지정 160회와 중립 80회. 유효 증명 생성과 선택적 D 제어를 분리한다.','']
    if not r['data_complete']:
        lines += ['## 미완료',f"{r['failure_stage']} / {r['failure_kind']} / {r['run_error']}",
            '미실행·무효 응답을 같은 원인으로 세지 않는다. 전체 비교율은 null이며 0%가 아니다.','']
    for key,m in r['models'].items():
        lines += [f"## {key}: {m['model']}",'','|문제/순서/방향|배정|관측|유효 증명|방향 일치|깊이|','|---|---:|---:|---:|---:|---|']
        for name,g in m['groups'].items():
            success='해당 없음' if g['direction_success'] is None else g['direction_success']
            lines.append(f"|{name}|{g['assigned']}|{g['observed']}|{g['layers']['strict_valid']['correct']}|{success}|{g['depth_distribution']}|")
        lines += ['','### 선택적 제어','', '|문제/순서|배정 쌍|둘 다 유효|선택적 성공|중립 대비 차이|','|---|---:|---:|---:|---:|']
        for name,c in m['core_results'].items():
            diff=c['mean_directed_minus_neutral'];s='미완료' if diff is None else f'{100*diff:.1f}%p'
            lines.append(f"|{name}|{c['assigned_pairs']}|{c['both_valid_pairs']}|{c['direction_selective_success']}|{s}|")
        lines += ['','### 두 규칙순서 모두에서 유지되는 제어','', '|문제|배정 seed|4개 응답 유효|두 순서 모두 성공|','|---|---:|---:|---:|']
        for name,c in m['robust_results'].items():lines.append(f"|{name}|{c['assigned_seed_groups']}|{c['all_four_valid']}|{c['both_orders_selective_success']}|")
        lines += ['','### 순서 효과: 유효한 두 응답만 깊이 비교','', '|문제/방향|배정|둘 다 유효|깊이 변화|미측정|','|---|---:|---:|---:|---:|']
        for name,c in m['order_results'].items():lines.append(f"|{name}|{c['assigned_pairs']}|{c['both_valid_pairs']}|{c['depth_changed']}|{c['unmeasured']}|")
    lines += ['','## 모델 간 선택적 제어 비교','', '|문제/순서|배정|미관측 쌍|둘 다 성공|Qwen만|Gemma만|둘 다 미성공|Gemma−Qwen|','|---|---:|---:|---:|---:|---:|---:|---:|']
    for name,c in r['cross_model_results'].items():
        value=c['candidate_minus_reference_rate'];s='미완료' if value is None else f'{100*value:.1f}%p'
        lines.append(f"|{name}|{c['assigned']}|{c['unobserved_pairs']}|{c['both_success']}|{c['reference_only']}|{c['candidate_only']}|{c['neither_success']}|{s}|")
    lines += ['','## 해석 범위','',r['statistical_note'],
        '요청의 model 필드만 바꿨다. 모델 패키지의 가중치·tokenizer·native template·한국어 처리 차이를 단독 분해한 실험은 아니다.',
        '규칙 순서에 반응하는 것만으로 D 제어에 성공한 것이 아니다. 내부 사고·학습 우선순위·A/M 전체 제어를 직접 계측하지 않는다.',
        'HTTP 실패는 자동 재시도하지 않는다. 원문을 보정하거나 정답 경로를 대신 채우지 않는다.',
        '모델별 raw token/time은 summary.json에 있다. 캐시·로드 비용을 포함하므로 속도 우열 검정이 아니다.',
        f"계획 SHA-256: {r['plan_sha256']}",f"event tip: {r['event_tip']}",
        '해시는 동봉 계획·원문 일관성 검사이며 외부 실행 전자서명이 아니다.']
    (out/'summary.ko.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
