import copy,unittest
from layout_probe_v056.reporting import summarize
from .quick_fixture import plan,trials

def counts(r):return [sum(c['direction_selective_success'] for c in r['layouts'][a]['models'][k]['core_results'].values()) for a in ('split','merged') for k in ('reference','candidate')]
class Reporting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.p=plan()
    def test_all_unobserved_not_neither_failure(self):
        r=summarize(self.p,trials(self.p),[],False)
        for c in r['layout_results'].values():self.assertEqual(c['unobserved_pairs'],10);self.assertEqual(c['neither_success'],0);self.assertIsNone(c['merged_minus_split_rate'])
    def test_unobserved_validity_comparison_null(self):
        r=summarize(self.p,trials(self.p),[],False)
        for c in r['validity_contrasts'].values():self.assertEqual(c['unobserved_pairs'],120);self.assertEqual(c['neither_valid'],0);self.assertIsNone(c['merged_minus_split_validity_rate'])
    def test_only_split_observed_does_not_win(self):
        ts=trials(self.p,'perfect');empty=trials(self.p)
        ts=[a if a['layout']=='split' else b for a,b in zip(ts,empty)];r=summarize(self.p,ts,[],False)
        self.assertTrue(all(c['split_only']==0 and c['unobserved_pairs']==10 for c in r['layout_results'].values()))
    def test_perfect_both_success(self):self.assertEqual(counts(summarize(self.p,trials(self.p,'perfect'),[],True)),[40,40,40,40])
    def test_first_path_is_not_control(self):
        r=summarize(self.p,trials(self.p,'first_branch'),[],True);self.assertEqual(counts(r),[0,0,0,0])
        self.assertTrue(all(c['both_valid']==120 for c in r['validity_contrasts'].values()))
    def test_merged_only_control(self):
        r=summarize(self.p,trials(self.p,'merged_only'),[],True);self.assertEqual(counts(r),[0,0,40,40]);self.assertTrue(all(c['merged_only']==10 for c in r['layout_results'].values()))
    def test_invalid_rule_not_repaired(self):
        ts=trials(self.p,'invalid');self.assertTrue(all(t['measurement']['final_ref_valid'] and not t['measurement']['proof_valid'] and t['measurement']['D'] is None for t in ts))
        self.assertEqual(counts(summarize(self.p,ts,[],True)),[0,0,0,0])
    def test_layout_primary_neutral_denominators(self):
        r=summarize(self.p,trials(self.p,'perfect'),[],True);self.assertEqual((r['primary_directed_assigned'],r['neutral_assigned']),(320,160))
    def test_missing_usage_stays_null(self):
        r=summarize(self.p,trials(self.p),[],False)
        self.assertTrue(all(r['layouts'][a]['models'][k]['unique_execution_usage']['prompt_eval_count'] is None for a in ('split','merged') for k in ('reference','candidate')))
