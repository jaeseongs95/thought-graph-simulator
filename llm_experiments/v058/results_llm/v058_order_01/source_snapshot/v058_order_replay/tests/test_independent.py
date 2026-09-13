"""Independent v058 replay verification; only PRIOR baseline audit is mocked.

The local HTTP responses and all v058 request/event/measurement/bundle checks
are real fixture executions. The minimal synthetic v057 container is not
claimed to pass the complete v047-v057 historical evidence chain.
"""
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import zipfile
try:
    from .fixtures import ROOT, executed
except ImportError:
    from fixtures import ROOT, executed
from order_replay_v058.evidence import bundle_run
from order_replay_v058.contracts import wire, sha

SPEC = importlib.util.spec_from_file_location('v058_independent_test_target', ROOT / 'tools' / 'verify_v058.py')
independent = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(independent)


def verify_synthetic(path, *, baseline_result=None):
    receipt = {'complete': True, 'compared_fields': 1, 'differences': [], 'observed_calls': 480,
               'test_scope': 'PRIOR baseline verification mocked; v058 verification real'}
    if baseline_result is not None:
        receipt.update(baseline_result)
    with patch.object(independent, 'baseline_verify', return_value=receipt):
        return independent.verify(path)


def altered_bundle(original, target, mutation):
    with zipfile.ZipFile(original) as archive:
        files = {n: archive.read(n) for n in archive.namelist()}
    manifest = json.loads(files.pop('BUNDLE_MANIFEST.json'))
    mutation(files)
    manifest['file_hashes'] = {name: sha(raw) for name, raw in files.items()}
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in files.items():
            archive.writestr(name, raw)
        archive.writestr('BUNDLE_MANIFEST.json', wire(manifest))


class IndependentTests(unittest.TestCase):
    def test_complete_fake_http_bundle_independently_verified(self):
        with executed() as (root, pp, run, plan, report, state):
            bundle = root / 'complete.zip'
            bundle_run(pp, run, bundle)
            result = verify_synthetic(bundle)
            self.assertTrue(result['complete'])
            self.assertEqual(result['observed_calls'], 80)
            self.assertEqual(result['metadata_records'], 40)
            self.assertFalse(result['production_imports'])
            self.assertEqual(result['differences'], [])
            self.assertGreater(result['compared_fields'], 500)

    def test_partial_fake_http_bundle_is_not_complete(self):
        with executed('http_error') as (root, pp, run, plan, report, state):
            bundle = root / 'partial.zip'
            bundle_run(pp, run, bundle)
            result = verify_synthetic(bundle)
            self.assertFalse(result['complete'])
            self.assertEqual(result['observed_calls'], 1)
            self.assertEqual(result['differences'], [])

    def test_failed_baseline_verification_cannot_be_ignored(self):
        with executed() as (root, pp, run, plan, report, state):
            bundle = root / 'baseline_gate.zip'
            bundle_run(pp, run, bundle)
            for receipt in [{'complete': False}, {'differences': ['injected baseline mismatch']},
                            {'observed_calls': 479}, {'observed_calls': 481},
                            {'complete': 1}, {'observed_calls': 480.0}]:
                with self.subTest(receipt=receipt), self.assertRaises(ValueError):
                    verify_synthetic(bundle, baseline_result=receipt)

    def test_rehashed_manifest_cannot_change_endpoint_host(self):
        with executed() as (root, pp, run, plan, report, state):
            bundle, changed = root / 'endpoint_source.zip', root / 'endpoint_changed.zip'
            bundle_run(pp, run, bundle)

            def wrong_endpoint(files):
                run_manifest = json.loads(files['run/run_manifest.json'])
                run_manifest['endpoint'] = 'http://wrong-host.invalid:11434'
                files['run/run_manifest.json'] = wire(run_manifest)

            altered_bundle(bundle, changed, wrong_endpoint)
            with self.assertRaises(ValueError):
                verify_synthetic(changed)

    def test_rehashed_control_records_require_exact_types_and_fields(self):
        with executed() as (root, pp, run, plan, report, state):
            bundle = root / 'control_source.zip'
            bundle_run(pp, run, bundle)
            for label, record, change in [
                    ('float_call_count', 'run/run_manifest.json', {'max_calls': 80.0}),
                    ('extra_manifest_field', 'run/run_manifest.json', {'unexpected': True}),
                    ('extra_status_field', 'run/status.json', {'unexpected': True})]:
                def mutate(files, record=record, change=change):
                    value = json.loads(files[record])
                    value.update(change)
                    files[record] = wire(value)
                changed = root / (label + '.zip')
                altered_bundle(bundle, changed, mutate)
                with self.subTest(case=label), self.assertRaises(ValueError):
                    verify_synthetic(changed)

    def test_manifest_rehash_does_not_hide_semantic_or_integrity_mutations(self):
        with executed() as (root, pp, run, plan, report, state):
            bundle = root / 'source.zip'
            bundle_run(pp, run, bundle)
            first_id = plan['slots'][0]['id']

            def change_summary(files, apply):
                summary = json.loads(files['run/summary.json'])
                apply(summary)
                files['run/summary.json'] = wire(summary)

            mutations = {
                'duplicate_pair': lambda files: change_summary(files, lambda s: s['pairs'].__setitem__(1, s['pairs'][0])),
                'duplicate_trial': lambda files: change_summary(files, lambda s: s['trials'].__setitem__(1, s['trials'][0])),
                'forged_changed_count': lambda files: change_summary(files, lambda s: s['models']['reference']['modes']['choice'].__setitem__('selected_rule_changed_pairs', 10)),
                'forged_selected_rule': lambda files: change_summary(files, lambda s: next(p for p in s['pairs'] if p['mode'] == 'choice').__setitem__('first_selected_rule_id', 'invented')),
                'missing_response': lambda files: files.pop(f'run/calls/{first_id}/response.raw.json'),
                'missing_status': lambda files: files.pop('run/status.json'),
                'alter_request': lambda files: files.__setitem__(f'run/calls/{first_id}/request.wire.json', b'{}'),
                'extra_file': lambda files: files.__setitem__('run/invented.json', b'{}'),
            }
            for name, mutation in mutations.items():
                target = root / (name + '.zip')
                altered_bundle(bundle, target, mutation)
                with self.subTest(mutation=name), self.assertRaises((ValueError, KeyError, AssertionError)):
                    verify_synthetic(target)


if __name__ == '__main__':
    unittest.main()
