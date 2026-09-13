"""Build a fresh source candidate and validate its extracted offline suite."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import zipfile

HERE = Path(__file__).resolve().parent
VERSION = HERE.parent
REPO = VERSION.parents[1]
PROBE = VERSION / 'probe'
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(name, obj):
    (HERE / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')


def command(args, cwd, name):
    started = time.monotonic()
    result = subprocess.run([sys.executable, '-B', *args], cwd=cwd, env=ENV,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (HERE / (name + '.log')).write_bytes(result.stdout)
    receipt = {'command': [sys.executable, '-B', *map(str, args)], 'cwd': str(cwd),
               'exit_code': result.returncode, 'elapsed_seconds': round(time.monotonic() - started, 3),
               'new_model_inference': False}
    save(name + '.json', receipt)
    print(name, receipt, flush=True)
    if result.returncode:
        raise RuntimeError(result.stdout.decode('utf-8', errors='replace'))
    return receipt


def main():
    baseline = REPO / 'llm_experiments/v058/results_llm/v058_order_02_evidence.zip'
    plan = VERSION / 'experiments/v059_rules_validation_02.plan.json'
    command(['-m', 'rule_order_v059', 'prepare', '--baseline-bundle', str(baseline), '--out', str(plan)], PROBE, 'prepare_r2')
    command(['-m', 'rule_order_v059', 'show', '--plan', str(plan)], PROBE, 'show_r2')
    spec = importlib.util.spec_from_file_location('release_builder', PROBE / 'tools/build_release.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    archive = VERSION / 'releases/v059_rule_order_source_r2.zip'
    builder.build(archive)
    manifest = builder.check(archive)
    save('candidate_manifest_r2.json', manifest)
    digest = sha(json.dumps(manifest['file_hashes'], sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8'))
    extracted = Path(tempfile.mkdtemp(prefix='v059_release_r2_verified_'))
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(extracted)
    receipt = command(['-m', 'rule_order_v059', 'selftest'], extracted / manifest['entrypoint'], 'release_selftest_r2')
    changed = [name for name, value in manifest['file_hashes'].items() if sha((extracted / name).read_bytes()) != value]
    baseline_state = json.loads((HERE / 'start_state.json').read_text(encoding='utf-8'))
    prior_changes = [name for name, value in baseline_state['existing_version_sources'].items() if sha((REPO / name).read_bytes()) != value]
    input_changes = [name for name, value in baseline_state['inputs'].items() if sha(Path(name).read_bytes()) != value]
    working_changes = [name for name, value in manifest['file_hashes'].items() if sha((REPO / name).read_bytes()) != value]
    assert not changed and not prior_changes and not input_changes and not working_changes
    receipt.update(source_zip=str(archive), source_zip_sha256=sha(archive.read_bytes()),
                   candidate_digest=digest, manifest_files=len(manifest['file_hashes']),
                   extracted_root=str(extracted), extracted_files_changed=changed,
                   existing_source_changes=prior_changes, user_input_changes=input_changes,
                   release_working_tree_mismatches=working_changes,
                   cache_files_in_release=any('__pycache__' in name or name.endswith('.pyc') for name in manifest['file_hashes']),
                   plan_sha256=json.loads(plan.read_text(encoding='utf-8'))['plan_sha256'])
    save('release_check_r2.json', receipt)
    print(json.dumps(receipt, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
