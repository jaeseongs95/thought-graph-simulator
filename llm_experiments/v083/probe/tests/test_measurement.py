"""graph·집계 정상/반례와 두 의미 검산 구현의 차등 검사."""
from pathlib import Path
from copy import deepcopy
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core083 as c,report083 as r,audit083 as a,calibrate083 as cal
from fixtures083 import plan,response_set

class Measurement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.p=plan()
    def run_policy(self,policy,transform=None):
        rec,raw,_=response_set(self.p,policy,transform)
        left=r.summarize(self.p,rec,raw,'complete');right=a.independent_summary(self.p,rec,raw,'complete')
        self.assertTrue(c.exact(left,right));self.assertTrue(r.render(left));return left,rec,raw
    def test_calibration_87(self):self.assertEqual(cal.calibration()['passed'],87)
    def test_oracle_policy(self):
        s,_,_=self.run_policy('oracle')
        for v,g in s['groups'].items():
            self.assertEqual(g['totals']['D']['selection_pairs']['successes'],32)
            self.assertEqual(g['totals']['W']['selection_pairs']['successes'],16)
            self.assertEqual(g['totals']['W']['metric_end_to_end']['assigned'],0)
        self.assertEqual(s['reference']['successes'],16)
    def test_reported_value_policy_detects_reversed_control(self):
        s,_,_=self.run_policy('reported')
        self.assertEqual(s['groups']['swapped_values']['totals']['D']['selection_success']['successes'],0)
        self.assertEqual(s['groups']['swapped_values']['totals']['D']['follows_supplied_extreme']['successes'],64)
        self.assertEqual(s['hypothesis_comparisons']['H3_value_swap']['by_metric']['D']['changed_path']['successes'],64)
        self.assertEqual(s['hypothesis_comparisons']['H3_value_swap']['by_metric']['W']['both_follow_supplied_extreme']['successes'],32)
    def test_first_position_not_depth_control(self):
        s,_,_=self.run_policy('first')
        for g in s['groups'].values():
            self.assertEqual(g['totals']['D']['selection_success']['successes'],32)
            self.assertEqual(g['totals']['D']['selection_pairs']['successes'],0)
        self.assertEqual(s['hypothesis_comparisons']['H3_value_swap']['by_metric']['D']['changed_path']['successes'],0)
    def test_fixed_id_not_depth_control(self):
        s,_,_=self.run_policy('id0')
        for g in s['groups'].values():self.assertEqual(g['totals']['D']['selection_pairs']['successes'],0)
    def test_reverse_not_counted_as_control_success(self):
        s,_,_=self.run_policy('reverse')
        for name in ('candidate_id','correct_full','correct_values'):
            self.assertEqual(s['groups'][name]['totals']['D']['generator_success']['successes'],64)
            self.assertEqual(s['groups'][name]['totals']['D']['metric_end_to_end']['successes'],0)
            self.assertTrue(all(p['valid_graph_direction']=='reversed' for p in s['groups'][name]['pairs'] if p['metric']=='D'))
    def test_W_only_does_not_satisfy_D(self):
        s,_,_=self.run_policy('count_only')
        for v in s['groups']:
            rows=[x for x in s['trials'] if x['selector_variant']==v and x['metric']=='D' and x['problem_id'] in ('H03','H04')]
            self.assertFalse(any(x['selection_success'] for x in rows))
    def test_D_only_does_not_satisfy_W(self):
        s,_,_=self.run_policy('depth_only')
        for g in s['groups'].values():self.assertEqual(g['totals']['W']['selection_success']['successes'],0)
    def test_support_improves_synthetic_fixture(self):
        s,_,_=self.run_policy({'candidate_id':'first','correct_full':'oracle','correct_values':'oracle','swapped_values':'reported'})
        delta=s['hypothesis_comparisons']['H1_accuracy_support']['by_metric']['D']['selection_pairs']
        self.assertEqual(delta['right_only'],32);self.assertEqual(delta['left_only'],0)
    def test_support_worsens_synthetic_fixture(self):
        s,_,_=self.run_policy({'candidate_id':'oracle','correct_full':'first','correct_values':'first','swapped_values':'first'})
        delta=s['hypothesis_comparisons']['H1_accuracy_support']['by_metric']['D']['selection_pairs']
        self.assertEqual(delta['left_only'],32);self.assertEqual(delta['right_only'],0)
    def test_invalid_select_is_not_filled(self):
        t=next(t for t in self.p['trials'] if t['selector_variant']=='correct_values' and t['generate'])
        def mutate(op,body,raw):
            if op['id']==t['selection_slot_id']:
                obj=c.load(raw);obj['message']['content']='{"candidate_id":"absent"}';return c.wire(obj)
            return raw
        s,_,_=self.run_policy('oracle',mutate);row=next(r for r in s['trials'] if r['trial_id']==t['id'])
        self.assertFalse(row['selection_success']);self.assertFalse(row['metric_end_to_end'])
        self.assertIsNone(row['generator_success']);self.assertIsNone(row['actual_D'])
    def test_bad_graph_not_repaired(self):
        target=next(op['id'] for op in self.p['slots'] if op['stage']=='rule')
        def mutate(op,body,raw):
            if op['id']==target:
                x=c.load(raw);v=c.load(x['message']['content']);v['node']['parents']=[];x['message']['content']=c.wire(v).decode();return c.wire(x)
            return raw
        s,_,_=self.run_policy('oracle',mutate)
        row=next(r for r in s['trials'] if target.startswith(r['trial_id']+'_'))
        self.assertFalse(row['generator_success']);self.assertIsNone(row['actual_D'])
    def test_empty_partial_is_not_all_wrong(self):
        s=r.summarize(self.p,{}, {},'crashed');other=a.independent_summary(self.p,{}, {},'crashed');self.assertTrue(c.exact(s,other))
        self.assertEqual(s['groups']['candidate_id']['totals']['D']['selection_success']['unmeasured'],64)
        self.assertEqual(s['groups']['candidate_id']['totals']['D']['selection_success']['failures'],0)
    def test_one_arm_unobserved_not_other_arm_win(self):
        rec,raw,_=response_set(self.p)
        drop={op['id'] for op in self.p['slots'] if next(t for t in self.p['trials'] if t['id']==op['trial_id'])['selector_variant']=='correct_full'}
        rec={k:v for k,v in rec.items() if k not in drop};raw={k:v for k,v in raw.items() if k not in drop}
        s=r.summarize(self.p,rec,raw,'crashed');self.assertTrue(c.exact(s,a.independent_summary(self.p,rec,raw,'crashed')))
        m=s['hypothesis_comparisons']['H1_accuracy_support']['by_metric']['D']['selection']
        self.assertEqual((m['not_comparable'],m['left_only']),(64,0))
    def test_not_scheduled_is_not_unobserved(self):
        s,_,_=self.run_policy('oracle')
        rows=[r for r in s['trials'] if not r['generation_scheduled']]
        self.assertEqual(len(rows),192)
        for row in rows:
            self.assertEqual(row['generator_status'],'not_scheduled_by_design');self.assertIsNone(row['metric_end_to_end'])
        text=r.render(s);self.assertIn('배정 없음',text)
    def test_missing_usage_is_not_zero(self):
        opid=self.p['slots'][0]['id']
        def mutate(op,body,raw):
            if op['id']==opid:
                v=c.load(raw);v.pop('eval_count');return c.wire(v)
            return raw
        s,_,_=self.run_policy('oracle',mutate)
        self.assertEqual(s['usage']['eval_count']['missing'],1)
    def test_180_graph_differentials(self):
        import bootstrap,measure
        from audit_graph import _semantic
        cases=0
        for p in self.p['protocol']['problems']:
            for ids in self.p['protocol']['reference_plans'][p['id']].values():
                good=cal.proof(p,ids)
                changes=[lambda g:g,lambda g:g.update(final_node_id='absent'),lambda g:g['nodes'][-1].update(parents=[]),
                    lambda g:g['nodes'][-1].update(atom='wrong'),lambda g:g['nodes'][-1].update(rule='absent'),
                    lambda g:g['nodes'][-1].update(parents=['absent']),lambda g:g['nodes'][-1].update(parents=[g['nodes'][-1]['id']]),
                    lambda g:g['nodes'][-1].update(id=g['nodes'][0]['id']),lambda g:g['nodes'].append(deepcopy(g['nodes'][0])),
                    lambda g:g['nodes'][0].update(rule='absent'),lambda g:g['nodes'][0].update(parents=[g['nodes'][-1]['id']]),
                    lambda g:g['nodes'][-1].update(parents=g['nodes'][-1]['parents']*2),
                    lambda g:g.update(final_node_id=g['nodes'][0]['id']),lambda g:g['nodes'].pop(-2),
                    lambda g:g['nodes'][-1].update(parents=[g['nodes'][0]['id']]),lambda g:g['nodes'][0].update(atom='wrong'),
                    lambda g:g['nodes'].reverse(),lambda g:g['nodes'].pop(0),lambda g:g['nodes'].clear(),
                    lambda g:g['nodes'][-1].update(rule=None),lambda g:g['nodes'].insert(0,{'id':'extra','atom':p['facts'][0],'rule':None,'parents':[]}),
                    lambda g:g['nodes'][-1].update(parents=g['nodes'][-1]['parents'][::-1])]
                for change in changes:
                    g=deepcopy(good);change(g);self.assertTrue(c.exact(measure.assess(p,g),_semantic(p,g)));cases+=1
        for p in self.p['protocol']['problems']:
            g=cal.proof(p,next(iter(self.p['protocol']['reference_plans'][p['id']].values())))
            g['final_node_id']='nonexistent';self.assertTrue(c.exact(measure.assess(p,g),_semantic(p,g)));cases+=1
        self.assertEqual(cases,180)
