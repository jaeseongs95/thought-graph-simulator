from copy import deepcopy
import unittest
try:
    from .fixtures import plan, measured_trials
except ImportError:
    from fixtures import plan, measured_trials
from order_replay_v058.reporting import summarize


class ReportingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = plan()

    def test_same_seed_order_pairs_not_new_problem_samples(self):
        r = summarize(self.plan, measured_trials(self.plan), [], True)
        self.assertEqual(r['unique_model_seed_blocks'], 20)
        self.assertEqual(len(r['pairs']), 40)
        self.assertIsNone(r['selective_D_control'])
        self.assertFalse(r['historical_responses_are_new_observations'])
        for model in r['models'].values():
            choice = model['modes']['choice']
            self.assertEqual(choice['assigned_pairs'], 10)
            self.assertEqual(choice['order_outcomes']['both_success'], 10)
            self.assertEqual(choice['second_minus_first_rate'], 0)
            self.assertEqual(choice['selected_rule_changed_rate'], 0)
        for pair in r['pairs']:
            if pair['mode'] == 'choice':
                self.assertIsNone(pair['first_D'])
                self.assertIsNone(pair['second_D'])

    def test_discordance_sign_uses_position_not_sequence_label(self):
        for sequence, outcome, sign in [('graph_choice', 'second_only', 1), ('choice_graph', 'first_only', -1)]:
            r = summarize(self.plan, measured_trials(self.plan, choice_sequence=sequence), [], True)
            for model in r['models'].values():
                choice = model['modes']['choice']
                self.assertEqual(choice['order_outcomes'][outcome], 10)
                self.assertEqual(choice['discordant_pairs'], 10)
                self.assertEqual(choice['second_minus_first_rate'], sign)
                self.assertEqual(choice['selected_rule_changed_pairs'], 10)

    def test_incomplete_comparison_rates_null(self):
        r = summarize(self.plan, measured_trials(self.plan), [], False)
        for model in r['models'].values():
            for mode in model['modes'].values():
                self.assertIsNone(mode['second_minus_first_rate'])
            self.assertIsNone(model['modes']['choice']['selected_rule_changed_rate'])

    def test_unobserved_not_neither_or_failure(self):
        r = summarize(self.plan, measured_trials(self.plan, absent=True), [], False)
        for model in r['models'].values():
            for mode in model['modes'].values():
                self.assertEqual(mode['order_outcomes']['unobserved'], 10)
                self.assertEqual(mode['order_outcomes']['neither'], 0)
                self.assertIsNone(mode['second_minus_first_rate'])

    def test_one_unmeasured_pair_cannot_be_zero_filled(self):
        trials = measured_trials(self.plan)
        row = next(t for t in trials if t['mode'] == 'choice' and t['model_key'] == 'reference')
        row['measurement'] = {**row['measurement'], 'format_valid': False, 'task_valid': None,
                              'shallow_success': None, 'selected_rule_id': None, 'implied_depth': None}
        row['role_match'] = None
        r = summarize(self.plan, trials, [], True)
        choice = r['models']['reference']['modes']['choice']
        self.assertEqual(choice['order_outcomes']['unmeasured'], 1)
        self.assertEqual(choice['order_outcomes']['neither'], 0)
        self.assertEqual(choice['measured_pairs'], 9)
        self.assertIsNone(choice['second_minus_first_rate'])


if __name__ == '__main__':
    unittest.main()
