"""로컬 계획/기준선 ZIP만 별도 한도로 읽고, 응답 JSON 8 MiB 한도는 유지한다."""
from pathlib import Path
from model_probe_v055.contracts import (ContractError,require,strict_json,wire,canonical,sha,digest,b64,unb64,
    read_json,write_json,utc_now,usage,require_external_plan,decode_response,validate_payload)
from layout_probe_v056.contracts import source_fingerprint as old_fingerprint
from model_probe_v055.contracts import strict_plan_json as old_plan_parser
PLAN_JSON_MAX_BYTES=32*1024*1024

def read_plan_json(path):
    require(path.is_file() and not path.is_symlink(),'계획 파일 없음/링크 거부')
    require(path.stat().st_size<=PLAN_JSON_MAX_BYTES,'계획 JSON 32 MiB 한도 초과')
    raw=path.read_bytes();require(len(raw)<=PLAN_JSON_MAX_BYTES,'계획 JSON 32 MiB 한도 초과')
    return old_plan_parser(raw)

def source_fingerprint():
    result=old_fingerprint();root=Path(__file__).resolve().parent.parent
    for p in sorted((root/'selection_probe_v057').glob('*.py')):
        result['selection_probe_v057/'+p.name]=sha(p.read_text(encoding='utf-8-sig').replace('\r\n','\n').replace('\r','\n').encode())
    return result
