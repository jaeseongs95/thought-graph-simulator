"""Strict bounded I/O and exact source-byte fingerprints."""
from pathlib import Path
from selection_probe_v057.contracts import (ContractError, require, strict_json, wire, canonical, sha, digest, b64, unb64,
    read_json, write_json, utc_now, usage, require_external_plan, decode_response, validate_payload, read_plan_json)
from . import DEPENDENCY_ROOT
SOURCE_ROOT = Path(__file__).resolve().parent.parent
SOURCE_ROOTS = (
    ('v057_selection_probe', DEPENDENCY_ROOT),
    ('v058_order_replay', SOURCE_ROOT),
)

def source_fingerprint():
    result = {}
    for logical_root, base in SOURCE_ROOTS:
        for path in sorted(base.rglob('*.py')):
            require(not path.is_symlink(), 'Source symlink refused')
            result[logical_root + '/' + path.relative_to(base).as_posix()] = sha(path.read_bytes())
    return result

def source_path(name):
    p = Path(name)
    require(not p.is_absolute() and '..' not in p.parts and '\\' not in name and ':' not in name, 'Unsafe source path')
    roots = dict(SOURCE_ROOTS)
    require(len(p.parts) > 1 and p.parts[0] in roots, 'Unknown source root')
    return roots[p.parts[0]].joinpath(*p.parts[1:])


def completion_metadata(raw):
    """Preserve reported stopping fields independently of response validity."""
    try:
        envelope = strict_json(raw)
        if not isinstance(envelope, dict): return {'done': None, 'done_reason': None}
        return {'done': envelope.get('done') if type(envelope.get('done')) is bool else None,
                'done_reason': envelope.get('done_reason') if isinstance(envelope.get('done_reason'), str) else None}
    except ContractError:
        return {'done': None, 'done_reason': None}
