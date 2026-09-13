"""Offline adversarial checks: manipulation isolation, measurement and missingness."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import terminal_position_v060
from terminal_position_v060.contracts import ContractError, digest, strict_json, unb64, b64
from terminal_position_v060.design import schedule, RULE_ORDERS
from terminal_position_v060.plan import make_plan, validate_plan
from terminal_position_v060.requests import request_bytes, transform
from terminal_position_v060.measure import measure, match
from terminal_position_v060.reporting import summarize


def reference():
    source = terminal_position_v060.DEPENDENCY_ROOT / 'tests' / 'fixtures.py'
    spec = importlib.util.spec_from_file_location('v058_fixture_for_design', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    p = module.plan()
    slots = [s for s in p['slots'] if s['model_key'] == 'candidate' and
             s['mode'] == 'choice' and s['sequence'] == 'graph_choice']
    ref = {'contract': 'audited-v058-choice-r1', 'bundle_sha256': 'a' * 64,
           'plan_sha256': p['plan_sha256'], 'event_tip': 'b' * 64, 'recorded_calls': 80,
           'selected_calls': 10, 'evidence_kind': 'synthetic_fixture',
           'config': p['baseline']['config'], 'identities': {'candidate': p['identities']['candidate']},
           'seeds': p['seeds'], 'slots': slots,
           'request_bank': {s['id']: p['reference']['request_bank'][s['reference_slot_id']] for s in slots},
           'independent_compared_fields': 1}
    ref['receipt_sha256'] = digest(ref)
    return ref


class DesignTests(unittest.TestCase):
    def setUp(self):
        self.p = make_plan(reference())

    def test_balanced_full_schedule_and_history(self):
        from collections import Counter
        slots = self.p['slots']
        self.assertEqual(len(slots), 40)
        self.assertEqual(Counter(s['sequence'] for s in slots), {'ABBA': 20, 'BAAB': 20})
        self.assertEqual(Counter((s['variant'], s['period']) for s in slots),
                         {(v, period): 5 for v in RULE_ORDERS for period in range(4)})
        self.assertEqual(Counter((s['seed'], s['variant'], s['repeat']) for s in slots),
                         {(seed, v, rep): 1 for seed in self.p['seeds'] for v in RULE_ORDERS for rep in (0, 1)})
        for i, slot in enumerate(slots):
            self.assertNotIn('previous_call_mode', slot)
            self.assertNotIn('position_in_group', slot)
            self.assertEqual(slot['previous_call_id'], slots[i-1]['id'] if i else None)
            if slot['repeat']:
                self.assertIn(slot['repeat_distance'], (1, 3))
        self.assertEqual(slots, schedule(self.p['reference']))

    def test_only_rule_array_bytes_and_objects_change(self):
        for seed in self.p['seeds']:
            slots = [s for s in self.p['slots'] if s['seed'] == seed]
            a = next(s for s in slots if s['variant'] == 'deep_first')
            b = next(s for s in slots if s['variant'] == 'shallow_first')
            raw = unb64(self.p['reference']['request_bank'][a['reference_slot_id']])
            self.assertNotEqual(request_bytes(self.p, a), raw)
            self.assertNotEqual(request_bytes(self.p, b), raw)
            qa, qb = (strict_json(request_bytes(self.p, s)) for s in (a, b))
            pa = strict_json(qa['messages'][0]['content'].split('\n\nproblem: ')[1].encode())
            pb = strict_json(qb['messages'][0]['content'].split('\n\nproblem: ')[1].encode())
            self.assertEqual([r['id'] for r in pa['rules']], ['k17', 'k03', 'k10'])
            self.assertEqual([r['id'] for r in pb['rules']], ['k03', 'k17', 'k10'])
            self.assertEqual(sorted(pa['rules'], key=lambda r: r['id']), sorted(pb['rules'], key=lambda r: r['id']))
            self.assertEqual({k:v for k,v in qa.items() if k != 'messages'}, {k:v for k,v in qb.items() if k != 'messages'})
            self.assertEqual(qa['messages'][0]['content'].split('\n\nproblem: ')[0], qb['messages'][0]['content'].split('\n\nproblem: ')[0])
            self.assertEqual({k:v for k,v in pa.items() if k != 'rules'}, {k:v for k,v in pb.items() if k != 'rules'})

    def test_frozen_hypotheses_make_opposite_joint_predictions(self):
        first_terminal = tuple(RULE_ORDERS[v][0] for v in RULE_ORDERS)
        absolute_second = tuple(RULE_ORDERS[v][1] for v in RULE_ORDERS)
        self.assertEqual(first_terminal, ('k17', 'k03'))
        self.assertEqual(absolute_second, ('k03', 'k17'))
        self.assertNotEqual(first_terminal, absolute_second)

    def test_v059_analysis_predictions_separate_only_in_new_arrays(self):
        source = ROOT / 'tools' / 'analyze_v059.py'
        spec = importlib.util.spec_from_file_location('v059_analysis_for_v060', source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        old = [module.predictions(order) for order in (
            ['k10', 'k17', 'k03'], ['k10', 'k03', 'k17'])]
        new = [module.predictions(order) for order in (
            RULE_ORDERS['deep_first'], RULE_ORDERS['shallow_first'])]
        self.assertTrue(all(row['first_terminal'] == row['absolute_second']
                            for row in old))
        self.assertEqual([row['first_terminal'] for row in new], ['k17', 'k03'])
        self.assertEqual([row['absolute_second'] for row in new], ['k03', 'k17'])

    def test_rehashed_schedule_mutation_refused(self):
        p = deepcopy(self.p)
        p['slots'][0]['variant'] = ('shallow_first'
                                    if p['slots'][0]['variant'] == 'deep_first'
                                    else 'deep_first')
        p['plan_sha256'] = digest({k:v for k,v in p.items() if k != 'plan_sha256'})
        with self.assertRaises(ContractError):
            validate_plan(p)

    def test_duplicate_seed_rejected(self):
        ref = reference()
        ref['seeds'][0] = ref['seeds'][1]
        ref['receipt_sha256'] = digest({k:v for k,v in ref.items() if k != 'receipt_sha256'})
        with self.assertRaises(ContractError):
            make_plan(ref)

    def test_nonfinite_duplicate_json_rejected(self):
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}'):
            with self.assertRaises(ContractError):
                strict_json(raw)

    def test_generation_does_not_import_scoring(self):
        import ast
        tree = ast.parse((ROOT / 'terminal_position_v060/requests.py').read_text(encoding='utf-8'))
        modules = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        self.assertFalse(any(any(x in (m or '') for x in ('measure', 'oracle', 'reporting')) for m in modules))


class MeasurementTests(unittest.TestCase):
    def setUp(self):
        self.p = make_plan(reference())
        self.slot = self.p['slots'][0]
        q = strict_json(request_bytes(self.p, self.slot))
        self.problem = strict_json(q['messages'][0]['content'].split('\n\nproblem: ')[1].encode())

    def test_choice_depth_is_not_proof_depth(self):
        for rid, depth, success in [('k03', 1, True), ('k17', 2, False)]:
            m = measure(self.problem, {'final_rule_id': rid}, self.slot)
            self.assertTrue(m['choice_valid'])
            self.assertTrue(m['goal_reachable_choice'])
            self.assertEqual(m['implied_depth'], depth)
            self.assertIs(m['shallow_success'], success)
            self.assertIs(m['instruction_fulfilled'], success)
            for key in ('actual_D', 'D', 'proof_valid', 'strict_valid'):
                self.assertIsNone(m[key])

    def test_overall_position_and_terminal_rank_are_distinct(self):
        slots = {slot['variant']: slot for slot in self.p['slots']
                 if slot['seed'] == self.p['seeds'][0] and slot['repeat'] == 0}
        expected = {
            'deep_first': {'k17': (0, 0), 'k03': (1, 1)},
            'shallow_first': {'k03': (0, 0), 'k17': (1, 1)},
        }
        for variant, choices in expected.items():
            q = strict_json(request_bytes(self.p, slots[variant]))
            problem = strict_json(q['messages'][0]['content'].split('\n\nproblem: ')[1].encode())
            for rid, (position, rank) in choices.items():
                with self.subTest(variant=variant, rid=rid):
                    m = measure(problem, {'final_rule_id': rid}, slots[variant])
                    self.assertEqual(m['selected_rule_position'], position)
                    self.assertEqual(m['terminal_rank'], rank)

    def test_missing_invalid_and_wrong_goal_stay_distinct(self):
        for payload in (None, {}, {'final_rule_id': 5}):
            m = measure(self.problem, payload, self.slot)
            self.assertFalse(m['format_valid'])
            self.assertIsNone(m['shallow_success'])
            self.assertIsNone(m['goal_reachable_choice'])
            self.assertIsNone(m['instruction_fulfilled'])
        for rid in ('k10', 'unknown'):
            m = measure(self.problem, {'final_rule_id': rid}, self.slot)
            self.assertTrue(m['format_valid'])
            self.assertFalse(m['choice_valid'])
            self.assertFalse(m['goal_reachable_choice'])
            self.assertFalse(m['shallow_success'])
            self.assertFalse(m['instruction_fulfilled'])
            self.assertIsNone(m['terminal_rank'])

    def test_partial_summary_has_null_rates(self):
        trials = [{**s, 'observed': False, 'measurement': None, 'role_match': None} for s in self.p['slots']]
        r = summarize(self.p, trials, [], False)
        self.assertIsNone(r['seed_mean_B_minus_A'])
        self.assertIsNone(r['cross_variant']['selected_rule_changed_rate'])
        self.assertTrue(all(v['shallow_rate'] is None for v in r['variants'].values()))
        self.assertEqual(r['cross_variant']['outcomes']['unobserved'], 20)

    def test_within_instability_is_not_cross_condition_difference(self):
        rows = []
        for slot in self.p['slots']:
            q = strict_json(request_bytes(self.p, slot))
            pr = strict_json(q['messages'][0]['content'].split('\n\nproblem: ')[1].encode())
            payload = {'final_rule_id': 'k17' if slot['repeat'] == 0 else 'k03'}
            m = measure(pr, payload, slot)
            rows.append({**slot, 'observed': True, 'measurement': m, 'role_match': match(pr,m,slot)})
        r = summarize(self.p, rows, [], True)
        self.assertEqual(r['cross_variant']['selected_rule_changed_pairs'], 0)
        self.assertEqual(r['repeat_instability']['deep_first']['selected_rule_changed_pairs'], 10)
        self.assertEqual(r['repeat_instability']['shallow_first']['selected_rule_changed_pairs'], 10)
        self.assertEqual(r['seed_mean_B_minus_A'], 0)


if __name__ == '__main__':
    unittest.main()
