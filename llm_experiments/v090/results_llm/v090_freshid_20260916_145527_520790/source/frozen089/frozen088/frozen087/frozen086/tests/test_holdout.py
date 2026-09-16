"""신규 구조·절차 동결·하위 과제 중복의 사전 검증. 모델 호출 없음."""
from pathlib import Path
from copy import deepcopy
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core086 as c,cases086 as cases,audit086 as audit,report086 as report
from byte_diagnostics086 import collect,render
from fixtures086 import plan,response_set

class Holdout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.s=c.spec()
    def test_generator_rebuilds_frozen_case_bytes(self):
        cases._generated.cache_clear()
        self.assertTrue(c.exact(cases.build_protocol(),self.s))
    def test_twelve_old_pairs_and_no_duplicate_new_pair(self):
        prior=cases.prior_cases();self.assertEqual(len(prior),12)
        new=[]
        for p in self.s['problems']:
            ps=[self.s['reference_plans'][p['id']][x] for x in self.s['reference_conditions']]
            sig=cases.topology_signature(p,ps)
            self.assertEqual(sig,audit.independent_signature(p,ps))
            for q,qs in prior+new:self.assertFalse(audit.isomorphic_pair(p,ps,q,qs))
            new.append((p,ps))
        self.assertEqual(len(new),8)
    def test_all_sixteen_individual_routes_are_structurally_new(self):
        old=[(p,[r]) for p,rs in cases.prior_cases() for r in rs];checked=[];prior_checks=0
        for p in self.s['problems']:
            for path in self.s['reference_plans'][p['id']].values():
                for q,qs in old:
                    self.assertFalse(audit.isomorphic_pair(p,[path],q,qs));prior_checks+=1
                for q,qs in checked:self.assertFalse(audit.isomorphic_pair(p,[path],q,qs))
                checked.append((p,[path]))
        self.assertEqual(prior_checks,384);self.assertEqual(len(checked),16)
    def test_renamed_old_problem_is_rejected_even_with_valid_profiles(self):
        s=deepcopy(self.s);old=c.load((c.ROOT/'data/v085_protocol.json').read_bytes());q=deepcopy(old['problems'][0]);q['id']='U01'
        s['problems'][0]=q;s['reference_plans']['U01']=deepcopy(old['reference_plans']['T01'])
        s['frozen_profiles']['U01']=[audit.reference_profile(s,q,k) for k in (0,1)]
        paths=[s['reference_plans']['U01'][k] for k in s['reference_conditions']]
        s['structure_signatures']['U01']=audit.independent_signature(q,paths)
        with self.assertRaisesRegex(ValueError,'new pair|route novelty'):audit.validate_protocol(s)
    def test_new_case_renaming_cannot_multiply_structure_count(self):
        s=deepcopy(self.s);q=deepcopy(s['problems'][5]);q['id']='U07';s['problems'][6]=q
        s['reference_plans']['U07']=deepcopy(s['reference_plans']['U06'])
        s['frozen_profiles']['U07']=[audit.reference_profile(s,q,k) for k in (0,1)]
        s['structure_signatures']['U07']=s['structure_signatures']['U06']
        with self.assertRaisesRegex(ValueError,'new pair|route novelty'):audit.validate_protocol(s)
    def test_algorithm_seed_drift_is_rejected(self):
        s=deepcopy(self.s);s['holdout_generation']['seed']='different'
        with self.assertRaisesRegex(ValueError,'generation algorithm'):audit.validate_protocol(s)
    def test_diagnostic_lookup_contract_is_frozen(self):
        for key in ('numeric_compare_header','lookup_header','control_select_addendum'):
            s=deepcopy(self.s);s[key]+=' altered'
            with self.assertRaisesRegex(ValueError,'anchored contract drift'):audit.validate_protocol(s)
    def test_growing_correct_enum_is_not_permitted(self):
        s=deepcopy(self.s);s['numeric_compare_schema']['properties']['target_value']['enum']=[2,3]
        with self.assertRaises(ValueError):audit.validate_protocol(s)
    def test_numeric_generalization_strata_are_fixed_before_model_calls(self):
        groups={}
        for p in self.s['problems']:
            groups.setdefault(self.s['problem_metadata'][p['id']]['numeric_profile_regime'],[]).append(p['id'])
        self.assertEqual(groups['new_depth_profile'],['U02','U03','U04'])
        self.assertEqual(len(groups['previous_depth_profile']),5)
    def test_holdout_and_partial_reporting_scope(self):
        p=plan();summary=report.summarize(p,{}, {},'crashed')
        self.assertEqual(summary['new_heldout_structural_cases'],8)
        self.assertEqual(summary['structural_comparison']['unmeasured_structures'],8)
        self.assertIsNone(summary['structural_comparison']['mean_pair_rate_difference'])
        self.assertIn('U01~U08',report.render(summary))
        for regime in summary['structural_comparison']['numeric_profile_strata'].values():self.assertIsNone(regime['mean_pair_rate_difference'])
        self.assertTrue(c.exact(summary,audit.independent_summary(p,{}, {},'crashed')))

class ByteDiagnostics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p=plan();cls.records,cls.raws,cls.requests=response_set(cls.p)
        cls.summary=report.summarize(cls.p,cls.records,cls.raws,'complete')
        cls.d=collect(cls.p,cls.requests,cls.raws,cls.summary['trials'])
    def test_numeric_tasks_not_counted_as_unique_structures(self):
        x=next(x for x in self.d['distinct_request_counts'] if (x['variant'],x['metric'],x['stage'])==('two_stage_values','D','compare'))
        self.assertEqual(x['request_files'],128)
        self.assertEqual(x['distinct_requests_with_seed'],40)
        self.assertEqual(x['distinct_requests_without_seed'],20)
    def test_oracle_same_request_not_new_problem(self):
        xs=self.d['oracle_request_equivalence'];self.assertEqual(len(xs),192)
        self.assertTrue(all(x['identical_request'] is True for x in xs))
    def test_same_route_and_same_raw_history_are_counted(self):
        xs=self.d['same_route_correct_vs_two_stage'];self.assertEqual(len(xs),128)
        self.assertTrue(all(x['facts_request_byte_equal'] is True for x in xs))
        self.assertTrue(all(x['generator_outcome_differs'] is False for x in xs))
    def test_raw_spacing_difference_not_canonicalized_away(self):
        requests=dict(self.requests);t=next(t for t in self.p['trials'] if t['selector_variant']=='two_stage_values' and t['generate'])
        sid=t['id']+'_facts';body=c.load(requests[sid]);prefix,text=body['messages'][0]['content'].split('\n\ninput: ',1)
        data=c.load(text);data['selection_original']['content']=' '+data['selection_original']['content']
        body['messages'][0]['content']=prefix+'\n\ninput: '+c.wire(data).decode();requests[sid]=c.wire(body)
        d=collect(self.p,requests,self.raws,self.summary['trials'])
        xs=d['same_route_correct_vs_two_stage'];self.assertEqual(sum(x['facts_request_byte_equal'] is False for x in xs),1)
    def test_missing_usage_remains_missing(self):
        raw=dict(self.raws);sid=next(op['id'] for op in self.p['slots'] if op['stage']=='compare');x=c.load(raw[sid]);x.pop('eval_count');raw[sid]=c.wire(x)
        d=collect(self.p,self.requests,raw,self.summary['trials'])
        self.assertEqual(sum(x['usage']['eval_count']['missing'] for x in d['usage_by_variant_metric']),1)
    def test_unobserved_requests_not_equal(self):
        summary=report.summarize(self.p,{}, {},'crashed');d=collect(self.p,{}, {},summary['trials'])
        self.assertTrue(all(x['identical_request'] is None for x in d['oracle_request_equivalence']))
        self.assertEqual(sum(x['request_files'] for x in d['distinct_request_counts']),0)
        self.assertEqual(d['same_route_correct_vs_two_stage'],[])
    def test_metric_only_diagnostic_is_not_a_new_sample(self):
        xs=self.d['metric_only_lookup_pairs'];self.assertEqual(len(xs),64)
        self.assertTrue(all(x['only_metric_differs'] for x in xs));self.assertTrue(all(x['candidate_changed'] is False for x in xs))
        self.assertIn('중복',render(self.d))

if __name__=='__main__':unittest.main()
