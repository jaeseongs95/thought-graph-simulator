from pathlib import Path
from copy import deepcopy
from collections import Counter
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core087 as c,design087 as d,audit087 as a,fixtures087 as f,rows087 as r,audit_rows087 as ar,tables087 as tables
from calibrate087 import calibration

class Measurement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p=f.plan();cls.records,cls.raws,cls.requests=f.response_set(cls.p);cls.rows,cls.states,cls.usage=r.main_rows(cls.p,cls.records,cls.raws);cls.summary=tables.aggregate(cls.p,cls.rows,cls.states,cls.usage,'complete')
    def test_full_synthetic_count(self):self.assertEqual(len(self.raws),4080)
    def test_independent_requests_all_4080(self):
        for op in self.p['slots']:
            skip,raw=a.expected_request(self.p,op,self.raws)
            if op['id']in self.requests:self.assertIsNone(skip);self.assertEqual(raw,self.requests[op['id']])
            else:self.assertEqual(skip,self.records[op['id']]['reason'])
    def test_independent_semantics_all_1072(self):self.assertTrue(c.exact((self.rows,self.states,self.usage),ar.independent_rows(self.p,self.records,self.raws)))
    def test_expected_counts_not_just_verifier_agreement(self):
        for g in self.summary['groups'].values():
            for key,num in [('rule_probe_strict',140),('D_end_to_end',128),('D_bidirectional',64),('all_presentations',16)]:self.assertEqual(g[key]['successes'],num);self.assertEqual(g[key]['unmeasured'],0)
    def test_equal_factorial_effects_zero_in_oracle_fixture(self):self.assertTrue(all(e['equal_structure_mean']==0 for e in self.summary['factorial_effects'].values()))
    def test_shared_selection_usage_not_quadrupled(self):self.assertEqual(self.summary['usage_by_phase_and_arm']['shared_selection']['observed_calls'],256);self.assertEqual(self.summary['shared_selection']['assigned'],128)
    def test_fact_requests_identical_across_arms(self):
        for unit in self.p['protocol']['units']:
            vals=[self.requests[unit['unit_id']+'_'+arm+'_facts']for arm in self.p['protocol']['factors']];self.assertEqual(len(set(vals)),1)
    def test_no_premise_repair(self):
        anchor=d.anchors()[-1];data=f.data(anchor['request_body']);nodes=[]
        for h in data['history']:
            v=c.load(h['content']);nodes+=v['nodes']if 'nodes'in v else[v['node']]
        n=c.load(c.load(f.answer(anchor['request_body']))['message']['content'])['node'];n['parents'].pop();before=deepcopy(n)
        self.assertFalse(r.rule_check(data['problem'],nodes,n,anchor['rule_id'])['valid']);self.assertEqual(n,before)
    def test_parent_count_correct_but_wrong_atom_rejected(self):
        aa=next(x for x in d.anchors()if x['rule_id']=='j64');da=f.data(aa['request_body']);ns=[]
        for h in da['history']:
            x=c.load(h['content']);ns+=x['nodes']if 'nodes'in x else[x['node']]
        rule=da['operation']['requested_rule'];by={n['atom']:n['id']for n in ns};n=c.load(c.load(f.answer(aa['request_body']))['message']['content'])['node'];n['parents']=[by['C87'],by['C77']]
        v=r.rule_check(da['problem'],ns,n,'j64');self.assertTrue(v['parent_count_valid']);self.assertFalse(v['valid']);self.assertIn('C54',v['missing_direct_atoms']);self.assertEqual(v,ar.step_check(da['problem'],ns,n,'j64'))
    def test_ancestor_direct_premise_cannot_be_omitted(self):
        aa=next(x for x in d.anchors()if x['rule_id']=='o51');da=f.data(aa['request_body']);ns=[]
        for h in da['history']:
            x=c.load(h['content']);ns+=x['nodes']if 'nodes'in x else[x['node']]
        by={n['atom']:n['id']for n in ns};n=c.load(c.load(f.answer(aa['request_body']))['message']['content'])['node'];n['parents']=[by['H02'],by['H44']]
        v=r.rule_check(da['problem'],ns,n,'o51');self.assertFalse(v['valid']);self.assertEqual(v['missing_direct_atoms'],['H15'])
    def test_calibration_500_known_verdicts(self):out=calibration();self.assertEqual(out['passed'],500);self.assertEqual(out['failures'],0)
    def test_missing_calls_remain_unmeasured(self):
        rows,st,u=r.main_rows(self.p,{},{});s=tables.aggregate(self.p,rows,st,u,'crashed');self.assertIsNone(s['primary_effect']['equal_structure_mean']);self.assertEqual(s['groups']['baseline']['D_end_to_end']['unmeasured'],128)
    def test_known_pair_contrast_direction(self):self.assertEqual(tables.contrast([False,True,True,None],[True,False,True,False]),{'both_success':1,'left_only':1,'right_only':1,'both_failure':0,'not_comparable':1})
    def test_semantic_graph_correct_but_assigned_id_wrong_fails_trace(self):
        raws=dict(self.raws);t=next(t for t in self.p['trials']if t['phase']=='end_to_end'and t['generator_arm']=='allocated_id');path=next(rw['selected_rule_ids']for rw in self.rows if rw['trial_id']==t['id']);sid=t['id']+f'_rule_{len(path)-1:02d}';fid=t['id']+'_final'
        x=c.load(raws[sid]);obj=c.load(x['message']['content']);obj['node']['id']='other_fresh_identifier';x['message']['content']=c.wire(obj).decode();raws[sid]=c.wire(x)
        x=c.load(raws[fid]);x['message']['content']=c.wire({'final_node_id':'other_fresh_identifier'}).decode();raws[fid]=c.wire(x)
        rows,st,u=r.main_rows(self.p,self.records,raws);rw=next(rw for rw in rows if rw['trial_id']==t['id']);self.assertTrue(rw['generator_semantic_success']);self.assertFalse(rw['support_contract_success']);self.assertFalse(rw['end_to_end_success']);self.assertTrue(rw['target_graph_success_without_trace'])
        other,_,_=ar.independent_rows(self.p,self.records,raws);self.assertEqual(rw,next(v for v in other if v['trial_id']==t['id']))
    def test_wrong_comparison_even_if_goal_correct_fails_trace(self):
        raws=dict(self.raws);t=next(t for t in self.p['trials']if t['phase']=='end_to_end');sid=t['comparison_slot_id'];x=c.load(raws[sid]);obj=c.load(x['message']['content']);obj['target_value']=99;x['message']['content']=c.wire(obj).decode();raws[sid]=c.wire(x)
        rows,_,_=r.main_rows(self.p,self.records,raws);rw=next(v for v in rows if v['trial_id']==t['id']);self.assertFalse(rw['selection_success']);self.assertFalse(rw['end_to_end_success']);self.assertTrue(rw['target_graph_success_without_trace'])
    def test_probe_is_separate_from_end_to_end(self):self.assertEqual(len(self.summary['rule_probes']),560);self.assertEqual(len(self.summary['trials']),512);self.assertTrue(self.summary['rule_probe_is_not_end_to_end'])
    def test_duplicate_json_keys_rejected(self):
        with self.assertRaises(ValueError):c.load('{"x":1,"x":2}')
    def test_nan_rejected(self):
        with self.assertRaises(ValueError):c.load('{"x":NaN}')
    def test_unknown_output_numeric_not_replaced(self):
        op=next(o for o in self.p['slots']if o['stage']=='compare');v=f.answer(d.request_for(self.p,op,{}),'compare_outside');self.assertEqual(c.load(c.load(v)['message']['content'])['target_value'],99)
    def test_no_independent_structure_inflation(self):self.assertEqual(self.summary['distinct_observed_structures'],8);self.assertEqual(self.summary['new_holdout_structures'],0)
