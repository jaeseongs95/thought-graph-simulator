"""graph·집계 정상/반례와 두 의미 검산 구현의 차등 검사."""
from pathlib import Path
from copy import deepcopy
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core085 as c,report085 as r,audit085 as a,calibrate085 as cal
from fixtures085 import plan,response_set

class Measurement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.p=plan()
    def run_policy(self,policy,transform=None):
        rec,raw,_=response_set(self.p,policy,transform)
        left=r.summarize(self.p,rec,raw,'complete');right=a.independent_summary(self.p,rec,raw,'complete')
        self.assertTrue(c.exact(left,right));self.assertTrue(r.render(left));return left,rec,raw
    def test_calibration_new_structures(self):
        result=cal.calibration();self.assertEqual(result['failed'],0);self.assertGreater(result['passed'],100)
    def test_oracle_policy(self):
        s,_,_=self.run_policy('oracle')
        for v,g in s['groups'].items():
            self.assertEqual(g['totals']['D']['selection_pairs']['successes'],64)
            self.assertEqual(g['totals']['W']['selection_pairs']['successes'],32)
            self.assertEqual(g['totals']['W']['metric_end_to_end']['assigned'],0)
        self.assertEqual(s['reference']['successes'],32)
    def test_reported_values_perfect_in_synthetic_fixture(self):
        s,_,_=self.run_policy('reported')
        self.assertEqual(s['groups']['correct_values']['totals']['D']['follows_supplied_extreme']['successes'],128)
        self.assertEqual(s['groups']['correct_values']['totals']['D']['end_to_end_pairs']['successes'],64)
    def test_first_position_not_depth_control(self):
        s,_,_=self.run_policy('first')
        for g in s['groups'].values():
            self.assertEqual(g['totals']['D']['selection_success']['successes'],64)
            self.assertEqual(g['totals']['D']['selection_pairs']['successes'],0)
        self.assertEqual(s['hypothesis_comparisons']['C0_anchor_support']['by_metric']['D']['changed_path']['successes'],0)
    def test_fixed_id_not_depth_control(self):
        s,_,_=self.run_policy('id0')
        for g in s['groups'].values():self.assertEqual(g['totals']['D']['selection_pairs']['successes'],0)
    def test_reverse_not_counted_as_control_success(self):
        s,_,_=self.run_policy('reverse')
        for name in ('candidate_id','correct_values'):
            self.assertEqual(s['groups'][name]['totals']['D']['generator_success']['successes'],128)
            self.assertEqual(s['groups'][name]['totals']['D']['metric_end_to_end']['successes'],0)
            self.assertTrue(all(p['valid_graph_direction']=='reversed' for p in s['groups'][name]['pairs'] if p['metric']=='D'))
    def test_W_only_does_not_satisfy_D(self):
        s,_,_=self.run_policy('count_only')
        for v in ('candidate_id','correct_values'):
            rows=[x for x in s['trials'] if x['selector_variant']==v and x['metric']=='D' and x['problem_id'] in ('T05','T06','T07','T08')]
            self.assertFalse(any(x['selection_success'] for x in rows))
    def test_D_only_does_not_satisfy_W(self):
        s,_,_=self.run_policy('depth_only')
        for v in ('candidate_id','correct_values'):self.assertEqual(s['groups'][v]['totals']['W']['selection_success']['successes'],0)
    def test_support_improves_synthetic_fixture(self):
        s,_,_=self.run_policy({'candidate_id':'first','correct_values':'oracle'})
        delta=s['hypothesis_comparisons']['C0_anchor_support']['by_metric']['D']['selection_pairs']
        self.assertEqual(delta['right_only'],64);self.assertEqual(delta['left_only'],0)
    def test_support_worsens_synthetic_fixture(self):
        s,_,_=self.run_policy({'candidate_id':'oracle','correct_values':'first'})
        delta=s['hypothesis_comparisons']['C0_anchor_support']['by_metric']['D']['selection_pairs']
        self.assertEqual(delta['left_only'],64);self.assertEqual(delta['right_only'],0)
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
        self.assertEqual(s['groups']['candidate_id']['totals']['D']['selection_success']['unmeasured'],128)
        self.assertEqual(s['groups']['candidate_id']['totals']['D']['selection_success']['failures'],0)
    def test_one_arm_unobserved_not_other_arm_win(self):
        rec,raw,_=response_set(self.p)
        drop={op['id'] for op in self.p['slots'] if next(t for t in self.p['trials'] if t['id']==op['trial_id'])['selector_variant']=='correct_values'}
        rec={k:v for k,v in rec.items() if k not in drop};raw={k:v for k,v in raw.items() if k not in drop}
        s=r.summarize(self.p,rec,raw,'crashed');self.assertTrue(c.exact(s,a.independent_summary(self.p,rec,raw,'crashed')))
        m=s['hypothesis_comparisons']['C0_anchor_support']['by_metric']['D']['selection']
        self.assertEqual((m['not_comparable'],m['left_only']),(128,0))
    def test_not_scheduled_is_not_unobserved(self):
        s,_,_=self.run_policy('oracle')
        rows=[r for r in s['trials'] if not r['generation_scheduled']]
        self.assertEqual(len(rows),384)
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
    def test_360_graph_differentials(self):
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
        self.assertEqual(cases,360)


class StructuralInference(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.p=plan()
    def test_support_effect_structural_macro(self):
        rec,raw,_=response_set(self.p,{'correct_values':'first','two_stage_values':'oracle'})
        s=r.summarize(self.p,rec,raw,'complete');self.assertTrue(c.exact(s,a.independent_summary(self.p,rec,raw,'complete')))
        x=s['structural_comparison'];self.assertEqual(x['assigned_structures'],8)
        self.assertEqual(x['improved_structures'],8);self.assertEqual(x['mean_pair_rate_difference'],1.0)
        self.assertIsNone(x['inferential_p_value']);self.assertFalse(s['iid_structure_sampling'])
    def test_empty_partial_no_structure_effect(self):
        s=r.summarize(self.p,{}, {},'crashed');x=s['structural_comparison']
        self.assertEqual(x['complete_structures'],0);self.assertEqual(x['unmeasured_structures'],8)
        self.assertIsNone(x['mean_pair_rate_difference']);self.assertEqual(x['improved_structures'],0)
    def test_one_missing_condition_does_not_gain_a_win(self):
        rec,raw,_=response_set(self.p)
        t=next(t for t in self.p['trials'] if t['selector_variant']=='correct_values' and t['metric']=='D')
        for op in self.p['slots']:
            if op['trial_id']==t['id']:rec.pop(op['id'],None);raw.pop(op['id'],None)
        s=r.summarize(self.p,rec,raw,'crashed');self.assertTrue(c.exact(s,a.independent_summary(self.p,rec,raw,'crashed')))
        x=s['structural_comparison'];self.assertEqual(x['complete_structures'],7)
        self.assertIsNone(x['mean_pair_rate_difference']);self.assertEqual(x['improved_structures'],0)
    def test_maximum_and_minimum_mapped_budgets(self):
        import design085 as d
        for policy,expected in [('longest',3708),('shortest',3516)]:
            def transform(op,body,raw):
                if op['stage']!='compare':return raw
                trial=d.trial_for(self.p,op);cards=d.cards(self.p,trial);problem=d.problem_for(self.p,trial)
                chosen=(max if policy=='longest' else min)(cards,key=lambda c:len(c['rules']))
                value=a.prior.route_depth(problem,[x['id'] for x in chosen['rules']]) if trial['metric']=='D' else len(chosen['rules'])
                x=c.load(raw);x['message']['content']=c.wire({'target_value':value}).decode();return c.wire(x)
            _,raw,_=response_set(self.p,policy,transform);self.assertEqual(len(raw),expected)
    def test_generation_length_is_not_a_semantic_failure(self):
        rec,raw,_=response_set(self.p)
        target=next(o for o in self.p['slots'] if o['stage']=='rule')
        x=c.load(raw[target['id']]);x['done_reason']='length';raw[target['id']]=c.wire(x)
        s=r.summarize(self.p,rec,raw,'complete');self.assertTrue(c.exact(s,a.independent_summary(self.p,rec,raw,'complete')))
        row=next(x for x in s['trials'] if x['trial_id']==target['trial_id'])
        self.assertIsNone(row['generator_success']);self.assertIsNone(row['actual_D'])
