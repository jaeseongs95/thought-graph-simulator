"""수치 판정은 두 검산기가 별도 수행한다. 이 파일은 공통 한국어 표시 전용이다."""
def render(s):
    def ratio(x):return f"{x['successes']}/{x['assigned']} (미측정 {x['unmeasured']})"
    out=['# v082 — 직접 ID 선택 대 후보 계산표 후 ID 선택','',
         f"실행 상태: `{s['state']}` / 출처: `{s['provenance']}`",'',
         'D는 실제 목표 증명 DAG의 최장 의존 깊이, W는 목표 지지 규칙 수다. 네 구조는 기존 진단 문제이며 새 구조/holdout 0개다.',
         '아래 주평가는 최종 실제 graph·모든 단계·경로·요구 지표 기준이다. 계산표 정확도는 주평가를 소급 변경하지 않는다.','']
    for metric in ('D','W'):
        out.extend([f'## {metric} 주평가','', '| 지표 | candidate_id | profiled_id |','|---|---:|---:|'])
        for key,title in [('selection_success','요구 선택'),('generator_success','선택 경로 생성'),('metric_end_to_end','요구 지표 종단'),
                          ('selection_pairs','양방향 선택'),('end_to_end_pairs','양방향 종단'),
                          ('presentation_robust_end_to_end','네 표시 전체 양방향 종단')]:
            out.append(f"| {title} | {ratio(s['groups']['candidate_id']['totals'][metric][key])} | {ratio(s['groups']['profiled_id']['totals'][metric][key])} |")
        p=s['paired_trials'][metric]['metric_end_to_end']
        out += ['',f"같은 조건 종단: 양쪽 성공 {p['both_success']}, 직접군만 {p['candidate_id_only']}, 계산표군만 {p['profiled_id_only']}, 양쪽 실패 {p['both_failure']}, 비교 불가 {p['not_comparable']}.",'']
    d=s['profile_analysis']
    out += ['## 계산표 — 독립 호출 및 추가 계약','',
            f"계산표 호출 배정: {d['unique_profile_calls']}개. 문제×seed×경로마다 1회이며 양방향·D/W·표시 조건에 공유한다. 반복 사용을 새 계산 표본으로 세지 않는다.",
            f"계산표 전체 정확: {ratio(d['trace'])}; 최종 D 숫자: {ratio(d['D_values'])}; 최종 W 숫자: {ratio(d['W_values'])}.",
            '숫자만 맞은 것, 과정까지 맞은 것, 해당 숫자를 따라 선택한 것, 실제 graph 종단 성공을 구별한다.',
            '틀린 계산표라도 정상적으로 반환된 원문은 선택기에 그대로 전달한다. 동점 보고는 사후 타이브레이크하지 않는다.','',
            '| 추가 계약 지표 | D | W |','|---|---:|---:|']
    for key,title in [('both_traces_success','선택에 공유된 두 계산표 정확'),('both_requested_values_correct','두 요청 지표 숫자 정확'),
                      ('follows_reported_extreme','모델 보고값의 요구 극값 선택'),('full_pipeline_success','계산표부터 종단까지 모두 성공')]:
        out.append(f"| {title} | {ratio(d['trial_diagnostics']['D'][key])} | {ratio(d['trial_diagnostics']['W'][key])} |")
    out.append(f"| 추가 계약 양방향 | {ratio(d['pipeline_pairs']['D'])} | {ratio(d['pipeline_pairs']['W'])} |")
    out += ['', '계산부터 종단까지의 추가 성공 조건은 기존 graph 성공 기준과 다르다. 앞 표의 성과를 이 조건으로 덮어쓰지 않는다.',
            '## D/W 네 요구 구별','']
    for v in ('candidate_id','profiled_id'):
        rows=s['groups'][v]['metric_discrimination']
        out.append(f"{v}: 네 선택 모두 정답 {sum(x['all_four_selections_correct'] is True for x in rows)}/{len(rows)}, 네 종단 모두 정답 {sum(x['all_four_end_to_end_correct'] is True for x in rows)}/{len(rows)}.")
    out += ['',f"공통 지정 경로 참조: {ratio(s['reference'])}. 두 군에 복제하지 않는다.", '','## 호출·사용량','']
    for v in ('candidate_id','profiled_id'):
        for stage,g in s['groups'][v]['usage_by_stage'].items():
            out.append(f"{v} / {stage}: {g['calls']}회, 출력 계측 합 {g['fields']['eval_count']['sum_observed']}, 누락 {g['fields']['eval_count']['missing']}.")
    out += ['', '## 판정 범위와 종료',
            '후보별 명시적 구조 계산을 먼저 수행하는 추가 계산 예산·중간 자료 제공 패키지의 효과다. 토큰 예산을 맞춘 순수 문구 효과 실험이나 모델 내부 원인 식별 실험은 아니다.',
            '계산표가 맞아도 선택이 틀리면 해당 계약에서 계산 성공이 선택 성공으로 이어지지 않은 것이다. 틀린 계산표 뒤 graph 성공은 보존하되 전체 계산-종단 계약 성공으로 세지 않는다.',
            '선택 출력은 양쪽 모두 후보 ID 하나이며, 계산표는 생성기에 직접 전달하지 않는다. 생성기는 각 군의 선택 ID 원문과 자신의 실제 이력을 사용한다.',
            '성공/실패 모두 한 배치 후 검토한다. 자동 문구·seed 탐색, 가드 삭제, 재시도, 모델 갱신, 후속 자동 실행 없음.',
            f"결정: `{s['decision']}`", '']
    return '\n'.join(out)
