"""전체 배정과 양쪽 유효쌍을 함께 보고. 실패한 역할/seed를 빼지 않는다."""
from __future__ import annotations
import collections
import itertools
import statistics
from .contracts import write_json
from .design import ROLES


def cost(calls):
    keys = ('prompt_eval_count', 'prompt_eval_cached_count', 'eval_count', 'total_duration',
            'load_duration', 'prompt_eval_duration', 'eval_duration')
    out = {'calls': len(calls)}
    for k in keys:
        values = [c.get(k) for c in calls]
        out[k] = sum(values) if values and all(v is not None for v in values) else None
        out[k + '_missing'] = sum(v is None for v in values)
    elapsed = [c['elapsed_ns'] / 1e6 for c in calls]
    out['http_median_ms'] = statistics.median(elapsed) if elapsed else None
    out['http_mean_ms'] = statistics.mean(elapsed) if elapsed else None
    return out


def matched_review(m, role):
    if m is None or not m['format_valid']:
        return False
    target = [] if role['M'] == 0 else (['argument'] if role['M'] == 1 else ['acceptance_criterion'])
    return m['review_targets'] == target and m['review_target_valid'] is True and m['review_findings_valid'] is True


def coordinate_role_match(m, role):
    """대상 조작 관측. 검토 finding의 참/거짓 성공과는 다른 지표."""
    if m is None or not (m['proof_valid'] and m['representation_valid'] and m['review_target_valid']):
        return False
    targets = [] if role['M'] == 0 else (['argument'] if role['M'] == 1 else ['acceptance_criterion'])
    return (m['A'] == role['A'] and m['D'] == (1 if role['D'] == 'shallow' else 2)
            and m['M'] == role['M'] and m['review_targets'] == targets)


def contrast_rows(plan, trials, complete):
    lookup = {(t['seed'], t['cycle'], t['role_id']): t for t in trials}
    rows = []
    for axis in ('A', 'D', 'M'):
        others = [a for a in ('A', 'D', 'M') if a != axis]
        for left, right in itertools.combinations(ROLES, 2):
            if not all(left[a] == right[a] for a in others):
                continue
            summary = {'axis': axis, 'left': left['id'], 'right': right['id'],
                       'assigned_pairs': len(plan['seeds']) * plan['cycles'],
                       'both_assessable': 0, 'both_semantically_valid': 0,
                       'coordinate_pairs_available': 0, 'coordinate_change_observed': 0,
                       'clean_requested_axis_change': 0, 'unmanipulated_axes_changed': 0,
                       'both_valid_no_axis_change': 0, 'not_jointly_valid': 0}
            for seed in plan['seeds']:
                for cycle in range(plan['cycles']):
                    l, r = lookup[seed, cycle, left['id']], lookup[seed, cycle, right['id']]
                    if not (l['assessable'] and r['assessable']):
                        continue
                    summary['both_assessable'] += 1
                    ml, mr = l['measurement'], r['measurement']
                    if all(m['proof_valid'] and m['representation_valid'] and m['review_target_valid'] for m in (ml,mr)):
                        summary['coordinate_pairs_available'] += 1
                        if coordinate_role_match(ml,left) and coordinate_role_match(mr,right) and all(ml[a] == mr[a] for a in others) and ml[axis] != mr[axis]:
                            summary['coordinate_change_observed'] += 1
                    if not (ml['strict_valid'] and mr['strict_valid']):
                        summary['not_jointly_valid'] += 1; continue
                    summary['both_semantically_valid'] += 1
                    if any(ml[a] != mr[a] for a in others):
                        summary['unmanipulated_axes_changed'] += 1
                    if ml[axis] == mr[axis]:
                        summary['both_valid_no_axis_change'] += 1
                    if l['role_match'] and r['role_match'] and all(ml[a] == mr[a] for a in others) and ml[axis] != mr[axis]:
                        summary['clean_requested_axis_change'] += 1
            # 끝나지 않은 계획을 완료된 대응 비교로 계산하지 않는다.
            summary['rate_over_assigned'] = summary['clean_requested_axis_change'] / summary['assigned_pairs'] if complete else None
            n = summary['both_semantically_valid']
            summary['rate_given_both_valid'] = summary['clean_requested_axis_change'] / n if complete and n else None
            rows.append(summary)
    return rows


def summarize(p, trials, calls, observations, complete):
    arms = {}
    for role in ROLES:
        selected = [t for t in trials if t['role_id'] == role['id']]
        measured = [t['measurement'] for t in selected if t['assessable']]
        rcalls = [c for c in calls if c['role_id'] == role['id']]
        row = {'assigned': len(selected), 'recorded': sum(t['observed'] for t in selected),
               'assessable': len(measured), 'format_valid': sum(m['format_valid'] for m in measured),
               'goal_string_correct': sum(m['goal_string_correct'] is True for m in measured),
               'proof_valid': sum(m['proof_valid'] is True for m in measured),
               'representation_valid': sum(m['representation_valid'] is True for m in measured),
               'requested_review_correct': sum(matched_review(m, role) for m in measured),
               'strict_valid': sum(m['strict_valid'] for m in measured),
               'role_match': sum(t['role_match'] is True for t in selected),
               'observed_coordinates': dict(collections.Counter(str((m['A'], m['D'], m['M'])) for m in measured)),
               'usage': cost(rcalls)}
        row['role_match_rate_over_assigned'] = row['role_match'] / row['assigned'] if complete else None
        arms[role['id']] = row
    groups = collections.defaultdict(list)
    for c in calls:
        groups[c['request_sha256']].append(c)
    unstable = []
    for key, group in groups.items():
        contents = {c['content_sha256'] for c in group}
        payloads = {c.get('payload_sha256') for c in group}
        if len(contents) > 1 or len(payloads) > 1:
            unstable.append({'request_sha256': key, 'slots': [c['id'] for c in group],
                             'content_variants': len(contents), 'payload_variants': len(payloads)})
    per_seed = {str(seed): {role['id']: sum(t['role_match'] is True for t in trials if t['seed'] == seed and t['role_id'] == role['id'])
                           for role in ROLES} for seed in p['seeds']}
    return {'contract': 'v051-adm-pilot-report-r1', 'model': p['baseline']['config']['model'],
            'temperature': p['baseline']['config']['options'].get('temperature'),
            'seeds': p['seeds'], 'cycles': p['cycles'], 'problem_sha256': p['problem_sha256'],
            'problem_id': p['problem']['id'], 'fixed_goal': p['problem']['goal'],
            'roles': arms, 'per_seed': per_seed, 'paired': contrast_rows(p, trials, complete),
            'call_status_counts': dict(collections.Counter(c['status'] for c in calls)),
            'unique_execution_usage': cost(calls), 'unique_request_count': len(groups),
            'unstable_request_groups': unstable,
            'all_requested_roles_succeeded': (all(t['role_match'] is True for t in trials) if complete else None),
            'policy': p['policy']}


def save_report(out, r):
    write_json(out / 'audit.json', {k:r[k] for k in ('contract', 'data_integrity', 'data_complete', 'comparative_analysis_ready', 'inference_calls', 'plan_sha256', 'event_tip')})
    write_json(out / 'summary.json', r)
    lines = ['# v051 고정 문제·목표 A/D/M 조작 예비실험', '',
             f"- 자료 무결성: **{r['data_integrity']}** / 수집 완료: **{r['data_complete']}** / 기록 호출: **{r['inference_calls']}/{r['max_inference_calls']}**",
             f"- 문제: `{r['problem_id']}` / 고정 목표: `{r['fixed_goal']}` / seed: {len(r['seeds'])}개 / 반복: {r['cycles']}",
             f"- 출처: `{r['evidence_kind']}` / 모델: `{r['model']}` / temperature: `{r['temperature']}`", '',
             '**자료 PASS는 가설 PASS가 아니다.** 아래 모든 분모는 사전 배정 수다. 미실행/통신 실패는 모델 오답으로 확정하지 않으며 세부 관측 분모를 JSON에 남긴다.', '',
             '| 요청 역할 | 유효 형식 | 유효 증명 | 유효 표현 | 요청 검토 정답 | 전체 기록 유효 | 역할 일치 |',
             '|---|---:|---:|---:|---:|---:|---:|']
    for name, a in r['roles'].items():
        n = a['assigned']; review = '해당 없음' if name.endswith('M0') else f"{a['requested_review_correct']}/{n}"
        lines.append(f"| {name} | {a['format_valid']}/{n} | {a['proof_valid']}/{n} | {a['representation_valid']}/{n} | {review} | {a['strict_valid']}/{n} | {a['role_match']}/{n} |")
    lines += ['', '## 한 축 대조', '', '| 축 | 구조·대상 조작 관측 / 전체 배정쌍 | 전체 판정까지 유효한 조작 | 양쪽 유효쌍 | 다른 축도 달라진 쌍 |', '|---|---:|---:|---:|---:|']
    for axis in ('A', 'D', 'M'):
        rows = [x for x in r['paired'] if x['axis'] == axis]
        lines.append(f"| {axis} | {sum(x['coordinate_change_observed'] for x in rows)}/{sum(x['assigned_pairs'] for x in rows)} | {sum(x['clean_requested_axis_change'] for x in rows)}/{sum(x['assigned_pairs'] for x in rows)} | {sum(x['both_semantically_valid'] for x in rows)} | {sum(x['unmanipulated_axes_changed'] for x in rows)} |")
    lines += ['', '구조·대상 조작은 M finding 정답까지 보장하지 않는다. 전체 배정쌍 분모와 양쪽 유효쌍 분모를 구분한다. 실패한 조건을 빼서 독립성을 주장하지 않는다.',
              'M의 집계에는 0↔1, 0↔2, 1↔2 대조가 함께 들어간다. 서로 독립된 표본 수가 아니며 세부 표는 summary.json의 paired에 있다.', '',
              '## 비용·해석', '', f"실제 호출 수: {r['unique_execution_usage']['calls']}. 경로마다 1회 호출이지만 토큰 수·출력 길이·지연은 같다고 가정하지 않는다.",
              f"동일 요청의 응답이 달라진 그룹: {len(r['unstable_request_groups'])}. 같은 seed의 완전 결정성을 전제하지 않는다.",
              '이 결과는 한 문제의 외부 증명·표현·검토 기록에 관한 조작 예비실험이다. 잠재 사고 좌표, 범용 축 독립성, 더 큰 모델과 동급 성능을 판정하지 않는다.',
              'M2 판정이 틀리더라도 유효한 A/D 관측은 별도로 남는다. M2라는 대상을 지정한 것과 그 검토의 정답은 다르다.', '',
              f"계획 SHA-256: `{r['plan_sha256']}`", f"마지막 event: `{r['event_tip']}`", '',
              '해시는 동봉 외부 계획·원문의 일관성 검사이며 외부 실행 전자서명은 아니다.']
    (out / 'summary.ko.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
