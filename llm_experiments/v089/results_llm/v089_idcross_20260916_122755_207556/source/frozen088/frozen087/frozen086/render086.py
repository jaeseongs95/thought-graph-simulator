"""계산된 결과를 표시만 한다. 생산·독립 검산은 별도 의미 판정을 수행한다."""

def render(s):
    def ratio(v):
        return '배정 없음' if v['assigned']==0 else f"{v['successes']}/{v['assigned']} (미관측/판정불가 {v['unmeasured']})"
    def effect(v):return '미판정' if v is None else f'{v*100:+.2f}%p'
    names={'candidate_id':'직접 선택','correct_values':'기존 수치 지원','two_stage_values':'값 비교→ID 조회'}
    out=['# v086 — 동결한 값 비교·ID 조회 절차의 신규 구조 재현','',
         f"실행 상태: `{s['state']}` / 출처: `{s['provenance']}`",'',
         'U01~U08은 기존 H01~H04 및 T01~T08과 비동형인 사전 고정 신규 구조쌍이다. 두 seed·네 표시 반복을 독립 구조로 세지 않는다.',
         '두 단계군의 첫 응답은 수정 없이 조회기에 전달한다. 조회기는 요구 방향을 받지 않는다. 정답 목표값 조회 대조는 진단 전용이다.',
         'D 자력 계산을 시험하지 않는다. 정확한 외부 수치 지원을 포함한 절차의 관측 성과다.','',
         '## 실제 D 제어','', '| 지표 | '+' | '.join(names.values())+' |','|---|---:|---:|---:|']
    for key,title in [('selection_success','모든 선택 단계 성공'),('selection_pairs','양방향 선택'),('generator_success','선택 경로의 유효 생성'),
                      ('metric_end_to_end','요구 D 종단'),('end_to_end_pairs','양방향 D 종단'),
                      ('presentation_robust_selection','네 표시 모두 양방향 선택'),('presentation_robust_end_to_end','네 표시 모두 양방향 종단')]:
        out.append('| '+title+' | '+' | '.join(ratio(s['groups'][v]['totals']['D'][key]) for v in names)+' |')
    c=s['structural_comparison']
    out+=['','## 주평가: 두 단계군−기존 수치 지원군','',
          f"구조별 양방향 D 종단 차이의 동일 가중치 평균: **{effect(c['mean_pair_rate_difference'])}**.",
          f"완전 비교 {c['complete_structures']}/8; 개선 {c['improved_structures']}, 악화 {c['worsened_structures']}, 동일 {c['unchanged_structures']}, 미판정 {c['unmeasured_structures']}개.",
          '','| 구조 | 직접 양방향 | 수치 지원 양방향 | 두 단계 양방향 | 두 단계−수치 지원 |','|---|---:|---:|---:|---:|']
    for r in c['cases']:
        out.append('| '+r['problem_id']+' | '+' | '.join(ratio(r['arms'][v]['pairs']) for v in names)+' | '+effect(r['pair_rate_difference'])+' |')
    out+=['','### 기존 수치 조합과 새 깊이 조합을 분리','',
          '| 구분 | 구조 수 | 양방향 D 종단 차이 평균 |','|---|---:|---:|']
    for regime,label in [('previous_depth_profile','기존 D/W 조합의 새 구조'),('new_depth_profile','새 D/W 조합의 새 구조')]:
        item=c['numeric_profile_strata'][regime]
        out.append('| '+label+' | '+str(item['assigned_structures'])+' | '+effect(item['mean_pair_rate_difference'])+' |')
    out+=['','U02: D=2/4, U03: D=3/5, U04: D=4/5는 v085에 없던 깊이 조합이다. 기존 조합의 구조 재현과 수치 조합 확장을 한 성과로 섞지 않는다.']
    out+=['','## 단계 진단 — 정답 조회 성공은 D 종단에 합산하지 않음','',
          '| 지표 | D | W |','|---|---:|---:|']
    for variant,key,title in [('two_stage_values','comparison','숫자 작은/큰 값 선택'),('two_stage_values','lookup_adherence','모델 보고값에 대한 조회 준수'),
                               ('two_stage_values','lookup_given_correct_comparison','올바른 비교 뒤 조회 준수'),('oracle_lookup','lookup_adherence','실험자가 정답값을 준 조회 양성 대조'),
                               ('two_stage_values','accidental_target_graph_after_wrong_comparison','비교는 틀렸지만 목표 graph 우연 도달')]:
        out.append('| '+title+' | '+' | '.join(ratio(s['stage_diagnostics'][variant][m][key]) for m in ('D','W'))+' |')
    out+=['','마지막 ID/graph가 맞아도 비교 또는 조회 준수가 실패하면 두 단계 종단 성공이 아니다. 비교 실패 뒤 미실행 graph를 D=0으로 채우지 않는다.','',
          '## 정답 위치·ID별 모든 선택 단계 성공','', '| 정답 위치·ID | 직접 | 수치 지원 | 두 단계 | 정답값 조회 진단 |','|---|---:|---:|---:|---:|']
    for position in (1,2):
        for cid in ('route_0','route_1'):
            k=f'position_{position}_{cid}'
            out.append('| '+k+' | '+' | '.join(ratio(s['stage_diagnostics'][v]['D']['target_position_id_cells'][k]['full_selection']) for v in [*names,'oracle_lookup'])+' |')
    out+=['','## W 보조 대조','', '| 지표 | '+' | '.join(names.values())+' |','|---|---:|---:|---:|']
    for key in ('selection_success','selection_pairs','presentation_robust_selection'):
        out.append('| '+key+' | '+' | '.join(ratio(s['groups'][v]['totals']['W'][key]) for v in names)+' |')
    out+=['','W와 정답값 조회군에는 graph 생성이 배정되지 않았다.','',f"공통 지정 경로 생성: {ratio(s['reference'])}. 군별 중복 합산 없음.",'',
          '## 호출·토큰 기록','', '| 군 | 숫자 비교 호출 | 선택/조회 호출 | 생성 호출 | 관측 prompt 토큰 | 관측 생성 토큰 |','|---|---:|---:|---:|---:|---:|']
    for v in [*names,'oracle_lookup']:
        u=s['groups'][v]['usage_by_stage']
        def total(k):return sum(x['fields'][k]['sum_observed'] for x in u.values())
        out.append('| '+v+' | '+' | '.join(str(u[k]['calls']) for k in ('compare','select','generation'))+' | '+str(total('prompt_eval_count'))+' | '+str(total('eval_count'))+' |')
    out+=['','원 JSON은 usage 필드 누락 수도 보존한다. 표의 토큰 합계는 관측된 값이며 가격/비용 우월성을 뜻하지 않는다.',
          '추가 호출·프롬프트 변경·단계 분리를 함께 적용한 절차 비교다. 내부 원인의 유일한 식별로 확대하지 않는다.',
          '숫자 비교 요청이 여러 조건에서 같아도 실제 호출·응답은 보존하며, 반복을 독립 숫자 문제나 새 구조로 가산하지 않는다.',
          '종단 평균의 개선과 모든 표시 통과는 별도로 해석한다. 합성 결과는 Qwen 연구 결과가 아니다. 자동 후속 실행 없음.','']
    return '\n'.join(out)
