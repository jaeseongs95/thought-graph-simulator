"""순서에 따른 경로 변화와 방향 지시에 따른 D 제어를 별도로 보고한다."""
from collections import Counter
from statistics import mean
from adm_pilot_v051.reporting import cost
from .contracts import write_json
from .design import PROBLEMS, ARMS, DIRECTIONS
from .measure import depth_bounds

FIELDS = ('format_valid', 'final_ref_valid', 'proof_valid', 'strict_valid')

def summarize(plan, trials, calls, observations, complete):
    groups = {}
    for pid in PROBLEMS:
        for arm in ARMS:
            for direction in DIRECTIONS:
                rows = [r for r in trials if (r['problem_id'],r['arm'],r['direction']) == (pid,arm,direction)]
                layers = {}
                for field in FIELDS:
                    values = [r['measurement'].get(field) if r['measurement'] is not None else None for r in rows]
                    layers[field] = {'correct':sum(v is True for v in values), 'incorrect':sum(v is False for v in values), 'unmeasured':sum(v is None for v in values)}
                distribution = Counter(str(r['measurement']['D']) if r['measurement'] is not None and r['measurement']['D'] is not None else 'unmeasured' for r in rows)
                success = None if direction == 'neutral' else sum(r['role_match'] is True for r in rows)
                groups[pid+'/'+arm+'/'+direction] = {'assigned':len(rows), 'observed':sum(r['observed'] for r in rows),
                    'layers':layers, 'depth_distribution':dict(distribution), 'direction_success':success,
                    'success_rate':success/len(rows) if complete and success is not None else None}
    lookup = {(r['problem_id'],r['arm'],r['seed'],r['direction']):r for r in trials}
    pairs, neutral = [], []
    for pid, problem in PROBLEMS.items():
        low, high = depth_bounds(problem)
        for arm in ARMS:
            for seed in plan['seeds']:
                left, right = (lookup[pid,arm,seed,d] for d in ('shallow','deep'))
                lm, rm = left['measurement'], right['measurement']
                both_valid = bool(lm and rm and lm['strict_valid'] and rm['strict_valid'])
                success = bool(both_valid and left['role_match'] and right['role_match'] and lm['D'] != rm['D'])
                pairs.append({'problem_id':pid, 'arm':arm, 'seed':seed, 'both_observed':left['observed'] and right['observed'],
                    'both_valid':both_valid, 'shallow_actual':lm['D'] if lm else None, 'deep_actual':rm['D'] if rm else None,
                    'direction_selective_success':success})
                nm = lookup[pid,arm,seed,'neutral']['measurement']
                expected = (int(nm['D'] == low)+int(nm['D'] == high))/2 if nm and nm['strict_valid'] else 0
                directed = (int(left['role_match'] is True)+int(right['role_match'] is True))/2
                neutral.append({'problem_id':pid, 'arm':arm, 'seed':seed, 'neutral_actual':nm['D'] if nm else None,
                    'neutral_standardized_success':expected if complete else None, 'directed_minus_neutral':directed-expected if complete else None,
                    'note':'중립 응답 1개를 두 방향에 재채점. 새 호출 또는 독립 표본 2개가 아님'})
    core = {}
    for pid in PROBLEMS:
        for arm in ARMS:
            ps = [x for x in pairs if x['problem_id'] == pid and x['arm'] == arm]
            ns = [x for x in neutral if x['problem_id'] == pid and x['arm'] == arm]
            success = sum(x['direction_selective_success'] for x in ps)
            core[pid+'/'+arm] = {'assigned_pairs':len(ps), 'both_valid_pairs':sum(x['both_valid'] for x in ps),
                'direction_selective_success':success, 'rate_over_assigned':success/len(ps) if complete else None,
                'mean_directed_minus_neutral':mean(x['directed_minus_neutral'] for x in ns) if complete else None,
                'interpretation':'incomplete' if not complete else ('selective_D_control_observed' if success else 'selective_D_control_not_observed')}
    # 같은 응답을 재사용한 파생 비교다. 분모를 늘려 독립 표본으로 합산하지 않는다.
    order_contrasts, order_results = [], {}
    for pid in PROBLEMS:
        for direction in DIRECTIONS:
            cells = []
            for seed in plan['seeds']:
                a,b = (lookup[pid,arm,seed,direction]['measurement'] for arm in ARMS)
                valid = bool(a and b and a['strict_valid'] and b['strict_valid'])
                cell = {'problem_id':pid, 'direction':direction, 'seed':seed, 'both_valid':valid,
                    'original_D':a['D'] if a else None, 'swapped_D':b['D'] if b else None,
                    'depth_changed':bool(a['D'] != b['D']) if valid else None,
                    'structure_changed':bool(a['proof_signature'] != b['proof_signature']) if valid else None}
                cells.append(cell); order_contrasts.append(cell)
            order_results[pid+'/'+direction] = {'assigned_pairs':len(cells), 'both_valid_pairs':sum(x['both_valid'] for x in cells),
                'depth_changed':sum(x['depth_changed'] is True for x in cells),
                'unmeasured':sum(not x['both_valid'] for x in cells),
                'rate_over_assessable':sum(x['depth_changed'] is True for x in cells)/sum(x['both_valid'] for x in cells) if complete and any(x['both_valid'] for x in cells) else None}
    robust_pairs, robust_results = [], {}
    pairmap = {(x['problem_id'],x['arm'],x['seed']):x for x in pairs}
    for pid in PROBLEMS:
        for seed in plan['seeds']:
            a,b = (pairmap[pid,arm,seed] for arm in ARMS)
            robust_pairs.append({'problem_id':pid, 'seed':seed, 'all_four_valid':a['both_valid'] and b['both_valid'],
                'both_orders_selective_success':a['direction_selective_success'] and b['direction_selective_success']})
        ps = [x for x in robust_pairs if x['problem_id'] == pid]
        robust_results[pid] = {'assigned_seed_groups':len(ps), 'all_four_valid':sum(x['all_four_valid'] for x in ps),
            'both_orders_selective_success':sum(x['both_orders_selective_success'] for x in ps),
            'rate_over_assigned':sum(x['both_orders_selective_success'] for x in ps)/len(ps) if complete else None}
    return {'contract':'v054-order-probe-report-r1', 'model':plan['baseline']['config']['model'],
        'temperature':plan['baseline']['config']['options'].get('temperature'), 'seeds':plan['seeds'],
        'groups':groups, 'core_results':core, 'pairs':pairs, 'neutral_comparisons':neutral,
        'order_contrasts':order_contrasts, 'order_results':order_results, 'robust_pairs':robust_pairs, 'robust_results':robust_results,
        'unique_execution_usage':cost(calls), 'policy':plan['policy'], 'primary_directed_assigned':80, 'neutral_assigned':40,
        'statistical_note':'고정 문제 2개. 방향쌍 40·순서쌍 60·견고성 20은 같은 120응답의 서로 다른 재집계이며 합산하지 않음'}

def save_report(out, report):
    keys = ('contract','data_integrity','data_complete','comparative_analysis_ready','inference_calls','plan_sha256','event_tip',
        'run_state','failure_stage','failure_kind','failure_slot_id','run_error')
    write_json(out/'audit.json',{k:report[k] for k in keys}); write_json(out/'summary.json',report)
    lines = ['# v054 규칙 순서와 D 방향 제어 대조','',
        f"자료 무결성: {report['data_integrity']} / 완료: {report['data_complete']} / 호출: {report['inference_calls']}/120",
        f"모델: {report['model']} / 출처: {report['evidence_kind']}",'',
        '규칙 순서에 따라 경로가 바뀌는 것과, 요청한 shallow/deep에 따라 바뀌는 것은 다른 결과다.',
        '방향 지정 80회와 중립(neutral) 40회는 별도 대조다. 중립 응답 하나를 두 방향에 재채점해도 호출은 한 번이다.','']
    if not report['data_complete']:
        lines += ['## 실행 중단',f"단계: {report['failure_stage']} / 종류: {report['failure_kind']} / 원인: {report['run_error']}",
            '전체 미완료. 미실행·전송 실패를 의미 오답으로 바꾸지 않는다.','']
    lines += ['## 실제 깊이와 방향 이행','', '|문제/규칙순서/방향|배정|유효 증명|방향 일치|실제 깊이|','|---|---:|---:|---:|---|']
    for key, g in report['groups'].items():
        success = '해당 없음' if g['direction_success'] is None else g['direction_success']
        lines.append(f"|{key}|{g['assigned']}|{g['layers']['strict_valid']['correct']}|{success}|{g['depth_distribution']}|")
    lines += ['','## 같은 순서에서 shallow/deep 선택적 제어','', '|문제/순서|배정 대응쌍|둘 다 유효|선택적 성공|중립 대비 평균 차이|','|---|---:|---:|---:|---:|']
    for key, c in report['core_results'].items():
        diff=c['mean_directed_minus_neutral']; text='미완료' if diff is None else f'{100*diff:.2f}%p'
        lines.append(f"|{key}|{c['assigned_pairs']}|{c['both_valid_pairs']}|{c['direction_selective_success']}|{text}|")
    lines += ['','## 두 순서 모두에서 유지되는 선택적 제어','', '|문제|seed 묶음|4응답 유효|두 순서 모두 성공|','|---|---:|---:|---:|']
    for key,c in report['robust_results'].items():
        lines.append(f"|{key}|{c['assigned_seed_groups']}|{c['all_four_valid']}|{c['both_orders_selective_success']}|")
    lines += ['','## 방향을 고정하고 순서만 바꾼 효과','', '|문제/방향|배정|둘 다 유효|깊이 변경|비교 미측정|','|---|---:|---:|---:|---:|']
    for key,c in report['order_results'].items():
        lines.append(f"|{key}|{c['assigned_pairs']}|{c['both_valid_pairs']}|{c['depth_changed']}|{c['unmeasured']}|")
    lines += ['','## 판정 범위','',
        'original 60요청은 v053 original과 바이트 동일. swapped는 입력 rules의 블록 순서만 다르다.',
        '규칙 내용·ID·연쇄 내부 순서·facts·goal·모델·옵션·seed·system·schema는 보존한다.',
        '선택적 성공 0인데 순서 효과만 있으면 규칙 제시 방식에 따른 경로 변화이지 D 제어 성공이 아니다.',
        '정답 깊이·증명·선택할 규칙을 제공하지 않고 자동 보정·재시도하지 않는다.',
        '모든 seed·실패를 보존한다. A/M 통합·내부 사고 제어·광범위 일반화는 이 실험의 판정 범위가 아니다.',
        report['statistical_note'], f"계획 SHA-256: {report['plan_sha256']}", f"마지막 event: {report['event_tip']}",
        '해시는 동봉 원문·계획의 일관성 검사이며 외부 실행 전자서명이 아니다.']
    (out/'summary.ko.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
