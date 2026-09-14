"""수치 중간값과 후보 인덱스의 오프라인 채점. 실행 요청의 답을 대신 결정하지 않는다."""
def depth_format(obj):
    return (isinstance(obj,dict) and set(obj)=={'depths'} and isinstance(obj['depths'],list)
        and len(obj['depths'])==2 and all(type(x) is int and 0<=x<=64 for x in obj['depths']))

def choice_format(obj):
    return (isinstance(obj,dict) and set(obj)=={'candidate_index'}
        and type(obj['candidate_index']) is int and obj['candidate_index'] in (0,1))

def assess_depth(obj,truth):
    if not depth_format(obj):
        return {'format_valid':False,'reported_depths':None,'depth_report_success':None,'error_codes':['invalid_depth_schema']}
    values=obj['depths'][:]
    correct=values==truth
    return {'format_valid':True,'reported_depths':values,'depth_report_success':correct,
        'error_codes':[] if correct else ['wrong_candidate_depths']}

def assess_choice(obj,candidates,truth,target_D,input_depths):
    out={'format_valid':choice_format(obj),'candidate_index':None,'selected_rule_ids':None,'selected_D':None,
        'selection_success':None,'numeric_choice_success':None,'error_codes':[]}
    if not out['format_valid']:
        out['error_codes']=['invalid_choice_schema'];return out
    i=obj['candidate_index']
    out.update(candidate_index=i,selected_rule_ids=list(candidates[i]),selected_D=truth[i],selection_success=truth[i]==target_D)
    if input_depths is not None and input_depths[0]!=input_depths[1]:
        shallow=target_D==min(truth)
        expected=min(input_depths) if shallow else max(input_depths)
        out['numeric_choice_success']=input_depths[i]==expected
        if not out['numeric_choice_success']:out['error_codes'].append('wrong_numeric_direction')
    if not out['selection_success']:out['error_codes'].append('wrong_actual_depth_direction')
    out['error_codes'].sort()
    return out
