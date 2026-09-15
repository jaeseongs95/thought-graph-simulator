"""공통 한국어 표시 전용. 수치 판정은 생산·독립 구현에서 각각 수행한다."""

def render(s):
    def ratio(x):
        if x['assigned']==0:return '배정 없음'
        return f"{x['successes']}/{x['assigned']} (미관측/판정불가 {x['unmeasured']})"
    names={'candidate_id':'직접 선택','correct_full':'정확한 전체 계산표','correct_values':'정확한 숫자 요약','swapped_values':'요청 지표 값 교환'}
    out=['# v083 — 정확한 지원·표현·값 교환의 세 가설','',f"실행 상태: `{s['state']}` / 출처: `{s['provenance']}`",'',
         '**정확한 자료는 실험자가 추론 전에 만든 양성 대조다. 모델이 D를 스스로 계산한 성과로 집계하지 않는다.**',
         '값 교환은 사전에 고정한 입력 처치다. 모델의 실제 응답, 기존 v082 결과, 선택 또는 증명을 사후 보정하지 않는다.',
         'H01~H04는 기존 진단 구조 4개이며 새 독립 구조·holdout은 0개다. W는 선택 대조만 실행한다.','',
         '## D 선택과 종단','', '| 지표 | 직접 선택 | 정확한 전체표 | 정확한 숫자 | 값 교환 |','|---|---:|---:|---:|---:|']
    for key,title in [('selection_success','D 선택'),('selection_pairs','D 양방향 선택'),
                      ('generator_success','선택 경로 생성'),('metric_end_to_end','요구 D 종단'),
                      ('end_to_end_pairs','D 양방향 종단'),('presentation_robust_selection','네 표시 전체 양방향 선택'),
                      ('presentation_robust_end_to_end','네 표시 전체 양방향 종단')]:
        out.append('| '+title+' | '+' | '.join(ratio(s['groups'][v]['totals']['D'][key]) for v in names)+' |')
    out+=['','값 교환군의 graph는 사전 미배정이다. 실패 또는 실행 누락으로 읽지 않는다. 유효 graph의 역전·동일·정방향은 pairs에 별도 보존한다.',
          '','## W 선택 대조','', '| 지표 | 직접 선택 | 정확한 전체표 | 정확한 숫자 | 값 교환 |','|---|---:|---:|---:|---:|']
    for key,title in [('selection_success','W 선택'),('selection_pairs','W 양방향 선택'),('presentation_robust_selection','네 표시 전체 양방향 선택')]:
        out.append('| '+title+' | '+' | '.join(ratio(s['groups'][v]['totals']['W'][key]) for v in names)+' |')
    out+=['','W는 모든 군에서 증명 생성을 배정하지 않았다. D와 W 네 요구 구별도 선택 단계에서만 검사한다.','',
          '## 사전 가설별 같은 조건 대조','']
    for name,comp in s['hypothesis_comparisons'].items():
        out.append(f"### {name}: {names[comp['left']]} → {names[comp['right']]}")
        for metric,row in comp['by_metric'].items():
            p=row['selection'];out.append(f"{metric} 선택: 둘 다 성공 {p['both_success']}, 왼쪽만 {p['left_only']}, 오른쪽만 {p['right_only']}, 둘 다 실패 {p['both_failure']}, 비교불가 {p['not_comparable']}.")
            out.append(f"선택 경로 변경: {ratio(row['changed_path'])}; 두 조건에서 각각 제공된 극값을 모두 따름: {ratio(row['both_follow_supplied_extreme'])}.")
        out.append('')
    out+=['H1은 정확한 외부 자료 제공 패키지의 효과·충분성 검사다. v082의 틀린 모델 응답을 고쳐서 재채점한 실험도, 내부 계산 오류만의 순수 효과도 아니다.',
          'H2는 전체 계산표와 동일한 정답 숫자만 남긴 요약의 비교다. 입력 길이·구조가 함께 달라지며 토큰 예산을 같게 맞추지 않았다.',
          'H3은 요약 내 요청 지표의 두 값만 교환한다. 단순 선택 변화뿐 아니라 정답 및 제공값 순서를 각각 따르는지 판정한다.',
          '','## D/W 네 요구 선택 구별','']
    for v,g in s['groups'].items():
        out.append(f"{names[v]}: {ratio({'assigned':len(g['metric_discrimination']),'successes':sum(r['all_four_selections_correct'] is True for r in g['metric_discrimination']),'unmeasured':sum(r['all_four_selections_correct'] is None for r in g['metric_discrimination'])})}.")
    out+=['',f"공통 지정 경로 참조: {ratio(s['reference'])}. 한 번만 실행하며 각 군에 복제하지 않는다.",
          '','## 호출·계측','']
    for v,g in s['groups'].items():
        for stage,u in g['usage_by_stage'].items():
            out.append(f"{names[v]} / {stage}: {u['calls']}회, 출력 토큰 계측 합 {u['fields']['eval_count']['sum_observed']}, 미기록 {u['fields']['eval_count']['missing']}.")
    out+=['','실험자 자료 생성은 결정적 오프라인 계산이며 모델 호출은 0회다. 그 사실을 무료인 자력 모델 추론 성과로 표현하지 않는다.',
          '서버 응답 시간 합은 전체 자동화 시간과 다르다. 성공한 선택 하위집합만으로 전체 성공률을 보고하지 않는다.',
          '','## 종료와 해석',
          '이 배치는 외부 정답 지원하의 선택·graph 구성과 참고 숫자 민감성을 검사한다. 인간의 사고 깊이 전체, hidden state, ADM 세 축 독립성 또는 새 문제 일반화를 검증하지 않는다.',
          '양성 대조의 개선을 지원 없는 모델 성과로 승격하지 않는다. 정확한 숫자에서 실패하면 계산만으로 해결되지 않는 관측을 남긴다. 숫자 교환 반응만으로 내부 메커니즘을 확정하지 않는다.',
          '참고자료는 선택기에만 들어간다. 생성기는 실제 선택 원문과 자기 군의 이전 원문을 보정 없이 사용한다.',
          '한 동결 배치 후 종료한다. 결과에 따른 자동 문구/seed 탐색·모델 변경·추가 실행은 없다.',
          f"결정: `{s['decision']}`",'']
    return '\n'.join(out)
