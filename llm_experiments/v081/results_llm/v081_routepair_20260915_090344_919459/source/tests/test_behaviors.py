"""선택·생성·복사 오류·부분 실행의 경계를 합성 응답으로 검사한다."""
from copy import deepcopy
from collections import Counter
import unittest
import core081 as core
import design081 as design
import report081 as report
import audit081 as audit
from fixtures081 import plan, response_set, decode_request, answer


def replace_content(raw, obj=None, text=None):
    out = core.load(raw)
    out['message']['content'] = text if text is not None else core.wire(obj).decode()
    return core.wire(out)


class AlternativePolicies(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = plan()
        cls.summaries = {}
        policies = {'first': 'first', 'id0': 'id0', 'count_only': 'count_only', 'depth_only': 'depth_only',
                    'reverse': 'reverse', 'improvement': {'candidate_id': 'first', 'rule_ids': 'oracle'},
                    'regression': {'candidate_id': 'oracle', 'rule_ids': 'first'}}
        for label, policy in policies.items():
            records, raws, _ = response_set(cls.p, policy)
            s = report.summarize(cls.p, records, raws, 'complete')
            other = audit.independent_summary(cls.p, records, raws, 'complete')
            if s != other:
                raise AssertionError('independent summary mismatch: ' + label)
            cls.summaries[label] = s

    def test_first_cannot_pass_D_pairs(self):
        for g in self.summaries['first']['groups'].values():
            self.assertEqual(g['totals']['D']['end_to_end_pairs']['successes'], 0)

    def test_id0_cannot_pass_D_pairs(self):
        for g in self.summaries['id0']['groups'].values():
            self.assertEqual(g['totals']['D']['end_to_end_pairs']['successes'], 0)

    def test_first_and_ID_not_confounded(self):
        for v in ('candidate_id', 'rule_ids'):
            self.assertEqual(self.summaries['first']['groups'][v]['position_id_diagnostic'],
                             {'observed_choices': 96, 'first_position': 96, 'route_0_id': 48})
            self.assertEqual(self.summaries['id0']['groups'][v]['position_id_diagnostic'],
                             {'observed_choices': 96, 'first_position': 48, 'route_0_id': 96})

    def test_count_policy_does_not_pass_inverted_D(self):
        rs = [r for r in self.summaries['count_only']['trials'] if r['arm'] == 'model' and r['metric'] == 'D' and r['problem_id'] in ('H03', 'H04')]
        self.assertTrue(all(r['generator_success'] is True and r['metric_end_to_end'] is False for r in rs))

    def test_W_success_not_added_to_D(self):
        for g in self.summaries['count_only']['groups'].values():
            self.assertEqual(g['totals']['W']['metric_end_to_end']['successes'], 32)
            self.assertEqual(g['totals']['D']['end_to_end_pairs']['successes'], 0)

    def test_depth_only_fails_W_and_four_requests(self):
        for g in self.summaries['depth_only']['groups'].values():
            self.assertEqual(g['totals']['D']['metric_end_to_end']['successes'], 64)
            self.assertEqual(g['totals']['W']['metric_end_to_end']['successes'], 0)
            self.assertFalse(any(c['all_four_selections_correct'] for c in g['metric_discrimination']))

    def test_reverse_valid_graphs_not_success(self):
        for g in self.summaries['reverse']['groups'].values():
            self.assertEqual(sum(p['valid_graph_direction'] == 'reversed' for p in g['pairs']), 48)
            self.assertEqual(g['totals']['D']['generator_success']['successes'], 64)
            self.assertEqual(g['totals']['D']['metric_end_to_end']['successes'], 0)

    def test_flips_alone_do_not_pass_all_four(self):
        for g in self.summaries['reverse']['groups'].values():
            self.assertTrue(all(c['opposite_choices_for_both_directions'] for c in g['metric_discrimination']))
            self.assertFalse(any(c['all_four_selections_correct'] for c in g['metric_discrimination']))

    def test_new_only_improvement_reported(self):
        s = self.summaries['improvement']
        self.assertEqual(s['paired_pairs']['D']['end_to_end_success']['rule_ids_only'], 32)
        self.assertEqual(s['paired_pairs']['D']['end_to_end_success']['candidate_id_only'], 0)
        self.assertEqual(s['paired_trials']['D']['metric_end_to_end']['rule_ids_only'], 32)

    def test_new_only_regression_reported(self):
        s = self.summaries['regression']
        self.assertEqual(s['paired_pairs']['D']['end_to_end_success']['candidate_id_only'], 32)
        self.assertEqual(s['paired_trials']['D']['metric_end_to_end']['candidate_id_only'], 32)
        self.assertEqual(s['paired_trials']['D']['metric_end_to_end']['rule_ids_only'], 0)


class OutputBoundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = plan()
        cls.records, cls.raws, _ = response_set(cls.p)
        cls.t = next(t for t in cls.p['trials'] if t['selector_variant'] == 'rule_ids')
        cls.slot = next(s for s in cls.p['slots'] if s['id'] == cls.t['selection_slot_id'])
        cls.cards = design.cards(cls.p, cls.t)

    def reject(self, obj=None, text=None):
        raws = dict(self.raws)
        raws[self.t['selection_slot_id']] = replace_content(raws[self.t['selection_slot_id']], obj, text)
        self.assertIsNone(design.selected_route(self.p, self.t, raws))
        self.assertIsNone(audit.context(self.p, self.t, raws)[3])
        generation = [o for o in self.p['slots'] if o['trial_id'] == self.t['id'] and o['stage'] != 'select']
        for op in generation:
            self.assertEqual(design.disposition(self.p, op, raws), 'unmappable_selection')
            self.assertEqual(audit.expected_request(self.p, op, raws), ('unmappable_selection', None))
            with self.assertRaises(ValueError):
                design.request_for(self.p, op, raws)
        return raws

    def test_exact_rule_path_maps(self):
        for c in self.cards:
            raw = dict(self.raws)
            ids = [r['id'] for r in c['rules']]
            raw[self.t['selection_slot_id']] = replace_content(raw[self.t['selection_slot_id']], {'rule_ids': ids})
            self.assertEqual(design.selected_route(self.p, self.t, raw), {'candidate_id': c['candidate_id'], 'rule_ids': ids})

    def test_rule_order_not_repaired(self):
        ids = [r['id'] for r in self.cards[0]['rules']]
        self.reject({'rule_ids': ids[::-1]})

    def test_rule_omission_not_filled(self):
        self.reject({'rule_ids': [r['id'] for r in self.cards[0]['rules']][:-1]})

    def test_rules_not_deduplicated(self):
        ids = [r['id'] for r in self.cards[0]['rules']]
        self.reject({'rule_ids': ids + ids[:1]})

    def test_two_candidates_not_mixed(self):
        self.reject({'rule_ids': [self.cards[0]['rules'][0]['id']] + [r['id'] for r in self.cards[1]['rules']][1:]})

    def test_unknown_rule_not_replaced(self):
        self.reject({'rule_ids': ['unknown']})

    def test_extra_fields_rejected(self):
        self.reject({'rule_ids': [r['id'] for r in self.cards[0]['rules']], 'candidate_id': self.cards[0]['candidate_id']})

    def test_direct_ID_in_list_arm_rejected(self):
        self.reject({'candidate_id': self.cards[0]['candidate_id']})

    def test_wrong_types_rejected(self):
        for obj in [None, [], {'rule_ids': []}, {'rule_ids': 'u50'}, {'rule_ids': [True]}, {'rule_ids': [1]}, {'rule_ids': ['x'] * 17}]:
            self.reject(obj)

    def test_duplicate_json_keys_rejected(self):
        ids = core.wire([r['id'] for r in self.cards[0]['rules']]).decode()
        self.reject(text='{"rule_ids":' + ids + ',"rule_ids":' + ids + '}')

    def test_unmappable_observed_not_unobserved(self):
        def transform(op, body, raw):
            if op['stage'] == 'select' and 'rule_ids' in body['format']['properties']:
                obj = core.load(core.load(raw)['message']['content'])
                return replace_content(raw, {'rule_ids': obj['rule_ids'][::-1]})
            return raw
        r, w, _ = response_set(self.p, transform=transform)
        s = report.summarize(self.p, r, w, 'complete')
        self.assertEqual(s, audit.independent_summary(self.p, r, w, 'complete'))
        new = [x for x in s['trials'] if x['selector_variant'] == 'rule_ids']
        self.assertTrue(all(x['selector_status'] == 'unmappable_selection' and x['mapping_success'] is False for x in new))
        self.assertTrue(all(x['metric_end_to_end'] is False and x['generator_success'] is None and x['actual_D'] is None for x in new))
        self.assertEqual(s['groups']['rule_ids']['totals']['D']['generator_success']['unmeasured'], 64)
        self.assertEqual(s['paired_trials']['D']['generator_success']['not_comparable'], 64)
        self.assertTrue(all(x['copy_diagnostic']['kind'] == 'order_mismatch' for x in new))
        self.assertEqual(s['copy_diagnostic_counts'].get('order_mismatch'), 96)

    def test_missing_new_arm_never_rewarded_as_base_win(self):
        ids = {o['id'] for o in self.p['slots'] if design.trial_for(self.p, o)['selector_variant'] == 'rule_ids'}
        records = {k: v for k, v in self.records.items() if k not in ids}
        raws = {k: v for k, v in self.raws.items() if k not in ids}
        s = report.summarize(self.p, records, raws, 'crashed')
        self.assertEqual(s, audit.independent_summary(self.p, records, raws, 'crashed'))
        self.assertEqual(s['paired_trials']['D']['metric_end_to_end']['candidate_id_only'], 0)
        self.assertEqual(s['paired_trials']['D']['metric_end_to_end']['not_comparable'], 64)
        self.assertEqual(s['copy_diagnostic_counts'], {})

    def test_initial_and_previous_node_errors_not_repaired(self):
        def transform(op, body, raw):
            if op['stage'] == 'rule':
                obj = core.load(core.load(raw)['message']['content'])
                obj['node']['parents'] = []
                return replace_content(raw, obj)
            return raw
        r, w, _ = response_set(self.p, transform=transform)
        s = report.summarize(self.p, r, w, 'complete')
        self.assertEqual(s, audit.independent_summary(self.p, r, w, 'complete'))
        self.assertTrue(all(row['generator_success'] is False for row in s['trials']))
        self.assertTrue(all(row['actual_D'] is None for row in s['trials']))
        self.assertTrue(all(row['step_checks'][-1]['valid'] is True for row in s['trials']))

    def test_generation_format_failure_distinct(self):
        def transform(op, body, raw):
            return replace_content(raw, text='not JSON') if op['stage'] == 'final' else raw
        r, w, _ = response_set(self.p, transform=transform)
        s = report.summarize(self.p, r, w, 'complete')
        self.assertEqual(s, audit.independent_summary(self.p, r, w, 'complete'))
        self.assertTrue(all(row['generator_status'] == 'model_output_format_failure' for row in s['trials']))
        self.assertTrue(all(row['actual_D'] is None for row in s['trials']))

    def test_length_is_not_logic_failure_or_zero_depth(self):
        def transform(op, body, raw):
            if op['stage'] == 'final':
                value = core.load(raw); value['done_reason'] = 'length'
                return core.wire(value)
            return raw
        r, w, _ = response_set(self.p, transform=transform)
        s = report.summarize(self.p, r, w, 'complete')
        self.assertEqual(s, audit.independent_summary(self.p, r, w, 'complete'))
        self.assertTrue(all(row['generator_success'] is None and row['actual_D'] is None for row in s['trials']))

    def test_usage_missing_not_zero(self):
        raws = {}
        for sid, raw in self.raws.items():
            value = core.load(raw); value.pop('eval_count')
            raws[sid] = core.wire(value)
        s = report.summarize(self.p, self.records, raws, 'complete')
        self.assertEqual(s, audit.independent_summary(self.p, self.records, raws, 'complete'))
        self.assertEqual(s['usage']['eval_count']['missing'], 1404)


if __name__ == '__main__':
    unittest.main()
