"""생산 채점기와 별도 구현된 검증기에도 같은 반례를 적용한다."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from independent_review_v052 import load,Invalid,check,bound_depths
from depth_probe_v053.schema import schema_for
from depth_probe_v053.design import PROBLEMS
from .fixtures import graph_payload

class IndependentChecker(unittest.TestCase):
    def evaluate(self,payload,pid='K01'):
        return check(PROBLEMS[pid],payload,schema_for(None),'explicit','graph_only')
    def test_duplicate_json_keys_rejected(self):
        with self.assertRaises(Invalid):load('{"final_node_id":"a","final_node_id":"b"}')
    def test_nonfinite_json_rejected(self):
        with self.assertRaises(Invalid):load('{"x":NaN}')
    def test_all_valid_paths_and_bounds(self):
        for pid in PROBLEMS:
            for i,d in enumerate(('shallow','deep')):
                m=self.evaluate(graph_payload(PROBLEMS[pid],d),pid)
                self.assertTrue(m['strict_valid']);self.assertEqual(m['D'],bound_depths(PROBLEMS[pid])[i])
    def test_wrong_final_not_repaired(self):
        p=graph_payload(PROBLEMS['K01']);p['final_node_id']='Cc'
        self.assertFalse(self.evaluate(p)['strict_valid'])
    def test_wrong_rule_is_existing_but_invalid(self):
        p=graph_payload(PROBLEMS['K01']);p['nodes'][-1]['atom']='WRONG'
        m=self.evaluate(p);self.assertTrue(m['final_reference_exists']);self.assertFalse(m['strict_valid'])
    def test_cycle_rejected(self):
        p=graph_payload(PROBLEMS['K01']);p['nodes'][-1]['parents']=[p['final_node_id']]
        self.assertFalse(self.evaluate(p)['strict_valid'])
    def test_duplicate_node_rejected(self):
        p=graph_payload(PROBLEMS['K01']);p['nodes'].append(dict(p['nodes'][-1]))
        self.assertFalse(self.evaluate(p)['strict_valid'])
    def test_unrelated_node_rejected(self):
        p=graph_payload(PROBLEMS['K01']);p['nodes'].append({'id':'u','atom':PROBLEMS['K01']['facts'][0],'rule':None,'parents':[]})
        self.assertFalse(self.evaluate(p)['strict_valid'])
