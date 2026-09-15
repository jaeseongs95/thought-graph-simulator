"""새 단계 경계와 불리한 결과/중단을 포함한 시험. 실제 Qwen 호출 없음."""
from pathlib import Path
from copy import deepcopy
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core085 as c,design085 as d,report085 as r,audit085 as a,numeric085
from fixtures085 import plan,response_set,decode_request

class Pipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p=plan();cls.records,cls.raws,cls.requests=response_set(cls.p)
        cls.t=next(t for t in cls.p['trials'] if t['selector_variant']=='two_stage_values' and t['generate'])
    def analyze(self,policy='oracle',transform=None):
        rec,raw,req=response_set(self.p,policy,transform)
        x=r.summarize(self.p,rec,raw,'complete');y=a.independent_summary(self.p,rec,raw,'complete')
        self.assertTrue(c.exact(x,y));return x,rec,raw,req
    def target_row(self,s):return next(x for x in s['trials'] if x['trial_id']==self.t['id'])
    def mutate_content(self,value,phase='compare',raw_text=None,outer_change=None):
        sid=self.t['comparison_slot_id'] if phase=='compare' else self.t['selection_slot_id']
        def change(op,body,raw):
            if op['id']!=sid:return raw
            x=c.load(raw);x['message']['content']=raw_text if raw_text is not None else c.wire(value).decode()
            if outer_change:x.update(outer_change)
            return c.wire(x)
        return change
    def test_numbers_only_comparison_has_no_candidate_id_or_goal(self):
        for op in self.p['slots']:
            if op['stage']!='compare':continue
            x=decode_request(c.load(self.requests[op['id']]))
            self.assertEqual(set(x),{'metric','direction','values'})
            self.assertEqual(len(x['values']),2);self.assertTrue(all(type(v) is int for v in x['values']))
            for token in ('route_0','route_1','candidate_id','facts','rules','goal'):
                self.assertNotIn(token,c.load(self.requests[op['id']])['messages'][0]['content'])
    def test_lookup_never_receives_target_direction_or_problem(self):
        for t in self.p['trials']:
            if t['selector_variant'] not in ('two_stage_values','oracle_lookup'):continue
            x=decode_request(c.load(self.requests[t['selection_slot_id']]))
            self.assertEqual(set(x),{'candidate_measurements','metric','value_original'})
    def test_numeric_output_not_replaced_with_ground_truth(self):
        s,_,raw,req=self.analyze({'two_stage_values':'compare_wrong'})
        rows=[x for x in s['trials'] if x['selector_variant']=='two_stage_values' and x['metric']=='D']
        self.assertEqual(sum(x['comparison_success'] for x in rows),0)
        self.assertEqual(sum(x['lookup_adherence'] for x in rows),128)
        self.assertEqual(sum(x['generator_success'] for x in rows),128)
        self.assertEqual(sum(x['metric_end_to_end'] for x in rows),0)
        for x in rows:
            t=next(t for t in self.p['trials'] if t['id']==x['trial_id'])
            inp=decode_request(c.load(req[t['selection_slot_id']]))
            self.assertEqual(inp['value_original'],c.load(raw[t['comparison_slot_id']])['message']['content'])
    def test_two_wrong_stages_lucky_goal_is_not_full_success(self):
        s,_,_,_=self.analyze({'two_stage_values':'reverse'})
        rows=[x for x in s['trials'] if x['selector_variant']=='two_stage_values' and x['metric']=='D']
        self.assertEqual(sum(x['final_choice_success'] for x in rows),128)
        self.assertEqual(sum(x['target_graph_success_without_selection_trace'] for x in rows),128)
        self.assertEqual(sum(x['metric_end_to_end'] for x in rows),0)
        self.assertEqual(s['groups']['two_stage_values']['totals']['D']['end_to_end_pairs']['successes'],0)
    def test_correct_comparison_wrong_lookup_is_failure(self):
        s,_,_,_=self.analyze({'two_stage_values':'lookup_wrong'})
        g=s['stage_diagnostics']['two_stage_values']['D']
        self.assertEqual(g['comparison']['successes'],128);self.assertEqual(g['lookup_adherence']['successes'],0)
    def test_out_of_candidate_value_is_not_corrected(self):
        s,rec,_,_=self.analyze({'two_stage_values':'compare_outside'})
        rows=[x for x in s['trials'] if x['selector_variant']=='two_stage_values' and x['metric']=='D']
        self.assertTrue(all(x['comparison_value']==99 and x['lookup_adherence'] is True for x in rows))
        self.assertTrue(all(x['selection_success'] is False and x['generator_success'] is None for x in rows))
        self.assertTrue(all(x['metric_end_to_end'] is False and x['actual_D'] is None for x in rows))
    def test_invalid_comparison_blocks_lookup_and_preserves_unexecuted_graph(self):
        s,rec,_,_=self.analyze(transform=self.mutate_content({'target_value':'3'}))
        x=self.target_row(s);self.assertFalse(x['selection_success']);self.assertFalse(x['metric_end_to_end'])
        self.assertEqual(rec[self.t['selection_slot_id']]['reason'],'invalid_comparison_output')
        self.assertIsNone(x['actual_D']);self.assertIsNone(x['generator_success'])
    def test_comparison_json_failure_is_not_repaired(self):
        s,_,_,_=self.analyze(transform=self.mutate_content(None,raw_text='{'))
        x=self.target_row(s);self.assertEqual(x['comparison_status'],'invalid_json');self.assertFalse(x['comparison_success'])
    def test_comparison_length_is_unmeasured_not_wrong(self):
        s,rec,_,_=self.analyze(transform=self.mutate_content({'target_value':3},outer_change={'done_reason':'length'}))
        x=self.target_row(s);self.assertIsNone(x['comparison_success']);self.assertIsNone(x['metric_end_to_end'])
        self.assertEqual(rec[self.t['selection_slot_id']]['reason'],'unusable_comparison_response')
    def test_null_lookup_when_match_exists_is_observed_failure(self):
        s,_,_,_=self.analyze(transform=self.mutate_content({'candidate_id':None},'select'))
        x=self.target_row(s);self.assertEqual(x['selector_status'],'lookup_null')
        self.assertFalse(x['lookup_adherence']);self.assertFalse(x['metric_end_to_end']);self.assertIsNone(x['actual_D'])
    def test_comparison_whitespace_and_raw_content_are_preserved(self):
        expected=a.reference_profile(self.p['protocol'],d.problem_for(self.p,self.t),int(self.t['condition']=='deep'))['goal_depth']
        text=' { "target_value" : '+str(expected)+' } '\

        _,_,raw,req=self.analyze(transform=self.mutate_content(None,raw_text=text))
        x=decode_request(c.load(req[self.t['selection_slot_id']]))
        self.assertEqual(x['value_original'],text)
        self.assertEqual(c.load(raw[self.t['comparison_slot_id']])['message']['content'],text)
    def test_oracle_and_model_lookup_same_value_same_request(self):
        for t in self.p['trials']:
            if t['selector_variant']!='two_stage_values':continue
            other=next(q for q in self.p['trials'] if q['unit_id']==t['unit_id'] and q['selector_variant']=='oracle_lookup')
            self.assertEqual(self.requests[t['selection_slot_id']],self.requests[other['selection_slot_id']])
    def test_oracle_is_diagnostic_only_and_never_generated(self):
        for t in self.p['trials']:
            if t['selector_variant']!='oracle_lookup':continue
            self.assertFalse(t['generate']);self.assertEqual([o['stage'] for o in self.p['slots'] if o['trial_id']==t['id']],['select'])
    def test_numeric_calls_are_charged_separately(self):
        s=r.summarize(self.p,self.records,self.raws,'complete')
        u=s['groups']['two_stage_values']['usage_by_stage']
        self.assertEqual((u['compare']['calls'],u['select']['calls'],u['generation']['calls']),(192,192,816))
        self.assertEqual(s['groups']['oracle_lookup']['usage_by_stage']['generation']['calls'],0)
    def test_comparison_not_added_to_generation_history(self):
        for op in self.p['slots']:
            if op['stage'] not in ('facts','rule','final') or op['id'] not in self.requests:continue
            x=decode_request(c.load(self.requests[op['id']]))
            self.assertEqual(set(x),{'problem','selection_original','provided_route_plan','operation','history'})
            self.assertFalse(any(h['source_slot_id'].endswith('_compare') for h in x['history']))
    def test_integer_and_null_contracts_type_strict(self):
        fake={'kind':'call','http_status':200,'error':None};spec=self.p['protocol']
        for val in (True,False,'3',3.0,None,-1,129,{},[]):
            raw=c.wire({'model':spec['model'],'message':{'role':'assistant','content':c.wire({'target_value':val}).decode()},'done':True,'done_reason':'stop'})
            x=numeric085.decode(fake,raw,spec,'compare');y=a.decode(fake,raw,spec,'compare','two_stage_values')
            self.assertEqual(x,y);self.assertEqual(x[0],'invalid_schema')
    def test_missing_compare_not_filled_from_oracle_control(self):
        rec=dict(self.records);raw=dict(self.raws);cid=self.t['comparison_slot_id']
        # Reconstruct a valid partial prefix: no downstream calls from this trial have occurred.
        for op in self.p['slots']:
            if op['trial_id']==self.t['id']:rec.pop(op['id'],None);raw.pop(op['id'],None)
        s=r.summarize(self.p,rec,raw,'crashed');self.assertTrue(c.exact(s,a.independent_summary(self.p,rec,raw,'crashed')))
        x=self.target_row(s);self.assertIsNone(x['comparison_value']);self.assertIsNone(x['selection_success'])
        self.assertIsNone(x['metric_end_to_end'])
