"""검산 완료 수치를 한국어 표로 표시한다. 두 검산 경로가 공유하는 표시 전용 모듈이다."""


def render(s):
    def ratio(c):
        return f"{c['successes']}/{c['assigned']} (미측정 {c['unmeasured']})"
    lines = ['# v081 — 후보 ID 대 규칙 목록 선택 짝대조', '',
             f"실행 상태: `{s['state']}` / 데이터 출처: `{s['provenance']}`", '',
             '**D는 실제 proof DAG의 의존 깊이, W는 목표 지지 규칙 수다. W를 D 성과에 합산하지 않는다.**',
             '같은 네 진단 구조를 사용한다. 신규 구조 0개, 새로운 holdout 일반화가 아니다.', '']
    for m, name in [('D', 'D 본실험'), ('W', 'W 구별 대조')]:
        lines += ['## ' + name, '', '| 지표 | candidate_id | rule_ids |', '|---|---:|---:|']
        for k, title in [('selection_success', '요구에 맞는 선택'), ('generator_success', '선택 경로 생성'),
                         ('metric_end_to_end', '요구 지표 종단'), ('selection_pairs', '양방향 선택'),
                         ('end_to_end_pairs', '양방향 종단'), ('presentation_robust_selection', '네 표시 모두 양방향 선택'),
                         ('presentation_robust_end_to_end', '네 표시 모두 양방향 종단')]:
            lines.append(f"| {title} | {ratio(s['groups']['candidate_id']['totals'][m][k])} | {ratio(s['groups']['rule_ids']['totals'][m][k])} |")
        p = s['paired_trials'][m]['metric_end_to_end']
        lines += ['', f"같은 조건 종단 짝비교: 양쪽 성공 {p['both_success']}, ID군만 성공 {p['candidate_id_only']}, "
                       f"규칙목록군만 성공 {p['rule_ids_only']}, 양쪽 실패 {p['both_failure']}, 비교 불가 {p['not_comparable']}.", '']
    lines += ['## 선택 매핑과 복사 오류', '',
              '규칙 목록이 후보의 원래 순서와 정확히 일치할 때만 실행한다. 정렬·누락 보충·가까운 경로 선택을 하지 않는다.',
              '규칙 목록 미매핑은 관측된 선택 인터페이스 실패로 기록한다. 이때 미실행 생성은 실패로 채우지 않고 D/W도 null로 둔다.',
              '복사 오류를 D 이해 부족으로 단정하지 않으며, 목록순서만 다른 진단도 실행에는 사용하지 않는다.', '']
    for variant in ('candidate_id', 'rule_ids'):
        g = s['groups'][variant]
        lines.append(f"- {variant}: D 매핑 {ratio(g['mapping']['D'])}, W 매핑 {ratio(g['mapping']['W'])}; 상태 {g['selection_statuses']}")
        for m in ('D', 'W'):
            c = g['conditional_choice'][m]
            lines.append(f"  {m}: 실제 후보로 대응된 응답에서 요구 정답 {c['successes']}/{c['measured']}. 전체 배정 {c['assigned']} 중 선택 경로 미측정 {c['unmeasured']}.")
    lines += ['', f"규칙목록 진단: {s['copy_diagnostic_counts']}", '', '## D/W 네 요구 구별', '']
    for v in ('candidate_id', 'rule_ids'):
        cs = s['groups'][v]['metric_discrimination']
        lines.append(f"{v}: 네 선택 모두 정답 {sum(c['all_four_selections_correct'] is True for c in cs)}/{len(cs)}, "
                     f"네 종단 모두 정답 {sum(c['all_four_end_to_end_correct'] is True for c in cs)}/{len(cs)}.")
    lines += ['', '## 문제별 D 종단', '| 문제 | candidate_id | rule_ids |', '|---|---:|---:|']
    for pid in ('H01', 'H02', 'H03', 'H04'):
        cols = []
        for v in ('candidate_id', 'rule_ids'):
            rs = [r for r in s['trials'] if r['selector_variant'] == v and r['metric'] == 'D' and r['problem_id'] == pid]
            cols.append(f"{sum(r['metric_end_to_end'] is True for r in rs)}/{len(rs)} (미측정 {sum(r['metric_end_to_end'] is None for r in rs)})")
        lines.append(f'| {pid} | {cols[0]} | {cols[1]} |')
    lines += ['', f"공유 지정 경로 참조: {ratio(s['reference'])}. 공통 생성기의 16개 참조이며 두 군에 복제하지 않는다.", '',
              '## 해석 및 종료',
              '선택 출력 안내와 스키마를 함께 바꾼 계약 전체의 효과다. 후보 ID의 내부 원인만 식별한 실험이 아니다.',
              '후보 ID는 입력에 여전히 존재한다. rule_ids군은 출력에서만 candidate_id를 사용하지 않는다.',
              '실제 선택 원문은 수정 없이 생성기에 전달한다. 두 출력 형식이 후속 입력에 미치는 차이도 종단 효과에 포함된다.',
              '주평가지표는 D 양방향 종단이며, 전체 성공 기준과 부분 효과를 따로 보존한다.',
              '한 배치 종료. 가드 삭제·자동 재시도·유리한 seed 탐색·자동 후속 실험 없음.',
              f"결정: `{s['decision']}`", '']
    return '\n'.join(lines)
