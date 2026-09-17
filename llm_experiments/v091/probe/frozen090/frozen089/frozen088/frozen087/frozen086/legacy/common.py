"""공유 바이트·JSON·경로 계약. 연구 의미 계산은 포함하지 않는다."""
from __future__ import annotations

import hashlib
import io
import json
import math
import re
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent
MAX_ZIP = 100 * 1024**2
MAX_EXPANDED = 256 * 1024**2
MAX_JSON = 8 * 1024**2
EXTENSIONS = {'.py', '.json', '.md', '.ps1', '.cmd', '.txt'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def wire(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')


def _pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError('duplicate JSON key: ' + key)
        out[key] = value
    return out


def load(raw):
    if isinstance(raw, str):
        raw = raw.encode('utf-8')
    if len(raw) > MAX_JSON:
        raise ValueError('JSON size limit')
    def reject(value):
        raise ValueError('nonfinite JSON: ' + value)
    def finite_float(value):
        result = float(value)
        if not math.isfinite(result):
            reject(value)
        return result
    return json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs, parse_constant=reject,
                      parse_float=finite_float)


def save(path, value):
    raw = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')
    write(path, raw)


def write(path, raw):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)


def safe_name(name):
    p = PurePosixPath(name)
    reserved = {'CON', 'PRN', 'AUX', 'NUL', 'CLOCK$', 'CONIN$', 'CONOUT$'}
    reserved |= {prefix + str(i) for prefix in ('COM', 'LPT') for i in range(1, 10)}
    if (not name or p.is_absolute() or p.as_posix() != name or '\\' in name
            or any(c in name for c in ':<>"|?*') or any(ord(c) < 32 for c in name)
            or any(part in ('.', '..') or part.endswith((' ', '.'))
                   or part.split('.')[0].upper() in reserved for part in p.parts)):
        raise ValueError('unsafe archive path: ' + name)
    return name


def unzip(raw):
    if len(raw) > MAX_ZIP:
        raise ValueError('ZIP size limit')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        if not 0 < len(infos) <= 12000 or sum(i.file_size for i in infos) > MAX_EXPANDED:
            raise ValueError('ZIP expansion limit')
        seen = set()
        for item in infos:
            name = safe_name(item.filename)
            if (name.casefold() in seen or item.is_dir()
                    or ((item.external_attr >> 16) & 0o170000) == 0o120000):
                raise ValueError('duplicate/link/directory ZIP member')
            seen.add(name.casefold())
        return {item.filename: archive.read(item) for item in infos}


def zip_bytes(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in sorted(files.items()):
            safe_name(name)
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED if name.endswith('.zip') else zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, raw)
    return stream.getvalue()


def sources():
    result = {}
    for path in sorted(ROOT.rglob('*'), key=lambda p: p.relative_to(ROOT).as_posix()):
        if '__pycache__' in path.parts or not path.is_file():
            continue
        if path.is_symlink() or (path.suffix not in EXTENSIONS and path.relative_to(ROOT).as_posix() != 'prior/v078_source.zip'):
            raise ValueError('unsupported source member: ' + str(path))
        result[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    return result


def source_hashes():
    return {name: sha(raw) for name, raw in sources().items()}


def spec():
    return load((ROOT / 'data/protocol.json').read_bytes())


def check_run_name(name):
    if not re.fullmatch(r'v079_[A-Za-z0-9_-]{1,70}', name):
        raise ValueError('RunName must start v079_ and contain ASCII letters/digits/_/-')
    return name


def exact(a, b):
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(exact(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(exact(x, y) for x, y in zip(a, b))
    return a == b
