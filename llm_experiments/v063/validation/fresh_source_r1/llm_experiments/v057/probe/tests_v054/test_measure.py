"""기존 참조 진단 결함과 D 제어 오판을 반례로 검사한다."""
import copy
import unittest
from order_probe_v054.design import PROBLEMS
from order_probe_v054.measure import measure,final_reference_exists,role_match,depth_bounds
from .fixtures import graph_payload

class Measurement(unittest.TestCase):
    def test_all_four_valid_paths(self):
        for pid in PROBLEMS:
            for direction in ('shallow','deep'):
                with self.subTest(problem=pid,direction=direction):
                    m=measure(PROBLEMS[pid],graph_payload(PROBLEMS[pid],direction))
                    self.assertTrue(m['strict_valid']);self.assertTrue(role_match(m,{'D':direction},PROBLEMS[pid]))
    def test_wrong_direction_not_success(self):
        p=PROBLEMS['K01'];m=measure(p,graph_payload(p,'deep'))
        self.assertTrue(m['strict_valid']);self.assertFalse(role_match(m,{'D':'shallow'},p))
    def test_role_label_does_not_change_measurement(self):
        p=PROBLEMS['K01'];payload=graph_payload(p,'deep')
        self.assertEqual(measure(p,payload,{'direction':'shallow'}),measure(p,payload,{'direction':'deep'}))
    def test_unparsed_is_not_false_proof(self):
        m=measure(PROBLEMS['K01'],None)
        self.assertFalse(m['format_valid']);self.assertIsNone(m['proof_valid']);self.assertIsNone(m['final_ref_valid'])
    def test_unsupported_goal_still_has_existing_reference(self):
        p=PROBLEMS['K01'];payload={'nodes':[{'id':'n','atom':p['goal'],'rule':None,'parents':[]}],'final_node_id':'n'}
        m=measure(p,payload);self.assertTrue(m['final_ref_valid']);self.assertFalse(m['proof_valid'])
    def test_invalid_rule_conclusion_still_has_reference(self):
        p=PROBLEMS['K01'];payload=graph_payload(p);payload['nodes'][-1]['atom']='WRONG'
        m=measure(p,payload);self.assertTrue(m['final_ref_valid']);self.assertFalse(m['strict_valid'])
    def test_missing_parent_still_has_reference(self):
        p=PROBLEMS['K01'];payload=graph_payload(p);payload['nodes'][-1]['parents']=['missing']
        m=measure(p,payload);self.assertTrue(m['final_ref_valid']);self.assertFalse(m['proof_valid'])
    def test_absent_final_reference_rejected(self):
        p=PROBLEMS['K01'];payload=graph_payload(p);payload['final_node_id']='absent'
        m=measure(p,payload);self.assertFalse(m['final_ref_valid']);self.assertFalse(m['strict_valid'])
    def test_duplicate_final_id_is_ambiguous(self):
        p=PROBLEMS['K01'];payload=graph_payload(p);payload['nodes'].append(copy.deepcopy(payload['nodes'][-1]))
        m=measure(p,payload);self.assertFalse(m['final_ref_valid']);self.assertFalse(m['strict_valid'])
    def test_bare_goal_not_auto_corrected(self):
        p=PROBLEMS['K01'];payload=graph_payload(p);payload['final_node_id']=p['goal'];before=copy.deepcopy(payload)
        self.assertFalse(measure(p,payload)['strict_valid']);self.assertEqual(payload,before)
    def test_alternative_unused_nodes_rejected(self):
        p=PROBLEMS['K01'];payload=graph_payload(p,'deep');payload['nodes'].append({'id':'extra','atom':p['facts'][0],'rule':None,'parents':[]})
        self.assertFalse(measure(p,payload)['proof_valid'])
    def test_cycle_rejected(self):
        p=PROBLEMS['K01'];payload=graph_payload(p);payload['nodes'][-1]['parents']=[payload['final_node_id']]
        self.assertFalse(measure(p,payload)['proof_valid'])
    def test_premise_omission_rejected(self):
        p=PROBLEMS['T02'];payload=graph_payload(p);payload['nodes'][-1]['parents'].pop()
        self.assertFalse(measure(p,payload)['proof_valid'])
    def test_extra_field_not_allowed(self):
        p=PROBLEMS['K01'];payload=graph_payload(p);payload['D']=1
        m=measure(p,payload);self.assertTrue(m['proof_valid']);self.assertFalse(m['strict_valid'])
    def test_graph_only_A_M_not_measured(self):
        p=PROBLEMS['K01'];m=measure(p,graph_payload(p));self.assertIsNone(m['A']);self.assertIsNone(m['M'])
    def test_actual_depth_not_total_nodes(self):
        p=PROBLEMS['T02'];m=measure(p,graph_payload(p,'deep'));self.assertEqual(m['D'],4);self.assertEqual(m['node_count'],6)
    def test_bounds_are_recomputed(self):
        self.assertEqual(depth_bounds(PROBLEMS['K01']),(1,2));self.assertEqual(depth_bounds(PROBLEMS['T02']),(1,4))
