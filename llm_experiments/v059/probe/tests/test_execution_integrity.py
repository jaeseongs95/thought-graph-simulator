import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

try:
    from .runtime_fixture import (executed, reference_and_baseline,
                                  request_problem, synthetic_v058_bundle,
                                  _v058_synthetic_plan)
except ImportError:
    from runtime_fixture import (executed, reference_and_baseline,
                                 request_problem, synthetic_v058_bundle,
                                 _v058_synthetic_plan)

from rule_order_v059.audit import audit_run
from rule_order_v059.contracts import ContractError, b64, digest, read_json, wire
from rule_order_v059.evidence import import_v058
from rule_order_v059.runner import metadata_failure


class ExecutionIntegrityTests(unittest.TestCase):
    def test_minimal_v058_bundle_reconstructs_reference_and_checks_opposite(self):
        expected, baseline = reference_and_baseline()
        summary = {
            'data_integrity': True,
            'data_complete': True,
            'comparative_analysis_ready': True,
            'inference_calls': 80,
            'event_tip': 'f' * 64,
            'evidence_kind': 'synthetic_fixture',
        }
        independent = types.SimpleNamespace(verify=lambda _: {
            'complete': True, 'differences': [], 'observed_calls': 80,
            'metadata_records': 40, 'compared_fields': 7})
        with tempfile.TemporaryDirectory(prefix='v059_import_fixture_') as temp:
            path = Path(temp) / 'v058.zip'
            path.write_bytes(baseline)
            with patch('order_replay_v058.audit.audit_run', return_value=summary), \
                    patch.dict(sys.modules, {'verify_v058': independent}):
                actual = import_v058(path)
            expected['independent_compared_fields'] = 7
            expected.pop('receipt_sha256')
            expected['receipt_sha256'] = digest(expected)
            self.assertEqual(actual, expected)

            path.write_bytes(synthetic_v058_bundle(
                _v058_synthetic_plan(), mismatch_opposite=True))
            with patch('order_replay_v058.audit.audit_run', return_value=summary), \
                    patch.dict(sys.modules, {'verify_v058': independent}), \
                    self.assertRaises(ContractError):
                import_v058(path)

    def test_metadata_parameter_line_order_is_stable_identity(self):
        model = 'fixture:model'
        details = {'family': 'fixture'}
        model_info = {'layers': 1}
        show = {
            'details': details,
            'template': 'fixture-template',
            'parameters': 'alpha 1\nbeta 2',
            'model_info': model_info,
        }
        expected = {
            'model': model,
            'digest': 'a' * 64,
            'show_sha256': digest(show),
            'server': {'version': 'fixture'},
            'details': details,
            'template': 'fixture-template',
            'parameters': 'alpha 1\nbeta 2',
            'model_info': model_info,
        }

        def record(parameters):
            changed = {**show, 'parameters': parameters}
            responses = (
                {'version': 'fixture'},
                {'models': [{
                    'name': model, 'digest': 'a' * 64, 'details': details}]},
                changed,
            )
            names = ('server', 'tags', 'show')
            paths = ('/api/version', '/api/tags', '/api/show')
            return {
                'at': 'fixture',
                'model': model,
                'requests': [{
                    'name': name,
                    'path': path,
                    'request_b64': (b64(wire({'model': model}))
                                    if name == 'show' else None),
                    'response_b64': b64(wire(response)),
                    'http_status': 200,
                    'transport_error': None,
                    'elapsed_ns': 1,
                } for name, path, response in zip(names, paths, responses)],
            }

        self.assertEqual(
            metadata_failure(record('beta 2\nalpha 1'), expected),
            (None, None))
        failure, _ = metadata_failure(record('beta 3\nalpha 1'), expected)
        self.assertEqual(failure, 'runtime_identity_error')

    def test_synthetic_40_call_run_and_offline_audit(self):
        with executed() as (_, plan_path, run, plan, report, state):
            self.assertTrue(report['data_integrity'])
            self.assertTrue(report['data_complete'])
            self.assertEqual(report['inference_calls'], 40)
            self.assertEqual(report['assigned_calls'], 40)
            self.assertEqual(len(state.requests), 40)
            self.assertEqual(len(state.http_requests), 100)
            self.assertEqual(report['evidence_kind'], 'synthetic_fixture')
            self.assertFalse(report['new_model_inference'])
            self.assertEqual(audit_run(plan_path, run), report)
            self.assertEqual(len(read_json(run / 'status.json')), 11)
            events = (run / 'events.jsonl').read_bytes().splitlines()
            self.assertEqual(len(events), 60)
            self.assertEqual(sum(json.loads(line)['action']['kind'] == 'metadata'
                                 for line in events), 20)
            for group in report['variants'].values():
                self.assertEqual(group['observed_calls'], 20)
                self.assertEqual(group['choice_valid'], 20)
                self.assertEqual(group['shallow_success'], 20)

            for slot in plan['slots']:
                raw = (run / 'calls' / slot['id'] / 'request.wire.json').read_bytes()
                problem = request_problem(raw)
                expected = (['k10', 'k17', 'k03'] if slot['variant'] == 'original'
                            else ['k10', 'k03', 'k17'])
                self.assertEqual([rule['id'] for rule in problem['rules']], expected)

    def test_transport_failure_stops_without_retry_and_keeps_partial(self):
        with executed('http_error') as (_, _, _, _, report, state):
            self.assertFalse(report['data_complete'])
            self.assertEqual(report['inference_calls'], 1)
            self.assertEqual(len(state.requests), 1)
            self.assertEqual(report['failure_kind'], 'transport_error')
            self.assertEqual(report['variants']['original']['observed_calls']
                             + report['variants']['terminal_swap']['observed_calls'], 1)
            self.assertIsNone(report['seed_mean_B_minus_A'])
            self.assertIsNone(report['cross_variant']['mean_b_minus_a'])

    def test_metadata_failure_before_inference(self):
        with executed('metadata_http') as (_, _, _, _, report, state):
            self.assertEqual(report['inference_calls'], 0)
            self.assertEqual(state.requests, [])
            self.assertEqual(report['failure_kind'], 'runtime_metadata_error')

    def test_identity_drift_after_first_block_stops(self):
        with executed('drift') as (_, _, _, _, report, state):
            self.assertEqual(report['inference_calls'], 4)
            self.assertEqual(len(state.requests), 4)
            self.assertEqual(report['failure_kind'], 'runtime_identity_error')
            self.assertFalse(report['data_complete'])

    def test_response_identity_failure_stops_without_retry(self):
        with executed('wrong_model') as (_, _, _, _, report, state):
            self.assertEqual(report['inference_calls'], 1)
            self.assertEqual(len(state.requests), 1)
            self.assertEqual(report['failure_kind'], 'response_identity_error')

    def test_invalid_payloads_are_recorded_without_host_repair(self):
        with executed('invalid_rule') as (_, _, _, _, report, state):
            self.assertTrue(report['data_complete'])
            self.assertEqual(len(state.requests), 40)
            for group in report['variants'].values():
                self.assertEqual(group['format_valid'], 20)
                self.assertEqual(group['choice_valid'], 0)
                self.assertEqual(group['shallow_success'], 0)
            self.assertTrue(all(t['measurement']['selected_rule_id'] == 'unknown'
                                and t['measurement']['selected_rule_position'] is None
                                and t['measurement']['actual_D'] is None
                                and t['measurement']['proof_valid'] is None
                                and t['measurement']['strict_valid'] is None
                                for t in report['trials']))

    def test_syntax_errors_continue_but_remain_unmeasured(self):
        with executed('syntax_error') as (_, _, _, _, report, state):
            self.assertTrue(report['data_complete'])
            self.assertEqual(len(state.requests), 40)
            for group in report['variants'].values():
                self.assertEqual(group['format_valid'], 0)
                self.assertEqual(group['unmeasured'], 20)
                self.assertIsNone(group['shallow_rate'])

    def test_run_artifact_mutations_are_rejected(self):
        with executed() as (root, plan_path, run, plan, _, _):
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
                folder = target / 'calls' / 'invented'
                folder.mkdir()
                (folder / 'response.raw.json').write_bytes(b'{}')

            def source_omission(target):
                next((target / 'source_snapshot').rglob('*.py')).unlink()

            mutations = (omit_response, change_response, duplicate_event,
                         extra_call, source_omission)
            for index, mutation in enumerate(mutations):
                target = root / f'mutated{index}'
                shutil.copytree(run, target)
                mutation(target)
                with self.subTest(mutation=mutation.__name__), \
                        self.assertRaises((ContractError, OSError)):
                    audit_run(plan_path, target)

    def test_failed_audit_does_not_follow_report_symlink(self):
        with executed() as (root, plan_path, run, _, _, _):
            target = root / 'linked-report'
            shutil.copytree(run, target)
            outside = root / 'outside.txt'
            outside.write_text('preserve', encoding='utf-8')
            report = target / 'summary.json'
            original_report = report.read_bytes()
            report.unlink()
            try:
                os.symlink(outside, report)
            except OSError as exc:
                report.write_bytes(original_report)
                real_is_symlink = Path.is_symlink

                def marked_as_symlink(path):
                    return path == report or real_is_symlink(path)

                with patch.object(Path, 'is_symlink', marked_as_symlink), \
                        self.assertRaises(ContractError):
                    audit_run(plan_path, target, write_report=True)
                self.assertEqual(report.read_bytes(), original_report,
                                 'Failure report followed a simulated link: ' + str(exc))
            else:
                with self.assertRaises(ContractError):
                    audit_run(plan_path, target, write_report=True)
                self.assertEqual(outside.read_text(encoding='utf-8'), 'preserve')


if __name__ == '__main__':
    unittest.main()
