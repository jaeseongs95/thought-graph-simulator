"""Import audited v058 evidence without executing its attached source snapshot."""
from __future__ import annotations

import copy
import io
import sys
import tempfile
import zipfile
from pathlib import Path

from order_replay_v058.evidence import (
    MAX_ARCHIVE_BYTES,
    safe_unpack,
)

from .contracts import *


def import_v058(bundle: Path):
    """Re-audit v058 with both installed trusted verifiers, then select requests."""
    from . import DEPENDENCY_ROOT
    from order_replay_v058.audit import audit_run as audit_v058

    tool_dir = str(DEPENDENCY_ROOT / 'tools')
    if tool_dir not in sys.path:
        sys.path.insert(0, tool_dir)
    from verify_v058 import verify as verify_v058

    require(bundle.is_file() and not bundle.is_symlink()
            and bundle.stat().st_size <= MAX_ARCHIVE_BYTES,
            'Baseline missing/symlink/size')
    raw = bundle.read_bytes()
    with tempfile.TemporaryDirectory(prefix='v060_import_') as td:
        root = Path(td)
        manifest = safe_unpack(raw, root)
        require(manifest.get('contract') == 'v058-evidence-bundle-r1',
                'v058 evidence contract required')
        plan_path = root / 'external_plan/v058.plan.json'
        run = root / 'run'

        # Both implementations come from the installed, trusted v058 tree.  Files
        # under run/source_snapshot are data and are never imported or executed.
        report = audit_v058(plan_path, run, write_report=False)
        require(report['data_integrity'] and report['data_complete']
                and report['comparative_analysis_ready'],
                'Complete integral v058 baseline required')
        require(report == read_json(run / 'summary.json'),
                'v058 summary differs from production recomputation')
        frozen = root / 'verified_v058.zip'
        frozen.write_bytes(raw)
        independent = verify_v058(frozen)
        require(independent['complete'] is True
                and independent['differences'] == []
                and type(independent['observed_calls']) is int
                and independent['observed_calls'] == 80
                and type(independent['metadata_records']) is int
                and independent['metadata_records'] == 40
                and type(independent['compared_fields']) is int
                and independent['compared_fields'] > 0,
                'Independent v058 verification failed')

        plan = read_plan_json(plan_path)
        require(manifest.get('plan_sha256') == plan['plan_sha256']
                and manifest.get('data_complete') is True,
                'v058 manifest status')
        require(report['inference_calls'] == 80,
                'v058 recorded call count')

        cell = [s for s in plan['slots']
                if s['model_key'] == 'candidate'
                and s['problem_id'] == 'K01'
                and s['arm'] == 'original'
                and s['direction'] == 'shallow'
                and s['mode'] == 'choice']
        graph_choice = [s for s in cell if s['sequence'] == 'graph_choice']
        choice_graph = [s for s in cell if s['sequence'] == 'choice_graph']
        require(len(cell) == 20 and len(graph_choice) == len(choice_graph) == 10,
                'v058 candidate K01 choice source count')
        by_opposite = {s['seed']: s for s in choice_graph}
        require(len(by_opposite) == 10
                and {s['seed'] for s in graph_choice} == set(plan['seeds']),
                'v058 source seed coverage')

        request_bank = {}
        for slot in graph_choice:
            source = (run / 'calls' / slot['id'] / 'request.wire.json').read_bytes()
            opposite = (run / 'calls' / by_opposite[slot['seed']]['id']
                        / 'request.wire.json').read_bytes()
            require(source == opposite,
                    'Opposite-sequence choice request differs for seed '
                    + str(slot['seed']))
            request_bank[slot['id']] = b64(source)

        ref = {
            'contract': 'audited-v058-choice-r1',
            'bundle_sha256': sha(raw),
            'plan_sha256': plan['plan_sha256'],
            'event_tip': report['event_tip'],
            'recorded_calls': 80,
            'selected_calls': 10,
            'evidence_kind': report['evidence_kind'],
            'config': copy.deepcopy(plan['baseline']['config']),
            'identities': {'candidate': copy.deepcopy(plan['identities']['candidate'])},
            'seeds': copy.deepcopy(plan['seeds']),
            'slots': copy.deepcopy(graph_choice),
            'request_bank': request_bank,
            'independent_compared_fields': independent['compared_fields'],
        }
        ref['receipt_sha256'] = digest(ref)
        require(all(sha((root / name).read_bytes()) == expected
                    for name, expected in manifest['file_hashes'].items()),
                'v058 source changed while importing')
    require(sha(bundle.read_bytes()) == sha(raw),
            'Baseline changed while importing')
    return ref


def validate_reference_file(bundle: Path, plan):
    require(bundle.is_file() and not bundle.is_symlink(),
            'Frozen v058 baseline ZIP missing/symlink')
    require(bundle.stat().st_size <= MAX_ARCHIVE_BYTES,
            'Frozen v058 baseline ZIP too large')
    require(sha(bundle.read_bytes()) == plan['reference']['bundle_sha256'],
            'Frozen v058 baseline ZIP hash mismatch')
    reference = import_v058(bundle)
    require(canonical(reference) == canonical(plan['reference']),
            'v058 baseline and plan reference receipt differ')
    return reference


def bundle_run(plan_path: Path, run: Path, out: Path):
    from .audit import audit_run

    require(not out.exists(), 'Existing ZIP preserved')
    require(not out.resolve().is_relative_to(run.resolve()),
            'ZIP must be outside the run directory')
    audit_run(plan_path, run, write_report=True)
    require(not any(p.is_symlink() for p in run.rglob('*')),
            'Run contains a symlink')
    files = {'run/' + p.relative_to(run).as_posix(): p.read_bytes()
             for p in sorted(run.rglob('*')) if p.is_file()}
    files['external_plan/v060.plan.json'] = plan_path.read_bytes()
    with tempfile.TemporaryDirectory(prefix='v060_bundle_') as td:
        root = Path(td)
        for name, content in files.items():
            dest = root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(content)
        report = audit_run(root / 'external_plan/v060.plan.json',
                           root / 'run', write_report=True)
        files = {p.relative_to(root).as_posix(): p.read_bytes()
                 for p in sorted(root.rglob('*')) if p.is_file()}
        out.parent.mkdir(parents=True, exist_ok=True)
        created = False
        try:
            with out.open('xb') as handle:
                created = True
                with zipfile.ZipFile(handle, 'w',
                                     compression=zipfile.ZIP_DEFLATED) as archive:
                    for name, content in files.items():
                        archive.writestr(name, content)
                    archive.writestr('BUNDLE_MANIFEST.json', wire({
                        'contract': 'v060-evidence-bundle-r1',
                        'plan_sha256': report['plan_sha256'],
                        'data_complete': report['data_complete'],
                        'file_hashes': {name: sha(content)
                                        for name, content in files.items()},
                        'note': 'Evidence consistency manifest; not an external execution signature.',
                    }))
        except BaseException:
            if created:
                out.unlink(missing_ok=True)
            raise
    return report
