"""참조 요청을 그대로 재사용한다. 후보 모델은 model 필드만 교체한다."""
from .contracts import require, strict_json, unb64
from adm_diagnostic_v052.requests import encode

def request_bytes(plan, slot):
    raw=unb64(plan['reference']['request_bank'][slot['reference_slot_id']])
    key=slot['model_key'];require(key in plan['model_keys'],'계획 밖 모델')
    original=strict_json(raw)
    require(original['model']==plan['identities']['reference']['model'],'원래 요청 모델 변경')
    require(original['options']['seed']==slot['seed'],'요청 seed 불일치')
    if key=='reference':return raw
    original['model']=plan['identities'][key]['model']
    return encode(original)
