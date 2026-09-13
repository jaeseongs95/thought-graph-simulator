"""증명 성공률과 방향 제어를 다른 분모·표로 보고한다."""
from collections import Counter
from statistics import mean
from adm_pilot_v051.reporting import cost
from .contracts import write_json
from .design import PROBLEMS, ARMS, DIRECTIONS
from .measure import depth_bounds

FIELDS = ('format_valid','final_ref_valid','proof_valid','strict_valid')

def summarize(plan, trials, calls, observations, complete):
    groups = {}
    for pid in PROBLEMS:
        for arm in ARMS:
            for direction in DIRECTIONS:
                rows = [r for r in trials if r['problem_id']==pid and r['arm']==arm and r['direction']==direction]
                layers = {}
                for field in FIELDS:
                    values = [r['measurement'].get(field) if r['measurement'] is not None else None for r in rows]
                    layers[field] = {'correct':sum(v is True for v in values), 'incorrect':sum(v is False for v in values),
                                     'unmeasured':sum(v is None for v in values)}
                distribution = Counter(str(r['measurement']['D']) if r['measurement'] is not None and r['measurement']['D'] is not None else 'unmeasured' for r in rows)
                groups[pid+'/'+arm+'/'+direction] = {'assigned':len(rows), 'observed':sum(r['observed'] for r in rows),
                    'layers':layers, 'depth_distribution':dict(distribution),
                    'direction_success': None if direction=='neutral' else sum(r['role_match'] is True for r in rows),
                    'success_rate': (sum(r['role_match'] is True for r in rows)/len(rows)) if complete and direction!='neutral' else None}
    lookup = {(r['problem_id'],r['arm'],r['seed'],r['direction']):r for r in trials}
    pairs=[]; neutral=[]
    for pid, problem in PROBLEMS.items():
        low, high = depth_bounds(problem)
        for arm in ARMS:
            for seed in plan['seeds']:
                left,right = (lookup[pid,arm,seed,d] for d in ('shallow','deep'))
                lm,rm = left['measurement'],right['measurement']
                both_valid = bool(lm and rm and lm['strict_valid'] and rm['strict_valid'])
                success = bool(both_valid and left['role_match'] and right['role_match'] and lm['D'] != rm['D'])
                pairs.append({'problem_id':pid,'arm':arm,'seed':seed,'assigned_pairs':1,
                    'both_observed':left['observed'] and right['observed'], 'both_valid':both_valid,
                    'shallow_actual':lm['D'] if lm else None,'deep_actual':rm['D'] if rm else None,
                    'direction_selective_success':success,
                    'directed_macro_success':(int(left['role_match'] is True)+int(right['role_match'] is True))/2 if complete else None})
                nm = lookup[pid,arm,seed,'neutral']['measurement']
                expected = ((int(nm['D']==low)+int(nm['D']==high))/2) if nm and nm['strict_valid'] else 0
                directed = (int(left['role_match'] is True)+int(right['role_match'] is True))/2
                neutral.append({'problem_id':pid,'arm':arm,'seed':seed,'neutral_actual':nm['D'] if nm else None,
                    'neutral_standardized_success':expected if complete else None,
                    'directed_minus_neutral':directed-expected if complete else None,
                    'note':'중립 응답 1개를 두 역할에 재채점. 새 호출/독립 표본 2개가 아님'})
    contrasts=[]; core={}
    for pid in PROBLEMS:
        for arm in ARMS:
            ps=[x for x in pairs if x['problem_id']==pid and x['arm']==arm]
            ns=[x for x in neutral if x['problem_id']==pid and x['arm']==arm]
            success=sum(x['direction_selective_success'] for x in ps)
            core[pid+'/'+arm]={'assigned_pairs':len(ps),'both_valid_pairs':sum(x['both_valid'] for x in ps),
                'direction_selective_success':success,'rate_over_assigned':success/len(ps) if complete else None,
                'mean_directed_minus_neutral':mean(x['directed_minus_neutral'] for x in ns) if complete else None,
                'interpretation':'incomplete' if not complete else ('selective_D_control_observed' if success else 'selective_D_control_not_observed')}
        for seed in plan['seeds']:
            original=next(x for x in pairs if x['problem_id']==pid and x['arm']=='original' and x['seed']==seed)
            defined=next(x for x in pairs if x['problem_id']==pid and x['arm']=='defined' and x['seed']==seed)
            contrasts.append({'problem_id':pid,'seed':seed,
                'defined_minus_original_macro_success':defined['directed_macro_success']-original['directed_macro_success'] if complete else None,
                'defined_minus_original_pair_success':int(defined['direction_selective_success'])-int(original['direction_selective_success']) if complete else None})
    return {'contract':'v053-depth-probe-report-r1','model':plan['baseline']['config']['model'],
            'temperature':plan['baseline']['config']['options'].get('temperature'),'seeds':plan['seeds'],
            'groups':groups,'core_results':core,'pairs':pairs,'neutral_comparisons':neutral,'definition_contrasts':contrasts,
            'unique_execution_usage':cost(calls),'policy':plan['policy'],
            'primary_directed_assigned':80,'neutral_assigned':40,
            'statistical_note':'두 고정 문제에 대한 seed별 기술적 대응 비교. p-value나 독립 표본수 확대 없음'}

def save_report(out, report):
    keys=('contract','data_integrity','data_complete','comparative_analysis_ready','inference_calls','plan_sha256','event_tip',
          'run_state','failure_stage','failure_kind','failure_slot_id','run_error')
    write_json(out/'audit.json',{key:report[key] for key in keys})
    write_json(out/'summary.json',report)
    lines=['# v053 D 정의 명시 대조','',
           f"자료 무결성: {report['data_integrity']} / 완료: {report['data_complete']} / 호출: {report['inference_calls']}/120", 
           f"모델: {report['model']} / 출처: {report['evidence_kind']}",'',
           '유효 증명 생성은 방향 제어 성공과 다르다. 아래 대응쌍 성공을 함께 확인한다.','']
    if not report['data_complete']:
        lines += ['## 실행 중단',f"단계: {report['failure_stage']} / 종류: {report['failure_kind']}",
                  f"슬롯: {report['failure_slot_id']} / 원인: {report['run_error']}",
                  '전체 실험 미완료. 미실행/전송 실패를 의미 오답으로 바꾸지 않는다.','']
    lines += ['## 실제 깊이와 방향 이행','',
              '|문제/지시문/방향|배정|유효 증명|요청 깊이 일치|실제 깊이 분포|',
              '|---|---:|---:|---:|---|']
    for key, group in report['groups'].items():
        success='해당 없음' if group['direction_success'] is None else str(group['direction_success'])
        lines.append(f"|{key}|{group['assigned']}|{group['layers']['strict_valid']['correct']}|{success}|{group['depth_distribution']}|")
    lines += ['','## 같은 seed의 shallow/deep 선택적 제어','',
              '|문제/지시문|배정 대응쌍|둘 다 유효|둘 다 요청 방향으로 변경|중립 대비 평균 차이|',
              '|---|---:|---:|---:|---:|']
    for key, core in report['core_results'].items():
        diff=core['mean_directed_minus_neutral']; text='미완료' if diff is None else f'{100*diff:.2f}%p'
        lines.append(f"|{key}|{core['assigned_pairs']}|{core['both_valid_pairs']}|{core['direction_selective_success']}|{text}|")
    lines += ['','## 판정 범위','',
              'original은 v052 D 단독의 요청 바이트를 유지했다. defined는 깊이 정의 문단 하나만 추가했다.',
              '최소/최대 깊이 정답, 선택할 규칙, 예시 정답 그래프를 요청에 주지 않았다. 호스트가 경로를 골라주지 않는다.',
              '모든 seed를 보고한다. 중립 재채점·대응쌍을 독립 문제로 더하지 않는다.',
              '정의 명시 후 개선되어도 길이/주의 효과를 내부 기전에서 분리한 결과는 아니다.',
              'A/M 또는 A×D×M 통합 성공으로 확대하지 않는다. 원래 v052 실패 기록은 그대로 보존한다.',
              f"계획 SHA-256: {report['plan_sha256']}",f"마지막 event: {report['event_tip']}",
              '동봉 원문과 계획의 일관성 검사이며 외부 실행 전자서명은 아니다.']
    (out/'summary.ko.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
