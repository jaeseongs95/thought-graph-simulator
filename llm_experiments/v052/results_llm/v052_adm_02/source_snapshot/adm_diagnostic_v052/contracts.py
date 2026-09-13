"""원문·계획·소스 계약. UTF-8 보존, 대체문자·오답 보정 없음."""
from pathlib import Path
from adm_pilot_v051.contracts import (ContractError, require, strict_json, wire, canonical,
    sha,digest,b64,unb64,read_json,write_json,utc_now,usage,require_external_plan,
    decode_response,validate_payload)

def source_fingerprint():
    root=Path(__file__).resolve().parent.parent
    result={}
    for mod in ('paired_probe_v047','paired_probe_v048','paired_probe_v049',
                'criterion_probe_v050','adm_pilot_v051','adm_diagnostic_v052'):
        for file in sorted((root/mod).glob('*.py')):
            result[mod+'/'+file.name]=sha(file.read_text(encoding='utf-8-sig').replace('\r\n','\n').replace('\r','\n').encode())
    return result
