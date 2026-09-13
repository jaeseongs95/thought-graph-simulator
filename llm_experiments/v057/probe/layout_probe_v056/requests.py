"""입력 텍스트를 교정/번역/보강하지 않는다. 후보 답이나 정답 깊이는 주입하지 않는다."""
from .contracts import require,strict_json,unb64
from adm_diagnostic_v052.requests import encode

def request_bytes(plan,slot):
    require(slot['layout'] in ('split','merged'),'미등록 배치')
    raw=unb64(plan['reference']['request_bank'][slot['reference_slot_id']]);q=strict_json(raw)
    require(q['model']==plan['identities'][slot['model_key']]['model'],'요청 모델 불일치')
    require(q['options']['seed']==slot['seed'],'요청 seed 불일치')
    messages=q['messages']
    require(len(messages)==2 and [m['role'] for m in messages]==['system','user'],'원래 system/user 두 메시지 필요')
    require(all(set(m)=={'role','content'} and isinstance(m['content'],str) for m in messages),'원래 메시지 필드')
    if slot['layout']=='split':return raw
    q['messages']=[{'role':'user','content':messages[0]['content']+'\n\n'+messages[1]['content']}]
    return encode(q)
