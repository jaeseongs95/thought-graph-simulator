"""동일 반례를 원본 r2와 수정된 v053 진단에 적용한다."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from depth_probe_v053.design import PROBLEMS
from tests_v053.fixtures import graph_payload
if sys.argv[1]=='old':
    from adm_diagnostic_v052.measure import measure as old
    def measure(p,v):return old(p,v,{'task':'graph_only','arm':'explicit'})
else:
    from depth_probe_v053.measure import measure
class FinalReferenceContract(unittest.TestCase):
    def test_unsupported_fact(self):
        p=PROBLEMS['K01'];v={'nodes':[{'id':'n','atom':p['goal'],'rule':None,'parents':[]}],'final_node_id':'n'}
        m=measure(p,v);self.assertFalse(m['proof_valid']);self.assertTrue(m['final_ref_valid'])
    def test_wrong_rule_conclusion(self):
        p=PROBLEMS['K01'];v=graph_payload(p);v['nodes'][-1]['atom']='WRONG'
        m=measure(p,v);self.assertFalse(m['proof_valid']);self.assertTrue(m['final_ref_valid'])
    def test_missing_parent(self):
        p=PROBLEMS['K01'];v=graph_payload(p);v['nodes'][-1]['parents']=['missing']
        m=measure(p,v);self.assertFalse(m['proof_valid']);self.assertTrue(m['final_ref_valid'])
result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(FinalReferenceContract))
raise SystemExit(not result.wasSuccessful())
