"""선택 원값의 후보 일치·규칙 유효성·goal 지지 깊이를 재계산한다. 실행을 보정하지 않는다."""
import reference

def format_valid(obj):
    return (isinstance(obj,dict) and set(obj)=={'rule_ids'} and isinstance(obj['rule_ids'],list)
        and 1<=len(obj['rule_ids'])<=16 and all(isinstance(x,str) and 1<=len(x)<=128 for x in obj['rule_ids']))

def assess(problem,payload,candidates,target_D):
    result={'format_valid':format_valid(payload),'candidate_member':None,'selected_position':None,
        'selected_rule_ids':None,'route_valid':None,'route_D':None,'selection_success':None,'error_codes':[]}
    if not result['format_valid']:
        result['error_codes']=['invalid_selection_schema'];return result
    ids=payload['rule_ids'];result['selected_rule_ids']=ids[:]
    matches=[i for i,c in enumerate(candidates) if c==ids]
    result['candidate_member']=len(matches)==1;result['selected_position']=matches[0] if len(matches)==1 else None
    if not result['candidate_member']:result['error_codes'].append('not_exact_candidate')
    try:result['route_D']=reference.validate(problem,ids);result['route_valid']=True
    except (ValueError,TypeError):result['route_valid']=False;result['error_codes'].append('invalid_goal_support_route')
    if result['route_valid'] and result['route_D']!=target_D:result['error_codes'].append('wrong_depth_direction')
    result['selection_success']=result['candidate_member'] and result['route_valid'] and result['route_D']==target_D
    result['error_codes'].sort();return result
