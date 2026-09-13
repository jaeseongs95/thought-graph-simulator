"""순서 효과를 방향 제어로 바꾸는 오판과 부분 성공의 확대를 거부한다."""
import copy, unittest
from order_probe_v054.reporting import summarize
from order_probe_v054.measure import measure
from order_probe_v054.design import PROBLEMS
from .fixtures import shared, executed, graph_payload

class OrderControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.base=shared()
    def test_first_branch_changes_all_sixty_order_pairs_but_controls_no_D_pairs(self):
        with executed('first_branch') as (root,plan,run,r,state):
            self.assertTrue(r['data_complete']);self.assertEqual(r['inference_calls'],120)
            self.assertEqual(sum(x['depth_changed'] for x in r['order_results'].values()),60)
            self.assertEqual(sum(x['direction_selective_success'] for x in r['core_results'].values()),0)
            self.assertEqual(sum(x['both_orders_selective_success'] for x in r['robust_results'].values()),0)
    def test_control_in_only_one_order_is_not_robust(self):
        with executed('only_original_control') as (root,plan,run,r,state):
            self.assertEqual(sum(x['direction_selective_success'] for x in r['core_results'].values()),20)
            self.assertEqual(sum(x['both_orders_selective_success'] for x in r['robust_results'].values()),0)
    def test_inverse_direction_is_never_success(self):
        with executed('inverse_direction') as (root,plan,run,r,state):
            self.assertEqual(sum(x['both_valid_pairs'] for x in r['core_results'].values()),40)
            self.assertEqual(sum(x['direction_selective_success'] for x in r['core_results'].values()),0)
    def test_misspelled_rule_has_reference_but_no_proof(self):
        with executed('misspelled_rule') as (root,plan,run,r,state):
            self.assertTrue(all(x['measurement']['final_ref_valid'] is True for x in r['trials']))
            self.assertTrue(all(x['measurement']['proof_valid'] is False for x in r['trials']))
            self.assertTrue(all(x['depth_changed'] is None for x in r['order_contrasts']))
    def test_actual_typo_k1_and_k1_7_are_not_repaired(self):
        for wrong in ('k1','k1_7'):
            payload=graph_payload(PROBLEMS['K01'],'deep');payload['nodes'][-1]['rule']=wrong;before=copy.deepcopy(payload)
            m=measure(PROBLEMS['K01'],payload);self.assertFalse(m['proof_valid']);self.assertIsNone(m['D'])
            self.assertTrue(m['final_ref_valid']);self.assertEqual(payload,before)
    def test_no_independent_sample_inflation(self):
        r=self.base['report'];self.assertEqual(r['unique_execution_usage']['calls'],120)
        self.assertEqual(len(r['pairs']),40);self.assertEqual(len(r['order_contrasts']),60);self.assertEqual(len(r['robust_pairs']),20)
    def test_unmeasured_order_contrast_is_not_unchanged(self):
        r=self.base['report'];rows=copy.deepcopy(r['trials']);rows[0]['measurement']=None;rows[0]['observed']=False;rows[0]['role_match']=None
        changed=summarize(self.base['plan'],rows,r['calls'],{},False)
        self.assertEqual(sum(x['depth_changed'] is None for x in changed['order_contrasts']),1)
        self.assertTrue(all(x['rate_over_assigned'] is None for x in changed['robust_results'].values()))
    def test_no_order_effect_for_perfect_direction_follower(self):
        self.assertEqual(sum(x['depth_changed'] for x in self.base['report']['order_results'].values()),0)
