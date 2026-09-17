from pathlib import Path
from copy import deepcopy
import unittest,sys,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core091 as c,design091 as d,fixtures091 as f,report091 as r,audit091 as a
from audit_metrics091 import check_aggregate
from diagnostics091 import collect
from calibrate091 import calibration

class Measurement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p,cls.rec,cls.raw,cls.req=f.oracle_cache()
        cls.summary=r.summarize(cls.p,cls.rec,cls.raw,'complete')
    def replace(self,raw,sid,edit):
        out=dict(raw);outer=c.load(out[sid]);obj=c.load(outer['message']['content']);edit(obj)
        outer['message']['content']=c.wire(obj).decode();out[sid]=c.wire(outer);return out
    def trial(self,arm):return next(t for t in self.p['trials'] if t['generator_arm']==arm)
    def summarize_both(self,raw=None,rec=None,state='complete'):
        raw=self.raw if raw is None else raw;rec=self.rec if rec is None else rec
        ss=r.summarize(self.p,rec,raw,state);ind=a.independent_summary(self.p,rec,raw,state)
        self.assertTrue(c.exact(ss,ind));return ss
    def test_oracle_all_1536_graphs_pass(self):
        for g in self.summary['cohorts']['new_topology']['groups']['end_to_end'].values():
            self.assertEqual(g['outcome'],dict(planned=128,success=128,failure=0,unobserved=0))
            self.assertEqual(g['bidirectional']['success'],64);self.assertEqual(g['four_display']['success'],16)
    def test_independent_all_trial_semantics(self):self.summarize_both()
    def test_shared_selection_not_quadrupled(self):self.assertEqual(self.summary['shared_selection']['planned'],384);self.assertEqual(self.summary['shared_selection']['success'],384)
    def test_primary_zero_when_oracle_all_success(self):self.assertEqual(self.summary['primary']['mean_delta'],0);self.assertTrue(all(x['mean_delta']==0 for x in self.summary['secondary']))
    def test_primary_direction_alias_failure_minus_one(self):
        raw=dict(self.raw)
        for t in self.p['trials']:
            if t['generator_arm']=='atom_alias':raw=self.replace(raw,t['id']+'_rule_00',lambda x:x['node'].__setitem__('parents',[]))
        ss=self.summarize_both(raw);self.assertEqual(ss['primary']['mean_delta'],-1)
    def test_primary_direction_baseline_failure_plus_one(self):
        raw=dict(self.raw)
        for t in self.p['trials']:
            if t['generator_arm']=='baseline':raw=self.replace(raw,t['id']+'_rule_00',lambda x:x['node'].__setitem__('parents',[]))
        ss=self.summarize_both(raw);self.assertEqual(ss['primary']['mean_delta'],1)
    def test_only_one_direction_not_a_successful_pair(self):
        raw=dict(self.raw)
        for t in self.p['trials']:
            if t['generator_arm']=='atom_alias' and t['condition']=='deep':raw=self.replace(raw,t['id']+'_rule_00',lambda x:x['node'].__setitem__('parents',[]))
        ss=self.summarize_both(raw);g=ss['cohorts']['new_topology']['groups']['end_to_end']['atom_alias'];self.assertEqual(g['outcome']['success'],64);self.assertEqual(g['bidirectional']['success'],0);self.assertEqual(g['pair_distribution']['only_one_success'],64)
    def test_nonexistent_parent_is_not_corrected(self):
        t=self.trial('atom_alias');sid=t['id']+'_rule_00';raw=self.replace(self.raw,sid,lambda x:x['node'].__setitem__('parents',['NOT_EXISTING']))
        ss=self.summarize_both(raw);row=next(x for x in ss['rows'] if x['trial_id']==t['id']);self.assertFalse(row['end_to_end_success']);self.assertIn('missing_parent',row['step_checks'][1]['error_codes'])
    def test_premise_omission_is_separate_from_reference_existence(self):
        t=self.trial('atom_alias');sid=t['id']+'_rule_00';raw=self.replace(self.raw,sid,lambda x:x['node'].__setitem__('parents',x['node']['parents'][1:]))
        row=next(x for x in self.summarize_both(raw)['rows'] if x['trial_id']==t['id']);self.assertIn('premise_counter_mismatch',row['step_checks'][1]['error_codes']);self.assertNotIn('missing_parent',row['step_checks'][1]['error_codes'])
    def test_facts_semantic_failure_is_not_hidden(self):
        t=self.trial('atom_alias');raw=self.replace(self.raw,t['id']+'_facts',lambda x:x['nodes'][0].__setitem__('atom','WRONG'))
        row=next(x for x in self.summarize_both(raw)['rows'] if x['trial_id']==t['id']);self.assertFalse(row['initial_fact_success']);self.assertFalse(row['end_to_end_success'])
    def test_facts_id_contract_can_fail_with_valid_graph(self):
        t=self.trial('atom_alias');raw=dict(self.raw);facts=c.load(c.load(raw[t['id']+'_facts'])['message']['content'])['nodes'];left,right=facts[0]['id'],facts[1]['id'];mapping={left:right,right:left}
        for op in self.p['slots']:
            if op['trial_id']!=t['id'] or op['id'] not in raw:continue
            def edit(obj):
                for n in obj.get('nodes',[obj['node']] if 'node' in obj else []):
                    n['id']=mapping.get(n['id'],n['id']);n['parents']=[mapping.get(x,x) for x in n['parents']]
                if 'final_node_id' in obj:obj['final_node_id']=mapping.get(obj['final_node_id'],obj['final_node_id'])
            raw=self.replace(raw,op['id'],edit)
        row=next(x for x in self.summarize_both(raw)['rows'] if x['trial_id']==t['id'])
        self.assertTrue(row['initial_fact_success']);self.assertFalse(row['initial_id_contract_success']);self.assertTrue(row['generator_semantic_success']);self.assertFalse(row['end_to_end_success'])
    def test_last_rule_id_contract_not_semantic_validity(self):
        t=self.trial('atom_alias');row0=next(x for x in self.summary['rows'] if x['trial_id']==t['id']);idx=len(row0['selected_rule_ids'])-1
        raw=self.replace(self.raw,t['id']+f'_rule_{idx:02d}',lambda x:x['node'].__setitem__('id','WRONG_BUT_UNIQUE_ID'))
        raw=self.replace(raw,t['id']+'_final',lambda x:x.__setitem__('final_node_id','WRONG_BUT_UNIQUE_ID'))
        row=next(x for x in self.summarize_both(raw)['rows'] if x['trial_id']==t['id']);self.assertTrue(row['generator_semantic_success']);self.assertFalse(row['support_contract_success']);self.assertFalse(row['end_to_end_success'])
    def test_goal_only_cannot_pass_broken_proof(self):
        t=self.trial('baseline');raw=self.replace(self.raw,t['id']+'_rule_00',lambda x:x['node'].__setitem__('parents',[]));row=next(x for x in self.summarize_both(raw)['rows'] if x['trial_id']==t['id'])
        self.assertTrue(row['step_checks'][-1]['valid']);self.assertFalse(row['end_to_end_success'])
    def test_wrong_comparison_and_followed_lookup_is_not_success(self):
        def transform(op,body,raw):
            if op['stage']=='compare':
                data=d.data_from(body);outer=c.load(raw);value=max(data['values']) if data['direction']=='min' else min(data['values']);outer['message']['content']=c.wire({'target_value':value}).decode();return c.wire(outer)
            return raw
        rec,raw,_=f.response_set(self.p,transform);ss=self.summarize_both(raw,rec)
        self.assertEqual(ss['shared_selection']['success'],0);self.assertTrue(all(x['outcome']['success']==0 for x in ss['cohorts']['new_topology']['groups']['end_to_end'].values()))
        self.assertTrue(all(x['generator_semantic_success'] is True for x in ss['rows']))
    def test_null_lookup_skips_graph_not_filled_with_fake_failures(self):
        def transform(op,body,raw):
            if op['stage']=='select':
                outer=c.load(raw);outer['message']['content']='{"candidate_id":null}';return c.wire(outer)
            return raw
        rec,raw,_=f.response_set(self.p,transform);ss=self.summarize_both(raw,rec)
        self.assertEqual(len(raw),768);self.assertTrue(all(x['end_to_end_success'] is False for x in ss['rows']));self.assertTrue(all(x['generator_semantic_success'] is None for x in ss['rows']))
    def test_minimum_maximum_mappable_call_bounds(self):
        for mode,expected in [('min',10176),('max',10944)]:
            def transform(op,body,raw):
                # D 순서와 규칙 수 순서는 다른 구조가 있다. 호출 상한은 실제 규칙 수로 정한다.
                if op['stage']=='select':
                    data=d.data_from(body);cards=data['candidate_measurements']
                    chosen=(min if mode=='min' else max)(cards,key=lambda x:c.load(x['content'])['rule_count'])
                    outer=c.load(raw);outer['message']['content']=c.wire({'candidate_id':chosen['candidate_id']}).decode();return c.wire(outer)
                return raw
            rec,raw,_=f.response_set(self.p,transform);self.assertEqual(len(raw),expected)
    def test_unobserved_not_zero_depth(self):
        ss=self.summarize_both({}, {}, 'crashed');self.assertIsNone(ss['primary']['mean_delta']);self.assertTrue(all(x['actual_D'] is None for x in ss['rows']));self.assertEqual(ss['shared_selection']['unobserved'],384)
    def test_partial_batch_suppresses_overall_effect(self):
        ss=self.summarize_both(state='stopped');self.assertIsNone(ss['primary']['mean_delta']);self.assertTrue(all(x['mean_delta'] is None for x in ss['secondary']))
    def test_length_termination_not_logical_error(self):
        t=self.trial('baseline');raw=dict(self.raw);sid=t['id']+'_rule_00';outer=c.load(raw[sid]);outer['done_reason']='length';raw[sid]=c.wire(outer)
        row=next(x for x in self.summarize_both(raw)['rows'] if x['trial_id']==t['id']);self.assertEqual(row['step_checks'][1]['status'],'length_termination');self.assertIsNone(row['generator_semantic_success'])
    def test_schema_failure_is_observed_model_failure(self):
        t=self.trial('atom_alias');raw=dict(self.raw);sid=t['id']+'_facts';outer=c.load(raw[sid]);outer['message']['content']='{"nodes": "bad"}';raw[sid]=c.wire(outer)
        row=next(x for x in self.summarize_both(raw)['rows'] if x['trial_id']==t['id']);self.assertFalse(row['initial_fact_success']);self.assertFalse(row['end_to_end_success'])
    def test_first_error_and_risk_set_include_facts_id_gate(self):
        t=self.trial('short_uniform');raw=self.replace(self.raw,t['id']+'_facts',lambda x:x['nodes'][0].__setitem__('id','UNASSIGNED'))
        ss=self.summarize_both(raw);diag=collect(self.p,self.req,raw,ss['rows'])
        item=next(x for x in diag['first_failures'] if x['trial_id']==t['id']);self.assertEqual(item['stage'],'facts');self.assertEqual(item['first_error_class'],'facts_id_contract')
        risk=next(x for x in diag['step_risk_sets'] if x['arm']=='short_uniform' and x['rule_position']==0);self.assertEqual(risk['eligible'],383)
    def test_diagnostic_usage_shared_once(self):
        diag=collect(self.p,self.req,self.raw,self.summary['rows']);self.assertEqual(diag['groups']['shared_selection']['requests'],768)
        for arm in d.ARMS:self.assertEqual(diag['groups'][arm]['requests'],2448)
    def test_calibration_expected_62400(self):
        result=calibration();self.assertEqual((result['passed'],result['facts_cases'],result['rule_cases'],result['graph_cases']),(62400,9216,47040,6144))
    def test_independent_tallies_reject_changed_group(self):
        ss=deepcopy(self.summary);ss['cohorts']['new_topology']['groups']['end_to_end']['atom_alias']['bidirectional']['success']=63
        with self.assertRaises(ValueError):check_aggregate(self.p,ss['rows'],ss,'complete')
    def test_independent_tallies_reject_changed_primary(self):
        ss=deepcopy(self.summary);ss['primary']['mean_delta']=0.1
        with self.assertRaises(ValueError):check_aggregate(self.p,ss['rows'],ss,'complete')
    def test_nonfinite_and_duplicate_json_rejected(self):
        for raw in ('{"x":NaN}','{"x":1,"x":2}','{"x":1e999}'):
            with self.subTest(raw=raw),self.assertRaises(ValueError):c.load(raw)
