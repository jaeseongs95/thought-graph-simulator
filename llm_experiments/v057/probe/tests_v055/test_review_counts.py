"""재검토: 관측되지 않은 모델 비교를 두 모델의 실패로 세지 않는다."""
import unittest
from unittest.mock import patch
from model_probe_v055.reporting import summarize
from model_probe_v055.design import PROBLEMS, ARMS

class MissingObservations(unittest.TestCase):
    def report(self, q_observed=False, g_observed=False, q_success=False, g_success=False, complete=False):
        seeds=list(range(10))
        def one(observed,success):
            return {'pairs':[{'problem_id':pid,'arm':arm,'seed':s,'both_observed':observed,
                 'direction_selective_success':success,'both_valid':observed}
                 for pid in PROBLEMS for arm in ARMS for s in seeds]}
        plan={'seeds':seeds,'baseline':{'config':{}},'policy':{},'identities':{
            'reference':{'model':'q'},'candidate':{'model':'g'}}}
        with patch('model_probe_v055.reporting.summarize_order',side_effect=[one(q_observed,q_success),one(g_observed,g_success)]):
            return summarize(plan,[],[],complete)
    def test_unexecuted_not_neither_success(self):
        for c in self.report()['cross_model_results'].values():
            self.assertEqual(c['neither_success'],0)
            self.assertEqual(c['unobserved_pairs'],10)
            self.assertIsNone(c['candidate_minus_reference_rate'])
    def test_reference_observed_not_reference_only(self):
        for c in self.report(True,False,True,False)['cross_model_results'].values():
            self.assertEqual(c['reference_only'],0)
            self.assertEqual(c['unobserved_pairs'],10)
    def test_both_observed_failure_retained(self):
        for c in self.report(True,True,False,False,True)['cross_model_results'].values():
            self.assertEqual(c['neither_success'],10)
            self.assertEqual(c['unobserved_pairs'],0)
            self.assertEqual(c['candidate_minus_reference_rate'],0)
    def test_candidate_improvement_retained(self):
        for c in self.report(True,True,False,True,True)['cross_model_results'].values():
            self.assertEqual(c['candidate_only'],10)
            self.assertEqual(c['unobserved_pairs'],0)
            self.assertEqual(c['candidate_minus_reference_rate'],1)
