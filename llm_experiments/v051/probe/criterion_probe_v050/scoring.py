"""오프라인 전용 평가. 요청 생성기와 실행기가 이 모듈을 사용하지 않는다."""
from __future__ import annotations
from .contracts import canonical
from .plan import ARMS
# 수동 표: answer_only, proof_and_goal, gap
TABLE={(False,False):(False,False,False),(False,True):(False,False,False),
       (True,False):(True,False,True),(True,True):(True,True,False)}

def expected(case):
    p=case['problem'];probe=case['probe']['atom'];a=probe==p['goal'];b=probe in p['facts']
    f=TABLE[a,b]
    return {'observed':{'probe_atom':probe,'goal_atom':p['goal'],'facts':p['facts']},
            'primitives':{'same_as_goal':a,'in_facts':b},
            'finding':dict(zip(('answer_only_accepts','proof_and_goal_accepts','gap_detected'),f))}

def reconstruct(block,arm,payloads):
    """제출된 model 값만 라우팅한다. 빠진 값에는 정답을 넣지 않는다."""
    key=lambda s:block['id']+'__'+s
    if arm.startswith('oneshot'):return payloads.get(key(arm))
    ext=payloads.get(key('extract'));proof=payloads.get(key('proof'))
    gap=payloads.get(key('gap_direct' if arm=='staged_commuted' else 'gap_and'))
    if ext is None or proof is None or gap is None:return None
    return {'observed':ext['observed'],'primitives':ext['primitives'],
            'finding':{'answer_only_accepts':ext['primitives']['same_as_goal'],
                       'proof_and_goal_accepts':proof['value'],'gap_detected':gap['value']}}

def path_stages(arm):
    if arm.startswith('oneshot'):return [arm]
    return ['extract','proof']+(['gap_direct'] if arm=='staged_commuted' else ['not','gap_and'])

def score_row(case,block,arm,payloads,observations):
    # 각 관측층을 따로 채점한다. 뒤 단계 형식 실패/미실행이 앞 단계의 정답을 지우지 않는다.
    key=lambda stage:block['id']+'__'+stage
    need=[key(s) for s in path_stages(arm)]
    observed=all(k in observations for k in need);target=expected(case);got=reconstruct(block,arm,payloads)
    source=key(arm if arm.startswith('oneshot') else 'extract')
    src=payloads.get(source)
    row={'block_id':block['id'],'case_id':case['id'],'seed':block['seed'],'cycle':block['cycle'],'arm':arm,
         'observed':observed,'gap_positive':target['finding']['gap_detected'],
         'payload_valid':(got is not None) if observed else None,
         'observed_correct':None,'primitives_correct':None,'finding_correct':None,'gap_correct':None,
         'witness_correct':None,'intermediate_correct':None,'strict_trace_correct':None,
         'first_failed_stage':None,'semantic_consistency':None,'actual':got}
    if source in observations:
        for part in ('observed','primitives'):
            row[part+'_correct']=src is not None and canonical(src[part])==canonical(target[part])
    if arm.startswith('oneshot'):
        if source in observations:
            row['finding_correct']=src is not None and canonical(src['finding'])==canonical(target['finding'])
            row['gap_correct']=src is not None and src['finding']['gap_detected'] is target['finding']['gap_detected']
    else:
        gap_id=key('gap_direct' if arm=='staged_commuted' else 'gap_and')
        gap=payloads.get(gap_id)
        if gap_id in observations:
            row['gap_correct']=gap is not None and gap['value'] is target['finding']['gap_detected']
        if all(k in observations for k in (source,key('proof'),gap_id)):
            row['finding_correct']=got is not None and canonical(got['finding'])==canonical(target['finding'])
    if observed:
        row['witness_correct']=all(row[k] is True for k in ('observed_correct','primitives_correct','finding_correct'))
    if arm=='staged_pipeline' and key('not') in observations:
        parent=payloads.get(key('not'))
        row['intermediate_correct']=src is not None and parent is not None and parent['value'] is (not src['primitives']['in_facts'])
    if observed:
        row['strict_trace_correct']=row['witness_correct'] and (row['intermediate_correct'] is True if arm=='staged_pipeline' else True)
    if got is not None:
        a=got['primitives']['same_as_goal'];b=got['primitives']['in_facts']
        row['semantic_consistency']=tuple(got['finding'][k] for k in ('answer_only_accepts','proof_and_goal_accepts','gap_detected'))==TABLE[a,b]
    # 공개된 출력/연결상 최초 오류이다. 모델 내부 사고 순서의 관측이 아니다.
    errors=[]
    if source in observations and src is None:
        errors.append('oneshot_format' if arm.startswith('oneshot') else 'extract_format')
    else:
        errors += [k for k in ('observed','primitives') if row[k+'_correct'] is False]
    if not arm.startswith('oneshot') and src is not None:
        a=src['primitives']['same_as_goal'];b=src['primitives']['in_facts']
        if arm=='staged_pipeline' and key('not') in observations:
            parent=payloads.get(key('not'))
            if parent is None:errors.append('NOT_format')
            elif row['intermediate_correct'] is False:errors.append('NOT_intermediate')
        proof=payloads.get(key('proof'))
        if key('proof') in observations:
            if proof is None:errors.append('proof_format')
            elif proof['value'] is not (a and b):errors.append('proof_local')
        gs='gap_direct' if arm=='staged_commuted' else 'gap_and'
        gap=payloads.get(key(gs))
        if key(gs) in observations:
            if gap is None:errors.append('gap_format')
            else:
                parent=payloads.get(key('not'))
                local=(a and not b) if gs=='gap_direct' else ((a and parent['value']) if parent is not None else None)
                if local is not None and gap['value'] is not local:errors.append('gap_local')
    if row['finding_correct'] is False:errors.append('finding')
    row['first_failed_stage']=next(iter(errors),None)
    return row
