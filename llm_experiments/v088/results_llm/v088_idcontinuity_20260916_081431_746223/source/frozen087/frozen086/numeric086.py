"""숫자 비교·조회 출력의 계약 검사. 실제 모델 응답을 정답으로 보정하지 않는다."""
import bootstrap
import report as base

def decode(record,raw,spec,phase):
    status,obj,usage=base.parse_response(record,raw,spec['model'],'select',spec,'explicit_rule')
    if status not in ('ok','invalid_schema'):return status,obj,usage
    if phase=='compare':
        valid=(type(obj) is dict and set(obj)=={'target_value'}
               and type(obj['target_value']) is int and 0<=obj['target_value']<=128)
    else:
        valid=(type(obj) is dict and set(obj)=={'candidate_id'}
               and (obj['candidate_id'] is None or type(obj['candidate_id']) is str and obj['candidate_id'] in spec['candidate_ids']))
    return ('ok' if valid else 'invalid_schema'),obj,usage
