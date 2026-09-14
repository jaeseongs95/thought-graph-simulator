"""이미 독립적으로 대조한 JSON을 한국어 표로 표시한다. 채점 로직은 없다."""
def render(s):
    def f(c):return f"{c['successes']}/{c['assigned']} (미측정 {c['unmeasured']})"
    out=['# v080 — D/W 구별과 후보 위치×ID 교차 검사', '',
         f"실행 상태: `{s['state']}` / 데이터 출처: `{s['provenance']}`",'',
         '**D는 출력 proof DAG의 의존 깊이, W는 규칙 적용 개수다. W 성과를 D 제어 성과에 합산하지 않는다.**','',
         '| 지표 | D 본실험 | W 구별 대조 |','|---|---:|---:|']
    for key,title in [('selection_success','선택'),('generator_success','선택 경로 생성'),('metric_end_to_end','요구 지표 종단'),('selection_pairs','양방향 선택'),('end_to_end_pairs','양방향 종단'),('presentation_robust_selection','위치×ID 전 조건 양방향 선택'),('presentation_robust_end_to_end','위치×ID 전 조건 양방향 종단')]:
        out.append(f"| {title} | {f(s['totals']['D'][key])} | {f(s['totals']['W'][key])} |")
    out+=['',f"실험자 지정 경로 참조: {f(s['reference'])}",'',
          '위치×ID 전 조건 집계의 단위는 문제×seed다. 두 seed를 독립 문제로 세지 않는다.',
          '이미 결과를 본 구조 4개이며, 새로운 독립 구조는 0개다. 이 배치는 새로운 holdout 검증이 아니다.','',
          '## 문제별 종단 결과','| 문제 | D 종단 | W 종단 |','|---|---:|---:|']
    for pid in ['H01','H02','H03','H04']:
        cells=[]
        for m in ['D','W']:
            rs=[r for r in s['trials'] if r['arm']=='model' and r['problem_id']==pid and r['metric']==m]
            cells.append('해당 없음' if not rs else f"{sum(r['metric_end_to_end'] is True for r in rs)}/{len(rs)} (미측정 {sum(r['metric_end_to_end'] is None for r in rs)})")
        out.append(f'| {pid} | {cells[0]} | {cells[1]} |')
    n=len(s['metric_discrimination']);sel=sum(c['all_four_selections_correct'] is True for c in s['metric_discrimination']);end=sum(c['all_four_end_to_end_correct'] is True for c in s['metric_discrimination'])
    out+=['','## D와 W를 반대로 고를 수 있는가',f'H03/H04의 네 요구(D 작게/크게, W 적게/많게) 모두 정답인 조건: 선택 {sel}/{n}, 실제 증명까지 {end}/{n}.',
          '단순히 D와 W의 선택이 서로 다르다는 것만으로 성공 처리하지 않는다. 네 선택의 정오를 모두 검사한다.','',
          '## 해석 경계','선택·생성·종단·역방향을 분리한다. 실제 실패를 고치거나 미측정 D를 0으로 채우지 않는다.',
          '내부 사고·문제 난이도·분해 축 전체·A/M 독립성·실행 시간 우월성은 이 배치의 측정 대상이 아니다.',
          '한 배치 후 종료한다. 결과가 불리해도 가드 삭제·자동 재시도·후속 제약 추가를 하지 않는다.','',
          f"결정: `{s['decision']}`",'']
    return '\n'.join(out)
