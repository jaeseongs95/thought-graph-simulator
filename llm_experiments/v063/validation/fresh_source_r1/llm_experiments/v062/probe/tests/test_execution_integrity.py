"""Local synthetic HTTP integrity checks; they never call Ollama or a model."""
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from construction_probe_v062.contracts import ContractError, b64, digest, sha, wire
from construction_probe_v062.evidence import validate_reference_file
from construction_probe_v062.runner import call_failure, metadata_failure

try:
    from .runtime_fixture import executed
except ImportError:
    from runtime_fixture import executed


class ExecutionIntegrityTests(unittest.TestCase):
    def test_synthetic_40_call_run_and_audit_records_actual_dag_layers(self):
        from construction_probe_v062.audit import audit_run

        with executed() as (_, plan_path, run, _, report, state):
            self.assertTrue(report['data_integrity'])
            self.assertTrue(report['data_complete'])
            self.assertEqual(report['inference_calls'], 40)
            self.assertEqual(report['admission_gate_passed'], True)
            self.assertEqual(len(state.requests), 40)
            self.assertEqual(len(state.http_requests), 100)
            self.assertEqual(report['evidence_kind'], 'synthetic_fixture')
            self.assertFalse(report['new_model_inference'])
            self.assertEqual(audit_run(plan_path, run), report)
            for variant, expected_depth in (('target_k03', '1'), ('target_k17', '2')):
                group = report['variants'][variant]
                self.assertEqual(group['observed_calls'], 20)
                self.assertEqual(group['format_valid'], 20)
                self.assertEqual(group['proof_valid'], 20)
                self.assertEqual(group['strict_valid'], 20)
                self.assertEqual(group['target_rule_match'], 20)
                self.assertEqual(group['instruction_fulfilled'], 20)
                self.assertEqual(group['actual_depths'], {expected_depth: 20})

    def test_transport_failure_stops_without_retry_and_keeps_gate_unresolved(self):
        with executed('http_error') as (_, _, _, _, report, state):
            self.assertFalse(report['data_complete'])
            self.assertEqual(report['inference_calls'], 1)
            self.assertEqual(len(state.requests), 1)
            self.assertEqual(report['failure_kind'], 'transport_error')
            self.assertIsNone(report['admission_gate_passed'])
            self.assertEqual(sum(group['observed_calls']
                                 for group in report['variants'].values()), 1)

    def test_schema_valid_but_invalid_dag_is_not_repaired(self):
        with executed('invalid_rule') as (_, _, _, _, report, state):
            self.assertTrue(report['data_complete'])
            self.assertEqual(len(state.requests), 40)
            self.assertEqual(report['admission_gate_passed'], False)
            for group in report['variants'].values():
                self.assertEqual(group['format_valid'], 20)
                self.assertEqual(group['proof_valid'], 0)
                self.assertEqual(group['instruction_fulfilled'], 0)

    def test_run_artifact_tampering_is_rejected_by_reaudit(self):
        from construction_probe_v062.audit import audit_run

        with executed() as (root, plan_path, run, plan, _, _):
            first = plan['slots'][0]['id']

            def remove_response(target):
                (target / 'calls' / first / 'response.raw.json').unlink()

            def alter_request(target):
                (target / 'calls' / first / 'request.wire.json').write_bytes(b'{}')

            def duplicate_event(target):
                path = target / 'events.jsonl'
                lines = path.read_bytes().splitlines()
                path.write_bytes(b'\n'.join([lines[0], lines[0]] + lines[1:]) + b'\n')

            def alter_snapshot(target):
                path = next((target / 'source_snapshot').rglob('*.py'))
                path.write_bytes(path.read_bytes() + b'\n# altered\n')

            for index, mutation in enumerate(
                    (remove_response, alter_request, duplicate_event, alter_snapshot)):
                target = root / f'mutated_{index}'
                shutil.copytree(run, target)
                mutation(target)
                with self.subTest(mutation=mutation.__name__), \
                        self.assertRaises((ContractError, OSError, KeyError, ValueError)):
                    audit_run(plan_path, target)

    def test_transport_and_response_identity_failures_remain_distinct(self):
        self.assertEqual(call_failure(b'{}', 503, 'connection refused', 'fixture:model'),
                         ('transport_error', 'HTTP 503: connection refused'))
        self.assertEqual(call_failure(b'{"model":"other:model"}', 200, None,
                                      'fixture:model'),
                         ('response_identity_error',
                          'Response model differs from request model: other:model'))
        # Payload syntax is measured after a successful transport; it is not a retry cue.
        self.assertEqual(call_failure(b'{', 200, None, 'fixture:model'), (None, None))

    def test_metadata_identity_normalizes_only_parameter_line_order(self):
        model = 'fixture:model'
        details, model_info = {'family': 'fixture'}, {'layers': 1}
        show = {
            'details': details, 'template': 'fixture-template',
            'parameters': 'alpha 1\nbeta 2', 'model_info': model_info,
        }
        expected = {
            'model': model, 'digest': 'a' * 64, 'show_sha256': digest(show),
            'server': {'version': 'fixture'}, 'details': details,
            'template': 'fixture-template', 'parameters': 'alpha 1\nbeta 2',
            'model_info': model_info,
        }

        def record(parameters):
            responses = ({'version': 'fixture'}, {'models': [{
                'name': model, 'digest': 'a' * 64, 'details': details,
            }]}, {**show, 'parameters': parameters})
            return {
                'at': 'fixture', 'model': model,
                'requests': [{
                    'name': name, 'path': path,
                    'request_b64': b64(wire({'model': model})) if name == 'show' else None,
                    'response_b64': b64(wire(response)), 'http_status': 200,
                    'transport_error': None, 'elapsed_ns': 1,
                } for name, path, response in zip(
                    ('server', 'tags', 'show'),
                    ('/api/version', '/api/tags', '/api/show'), responses)],
            }

        self.assertEqual(metadata_failure(record('beta 2\nalpha 1'), expected), (None, None))
        failure, _ = metadata_failure(record('beta 3\nalpha 1'), expected)
        self.assertEqual(failure, 'runtime_identity_error')

    def test_tampered_frozen_evidence_is_rejected_before_import(self):
        with tempfile.TemporaryDirectory(prefix='v062_tamper_') as temp:
            bundle = Path(temp) / 'baseline.zip'
            original = b'preserved evidence bytes'
            bundle.write_bytes(original + b' changed')
            plan = {'reference': {'bundle_sha256': sha(original)}}
            with self.assertRaises(ContractError):
                validate_reference_file(bundle, plan)

    def test_windows_launcher_keeps_check_only_before_server_start(self):
        source = (ROOT / 'windows' / 'Run-v062.ps1').read_text(encoding='utf-8')
        self.assertIn("'v062-one-click-completion-r1'", source)
        self.assertIn("'construction_probe_v062'", source)
        self.assertLess(source.index('if ($CheckOnly)'),
                        source.index('Ensure-LocalOllamaServer -PlanPath $planPath'))
        self.assertIn("'-B', '-m', 'construction_probe_v062'", source)


if __name__ == '__main__':
    unittest.main()
