import copy,unittest
from .quick_fixture import plan,trials
from selection_probe_v057.reporting import summarize
class Reporting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.p=plan()
    def report(self,mode,complete=True):return summarize(self.p,trials(self.p,mode),[],complete)
    def test_perfect_separate_success(self):
        r=self.report('perfect')
        for m in r['models'].values():
            self.assertEqual(m['modes']['graph']['selective_success'],40);self.assertEqual(m['modes']['choice']['selective_success'],40)
    def test_choice_not_full_proof(self):
        for m in self.report('perfect')['models'].values():self.assertIsNone(m['modes']['choice']['full_proof_D_control_success'])
    def test_first_path_not_selective(self):
        for m in self.report('first_branch')['models'].values():
            for x in m['modes'].values():self.assertEqual(x['selective_success'],0);self.assertEqual(x['task_valid'],120)
    def test_choice_only_preserved(self):
        for m in self.report('choice_only')['models'].values():self.assertEqual(m['task_contrast']['choice_only'],40);self.assertEqual(m['modes']['graph']['selective_success'],0)
    def test_graph_only_preserved(self):
        for m in self.report('graph_only')['models'].values():self.assertEqual(m['task_contrast']['graph_only'],40);self.assertEqual(m['modes']['choice']['selective_success'],0)
    def test_unobserved_not_neither(self):
        for m in self.report('unobserved',False)['models'].values():self.assertEqual(m['task_contrast']['neither'],0);self.assertEqual(m['task_contrast']['unobserved'],40);self.assertIsNone(m['choice_minus_graph_rate'])
    def test_missing_one_mode_not_win(self):
        ts=trials(self.p);blank=trials(self.p,'unobserved');ts=[b if s['mode']=='choice' else t for s,t,b in zip(self.p['slots'],ts,blank)]
        r=summarize(self.p,ts,[],False)
        for m in r['models'].values():self.assertEqual(m['task_contrast']['graph_only'],0);self.assertEqual(m['task_contrast']['unobserved'],40)
    def test_invalid_observed_is_neither(self):
        for m in self.report('invalid')['models'].values():self.assertEqual(m['task_contrast']['neither'],40)
    def test_all_neutral_records_preserved(self):self.assertEqual(len(self.report('perfect')['neutral_comparisons']),160)
    def test_robust_80_groups(self):self.assertEqual(len(self.report('perfect')['robust']),80)
    def test_no_observation_multiplication(self):
        r=self.report('perfect');self.assertEqual(sum(x['observed_calls'] for m in r['models'].values() for x in m['modes'].values()),480)
    def test_incomplete_success_rate_null(self):
        for m in self.report('perfect',False)['models'].values():
            for x in m['modes'].values():self.assertIsNone(x['selective_rate'])
