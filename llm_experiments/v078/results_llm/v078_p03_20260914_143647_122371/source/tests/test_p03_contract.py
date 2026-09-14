import copy, json, unittest
from pathlib import Path
from fixtures import ROOT,plan,memory_run,input_of,baseline_path
import common,design,report,audit_model,preflight,audit_design,measure


class P03Contract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p=plan();cls.s=cls.p['protocol'];cls.records,cls.raw,_=memory_run(cls.p)
        cls.summary=report.summarize(cls.p,cls.records,cls.raw,'complete')
    def test_two_independent_structure_validators(self):
        self.assertTrue(preflight.validate(self.s)['validated']);self.assertTrue(audit_design.validate_protocol(self.s)['verified'])
    def test_four_structures_not_32_independent_problems(self):
        self.assertEqual(len(self.s['problems']),4);self.assertEqual(self.summary['scientific_scope']['distinct_structural_problems'],4)
        for x in self.summary['strata'].values():self.assertEqual(x['distinct_structural_problems'],2)
    def test_rule_count_equal_cases(self):
        for pid in ('H01','H02'):
            m=self.s['problem_metadata'][pid];self.assertEqual(m['shallow_rule_count'],m['deep_rule_count']);self.assertLess(m['shallow_D'],m['deep_D'])
    def test_more_rules_can_have_smaller_D(self):
        for pid in ('H03','H04'):
            m=self.s['problem_metadata'][pid];self.assertGreater(m['shallow_rule_count'],m['deep_rule_count']);self.assertLess(m['shallow_D'],m['deep_D'])
    def test_rule_count_heuristic_cannot_pass_inverse_pairs(self):
        r,raw,_=memory_run(self.p,'rule_count_heuristic');s=report.summarize(self.p,r,raw,'complete')
        self.assertEqual(s['strata']['inverted_rule_count']['model_selection']['successes'],0)
        self.assertEqual(s['strata']['equal_rule_count']['model_selection']['successes'],8)
        self.assertEqual(s['arms']['base']['model_pairs']['successes'],0)
        self.assertEqual(s['arms']['base']['model_generator_fidelity']['successes'],32)
        self.assertEqual(s['arms']['base']['reference_construction']['successes'],16)
    def test_correct_inverse_pair_records_opposite_rule_count_delta(self):
        for p in self.summary['pairs']:
            if p['family']=='inverted_rule_count':
                self.assertTrue(p['success']);self.assertGreater(p['actual_Ds']['deep'],p['actual_Ds']['shallow'])
                self.assertLess(p['actual_rule_counts']['deep'],p['actual_rule_counts']['shallow'])
    def test_actual_rule_count_not_reported_for_invalid_graph(self):
        r,raw,_=memory_run(self.p,'bad_parent');s=report.summarize(self.p,r,raw,'complete')
        for t in s['trials']:
            if t['arm']=='model':self.assertIsNone(t['actual_goal_support_rule_count'])
    def test_no_answer_metadata_in_any_request(self):
        forbidden={'family','target_D','shallow_D','deep_D','shallow_rule_count','deep_rule_count','problem_metadata','bindings'}
        def keys(x):
            out=set()
            if isinstance(x,dict):
                out|=set(x)
                for v in x.values():out|=keys(v)
            elif isinstance(x,list):
                for v in x:out|=keys(v)
            return out
        for slot in self.p['slots']:
            if design.disposition(self.p,slot,self.raw):continue
            b=design.request_for(self.p,slot,self.raw);self.assertFalse(keys(input_of(b))&forbidden);self.assertNotIn('bindings',b['format']['properties'])
    def test_generator_does_not_read_depth_or_family_metadata(self):
        other=copy.deepcopy(self.p);other['protocol']['depth_ranges']={};other['protocol']['problem_metadata']={}
        for slot in self.p['slots']:
            if not design.disposition(self.p,slot,self.raw):self.assertEqual(design.request_for(self.p,slot,self.raw),design.request_for(other,slot,self.raw))
    def test_preserved_base_headers_options_schemas(self):
        with __import__('zipfile').ZipFile(baseline_path()) as z:old=common.load(z.read('source/data/protocol.json'))
        for k in ('api_defaults','generation_schema','selector_schema','seeds','candidate_ids','candidate_orders','identity'):
            self.assertEqual(self.s[k],old[k],k)
        for k in ('select','shallow','deep','generator','facts','rule','final'):self.assertEqual(self.s['headers'][k],old['headers'][k],k)
    def test_all_initial_facts_support_each_goal(self):
        for p in self.s['problems']:
            for seq in self.s['reference_plans'][p['id']].values():self.assertTrue(measure.assess(p,preflight.candidate_graph(p,seq))['strict_valid'])
    def test_reference_is_not_an_autonomous_selection(self):
        self.assertEqual(self.summary['shared_model_selection']['assigned'],32)
        self.assertEqual(self.summary['arms']['base']['reference_construction']['assigned'],16)
    def test_wrong_original_transferred_without_reselection(self):
        r,raw,_=memory_run(self.p,'always_first')
        for slot in self.p['slots']:
            if slot['stage']=='facts':
                t=next(t for t in self.p['trials'] if t['id']==slot['trial_id'])
                if t['arm']=='model':
                    x=input_of(design.request_for(self.p,slot,raw));self.assertEqual(common.load(x['selection_original']['content'])['candidate_id'],'route_0')
                    self.assertEqual(x['provided_route_plan']['candidate_id'],'route_0')
    def test_audit_envelope_change_is_not_prompt_change(self):
        raw=dict(self.raw)
        for sid,b in raw.items():
            x=common.load(b);x['created_at']='different';x['total_duration']=999999;raw[sid]=common.wire(x)
        for slot in self.p['slots']:
            if not design.disposition(self.p,slot,self.raw):self.assertEqual(design.request_for(self.p,slot,self.raw),design.request_for(self.p,slot,raw))
    def test_no_parent_count_restriction(self):
        for slot in self.p['slots']:
            if slot['stage']=='rule' and not design.disposition(self.p,slot,self.raw):
                b=design.request_for(self.p,slot,self.raw);ps=b['format']['properties']['node']['properties']['parents']
                self.assertEqual(ps['maxItems'],16);self.assertNotIn('enum',ps['items'])
    def test_unknown_or_invalid_shape_is_not_D_zero(self):
        for mode in ('malformed_facts','malformed_rule','length_rule','invalid_selector'):
            r,raw,_=memory_run(self.p,mode);s=report.summarize(self.p,r,raw,'complete')
            for t in s['trials']:
                if t['arm']=='model':self.assertIsNone(t['graph_metric']);self.assertIsNone(t['actual_goal_support_rule_count'])
    def test_report_cannot_confuse_partial_effect_with_partial_execution(self):
        r,raw,_=memory_run(self.p,'always_first');s=report.summarize(self.p,r,raw,'complete')
        self.assertEqual(s['state'],'complete');self.assertEqual(s['decision'],'close_frozen_structural_batch');self.assertFalse(s['end_to_end_baseline_ready'])
        self.assertEqual(s['arms']['base']['model_trace']['successes'],16)
    def test_protocol_mutations_rejected_by_both_validators(self):
        changes=[lambda s:s['problem_metadata']['H01'].update(shallow_D=9),
                 lambda s:s['problem_metadata']['H03'].update(family='equal_rule_count'),
                 lambda s:s['problems'][0].update(target_D=2),
                 lambda s:s['reference_plans']['H01']['reference_short'].reverse(),
                 lambda s:s.update(max_inference_calls=999),
                 lambda s:s['problems'][0]['facts'].append('unused_fact'),
                 lambda s:s.update(generator_variants=['base','premise_binding'])]
        for change in changes:
            for validator in (preflight.validate,audit_design.validate_protocol):
                s=copy.deepcopy(self.s);change(s)
                with self.assertRaises((ValueError,KeyError)):validator(s)
    def test_new_problems_not_old_renamed_graph_pairs(self):
        with __import__('zipfile').ZipFile(baseline_path()) as z:old=common.load(z.read('source/data/protocol.json'))
        old_counts={tuple(sorted(len(r) for r in ps.values())) for ps in old['reference_plans'].values()}
        for routes in self.s['reference_plans'].values():self.assertNotIn(tuple(sorted(map(len,routes.values()))),old_counts)
    def test_graph_success_cannot_override_requested_step_failure(self):
        r,raw,_=memory_run(self.p,'swap_valid_branches');s=report.summarize(self.p,r,raw,'complete')
        rows=[t for t in s['trials'] if t['arm']=='model' and t['problem_id']=='H01' and t['condition']=='shallow']
        for t in rows:self.assertTrue(t['target_structure_success']);self.assertFalse(t['trace_success'])

if __name__=='__main__':unittest.main()
