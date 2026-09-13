"""Offline checks for the v062 conditional-construction contract."""
from collections import Counter
from copy import deepcopy
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from construction_probe_v062.contracts import ContractError, digest, strict_json
from construction_probe_v062.design import TARGET_RULES, VARIANTS
from construction_probe_v062.measure import match, measure
from construction_probe_v062.plan import make_plan, validate_plan
from construction_probe_v062.reporting import summarize
from construction_probe_v062.requests import request_bytes

try:
    from .runtime_fixture import problem_from_request, reference
except ImportError:
    from runtime_fixture import problem_from_request, reference


def payload_for(target_rule_id):
    if target_rule_id == 'k03':
        return {
            'nodes': [
                {'id': 'fact', 'atom': 'Ca', 'rule_id': None, 'parents': []},
                {'id': 'goal', 'atom': 'Cc', 'rule_id': 'k03', 'parents': ['fact']},
            ],
            'final_node_id': 'goal',
        }
    return {
        # This order deliberately has forward references; it is not semantic.
        'nodes': [
            {'id': 'goal', 'atom': 'Cc', 'rule_id': 'k17', 'parents': ['mid']},
            {'id': 'fact', 'atom': 'Ca', 'rule_id': None, 'parents': []},
            {'id': 'mid', 'atom': 'Cb', 'rule_id': 'k10', 'parents': ['fact']},
        ],
        'final_node_id': 'goal',
    }


class DesignTests(unittest.TestCase):
    def setUp(self):
        self.plan = make_plan(reference())

    def test_frozen_schedule_and_target_mapping(self):
        slots = self.plan['slots']
        self.assertEqual(len(slots), 40)
        self.assertEqual(len(self.plan['actions']), 60)
        self.assertEqual(Counter(slot['sequence'] for slot in slots),
                         {'ABBA': 20, 'BAAB': 20})
        self.assertEqual(Counter((slot['seed'], slot['variant'], slot['repeat'])
                                 for slot in slots),
                         {(seed, variant, repeat): 1
                          for seed in self.plan['seeds']
                          for variant in VARIANTS for repeat in (0, 1)})
        for index, slot in enumerate(slots):
            self.assertEqual(slot['task'], 'conditional_construction')
            self.assertEqual((slot['mode'], slot['stage'], slot['direction']),
                             ('graph', 'graph', 'neutral'))
            self.assertEqual(slot['role_id'], slot['variant'])
            self.assertEqual(slot['target_rule_id'], TARGET_RULES[slot['variant']])
            self.assertEqual(slot['previous_call_id'],
                             slots[index - 1]['id'] if index else None)
            if slot['repeat']:
                self.assertIn(slot['repeat_distance'], (1, 3))
        validate_plan(self.plan)

    def test_only_target_literal_differs_between_variants(self):
        seed = self.plan['seeds'][0]
        slots = {slot['variant']: slot for slot in self.plan['slots']
                 if slot['seed'] == seed and slot['repeat'] == 0}
        first = strict_json(request_bytes(self.plan, slots['target_k03']))
        second = strict_json(request_bytes(self.plan, slots['target_k17']))
        first_text = first['messages'][0]['content']
        second_text = second['messages'][0]['content']
        self.assertEqual(second_text, first_text.replace(
            '지정된 마지막 규칙 id k03', '지정된 마지막 규칙 id k17', 1))
        self.assertEqual({key: value for key, value in first.items() if key != 'messages'},
                         {key: value for key, value in second.items() if key != 'messages'})
        first_problem = problem_from_request(request_bytes(self.plan, slots['target_k03']))
        second_problem = problem_from_request(request_bytes(self.plan, slots['target_k17']))
        self.assertEqual(first_problem, second_problem)
        self.assertEqual([rule['id'] for rule in first_problem['rules']],
                         ['k03', 'k17', 'k10'])
        self.assertNotIn('shallow', first_text)
        self.assertNotIn('deep', first_text)

    def test_rehashed_plan_mutation_is_refused(self):
        changed = deepcopy(self.plan)
        changed['slots'][0]['target_rule_id'] = (
            'k03' if changed['slots'][0]['target_rule_id'] == 'k17' else 'k17')
        changed['plan_sha256'] = digest({key: value for key, value in changed.items()
                                        if key != 'plan_sha256'})
        with self.assertRaises(ContractError):
            validate_plan(changed)


class MeasurementTests(unittest.TestCase):
    def setUp(self):
        self.plan = make_plan(reference())
        self.slots = {slot['variant']: slot for slot in self.plan['slots']
                      if slot['seed'] == self.plan['seeds'][0] and slot['repeat'] == 0}
        self.problem = problem_from_request(request_bytes(self.plan, self.slots['target_k03']))

    def test_valid_k03_and_forward_k17_have_actual_parent_depth(self):
        expected = {'target_k03': (1, 2), 'target_k17': (2, 3)}
        for variant, (depth, node_count) in expected.items():
            with self.subTest(variant=variant):
                slot = self.slots[variant]
                result = measure(self.problem, payload_for(slot['target_rule_id']), slot)
                self.assertTrue(result['format_valid'])
                self.assertTrue(result['proof_valid'])
                self.assertTrue(result['strict_valid'])
                self.assertTrue(result['goal_reached'])
                self.assertTrue(result['target_rule_match'])
                self.assertTrue(result['instruction_fulfilled'])
                self.assertEqual((result['D'], result['actual_D']), (depth, depth))
                self.assertEqual(result['node_count'], node_count)
                self.assertEqual(result['errors'], [])
                self.assertTrue(match(self.problem, result, slot))

    def test_node_rename_and_array_reorder_are_not_semantic(self):
        slot = self.slots['target_k17']
        payload = payload_for('k17')
        payload['nodes'] = [
            {'id': 'source', 'atom': 'Ca', 'rule_id': None, 'parents': []},
            {'id': 'terminal', 'atom': 'Cc', 'rule_id': 'k17', 'parents': ['bridge']},
            {'id': 'bridge', 'atom': 'Cb', 'rule_id': 'k10', 'parents': ['source']},
        ]
        payload['final_node_id'] = 'terminal'
        result = measure(self.problem, payload, slot)
        self.assertTrue(result['strict_valid'])
        self.assertEqual(result['actual_D'], 2)

    def test_zero_premise_registered_rule_has_depth_one(self):
        problem = {'facts': [], 'rules': [
            {'id': 'z0', 'premises': [], 'conclusion': 'G'}], 'goal': 'G'}
        slot = {'target_rule_id': 'z0'}
        result = measure(problem, {
            'nodes': [{'id': 'terminal', 'atom': 'G', 'rule_id': 'z0', 'parents': []}],
            'final_node_id': 'terminal',
        }, slot)
        self.assertTrue(result['instruction_fulfilled'])
        self.assertEqual(result['actual_D'], 1)

    def test_logical_error_categories_are_distinct_and_sorted(self):
        slot = self.slots['target_k03']
        cases = {
            'duplicate_id': ({
                'nodes': [
                    {'id': 'fact', 'atom': 'Ca', 'rule_id': None, 'parents': []},
                    {'id': 'fact', 'atom': 'Ca', 'rule_id': None, 'parents': []},
                    {'id': 'goal', 'atom': 'Cc', 'rule_id': 'k03', 'parents': ['fact']},
                ], 'final_node_id': 'goal'}, 'duplicate_id'),
            'missing_parent': ({
                'nodes': [
                    {'id': 'fact', 'atom': 'Ca', 'rule_id': None, 'parents': []},
                    {'id': 'goal', 'atom': 'Cc', 'rule_id': 'k03', 'parents': ['absent']},
                ], 'final_node_id': 'goal'}, 'missing_parent'),
            'duplicate_parent': ({
                'nodes': [
                    {'id': 'fact', 'atom': 'Ca', 'rule_id': None, 'parents': []},
                    {'id': 'goal', 'atom': 'Cc', 'rule_id': 'k03', 'parents': ['fact', 'fact']},
                ], 'final_node_id': 'goal'}, 'duplicate_parent'),
            'cycle': ({
                'nodes': [
                    {'id': 'goal', 'atom': 'Cc', 'rule_id': 'k03', 'parents': ['goal']},
                ], 'final_node_id': 'goal'}, 'cycle'),
            'wrong_atom': ({
                'nodes': [
                    {'id': 'fact', 'atom': 'Ca', 'rule_id': None, 'parents': []},
                    {'id': 'goal', 'atom': 'Cb', 'rule_id': 'k03', 'parents': ['fact']},
                ], 'final_node_id': 'goal'}, 'wrong_atom'),
            'final_goal_mismatch': ({
                'nodes': [
                    {'id': 'fact', 'atom': 'Ca', 'rule_id': None, 'parents': []},
                    {'id': 'not_goal', 'atom': 'Cb', 'rule_id': 'k10', 'parents': ['fact']},
                ], 'final_node_id': 'not_goal'}, 'final_goal_mismatch'),
            'unregistered_rule': ({
                'nodes': [
                    {'id': 'fact', 'atom': 'Ca', 'rule_id': None, 'parents': []},
                    {'id': 'goal', 'atom': 'Cc', 'rule_id': 'unknown', 'parents': ['fact']},
                ], 'final_node_id': 'goal'}, 'unregistered_rule'),
            'fact_with_parents': ({
                'nodes': [
                    {'id': 'fact', 'atom': 'Ca', 'rule_id': None, 'parents': ['fact']},
                    {'id': 'goal', 'atom': 'Cc', 'rule_id': 'k03', 'parents': ['fact']},
                ], 'final_node_id': 'goal'}, 'fact_with_parents'),
            'unreachable_fact': ({
                'nodes': payload_for('k03')['nodes'] + [
                    {'id': 'bad_fact', 'atom': 'not_a_fact', 'rule_id': None, 'parents': []}],
                'final_node_id': 'goal'}, 'unreachable_fact'),
            'extra_unused_node': ({
                'nodes': payload_for('k03')['nodes'] + [
                    {'id': 'unused', 'atom': 'Ca', 'rule_id': None, 'parents': []}],
                'final_node_id': 'goal'}, 'extra_unused_node'),
        }
        for name, (payload, expected_error) in cases.items():
            with self.subTest(name=name):
                result = measure(self.problem, payload, slot)
                self.assertEqual(result['errors'], sorted(result['errors']))
                self.assertIn(expected_error, result['errors'])
                if name == 'extra_unused_node':
                    self.assertTrue(result['proof_valid'])
                    self.assertFalse(result['strict_valid'])
                    self.assertEqual(result['actual_D'], 1)
                else:
                    self.assertFalse(result['proof_valid'])
                    self.assertFalse(result['goal_reached'])
                    self.assertIsNone(result['actual_D'])

    def test_format_failure_and_target_mismatch_remain_separate(self):
        slot = self.slots['target_k03']
        invalid = measure(self.problem, {'nodes': [], 'final_node_id': 'x'}, slot)
        self.assertFalse(invalid['format_valid'])
        self.assertEqual(invalid['errors'], ['schema_invalid'])
        for key in ('proof_valid', 'strict_valid', 'D', 'actual_D', 'selected_rule_id',
                    'selected_rule_position', 'terminal_rank', 'goal_reached',
                    'target_rule_match', 'instruction_fulfilled', 'node_count'):
            self.assertIsNone(invalid[key], key)
        missing = measure(self.problem, None, slot)
        self.assertFalse(missing['format_valid'])
        self.assertEqual(missing['errors'], [])
        self.assertIsNone(missing['instruction_fulfilled'])
        mismatch = measure(self.problem, payload_for('k03'), self.slots['target_k17'])
        self.assertTrue(mismatch['proof_valid'])
        self.assertTrue(mismatch['strict_valid'])
        self.assertFalse(mismatch['target_rule_match'])
        self.assertFalse(mismatch['instruction_fulfilled'])

    def test_partial_report_is_not_a_gate_failure(self):
        rows = [{**slot, 'observed': False, 'measurement': None, 'role_match': None}
                for slot in self.plan['slots']]
        report = summarize(self.plan, rows, [], False)
        self.assertIsNone(report['admission_gate_passed'])
        self.assertTrue(all(group['instruction_rate'] is None
                            for group in report['variants'].values()))
        self.assertEqual(report['cross_variant']['outcomes']['unobserved'], 20)

    def test_complete_perfect_rows_pass_gate_and_measure_stability(self):
        rows = []
        for slot in self.plan['slots']:
            problem = problem_from_request(request_bytes(self.plan, slot))
            result = measure(problem, payload_for(slot['target_rule_id']), slot)
            rows.append({**slot, 'observed': True, 'measurement': result,
                         'role_match': match(problem, result, slot)})
        report = summarize(self.plan, rows, [], True)
        self.assertIs(report['admission_gate_passed'], True)
        self.assertEqual(report['admission_gate']['strict_target_depth_calls'], 40)
        self.assertEqual(report['admission_gate']['stable_seed_blocks'], 10)
        self.assertTrue(all(row['stable_within_both'] is True
                            for row in report['seed_rows']))


if __name__ == '__main__':
    unittest.main()
