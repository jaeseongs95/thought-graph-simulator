"""Reuse strict bounded contracts without executing evidence snapshots."""
from pathlib import Path
from order_replay_v058.contracts import (ContractError, require, strict_json, wire,
    canonical, sha, digest, b64, unb64, read_json, write_json, utc_now, usage,
    require_external_plan, decode_response, validate_payload, read_plan_json,
    completion_metadata)
from . import DEPENDENCY_ROOT
SOURCE_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = (
    ('v057_selection_probe', DEPENDENCY_ROOT.parents[1] / 'v057' / 'probe'),
    ('v058_order_replay', DEPENDENCY_ROOT),
    ('v059_rule_order', SOURCE_ROOT.parents[1] / 'v059' / 'probe'),
    ('v060_terminal_position', SOURCE_ROOT),
)


def source_fingerprint():
    result = {}
    for name, root in SOURCE_ROOTS:
        require(root.is_dir() and not root.is_symlink(), 'Missing/linked source root')
        for path in sorted(root.rglob('*.py')):
            require(not path.is_symlink(), 'Source link refused')
            result[name + '/' + path.relative_to(root).as_posix()] = sha(path.read_bytes())
    return result


def source_path(name):
    p = Path(name)
    require(not p.is_absolute() and '..' not in p.parts and '\\' not in name
            and ':' not in name and len(p.parts) > 1, 'Unsafe source path')
    roots = dict(SOURCE_ROOTS)
    require(p.parts[0] in roots, 'Unknown source root')
    return roots[p.parts[0]].joinpath(*p.parts[1:])
