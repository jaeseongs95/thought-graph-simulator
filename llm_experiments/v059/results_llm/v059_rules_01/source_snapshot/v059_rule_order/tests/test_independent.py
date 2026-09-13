"""Independent v059 evidence checks; only the prior v058 verifier is mocked."""
from contextlib import redirect_stdout
import ast
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import zipfile

try:
    from .runtime_fixture import executed, synthetic_v058_bundle
except ImportError:
    from runtime_fixture import executed, synthetic_v058_bundle

from rule_order_v059.contracts import sha, wire
from rule_order_v059.evidence import bundle_run


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'v059_independent_test_target', ROOT / 'tools' / 'verify_v059.py')
independent = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(independent)


def verify_synthetic(path, *, baseline_result=None):
    receipt = {
        'contract': 'independent-v058-r1',
        'complete': True,
        'compared_fields': 1,
        'differences': [],
        'observed_calls': 80,
        'metadata_records': 40,
        'production_imports': False,
        'test_scope': 'Only the prior v058 verification result is mocked.',
    }
    if baseline_result is not None:
        receipt.update(baseline_result)
    with patch.object(independent, 'baseline_verify', return_value=receipt):
        return independent.verify(path)


def altered_bundle(original, target, mutation):
    with zipfile.ZipFile(original) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    manifest = json.loads(files.pop('BUNDLE_MANIFEST.json'))
    mutation(files)
    manifest['file_hashes'] = {name: sha(raw) for name, raw in files.items()}
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in files.items():
            archive.writestr(name, raw)
        archive.writestr('BUNDLE_MANIFEST.json', wire(manifest))


class IndependentTests(unittest.TestCase):
    def test_verifier_imports_only_standard_and_prior_independent_modules(self):
        source = (ROOT / 'tools' / 'verify_v059.py').read_text(encoding='utf-8')
        tree = ast.parse(source)
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or '')
        forbidden = ('rule_order_v059', 'order_replay_v058', 'selection_probe_v057',
                     '.audit', '.measure', '.plan', '.reporting', '.requests',
                     '.runner', '.evidence')
        self.assertFalse(any(any(term in module for term in forbidden)
                             for module in imported), imported)
        self.assertIn('verify_v058', imported)
        self.assertTrue(all(module == 'verify_v058'
                            or module.startswith('independent_')
                            or module.split('.')[0] in {
                                '__future__', 'argparse', 'base64', 'collections',
                                'hashlib', 'io', 'json', 'statistics', 'sys',
                                'tempfile', 'urllib', 'zipfile', 'pathlib'}
                            for module in imported), imported)

    def test_complete_fake_http_bundle_is_independently_verified(self):
        with executed() as (root, plan_path, run, _, _, _):
            bundle = root / 'complete.zip'
            bundle_run(plan_path, run, bundle)
            result = verify_synthetic(bundle)
            self.assertTrue(result['complete'])
            self.assertEqual(result['observed_calls'], 40)
            self.assertEqual(result['metadata_records'], 20)
            self.assertFalse(result['production_imports'])
            self.assertEqual(result['differences'], [])
            self.assertGreater(result['compared_fields'], 300)

    def test_invalid_rule_is_preserved_as_format_valid_choice_failure(self):
        with executed('invalid_rule') as (root, plan_path, run, _, _, _):
            bundle = root / 'invalid_rule.zip'
            bundle_run(plan_path, run, bundle)
            result = verify_synthetic(bundle)
            self.assertTrue(result['complete'])
            self.assertEqual(result['observed_calls'], 40)

    def test_partial_fake_http_bundle_is_not_complete(self):
        with executed('http_error') as (root, plan_path, run, _, _, _):
            bundle = root / 'partial.zip'
            bundle_run(plan_path, run, bundle)
            result = verify_synthetic(bundle)
            self.assertFalse(result['complete'])
            self.assertEqual(result['observed_calls'], 1)
            self.assertEqual(result['metadata_records'], 1)
            self.assertEqual(result['differences'], [])

    def test_failed_v058_verification_cannot_be_ignored(self):
        with executed() as (root, plan_path, run, _, _, _):
            bundle = root / 'baseline_gate.zip'
            bundle_run(plan_path, run, bundle)
            for receipt in [
                    {'complete': False},
                    {'differences': ['injected baseline mismatch']},
                    {'observed_calls': 79},
                    {'observed_calls': 81},
                    {'complete': 1},
                    {'observed_calls': 80.0},
                    {'compared_fields': 2},
            ]:
                with self.subTest(receipt=receipt), self.assertRaises(ValueError):
                    verify_synthetic(bundle, baseline_result=receipt)

    def test_opposite_v058_sequence_request_mismatch_is_rejected(self):
        baseline = synthetic_v058_bundle(mismatch_opposite=True)
        receipt = {'complete': True, 'differences': [], 'observed_calls': 80,
                   'metadata_records': 40, 'compared_fields': 1,
                   'production_imports': False}
        with self.assertRaises(ValueError):
            independent.reconstruct_reference(baseline, receipt)

    def test_rehashed_manifest_cannot_hide_semantic_or_file_mutations(self):
        with executed() as (root, plan_path, run, plan, _, _):
            source = root / 'source.zip'
            bundle_run(plan_path, run, source)
            first_id = plan['slots'][0]['id']

            def change_json(files, name, apply):
                value = json.loads(files[name])
                apply(value)
                files[name] = wire(value)

            mutations = {
                'forged_selected_position': lambda files: change_json(
                    files, 'run/summary.json',
                    lambda summary: summary['trials'][0]['measurement'].__setitem__(
                        'selected_rule_position',
                        (summary['trials'][0]['measurement']['selected_rule_position'] + 1) % 3)),
                'forged_seed_effect': lambda files: change_json(
                    files, 'run/summary.json',
                    lambda summary: summary.__setitem__('seed_mean_B_minus_A', 1.0)),
                'duplicate_pair': lambda files: change_json(
                    files, 'run/summary.json',
                    lambda summary: summary['pairs'].__setitem__(1, summary['pairs'][0])),
                'forged_status': lambda files: change_json(
                    files, 'run/summary.json',
                    lambda summary: summary['trials'][0].__setitem__(
                        'status', 'invalid_response')),
                'forged_korean_summary': lambda files: files.__setitem__(
                    'run/summary.ko.md',
                    '# v059 K01 규칙 배열 순열 진단\n\n조건 효과가 확정되었다.\n'.encode('utf-8')),
                'korean_summary_crlf': lambda files: files.__setitem__(
                    'run/summary.ko.md',
                    files['run/summary.ko.md'].replace(b'\n', b'\r\n')),
                'korean_summary_bom': lambda files: files.__setitem__(
                    'run/summary.ko.md', b'\xef\xbb\xbf' + files['run/summary.ko.md']),
                'missing_response': lambda files: files.pop(
                    f'run/calls/{first_id}/response.raw.json'),
                'alter_request': lambda files: files.__setitem__(
                    f'run/calls/{first_id}/request.wire.json', b'{}'),
                'extra_file': lambda files: files.__setitem__(
                    'run/invented.json', b'{}'),
            }
            for name, mutation in mutations.items():
                target = root / (name + '.zip')
                altered_bundle(source, target, mutation)
                with self.subTest(mutation=name), self.assertRaises(
                        (ValueError, KeyError, AssertionError)):
                    verify_synthetic(target)


if __name__ == '__main__':
    unittest.main()
