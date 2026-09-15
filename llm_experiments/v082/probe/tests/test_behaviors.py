"""관측된 성과/추가 계산 계약/잘못된 수치/미관측을 분리하는 합성 반례."""
import unittest,json
from copy import deepcopy
from collections import Counter
import core082 as core, report082 as report, audit082 as audit, design082 as design
import profile082 as prod, audit_profile082 as independent
from fixtures082 import plan,response_set,decode_request,answer


def change(raw,fn):
    outer=core.load(raw);obj=core.load(outer['message']['content']);fn(obj)
    outer['message']['content']=core.wire(obj).decode();return core.wire(outer)

class Behaviors(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p=plan();cls.rec,cls.raw,cls.req=response_set(cls.p)
    def run_case(self,policy='oracle',transform=None):
        rec,raw,req=response_set(self.p,policy,transform)
        s=report.summarize(self.p,rec,raw,'complete')
        self.assertEqual(s,audit.independent_summary(self.p,rec,raw,'complete'))
        return s,rec,raw,req
    def test_new_only_improves(self):
        s,*_=self.run_case({'candidate_id':'first','profiled_id':'oracle'})
        self.assertEqual(s['paired_pairs']['D']['end_to_end_success']['profiled_id_only'],32)
    def test_new_only_worsens(self):
        s,*_=self.run_case({'candidate_id':'oracle','profiled_id':'first'})
        self.assertEqual(s['groups']['profiled_id']['totals']['D']['end_to_end_pairs']['successes'],0)
        self.assertEqual(s['paired_pairs']['D']['end_to_end_success']['candidate_id_only'],32)
    def test_correct_profiles_but_first_position_still_not_success(self):
        s,*_=self.run_case('first')
        self.assertEqual(s['profile_analysis']['trace']['successes'],16)
        self.assertEqual(s['groups']['profiled_id']['totals']['D']['selection_success']['successes'],32)
        self.assertEqual(s['profile_analysis']['pipeline_pairs']['D']['successes'],0)
    def test_reverse_all_four_is_not_discrimination(self):
        s,*_=self.run_case('reverse')
        for v in ('candidate_id','profiled_id'):
            self.assertTrue(all(x['opposite_choices_for_both_directions'] for x in s['groups'][v]['metric_discrimination']))
            self.assertFalse(any(x['all_four_selections_correct'] for x in s['groups'][v]['metric_discrimination']))
    def test_rulecount_only_fails_inverse_D(self):
        s,*_=self.run_case('count_only')
        rows=[r for r in s['trials'] if r['arm']=='model' and r['problem_id'] in ('H03','H04') and r['metric']=='D']
        self.assertTrue(all(r['metric_end_to_end'] is False for r in rows))
    def test_wrong_worksheet_correct_graph_preserved(self):
        def bad(op,body,raw):
            return change(raw,lambda x:x.update(goal_depth=999)) if op['stage']=='profile' else raw
        s,rec,raw,req=self.run_case(transform=bad)
        self.assertEqual(s['groups']['profiled_id']['totals']['D']['metric_end_to_end']['successes'],64)
        self.assertEqual(s['profile_analysis']['trial_diagnostics']['D']['full_pipeline_success']['successes'],0)
        for o in self.p['slots']:
            if o['stage']=='select' and 'profiled_id' in o['id']:
                d=decode_request(core.load(req[o['id']]))
                self.assertTrue(all('999' in x['content'] for x in d['candidate_measurements']))
    def test_wrong_profile_report_can_be_followed_without_real_D_success(self):
        def bad(op,body,raw):
            return change(raw,lambda x:x.update(goal_depth=100-x['goal_depth'])) if op['stage']=='profile' else raw
        s,*_=self.run_case({'candidate_id':'oracle','profiled_id':'reported'},bad)
        self.assertEqual(s['groups']['profiled_id']['totals']['D']['metric_end_to_end']['successes'],0)
        self.assertEqual(s['profile_analysis']['trial_diagnostics']['D']['follows_reported_extreme']['successes'],64)
    def test_final_numbers_correct_but_intermediate_trace_wrong(self):
        def bad(op,body,raw):
            return change(raw,lambda x:x['steps'][0].update(depth=777)) if op['stage']=='profile' else raw
        s,*_=self.run_case(transform=bad)
        self.assertEqual(s['profile_analysis']['D_values']['successes'],16)
        self.assertEqual(s['profile_analysis']['W_values']['successes'],16)
        self.assertEqual(s['profile_analysis']['trace']['successes'],0)
        self.assertEqual(s['groups']['profiled_id']['totals']['D']['metric_end_to_end']['successes'],64)
    def test_good_profile_wrong_graph_is_not_pipeline_success(self):
        def bad(op,body,raw):
            if op['stage']=='rule' and op['rule_position']==0:return change(raw,lambda x:x['node'].update(parents=[]))
            return raw
        s,*_=self.run_case(transform=bad)
        self.assertEqual(s['profile_analysis']['trace']['successes'],16)
        self.assertEqual(s['groups']['profiled_id']['totals']['D']['metric_end_to_end']['successes'],0)
    def test_malformed_profile_is_forwarded_not_repaired_or_generation_gate(self):
        marker='not JSON -- this string is the model original'
        def bad(op,body,raw):
            if op['stage']!='profile':return raw
            x=core.load(raw);x['message']['content']=marker;return core.wire(x)
        s,rec,raw,req=self.run_case(transform=bad)
        self.assertEqual(s['profile_analysis']['trace']['failures'],16)
        self.assertEqual(s['groups']['profiled_id']['totals']['D']['metric_end_to_end']['successes'],64)
        for t in self.p['trials']:
            if t['selector_variant']=='profiled_id':
                d=decode_request(core.load(req[t['selection_slot_id']]))
                self.assertTrue(all(x['content']==marker for x in d['candidate_measurements']))
    def test_unmappable_selection_does_not_fill_graph_with_zero(self):
        def bad(op,body,raw):
            if op['stage']=='select' and 'profiled_id' in op['id']:return change(raw,lambda x:x.update(candidate_id='absent'))
            return raw
        s,*_=self.run_case(transform=bad)
        rs=[r for r in s['trials'] if r['selector_variant']=='profiled_id']
        self.assertTrue(all(r['generator_success'] is None and r['actual_D'] is None and r['metric_end_to_end'] is False for r in rs))
    def test_missing_arm_not_counted_as_other_arm_win(self):
        rec={k:v for k,v in self.rec.items() if 'profiled_id' not in k};raw={k:v for k,v in self.raw.items() if 'profiled_id' not in k}
        s=report.summarize(self.p,rec,raw,'crashed')
        self.assertEqual(s,audit.independent_summary(self.p,rec,raw,'crashed'))
        self.assertEqual(s['paired_trials']['D']['metric_end_to_end']['not_comparable'],64)
    def test_profile_length_ending_is_unmeasured_not_false_math(self):
        def bad(op,body,raw):
            if op['stage']!='profile':return raw
            x=core.load(raw);x['done_reason']='length';return core.wire(x)
        s,*_=self.run_case(transform=bad)
        self.assertEqual(s['profile_analysis']['trace']['unmeasured'],16)
        self.assertEqual(s['profile_analysis']['trial_diagnostics']['D']['full_pipeline_success']['unmeasured'],64)
    def test_equal_reported_values_do_not_get_host_tiebreak(self):
        def equal(op,body,raw):
            return change(raw,lambda x:x.update(goal_depth=5,rule_count=5)) if op['stage']=='profile' else raw
        s,*_=self.run_case(transform=equal)
        rows=[r for r in s['trials'] if r['selector_variant']=='profiled_id']
        self.assertTrue(all(r['profile_diagnostic']['reported_comparison_status']=='reported_tie' for r in rows))
        self.assertTrue(all(r['profile_diagnostic']['follows_reported_extreme'] is None for r in rows))
        self.assertEqual(s['groups']['profiled_id']['totals']['D']['metric_end_to_end']['successes'],64)

    def test_numeric_bool_never_passes_as_integer(self):
        op=next(x for x in self.p['slots'] if x['stage']=='profile');x=core.load(core.load(self.raw[op['id']])['message']['content'])
        x['facts'][0]['depth']=False
        self.assertFalse(prod.profile_shape(x));self.assertFalse(independent.profile_shape(x))

    def test_profile_mutation_differential(self):
        tested=0
        for o in self.p['slots']:
            if o['stage']!='profile':continue
            t=design.trial_for(self.p,o);p=design.problem_for(self.p,t);data=design.profile_data(self.p,o)
            x=core.load(core.load(self.raw[o['id']])['message']['content'])
            cases=[deepcopy(x)]
            for mutate in [lambda z:z.update(goal_depth=999),lambda z:z.update(rule_count=0),lambda z:z['facts'][0].update(depth=1),
                           lambda z:z['steps'][0].update(rule_id='absent'),lambda z:z['steps'][0].update(conclusion='absent'),
                           lambda z:z['steps'][0]['premises'][0].update(atom='absent'),lambda z:z['steps'][0]['premises'][0].update(depth=500),
                           lambda z:z['steps'][0].update(depth=500),lambda z:z['steps'].reverse(),lambda z:z['facts'].append(deepcopy(z['facts'][0])),
                           lambda z:z['steps'].pop(),lambda z:z['steps'].append(deepcopy(z['steps'][0])),lambda z:z.update(rule_count=True),
                           lambda z:z.update(goal_depth=2.0),lambda z:z.update(extra='bad')]:
                c=deepcopy(x);mutate(c);cases.append(c)
            for c in cases:
                self.assertEqual(prod.profile_shape(c),independent.profile_shape(c))
                status='ok' if prod.profile_shape(c) else 'invalid_schema'
                self.assertEqual(prod.grade(p,data['candidate_rules'],status,c),independent.grade(p,data['candidate_rules'],status,c))
                tested+=1
        self.assertEqual(tested,256)

if __name__=='__main__':unittest.main()
