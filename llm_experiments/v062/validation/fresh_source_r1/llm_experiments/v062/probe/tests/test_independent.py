"""Keep the v062 evidence verifier independent from production modules."""
import ast
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import zipfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from construction_probe_v062.measure import measure
from construction_probe_v062.contracts import sha, wire
from construction_probe_v062.evidence import bundle_run

try:
    from .runtime_fixture import (executed, problem_from_request, reference,
                                  synthetic_v058_bundle)
    from .test_design_measure import payload_for
except ImportError:
    from runtime_fixture import (executed, problem_from_request, reference,
                                 synthetic_v058_bundle)
    from test_design_measure import payload_for


def load_verifier():
    spec = importlib.util.spec_from_file_location(
        'v062_independent_test_target', ROOT / 'tools' / 'verify_v062.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASELINE_RECEIPT = {
    'contract': 'independent-v058-r1', 'complete': True,
    'compared_fields': 1, 'differences': [], 'observed_calls': 80,
    'metadata_records': 40, 'production_imports': False,
}


def verify_synthetic(verifier, path, *, baseline_result=None):
    receipt = dict(BASELINE_RECEIPT)
    if baseline_result:
        receipt.update(baseline_result)
    with patch.object(verifier, 'baseline_verify', return_value=receipt):
        return verifier.verify(path)


def altered_bundle(original, target, mutation):
    with zipfile.ZipFile(original) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    files.pop('BUNDLE_MANIFEST.json')
    mutation(files)
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in files.items():
            archive.writestr(name, raw)
        archive.writestr('BUNDLE_MANIFEST.json', wire({
            'contract': 'v062-evidence-bundle-r1',
            'plan_sha256': json.loads(files['external_plan/v062.plan.json'])['plan_sha256'],
            'data_complete': json.loads(files['run/status.json'])['complete'],
            'file_hashes': {name: sha(raw) for name, raw in files.items()},
            'note': 'Evidence consistency manifest; not an external execution signature.',
        }))


class IndependentTests(unittest.TestCase):
    def test_request_generation_does_not_import_measurement_or_reporting(self):
        tree = ast.parse((ROOT / 'construction_probe_v062' / 'requests.py').read_text(
            encoding='utf-8'))
        modules = [node.module or '' for node in ast.walk(tree)
                   if isinstance(node, ast.ImportFrom)]
        self.assertFalse(any(any(term in module for term in
                                 ('measure', 'oracle', 'reporting', 'audit'))
                             for module in modules), modules)

    def test_verifier_does_not_import_the_production_probe(self):
        tree = ast.parse((ROOT / 'tools' / 'verify_v062.py').read_text(encoding='utf-8'))
        modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                modules.append(node.module or '')
        forbidden = ('construction_probe_v062', '.audit', '.measure', '.plan',
                     '.reporting', '.requests', '.runner', '.evidence')
        self.assertFalse(any(any(term in module for term in forbidden)
                             for module in modules), modules)

    def test_kahn_verifier_matches_production_for_forward_dag_and_composite_error(self):
        verifier = load_verifier()
        ref = reference()
        slot = {'target_rule_id': 'k17'}
        raw = verifier.transform_request(
            __import__('base64').b64decode(ref['request_bank'][ref['slots'][0]['id']]), 'k17')
        problem = problem_from_request(raw)
        valid = payload_for('k17')
        composite = {
            'nodes': [
                {'id': 'fact', 'atom': 'Ca', 'rule_id': None, 'parents': ['absent']},
                {'id': 'goal', 'atom': 'Cb', 'rule_id': 'k03', 'parents': ['fact']},
            ],
            'final_node_id': 'goal',
        }
        for payload in (valid, composite):
            with self.subTest(payload=payload):
                expected = measure(problem, payload, slot)
                actual = verifier.independent_measure(problem, payload, slot)
                self.assertEqual(actual, expected)

    def test_complete_synthetic_run_bundle_is_independently_verified(self):
        verifier = load_verifier()
        with executed() as (root, plan_path, run, _, _, _):
            bundle = root / 'complete.zip'
            bundle_run(plan_path, run, bundle)
            result = verify_synthetic(verifier, bundle)
            self.assertTrue(result['complete'])
            self.assertEqual(result['observed_calls'], 40)
            self.assertEqual(result['metadata_records'], 20)
            self.assertEqual(result['differences'], [])
            self.assertFalse(result['production_imports'])
            self.assertGreater(result['compared_fields'], 300)

    def test_partial_synthetic_run_stays_incomplete_under_independent_verification(self):
        verifier = load_verifier()
        with executed('http_error') as (root, plan_path, run, _, _, _):
            bundle = root / 'partial.zip'
            bundle_run(plan_path, run, bundle)
            result = verify_synthetic(verifier, bundle)
            self.assertFalse(result['complete'])
            self.assertEqual(result['observed_calls'], 1)
            self.assertEqual(result['metadata_records'], 1)
            self.assertEqual(result['differences'], [])

    def test_complete_bundle_preserves_schema_parse_and_logical_failure_layers(self):
        verifier = load_verifier()
        expected = {
            'invalid_schema': ('invalid_payload_schema', False, ['schema_invalid']),
            'syntax_error': ('invalid_response', False, []),
            'invalid_rule': ('valid_payload', True, None),
        }
        for mode, (status, format_valid, errors) in expected.items():
            with self.subTest(mode=mode), executed(mode) as (root, plan_path, run, _, report, _):
                bundle = root / (mode + '.zip')
                bundle_run(plan_path, run, bundle)
                result = verify_synthetic(verifier, bundle)
                self.assertTrue(result['complete'])
                self.assertEqual(result['observed_calls'], 40)
                self.assertEqual({trial['status'] for trial in report['trials']}, {status})
                self.assertTrue(all(trial['measurement']['format_valid'] is format_valid
                                    for trial in report['trials']))
                if errors is not None:
                    self.assertTrue(all(trial['measurement']['errors'] == errors
                                        for trial in report['trials']))
                else:
                    self.assertTrue(all(trial['measurement']['proof_valid'] is False
                                        for trial in report['trials']))

    def test_rehashed_bundle_cannot_hide_measurement_event_request_or_snapshot_tampering(self):
        verifier = load_verifier()
        with executed() as (root, plan_path, run, plan, _, _):
            source = root / 'source.zip'
            bundle_run(plan_path, run, source)
            first = plan['slots'][0]['id']

            def change_json(files, name, apply):
                value = json.loads(files[name])
                apply(value)
                files[name] = wire(value)

            snapshot = next(name for name in zipfile.ZipFile(source).namelist()
                            if name.startswith('run/source_snapshot/') and name.endswith('.py'))
            mutations = {
                'forged_actual_depth': lambda files: change_json(
                    files, 'run/summary.json', lambda summary: summary['trials'][0]
                    ['measurement'].__setitem__('actual_D', 99)),
                'forged_instruction': lambda files: change_json(
                    files, 'run/summary.json', lambda summary: summary['trials'][0]
                    ['measurement'].__setitem__('instruction_fulfilled', False)),
                'forged_event_order': lambda files: files.__setitem__(
                    'run/events.jsonl', files['run/events.jsonl'].replace(b'\n', b'\n', 1)
                    + files['run/events.jsonl'].splitlines()[0] + b'\n'),
                'altered_request': lambda files: files.__setitem__(
                    f'run/calls/{first}/request.wire.json', b'{}'),
                'altered_snapshot': lambda files: files.__setitem__(
                    snapshot, files[snapshot] + b'\n# altered\n'),
                'forged_korean_summary': lambda files: files.__setitem__(
                    'run/summary.ko.md', b'# forged\n'),
            }
            for name, mutation in mutations.items():
                target = root / (name + '.zip')
                altered_bundle(source, target, mutation)
                with self.subTest(mutation=name), self.assertRaises(
                        (ValueError, KeyError, AssertionError, UnicodeError)):
                    verify_synthetic(verifier, target)

    def test_independent_baseline_gate_cannot_be_bypassed(self):
        verifier = load_verifier()
        with executed() as (root, plan_path, run, _, _, _):
            bundle = root / 'baseline_gate.zip'
            bundle_run(plan_path, run, bundle)
            for receipt in ({'complete': False}, {'differences': ['mismatch']},
                            {'observed_calls': 79}, {'metadata_records': 39},
                            {'production_imports': True}):
                with self.subTest(receipt=receipt), self.assertRaises(
                        (ValueError, KeyError, AssertionError)):
                    verify_synthetic(verifier, bundle, baseline_result=receipt)

    def test_opposite_prior_sequence_mismatch_is_rejected(self):
        verifier = load_verifier()
        baseline = synthetic_v058_bundle(mismatch_opposite=True)
        with self.assertRaises((ValueError, KeyError, AssertionError)):
            verifier.reconstruct_reference(baseline, BASELINE_RECEIPT)


if __name__ == '__main__':
    unittest.main()
