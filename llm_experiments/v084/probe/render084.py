"""공통 한국어 표시 전용. 의미 판정/집계는 생산·독립 구현에서 각각 수행한다."""

def render(s):
    def ratio(x):
        if x['assigned']==0:return '배정 없음'
        return f"{x['successes']}/{x['assigned']} (미관측/판정불가 {x['unmeasured']})"
    def effect(x):return '미판정' if x is None else f'{x*100:+.2f}%p'
    names={'candidate_id':'직접 선택','correct_values':'정확한 숫자 지원'}
    out=['# v084 — 신규 구조에서 D 양방향 종단 재현','',
         f"실행 상태: `{s['state']}` / 출처: `{s['provenance']}`",'',
         '**정확한 숫자는 실험자가 추론 전에 고정한 양성 대조다. 모델의 자력 깊이 계산 성과가 아니다.**',
         'T01~T08은 기존 H01~H04의 기호 변경 복제본이 아닌 신규 구조쌍이다. 응답 기반 선별은 없으며 IID 무작위 표본은 아니다.',
         '직접/숫자 선택 계약과 explicit_rule 생성 계약을 v083에서 유지했다. W는 선택 전용 보조 대조다.','',
         '## D 선택과 종단','', '| 지표 | 직접 선택 | 정확한 숫자 지원 |','|---|---:|---:|']
    for key,title in [('selection_success','D 선택'),('selection_pairs','D 양방향 선택'),
                      ('generator_success','선택 경로 생성'),('metric_end_to_end','요구 D 종단'),
                      ('end_to_end_pairs','D 양방향 종단'),('presentation_robust_selection','네 표시 전체 양방향 선택'),
                      ('presentation_robust_end_to_end','네 표시 전체 양방향 종단')]:
        out.append('| '+title+' | '+' | '.join(ratio(s['groups'][v]['totals']['D'][key]) for v in names)+' |')
    c=s['structural_comparison']
    out+=['','## 주평가: 구조 단위 같은 가중치 비교','',
        f"완전 비교 구조: {c['complete_structures']}/{c['assigned_structures']}. 구조별 양방향 pair 성공률 차이의 평균(지원−직접): **{effect(c['mean_support_minus_direct_pair_rate'])}**.",
        f"개선 {c['improved_structures']}, 악화 {c['worsened_structures']}, 동일 {c['unchanged_structures']}, 미판정 {c['unmeasured_structures']}개 구조.",
        '구조마다 2 seed × 4 표시의 8쌍이다. 이를 8개의 독립 구조로 부풀리지 않는다. 미관측이 남은 구조는 효과를 판정하지 않는다.',
        '','| 구조 | 유형 | 직접 양방향 | 지원 양방향 | 성공률 차이 | 직접 모든 seed·표시 | 지원 모든 seed·표시 |',
        '|---|---|---:|---:|---:|---|---|']
    for row in c['cases']:
        a,b=[row['arms'][v] for v in names]
        flag=lambda x:'성공' if x is True else '실패' if x is False else '미판정'
        family='같은 규칙 수' if row['family']=='equal_rule_count' else '규칙 수 역전'
        out.append(f"| {row['problem_id']} | {family} | {ratio(a['pairs'])} | {ratio(b['pairs'])} | {effect(row['support_minus_direct_pair_rate'])} | {flag(a['all_seeds_all_presentations'])} | {flag(b['all_seeds_all_presentations'])} |")
    out+=['','## W 선택 보조 대조','', '| 지표 | 직접 선택 | 정확한 숫자 지원 |','|---|---:|---:|']
    for key,title in [('selection_success','W 선택'),('selection_pairs','W 양방향 선택'),('presentation_robust_selection','네 표시 전체 W 양방향 선택')]:
        out.append('| '+title+' | '+' | '.join(ratio(s['groups'][v]['totals']['W'][key]) for v in names)+' |')
    out+=['','W 증명 생성은 배정 없음이다. D 성공과 합산하지 않는다.','',
         '## 공통 지정 경로 참조','',f"생성 성공: {ratio(s['reference'])}. 두 군에 중복 가산하지 않는다.",'',
         '| 구조 | shallow 지정 경로 | deep 지정 경로 |','|---|---:|---:|']
    for row in c['cases']:
        r=row['reference_by_direction'];out.append(f"| {row['problem_id']} | {ratio(r['shallow'])} | {ratio(r['deep'])} |")
    cmp=s['hypothesis_comparisons']['H1_holdout_support']['by_metric']['D']
    out+=['','## 같은 조건의 군간 짝비교','', '| 지표 | 둘 다 성공 | 직접만 | 지원만 | 둘 다 실패 | 미비교 |','|---|---:|---:|---:|---:|---:|']
    for key in ('selection','end_to_end','end_to_end_pairs'):
        d=cmp[key];out.append('| '+key+' | '+' | '.join(str(d[k]) for k in ('both_success','left_only','right_only','both_failure','not_comparable'))+' |')
    out+=['','## 해석 범위','',
        '실제 graph는 원응답에서 무보정으로 재조립·검사한다. 최종 ID만 맞거나 자기보고 숫자가 맞아도 증명 성공이 아니다.',
        '관측된 모델 출력 실패, HTTP/identity 오류, 길이 종료, 미실행·중단, 사전 미배정을 구분한다.',
        '새 구조에 대한 관측은 결과가 생성된 뒤에만 판단한다. 합성 시험과 재검산은 모델 표본이 아니다.',
        '총합의 개선, 구조별 재현, 모든 표시 100% 통과는 서로 다른 결과다. 하나의 gate로 부분 효과를 지우지 않는다.',
        'p-value를 자동 산출하지 않는다. 다음 실험은 이 배치 분석 이후 결정하며 자동 작성/재시도하지 않는다.','']
    return '\n'.join(out)
