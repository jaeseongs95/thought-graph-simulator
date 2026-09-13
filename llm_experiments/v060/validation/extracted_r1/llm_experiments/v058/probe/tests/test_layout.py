"""Repository-layout contracts for the version-centered experiment tree."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from order_replay_v058 import DEPENDENCY_ROOT
from order_replay_v058.contracts import (
    ContractError,
    SOURCE_ROOT,
    sha,
    source_fingerprint,
    source_path,
)

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('v058_build_release', ROOT / 'tools' / 'build_release.py')
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)
VALIDATE_SPEC = importlib.util.spec_from_file_location(
    'validate_inputs_layout', ROOT / 'tools' / 'validate_inputs.py')
validate_inputs = importlib.util.module_from_spec(VALIDATE_SPEC)
VALIDATE_SPEC.loader.exec_module(validate_inputs)


class LayoutTests(unittest.TestCase):
    def test_physical_roots_and_logical_fingerprint_names(self):
        self.assertEqual(SOURCE_ROOT, ROOT)
        self.assertEqual(DEPENDENCY_ROOT, ROOT.parents[1] / 'v057' / 'probe')
        fingerprint = source_fingerprint()
        self.assertTrue(fingerprint)
        self.assertEqual(
            {name.split('/', 1)[0] for name in fingerprint},
            {'v057_selection_probe', 'v058_order_replay'},
        )
        for name, expected in fingerprint.items():
            self.assertEqual(sha(source_path(name).read_bytes()), expected)

    def test_source_path_rejects_physical_and_unsafe_names(self):
        for name in (
            'llm_experiments/v057/probe/example.py',
            'probe/example.py',
            '../v057/probe/example.py',
            str(ROOT / 'order_replay_v058' / '__init__.py'),
        ):
            with self.assertRaises(ContractError):
                source_path(name)

    def test_split_v057_input_layout_is_resolved(self):
        with tempfile.TemporaryDirectory() as temp:
            version = Path(temp) / 'v057'
            results = version / 'results_llm'
            experiments = version / 'experiments'
            results.mkdir(parents=True)
            experiments.mkdir()
            name = 'v057_selection_01'
            for suffix in ('.plan.json', '.plan.baseline.zip', '.preflight.json'):
                (experiments / (name + suffix)).write_bytes(b'x')
            for suffix in ('_evidence.zip', '_independent.json'):
                (results / (name + suffix)).write_bytes(b'x')
            files = validate_inputs.input_files(results, name)
            self.assertTrue(all(path.is_file() for path in files.values()))
            self.assertEqual(files['.plan.json'].parent, experiments)
            self.assertEqual(files['_evidence.zip'].parent, results)

    def test_release_uses_version_centered_archive_paths(self):
        with tempfile.TemporaryDirectory(prefix='v058_release_layout_') as temp:
            out = Path(temp) / 'source.zip'
            result = release.build(out)
            self.assertGreater(result['files'], 0)
            manifest = release.check(out)
            self.assertEqual(manifest['entrypoint'], 'llm_experiments/v058/probe')
            names = set(manifest['file_hashes'])
            self.assertTrue(any(n.startswith('llm_experiments/v057/probe/') for n in names))
            self.assertTrue(any(n.startswith('llm_experiments/v058/probe/') for n in names))
            self.assertFalse(any(n.startswith('experiments/') for n in names))

    def test_release_rejects_missing_dependency_and_bad_manifest_path(self):
        with tempfile.TemporaryDirectory(prefix='v058_release_layout_') as temp:
            missing = Path(temp) / 'missing'
            with patch.object(release, 'SOURCES', ((missing, 'llm_experiments/v057/probe'),
                                                   (release.ROOT, 'llm_experiments/v058/probe'))):
                with self.assertRaisesRegex(ValueError, '필수 소스 루트 없음'):
                    release.build(Path(temp) / 'missing.zip')

            bad = Path(temp) / 'bad.zip'
            manifest = {
                'contract': 'v058-source-release-r2',
                'file_hashes': {'experiments/old.py': sha(b'x')},
                'dependency': release.DEPENDENCY,
                'entrypoint': release.ENTRYPOINT,
                'new_model_inference': False,
            }
            with zipfile.ZipFile(bad, 'w') as archive:
                archive.writestr('experiments/old.py', b'x')
                archive.writestr('RELEASE_MANIFEST.json', json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, '배포 소스 경로 불일치'):
                release.check(bad)


if __name__ == '__main__':
    unittest.main()
