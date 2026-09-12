"""입출력 형식만 검증한다. 모델의 의미상 오답을 교정하지 않는다."""
from __future__ import annotations
from pathlib import Path
from paired_probe_v049.contracts import (ContractError, require, strict_json, wire, canonical,
    sha, digest, b64, unb64, read_json, write_json, utc_now, usage, require_external_plan)

def obj(properties):
    return {"type":"object","properties":properties,"required":list(properties),"additionalProperties":False}
BOOL={"type":"boolean"}
STR={"type":"string","minLength":1,"maxLength":128}
OBS=obj({"probe_atom":STR,"goal_atom":STR,"facts":{"type":"array","items":STR,"minItems":1,"maxItems":10}})
PRIM=obj({"same_as_goal":BOOL,"in_facts":BOOL})
FIND=obj({"answer_only_accepts":BOOL,"proof_and_goal_accepts":BOOL,"gap_detected":BOOL})
EXTRACT_SCHEMA=obj({"observed":OBS,"primitives":PRIM})
WITNESS_SCHEMA=obj({"observed":OBS,"primitives":PRIM,"finding":FIND})
VALUE_SCHEMA=obj({"value":BOOL})

def validate_payload(value, schema, path='$'):
    t=schema['type']
    if t=='object':
        require(isinstance(value,dict) and set(value)==set(schema['properties']),path+': 객체 필드 불일치')
        for k,s in schema['properties'].items():validate_payload(value[k],s,path+'.'+k)
    elif t=='boolean':require(type(value) is bool,path+': 엄격한 bool 필요')
    elif t=='string':require(isinstance(value,str) and schema['minLength']<=len(value)<=schema['maxLength'],path+': 문자열 범위 오류')
    elif t=='array':
        require(isinstance(value,list) and schema['minItems']<=len(value)<=schema['maxItems'],path+': 배열 범위 오류')
        for i,v in enumerate(value):validate_payload(v,schema['items'],path+f'[{i}]')
    else:raise ContractError('지원하지 않는 고정 schema')

def schema_for(stage):
    if stage in ('oneshot_original','oneshot_commuted'):return WITNESS_SCHEMA
    if stage=='extract':return EXTRACT_SCHEMA
    require(stage in ('proof','gap_direct','not','gap_and'),'미등록 stage')
    return VALUE_SCHEMA

def decode_response(raw,model,stage):
    env=strict_json(raw)
    require(isinstance(env,dict) and env.get('model')==model,'응답 모델 불일치')
    require(env.get('done') is True and env.get('done_reason')=='stop','정상 stop 종료 아님')
    msg=env.get('message');require(isinstance(msg,dict) and msg.get('role')=='assistant','assistant 응답 아님')
    require(not msg.get('tool_calls') and not msg.get('images'),'도구/이미지 응답 금지')
    thinking=msg.get('thinking')
    require(thinking is None or (isinstance(thinking,str) and not thinking.strip()),'non-thinking 계약 위반')
    content=msg.get('content');require(isinstance(content,str) and '<think>' not in content and '</think>' not in content,'content 계약 위반')
    payload=strict_json(content);validate_payload(payload,schema_for(stage))
    return payload

def source_fingerprint():
    root=Path(__file__).resolve().parent.parent;result={}
    for mod in ('paired_probe_v047','paired_probe_v048','paired_probe_v049','criterion_probe_v050'):
        for p in sorted((root/mod).glob('*.py')):
            result[mod+'/'+p.name]=sha(p.read_text(encoding='utf-8-sig').replace('\r\n','\n').replace('\r','\n').encode())
    return result
