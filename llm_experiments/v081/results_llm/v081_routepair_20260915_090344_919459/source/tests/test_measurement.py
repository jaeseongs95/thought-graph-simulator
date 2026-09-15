"""동일 목표·실제 graph·의존 깊이·규칙 수를 서로 혼동하지 않는 측정 시험."""
from copy import deepcopy
import unittest
import core081 as core
import calibrate081 as calibration
import bootstrap
import measure
from audit_graph import _semantic


class Measurement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec=core.spec()
        cls.calibrated=calibration.calibration()
        cls.problem=cls.spec['problems'][0]
        cls.route=cls.spec['reference_plans']['H01']['reference_long']
        cls.graph=calibration.proof(cls.problem,cls.route)

    def test_all_offline_calibrations(self):
        self.assertEqual((self.calibrated['passed'],self.calibrated['failed']),(87,0))

    def test_equal_rule_count_different_D(self):
        for pid in ('H01','H02'):
            structures=[s for s in self.calibrated['structures'] if s['problem']==pid]
            self.assertEqual(structures[0]['W'],structures[1]['W'])
            self.assertLess(structures[0]['D'],structures[1]['D'])

    def test_inverted_rule_count_D(self):
        for pid in ('H03','H04'):
            structures=[s for s in self.calibrated['structures'] if s['problem']==pid]
            self.assertGreater(structures[0]['W'],structures[1]['W'])
            self.assertLess(structures[0]['D'],structures[1]['D'])

    def test_macro_unit_dependence_is_not_live_model_score(self):
        e=self.calibrated['macro_example']
        self.assertEqual((e['raw_primitive_D'],e['raw_macro_D'],e['expanded_in_fixed_primitive_system_D']),(2,1,2))
        self.assertEqual(self.calibrated['provenance'],'synthetic_offline_no_model_calls')

    def invalid(self,graph):
        a=measure.assess(self.problem,graph);b=_semantic(self.problem,graph)
        self.assertEqual(a,b);self.assertFalse(a['strict_valid']);self.assertIsNone(a['actual_D'])

    def test_wrong_parent_same_count(self):
        g=deepcopy(self.graph);g['nodes'][-1]['parents']=[g['nodes'][0]['id']];self.invalid(g)

    def test_missing_parent(self):
        g=deepcopy(self.graph);g['nodes'][-1]['parents']=[];self.invalid(g)

    def test_nonexistent_parent(self):
        g=deepcopy(self.graph);g['nodes'][-1]['parents']=['missing'];self.invalid(g)

    def test_duplicate_id(self):
        g=deepcopy(self.graph);g['nodes'][-1]['id']=g['nodes'][0]['id'];g['final_node_id']=g['nodes'][0]['id'];self.invalid(g)

    def test_cycle(self):
        g=deepcopy(self.graph);g['nodes'][-1]['parents']=[g['nodes'][-1]['id']];self.invalid(g)

    def test_wrong_final(self):
        g=deepcopy(self.graph);g['final_node_id']=g['nodes'][0]['id'];self.invalid(g)

    def test_unused_padding_not_depth(self):
        g=deepcopy(self.graph);g['nodes'].insert(0,{'id':'pad','atom':self.problem['facts'][0],'rule':None,'parents':[]});self.invalid(g)

    def test_unknown_rule(self):
        g=deepcopy(self.graph);g['nodes'][-1]['rule']='invented';self.invalid(g)

    def test_wrong_conclusion(self):
        g=deepcopy(self.graph);g['nodes'][-1]['atom']='invented';self.invalid(g)

    def test_minimum_problem_depth_not_forced_on_all_proofs(self):
        p=self.problem
        paths=self.spec['reference_plans']['H01']
        short=measure.assess(p,calibration.proof(p,paths['reference_short']))
        long=measure.assess(p,calibration.proof(p,paths['reference_long']))
        self.assertTrue(short['strict_valid'] and long['strict_valid'])
        self.assertEqual((short['actual_D'],long['actual_D']),(2,3))


if __name__=='__main__':
    unittest.main()
