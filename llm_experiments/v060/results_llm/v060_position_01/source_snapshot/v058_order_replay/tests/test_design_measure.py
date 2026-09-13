from copy import deepcopy
import ast
from pathlib import Path
import unittest
try:
    from .fixtures import plan, reference, ROOT
except ImportError:
    from fixtures import plan, reference, ROOT
from order_replay_v058.contracts import ContractError, digest, unb64
from order_replay_v058.plan import make_plan, validate_plan
from order_replay_v058.requests import request_bytes
from order_replay_v058.measure import measure
from order_replay_v058.design import PROBLEMS


class DesignMeasureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = plan()

    def test_schedule_80_calls_20_blocks_40_metadata(self):
        p = self.plan
        self.assertEqual(len(p['slots']), 80)
        self.assertEqual(len(p['actions']), 120)
        self.assertEqual(sum(a['kind'] == 'metadata' for a in p['actions']), 40)
        self.assertEqual(len({s['id'] for s in p['slots']}), 80)
        for block in range(20):
            slots = [s for s in p['slots'] if s['block'] == block]
            self.assertEqual(len(slots), 4)
            self.assertEqual(len({s['seed'] for s in slots}), 1)
            self.assertEqual(len({s['model_key'] for s in slots}), 1)
            for sequence, modes in [('graph_choice', ['graph', 'choice']), ('choice_graph', ['choice', 'graph'])]:
                group = [s for s in slots if s['sequence'] == sequence]
                self.assertEqual([s['mode'] for s in group], modes)
                self.assertEqual([s['position_in_group'] for s in group], [0, 1])

    def test_same_seed_gets_both_sequences_and_history_is_explicit(self):
        p = self.plan
        for i, seed in enumerate(p['seeds']):
            slots = [s for s in p['slots'] if s['seed'] == seed]
            self.assertEqual(slots[0]['model_key'], 'reference' if i % 2 == 0 else 'candidate')
            self.assertEqual(slots[0]['sequence'], 'graph_choice' if i % 2 == 0 else 'choice_graph')
        self.assertIsNone(p['slots'][0]['previous_call_id'])
        for previous, current in zip(p['slots'], p['slots'][1:]):
            self.assertEqual(current['previous_call_id'], previous['id'])
            self.assertEqual(current['previous_call_mode'], previous['mode'])

    def test_each_source_request_reused_twice_without_transformation(self):
        p = self.plan
        for source in p['reference']['slots']:
            copies = [s for s in p['slots'] if s['reference_slot_id'] == source['id']]
            self.assertEqual(len(copies), 2)
            frozen = unb64(p['reference']['request_bank'][source['id']])
            for slot in copies:
                self.assertEqual(request_bytes(p, slot), frozen)

    def test_request_module_has_no_scoring_imports(self):
        tree = ast.parse((ROOT / 'order_replay_v058' / 'requests.py').read_text(encoding='utf-8'))
        imports = [n.module or '' for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        self.assertFalse(any(any(word in name for word in ['measure', 'audit', 'reporting']) for name in imports))

    def test_omission_duplicate_and_schedule_tamper_rejected_even_rehashed(self):
        for mutate in [lambda p: p['slots'].pop(),
                       lambda p: p['slots'].__setitem__(1, deepcopy(p['slots'][0])),
                       lambda p: p['actions'].reverse(),
                       lambda p: p['slots'][0].__setitem__('previous_call_id', 'invented')]:
            p = deepcopy(self.plan)
            mutate(p)
            p['plan_sha256'] = digest({k: v for k, v in p.items() if k != 'plan_sha256'})
            with self.assertRaises(ContractError):
                validate_plan(p)

    def test_missing_reference_request_rejected(self):
        ref = reference()
        ref['request_bank'].pop(next(iter(ref['request_bank'])))
        ref['receipt_sha256'] = digest({k: v for k, v in ref.items() if k != 'receipt_sha256'})
        with self.assertRaises(ContractError):
            make_plan(ref)

    def test_choice_is_not_actual_proof(self):
        m = measure(PROBLEMS['K01'], {'final_rule_id': 'k03'}, {'mode': 'choice', 'direction': 'shallow'})
        self.assertTrue(m['shallow_success'])
        self.assertEqual(m['implied_depth'], 1)
        for key in ['proof_valid', 'strict_valid', 'D']:
            self.assertIsNone(m[key])

    def test_invalid_choices_not_repaired(self):
        for rid in ['K03', ' k03 ', 'Cc', 'k10', 'unknown']:
            m = measure(PROBLEMS['K01'], {'final_rule_id': rid}, {'mode': 'choice', 'direction': 'shallow'})
            self.assertFalse(m['task_valid'])
            self.assertFalse(m['shallow_success'])

    def test_format_failure_remains_unmeasured(self):
        for payload in [None, {}, {'final_rule_id': None}, {'final_rule_id': 'k03', 'extra': 1}]:
            m = measure(PROBLEMS['K01'], payload, {'mode': 'choice', 'direction': 'shallow'})
            self.assertIsNone(m['task_valid'])
            self.assertIsNone(m['shallow_success'])

    def test_graph_duplicate_parents_missing_fact_bad_final(self):
        base = {'nodes': [{'id': 'a', 'atom': 'Ca', 'rule': None, 'parents': []},
                          {'id': 'c', 'atom': 'Cc', 'rule': 'k03', 'parents': ['a']}], 'final_node_id': 'c'}
        for mutate in [lambda x: x['nodes'][-1].__setitem__('parents', ['a', 'a']),
                       lambda x: x['nodes'].pop(0),
                       lambda x: x.__setitem__('final_node_id', 'Cc')]:
            payload = deepcopy(base)
            mutate(payload)
            m = measure(PROBLEMS['K01'], payload, {'mode': 'graph', 'direction': 'shallow'})
            self.assertFalse(m['task_valid'])
            self.assertIsNone(m['D'])


if __name__ == '__main__':
    unittest.main()
