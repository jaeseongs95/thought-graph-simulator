from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import warnings
import zipfile
try:
    from .fixtures import executed
except ImportError:
    from fixtures import executed
from order_replay_v058.audit import audit_run
from order_replay_v058.contracts import ContractError, read_json, wire, sha
from order_replay_v058.evidence import safe_unpack


class ExecutionIntegrityTests(unittest.TestCase):
    def test_local_fake_http_80_complete_and_offline_audit(self):
        with executed() as (_, pp, run, plan, report, state):
            self.assertTrue(report['data_integrity'])
            self.assertTrue(report['data_complete'])
            self.assertEqual(report['inference_calls'], 80)
            self.assertEqual(len(state.requests), 80)
            self.assertEqual(len(state.http_requests), 200)
            self.assertEqual(report['evidence_kind'], 'synthetic_fixture')
            self.assertFalse(report['new_model_inference'])
            self.assertEqual(audit_run(pp, run), report)
            for model in report['models'].values():
                for mode in model['modes'].values():
                    self.assertEqual(mode['task_valid'], 20)
                    self.assertEqual(mode['order_outcomes']['both_success'], 10)

    def test_http_failure_stops_after_one_attempt(self):
        with executed('http_error') as (_, pp, run, plan, report, state):
            self.assertFalse(report['data_complete'])
            self.assertEqual(report['inference_calls'], 1)
            self.assertEqual(len(state.requests), 1)
            self.assertEqual(report['failure_kind'], 'transport_error')
            for model in report['models'].values():
                for mode in model['modes'].values():
                    self.assertIsNone(mode['second_minus_first_rate'])

    def test_second_model_failure_does_not_erase_first_model(self):
        with executed('candidate_http') as (_, pp, run, plan, report, state):
            self.assertEqual(report['inference_calls'], 5)
            self.assertEqual(len(state.requests), 5)
            self.assertFalse(report['data_complete'])
            self.assertEqual(report['models']['reference']['modes']['choice']['observed_pairs'], 1)
            self.assertIsNone(report['models']['reference']['modes']['choice']['second_minus_first_rate'])

    def test_metadata_failure_before_inference(self):
        with executed('metadata_http') as (_, pp, run, plan, report, state):
            self.assertEqual(report['inference_calls'], 0)
            self.assertEqual(state.requests, [])
            self.assertEqual(report['failure_kind'], 'runtime_metadata_error')

    def test_identity_drift_after_one_block_stops(self):
        with executed('drift') as (_, pp, run, plan, report, state):
            self.assertEqual(report['inference_calls'], 4)
            self.assertEqual(len(state.requests), 4)
            self.assertEqual(report['failure_kind'], 'runtime_identity_error')

    def test_wrong_response_model_stops_without_retry(self):
        with executed('wrong_model') as (_, pp, run, plan, report, state):
            self.assertEqual(report['inference_calls'], 1)
            self.assertEqual(report['failure_kind'], 'response_identity_error')

    def test_syntax_error_continues_but_is_unmeasured(self):
        with executed('syntax_error') as (_, pp, run, plan, report, state):
            self.assertEqual(len(state.requests), 80)
            self.assertTrue(report['data_complete'])
            for model in report['models'].values():
                for mode in model['modes'].values():
                    self.assertEqual(mode['task_valid'], 0)
                    self.assertEqual(mode['order_outcomes']['unmeasured'], 10)
                    self.assertEqual(mode['order_outcomes']['neither'], 0)

    def test_run_artifact_mutations_rejected(self):
        with executed() as (root, pp, run, plan, report, state):
            first_id = plan['slots'][0]['id']

            def omit_response(target):
                (target / 'calls' / first_id / 'response.raw.json').unlink()

            def change_response(target):
                (target / 'calls' / first_id / 'response.raw.json').write_bytes(b'{}')

            def duplicate_event(target):
                path = target / 'events.jsonl'
                lines = path.read_bytes().splitlines()
                path.write_bytes(b'\n'.join([lines[0], lines[0]] + lines[1:]) + b'\n')

            def extra_call(target):
                (target / 'calls' / 'invented').mkdir()
                (target / 'calls' / 'invented' / 'response.raw.json').write_bytes(b'{}')

            def source_omission(target):
                next((target / 'source_snapshot').rglob('*.py')).unlink()

            for i, mutation in enumerate([omit_response, change_response, duplicate_event, extra_call, source_omission]):
                target = root / f'mutated{i}'
                shutil.copytree(run, target)
                mutation(target)
                with self.subTest(mutation=mutation.__name__), self.assertRaises((ContractError, OSError)):
                    audit_run(pp, target)

    def test_traversal_duplicate_and_wrong_hash_archives_rejected(self):
        for name, members in [('traversal', [('../escape', b'x')]),
                              ('duplicate', [('same', b'x'), ('same', b'x')]),
                              ('wrong_hash', [('safe', b'x')])]:
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                stream = io.BytesIO()
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore', UserWarning)
                    with zipfile.ZipFile(stream, 'w') as archive:
                        for member, data in members:
                            archive.writestr(member, data)
                        hashes = {member: ('0' * 64 if name == 'wrong_hash' else sha(data)) for member, data in members}
                        archive.writestr('BUNDLE_MANIFEST.json', wire({'file_hashes': hashes}))
                with self.subTest(case=name), self.assertRaises(ContractError):
                    safe_unpack(stream.getvalue(), root / 'unpack')
                self.assertFalse((root / 'escape').exists())


if __name__ == '__main__':
    unittest.main()
