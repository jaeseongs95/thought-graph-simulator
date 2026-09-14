"""성공처럼 보일 수 있는 대체 행동을 실제로 탈락시키는 합성 검사."""
import unittest
from copy import deepcopy
import core080 as core
import report080,audit080
from fixtures080 import plan,response_set


class Policies(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p=plan();cls.summaries={}
        for policy in ['first','id0','count_only','depth_only','reverse']:
            r,w,q=response_set(cls.p,policy)
            a=report080.summarize(cls.p,r,w,'complete');b=audit080.independent_summary(cls.p,r,w,'complete')
            if a!=b:raise AssertionError(policy+' independent mismatch')
            cls.summaries[policy]=a
    def test_first_position_has_zero_D_pairs(self):self.assertEqual(self.summaries['first']['totals']['D']['end_to_end_pairs']['successes'],0)
    def test_fixed_ID_has_zero_D_pairs(self):self.assertEqual(self.summaries['id0']['totals']['D']['end_to_end_pairs']['successes'],0)
    def test_position_and_ID_are_distinguished(self):
        self.assertEqual(self.summaries['first']['position_id_diagnostic'],{'observed_choices':96,'first_position':96,'route_0_id':48})
        self.assertEqual(self.summaries['id0']['position_id_diagnostic'],{'observed_choices':96,'first_position':48,'route_0_id':96})
    def test_counting_cannot_pass_D_inverted_cases(self):
        rows=[r for r in self.summaries['count_only']['trials'] if r['arm']=='model' and r['metric']=='D' and r['problem_id'] in ('H03','H04')]
        self.assertTrue(all(r['generator_success'] is True and r['metric_end_to_end'] is False for r in rows))
    def test_correct_counting_is_not_D_success(self):
        s=self.summaries['count_only'];self.assertEqual(s['totals']['W']['metric_end_to_end']['successes'],32)
        self.assertEqual(s['totals']['D']['end_to_end_pairs']['successes'],0)
    def test_depth_only_cannot_pass_metric_discrimination(self):
        s=self.summaries['depth_only'];self.assertEqual(s['totals']['D']['metric_end_to_end']['successes'],64)
        self.assertEqual(s['totals']['W']['metric_end_to_end']['successes'],0)
        self.assertFalse(any(x['all_four_selections_correct'] for x in s['metric_discrimination']))
    def test_valid_reversed_graphs_preserved(self):
        s=self.summaries['reverse'];self.assertEqual(sum(p['valid_graph_direction']=='reversed' for p in s['pairs']),48)
        self.assertEqual(s['totals']['D']['generator_success']['successes'],64)
        self.assertEqual(s['totals']['D']['metric_end_to_end']['successes'],0)
    def test_same_direction_flip_alone_is_insufficient(self):
        p=self.p;r,w,_=response_set(p,'reverse')
        s=report080.summarize(p,r,w,'complete')
        self.assertTrue(all(c['opposite_choices_for_both_directions'] for c in s['metric_discrimination']))
        self.assertFalse(any(c['all_four_selections_correct'] for c in s['metric_discrimination']))

if __name__=='__main__':unittest.main()
