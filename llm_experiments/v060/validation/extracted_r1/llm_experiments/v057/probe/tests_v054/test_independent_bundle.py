"""독립 계산기에서도 순서 효과와 D 제어를 별도로 검증한다."""
import copy, sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from independent_verify_v054 import verify, payload_from
from forensic_replay_v053 import graph, possible_depths, load, Invalid
from order_probe_v054.evidence import bundle_run
from order_probe_v054.design import PROBLEMS
from .fixtures import copied, executed, graph_payload

class IndependentBundle(unittest.TestCase):
    def test_perfect_bundle_independently_replayed(self):
        with copied() as (root,p,run,base):
            z=root/'bundle.zip';bundle_run(p,run,z);r=verify(z)
            self.assertEqual(r['discrepancies'],[]);self.assertEqual(r['semantic_fields_compared'],860)
            self.assertEqual(r['selective_pairs'],40);self.assertEqual(r['order_robust_seed_groups'],20)
    def test_first_branch_is_not_D_success_in_independent_checker(self):
        with executed('first_branch') as (root,p,run,report,state):
            z=root/'bundle.zip';bundle_run(p,run,z);r=verify(z)
            self.assertEqual(r['discrepancies'],[]);self.assertEqual(r['order_changed_pairs'],60)
            self.assertEqual(r['selective_pairs'],0);self.assertEqual(r['order_robust_seed_groups'],0)
    def test_unknown_rules_remain_incorrect_not_missing_reference(self):
        for rid in ('k1','k1_7'):
            p=graph_payload(PROBLEMS['K01'],'deep');p['nodes'][-1]['rule']=rid;m=graph(PROBLEMS['K01'],p)
            self.assertTrue(m['final_ref_valid']);self.assertFalse(m['proof_valid']);self.assertIsNone(m['D'])
    def test_independent_all_depths_not_requested_depth(self):
        self.assertEqual(possible_depths(PROBLEMS['K01']),[1,2]);self.assertEqual(possible_depths(PROBLEMS['T02']),[1,4])
    def test_independent_checker_rejects_unused_valid_nodes(self):
        p=graph_payload(PROBLEMS['K01'],'deep');p['nodes'].append({'id':'unused','atom':'Ca','rule':None,'parents':[]})
        self.assertFalse(graph(PROBLEMS['K01'],p)['proof_valid'])
    def test_independent_duplicate_keys_rejected(self):
        with self.assertRaises(Invalid):load('{"x":1,"x":2}')
    def test_truncated_response_is_unmeasured(self):
        import json
        raw=json.dumps({'model':'test','done':True,'done_reason':'length','message':{'role':'assistant','content':'{}'}}).encode()
        self.assertIsNone(payload_from(raw,'test'))
    def test_wrong_nonempty_thinking_not_hidden(self):
        import json
        raw=json.dumps({'model':'test','done':True,'done_reason':'stop','message':{'role':'assistant','thinking':'hidden','content':'{}'}}).encode()
        self.assertIsNone(payload_from(raw,'test'))
