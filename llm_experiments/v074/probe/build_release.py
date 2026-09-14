"""새 v074 소스만 결정적 ZIP으로 묶는다. 고정 v073 검산기 배포본을 함께 보존한다."""
import argparse
from pathlib import Path

from common import exact, load, sha, sources, unzip, wire, write, zip_bytes

PREFIX = 'llm_experiments/v074/probe/'


def build(path):
    files = {PREFIX + name: raw for name, raw in sources().items()}
    files['RELEASE_MANIFEST.json'] = wire({'contract': 'v074-source-release-r1',
        'file_hashes': {name: sha(raw) for name, raw in files.items()},
        'external_input': 'v073_interface_20260914_060416_993148_evidence.zip (not embedded)',
        'actual_model_experiment_executed_during_development': False})
    write(path, zip_bytes(files))
    check(path)
    return {'source_zip': str(path.resolve()), 'sha256': sha(path.read_bytes()), 'source_files': len(files)-1}


def check(path):
    files = unzip(path.read_bytes())
    manifest = load(files.pop('RELEASE_MANIFEST.json'))
    if (manifest['contract'] != 'v074-source-release-r1'
            or not exact(manifest['file_hashes'], {name: sha(raw) for name, raw in files.items()})
            or any(not n.startswith(PREFIX) for n in files)):
        raise ValueError('source release manifest mismatch')
    return manifest


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--out', type=Path)
    g.add_argument('--check', type=Path)
    a = p.parse_args()
    print(build(a.out) if a.out else check(a.check))
