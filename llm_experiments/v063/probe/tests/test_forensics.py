"""Boundary tests for v063's non-repairing v062 failure forensics."""
from __future__ import annotations

from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import zipfile


ROOT = Path(__file__).resolve().parents[1]
V062_ROOT = ROOT.parents[1] / 'v062' / 'probe'
if str(V062_ROOT) not in sys.path:
    sys.path.insert(0, str(V062_ROOT))

from construction_probe_v062.contracts import sha, wire
from construction_probe_v062.evidence import bundle_run


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ANALYZER = _load_module('v063_analyze_v062_test_target',
                        ROOT / 'tools' / 'analyze_v062.py')
FIXTURE = _load_module('v062_runtime_fixture_for_v063',
                       V062_ROOT / 'tests' / 'runtime_fixture.py')

BASELINE_RECEIPT = {
    'contract': 'independent-v058-r1', 'complete': True,
    'compared_fields': 1, 'differences': [], 'observed_calls': 80,
    'metadata_records': 40, 'production_imports': False,
}

PROBLEM = {
    'id': 'K01', 'facts': ['Ca'],
    'rules': [
        {'id': 'k03', 'premises': ['Ca'], 'conclusion': 'Cc'},
        {'id': 'k17', 'premises': ['Cb'], 'conclusion': 'Cc'},
        {'id': 'k10', 'premises': ['Ca'], 'conclusion': 'Cb'},
    ],
    'goal': 'Cc',
}


def node(node_id, atom, rule_id, parents):
    return {'id': node_id, 'atom': atom, 'rule_id': rule_id, 'parents': parents}


def k03_payload(*, extra=()):
    return {
        'nodes': [node('source', 'Ca', None, []),
                  node('goal', 'Cc', 'k03', ['source']), *extra],
        'final_node_id': 'goal',
    }


@contextmanager
def patched_baseline_verify():
    legacy = sys.modules[ANALYZER.verify.__module__]
    with patch.object(legacy, 'baseline_verify', return_value=BASELINE_RECEIPT):
        yield


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def rehash_bundle(source, target, mutate):
    with zipfile.ZipFile(source) as archive:
        files = {entry.filename: archive.read(entry.filename) for entry in archive.infolist()}
    files.pop('BUNDLE_MANIFEST.json')
    mutate(files)
    plan = json.loads(files['external_plan/v062.plan.json'])
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in files.items():
            archive.writestr(name, raw)
        archive.writestr('BUNDLE_MANIFEST.json', wire({
            'contract': 'v062-evidence-bundle-r1',
            'plan_sha256': plan['plan_sha256'],
            'data_complete': json.loads(files['run/status.json'])['complete'],
            'file_hashes': {name: sha(raw) for name, raw in files.items()},
            'note': 'Evidence consistency manifest; not an external execution signature.',
        }))


class NodeDiagnosticTests(unittest.TestCase):
    k03_slot = {'target_rule_id': 'k03'}
    k17_slot = {'target_rule_id': 'k17'}

    def diagnostic(self, payload, target='k03'):
        return ANALYZER.node_diagnostics(PROBLEM, payload, target)

    def official(self, payload, slot=None):
        return ANALYZER.independent_measure(PROBLEM, payload, slot or self.k03_slot)

    def test_node_error_boundaries_remain_official_failures(self):
        cases = {
            'duplicate_id': ({
                'nodes': [node('source', 'Ca', None, []),
                          node('source', 'Ca', None, []),
                          node('goal', 'Cc', 'k03', ['source'])],
                'final_node_id': 'goal',
            }, 'duplicate_id'),
            'missing_parent': ({
                'nodes': [node('goal', 'Cc', 'k03', ['absent'])],
                'final_node_id': 'goal',
            }, 'missing_parent'),
            'cycle': ({
                'nodes': [node('source', 'Ca', None, ['goal']),
                          node('goal', 'Cc', 'k03', ['source'])],
                'final_node_id': 'goal',
            }, 'cycle_member'),
            'self_cycle': ({
                'nodes': [node('goal', 'Cc', 'k03', ['goal'])],
                'final_node_id': 'goal',
            }, 'cycle_member'),
            'unknown_rule': ({
                'nodes': [node('source', 'Ca', None, []),
                          node('goal', 'Cc', 'unknown', ['source'])],
                'final_node_id': 'goal',
            }, 'unregistered_rule'),
            'wrong_atom': ({
                'nodes': [node('source', 'Ca', None, []),
                          node('goal', 'Cb', 'k03', ['source'])],
                'final_node_id': 'goal',
            }, 'wrong_atom'),
            'fact_with_parents': ({
                'nodes': [node('source', 'Ca', None, ['source']),
                          node('goal', 'Cc', 'k03', ['source'])],
                'final_node_id': 'goal',
            }, 'fact_with_parents'),
            'unreachable_fact': (k03_payload(extra=[node('bad', 'not_fact', None, [])]),
                                 'unreachable_fact'),
            'final_goal_mismatch': ({
                'nodes': [node('source', 'Ca', None, []),
                          node('goal', 'Cb', 'k10', ['source'])],
                'final_node_id': 'goal',
            }, 'final_goal_mismatch'),
        }
        for name, (payload, expected) in cases.items():
            with self.subTest(name=name):
                diagnostic = self.diagnostic(payload)
                errors = {error for item in diagnostic['node_diagnostics']
                          for error in item['errors']}
                self.assertIn(expected, errors)
                measured = self.official(payload)
                self.assertFalse(measured['proof_valid'])
                self.assertFalse(measured['strict_valid'])
                self.assertIsNone(measured['actual_D'])

    def test_final_missing_none_and_schema_failure_stay_unmeasured(self):
        missing = k03_payload()
        missing['final_node_id'] = 'absent'
        diagnostic = self.diagnostic(missing)
        self.assertIsNone(diagnostic['final_rule_label_matches_target'])
        self.assertIsNone(diagnostic['final_atom_matches_goal'])
        self.assertIsNone(diagnostic['final_ancestor_ids'])
        measured = self.official(missing)
        self.assertTrue(measured['format_valid'])
        self.assertFalse(measured['proof_valid'])
        self.assertIsNone(measured['actual_D'])

        for payload in (None, {'nodes': [], 'final_node_id': 'goal'}):
            with self.subTest(payload=payload):
                diagnostic = self.diagnostic(payload)
                self.assertTrue(all(value is None for value in diagnostic.values()))
                measured = self.official(payload)
                self.assertFalse(measured['format_valid'])
                self.assertIsNone(measured['proof_valid'])
                self.assertIsNone(measured['actual_D'])

    def test_rename_and_reorder_do_not_change_a_valid_k17_dag(self):
        payload = {
            'nodes': [node('terminal', 'Cc', 'k17', ['bridge']),
                      node('origin', 'Ca', None, []),
                      node('bridge', 'Cb', 'k10', ['origin'])],
            'final_node_id': 'terminal',
        }
        diagnostic = self.diagnostic(payload, 'k17')
        self.assertTrue(diagnostic['final_rule_label_matches_target'])
        self.assertTrue(diagnostic['final_atom_matches_goal'])
        self.assertFalse(diagnostic['has_nodes_outside_final_ancestry'])
        self.assertEqual(diagnostic['error_nodes_inside'], 0)
        self.assertEqual(diagnostic['error_nodes_outside'], 0)
        measured = self.official(payload, self.k17_slot)
        self.assertTrue(measured['instruction_fulfilled'])
        self.assertEqual(measured['actual_D'], 2)

    def test_unused_nodes_never_become_repaired_successes(self):
        valid_unused = k03_payload(extra=[node('unused', 'Ca', None, [])])
        diagnostic = self.diagnostic(valid_unused)
        self.assertTrue(diagnostic['has_nodes_outside_final_ancestry'])
        self.assertEqual((diagnostic['error_nodes_inside'], diagnostic['error_nodes_outside']),
                         (0, 0))
        self.assertFalse(diagnostic['errors_only_outside_final_ancestry'])
        measured = self.official(valid_unused)
        self.assertTrue(measured['proof_valid'])
        self.assertFalse(measured['strict_valid'])
        self.assertEqual(measured['actual_D'], 1)

        invalid_unused = k03_payload(extra=[node('bad', 'not_fact', None, [])])
        diagnostic = self.diagnostic(invalid_unused)
        self.assertTrue(diagnostic['has_nodes_outside_final_ancestry'])
        self.assertEqual((diagnostic['error_nodes_inside'], diagnostic['error_nodes_outside']),
                         (0, 1))
        self.assertTrue(diagnostic['errors_only_outside_final_ancestry'])
        measured = self.official(invalid_unused)
        self.assertFalse(measured['proof_valid'])
        self.assertFalse(measured['strict_valid'])
        self.assertFalse(measured['instruction_fulfilled'])
        self.assertIsNone(measured['actual_D'])


class EndToEndTests(unittest.TestCase):
    def analyze_bundle(self, mode):
        with FIXTURE.executed(mode) as (root, plan_path, run, _, _, _):
            bundle = root / (mode + '.zip')
            bundle_run(plan_path, run, bundle)
            with patched_baseline_verify():
                report = ANALYZER.analyze(bundle)
            return sha(bundle.read_bytes()), report

    def test_analyzer_preserves_complete_partial_and_failure_layers(self):
        for mode in ('perfect', 'http_error', 'invalid_schema', 'syntax_error', 'invalid_rule'):
            with self.subTest(mode=mode):
                bundle_sha256, report = self.analyze_bundle(mode)
                self.assertEqual(report['contract'], 'v062-failure-forensics-r1')
                self.assertEqual(report['bundle_sha256'], bundle_sha256)
                self.assertEqual(report['source_evidence_kind'], 'synthetic_fixture')
                self.assertFalse(report['source_recorded_new_model_inference'])
                self.assertFalse(report['new_model_inference'])
                self.assertTrue(report['posthoc_diagnostics'])
                self.assertFalse(report['repaired_scores_generated'])
                self.assertEqual(len(report['rows']), 40)
                if mode == 'perfect':
                    self.assertTrue(report['official_admission_gate_passed'])
                    self.assertEqual(report['groups']['target_k03']['actual_depths'], {'1': 20})
                    self.assertEqual(report['groups']['target_k17']['actual_depths'], {'2': 20})
                elif mode == 'http_error':
                    self.assertFalse(report['independent_receipt']['complete'])
                    self.assertGreater(sum(not row['observed'] for row in report['rows']), 0)
                    self.assertTrue(any(row['official_measurement'] is None
                                        for row in report['rows']))
                    self.assertIsNone(report['official_admission_gate_passed'])
                else:
                    self.assertTrue(report['independent_receipt']['complete'])
                    expected_category = ('invalid_payload_schema'
                                         if mode == 'invalid_schema' else
                                         'invalid_response' if mode == 'syntax_error' else
                                         'valid_payload')
                    self.assertEqual({row['raw_parse_category'] for row in report['rows']},
                                     {expected_category})
                    self.assertTrue(all(row['official_measurement']['proof_valid'] is not True
                                        for row in report['rows']))
                    self.assertTrue(all(row['official_measurement']['actual_D'] is None
                                        for row in report['rows']))
                    if mode in ('invalid_schema', 'syntax_error'):
                        self.assertTrue(all(row['diagnostics']['node_diagnostics'] is None
                                            for row in report['rows']))

    def test_rehashed_request_is_rejected_before_forensics_report(self):
        with FIXTURE.executed() as (root, plan_path, run, plan, _, _):
            source = root / 'source.zip'
            target = root / 'rehashed-request.zip'
            bundle_run(plan_path, run, source)
            first = plan['slots'][0]['id']
            rehash_bundle(source, target, lambda files: files.__setitem__(
                'run/calls/' + first + '/request.wire.json', b'{}'))
            with patched_baseline_verify(), self.assertRaises(ValueError):
                ANALYZER.analyze(target)


class IndependentReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.verifier = _load_module('v063_verify_forensics_test_target',
                                    ROOT / 'tools' / 'verify_forensics.py')

    def test_independent_verifier_accepts_report_and_rejects_semantic_tampering(self):
        with FIXTURE.executed() as (root, plan_path, run, _, _, _):
            bundle = root / 'source.zip'
            bundle_run(plan_path, run, bundle)
            with patched_baseline_verify():
                report = ANALYZER.analyze(bundle)
            report_path = root / 'analysis.json'
            write_json(report_path, report)
            with patched_baseline_verify():
                receipt = self.verifier.verify_report(bundle, report_path)
            self.assertEqual(receipt['contract'], 'independent-v063-forensics-r1')
            self.assertEqual(receipt['differences'], [])
            self.assertFalse(receipt['production_imports'])

            mutations = {
                'official_D': lambda value: value['rows'][0]['official_measurement'].__setitem__(
                    'actual_D', 99),
                'gate': lambda value: value.__setitem__('official_admission_gate_passed', False),
                'inside_outside': lambda value: value['rows'][0]['diagnostics'].__setitem__(
                    'errors_only_outside_final_ancestry', True),
                'strata': lambda value: value['strata']['sequence'].__setitem__('forged', {}),
                'literal_label': lambda value: value['groups']['target_k03'].__setitem__(
                    'final_rule_label_matches_target', 0),
                'raw_parse_category': lambda value: value['rows'][0].__setitem__(
                    'raw_parse_category', 'forged'),
            }
            for name, mutate in mutations.items():
                with self.subTest(name=name):
                    altered = json.loads(json.dumps(report))
                    mutate(altered)
                    altered_path = root / (name + '.json')
                    write_json(altered_path, altered)
                    with patched_baseline_verify(), self.assertRaises(ValueError):
                        self.verifier.verify_report(bundle, altered_path)

    def test_independent_verifier_preserves_partial_missingness(self):
        with FIXTURE.executed('http_error') as (root, plan_path, run, _, _, _):
            bundle = root / 'partial.zip'
            bundle_run(plan_path, run, bundle)
            with patched_baseline_verify():
                report = ANALYZER.analyze(bundle)
            report_path = root / 'analysis.json'
            write_json(report_path, report)
            with patched_baseline_verify():
                receipt = self.verifier.verify_report(bundle, report_path)
            self.assertFalse(receipt['complete'])
            self.assertEqual(receipt['differences'], [])
            self.assertIsNone(report['official_admission_gate_passed'])
            self.assertGreater(sum(not row['observed'] for row in report['rows']), 0)
            self.assertTrue(any(row['official_measurement'] is None
                                for row in report['rows']))

    def test_strict_report_boundaries_and_existing_receipt_are_rejected(self):
        with FIXTURE.executed() as (root, plan_path, run, _, _, _):
            bundle = root / 'source.zip'
            bundle_run(plan_path, run, bundle)
            with patched_baseline_verify():
                report = ANALYZER.analyze(bundle)
            valid = root / 'analysis.json'
            write_json(valid, report)

            malformed = {
                'duplicate_key': b'{"a":1,"a":2}',
                'nonfinite': b'{"a":NaN}',
                'oversized': b' ' * (self.verifier.REPORT_LIMIT + 1),
            }
            for name, raw in malformed.items():
                with self.subTest(name=name):
                    path = root / (name + '.json')
                    path.write_bytes(raw)
                    with self.assertRaises(ValueError):
                        self.verifier.verify_report(bundle, path)

            bool_for_int = json.loads(json.dumps(report))
            bool_for_int['official_admission_gate']['required_calls'] = True
            typed = root / 'bool-for-int.json'
            write_json(typed, bool_for_int)
            with patched_baseline_verify(), self.assertRaises(ValueError):
                self.verifier.verify_report(bundle, typed)

            existing = root / 'existing-receipt.json'
            existing.write_text('{"preserve":true}\n', encoding='utf-8')
            with patched_baseline_verify(), self.assertRaises(FileExistsError):
                self.verifier.main([str(bundle), str(valid), '--out', str(existing)])
            self.assertEqual(existing.read_text(encoding='utf-8'), '{"preserve":true}\n')


class RunWrapperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tools = str(ROOT / 'tools')
        if tools not in sys.path:
            sys.path.insert(0, tools)
        cls.runner = _load_module('v063_run_forensics_test_target',
                                  ROOT / 'tools' / 'run_forensics.py')

    def test_wrapper_binds_the_synthetic_input_hash_before_writing(self):
        with FIXTURE.executed() as (root, plan_path, run, _, _, _):
            bundle = root / 'source.zip'
            bundle_run(plan_path, run, bundle)
            output = root / 'forensics'
            expected = sha(bundle.read_bytes())
            with patched_baseline_verify(), self.assertRaises(ValueError):
                self.runner.run(bundle, output, expected_sha256='0' * 64)
            self.assertFalse(output.exists())

            with patched_baseline_verify():
                completion = self.runner.run(bundle, output, expected_sha256=expected)
            self.assertFalse(completion['new_model_inference'])
            self.assertFalse(completion['official_scores_changed'])
            self.assertEqual(set(completion['artifact_hashes']), {
                'analysis.json', 'independent.json', 'summary.ko.md'})
            self.assertTrue((output / 'completion.json').is_file())
            with self.assertRaises(FileExistsError):
                self.runner.run(bundle, output, expected_sha256=expected)


if __name__ == '__main__':
    unittest.main()
