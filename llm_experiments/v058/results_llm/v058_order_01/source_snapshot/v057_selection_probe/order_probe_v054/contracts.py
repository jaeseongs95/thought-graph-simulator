"""기존 공통 계약은 보존하고 새 모듈까지 소스 지문을 확장한다."""
from pathlib import Path
from adm_diagnostic_v052.contracts import (ContractError, require, strict_json, wire, canonical,
    sha, digest, b64, unb64, read_json, write_json, utc_now, usage, require_external_plan,
    decode_response, validate_payload)

def source_fingerprint():
    root = Path(__file__).resolve().parent.parent
    result = {}
    for name in ('paired_probe_v047', 'paired_probe_v048', 'paired_probe_v049',
                 'criterion_probe_v050', 'adm_pilot_v051', 'adm_diagnostic_v052', 'depth_probe_v053', 'order_probe_v054'):
        for path in sorted((root / name).glob('*.py')):
            raw = path.read_text(encoding='utf-8-sig').replace('\r\n','\n').replace('\r','\n').encode('utf-8')
            result[name + '/' + path.name] = sha(raw)
    return result
