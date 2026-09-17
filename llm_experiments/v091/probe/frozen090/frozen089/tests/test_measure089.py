from pathlib import Path
from copy import deepcopy
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core089 as c,design089 as d,audit089 as a,fixtures089 as f,rows089 as r,audit_rows089 as ar,tables089 as tb,diagnostics089 as dg
from calibrate089 import calibration
from rows087 import rule_check
from audit_rows087 import step_check

class Measurement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p=f.plan();cls.rec,cls.raw,cls.req=f.response_set(cls.p)
        cls.rs,cls.st,cls.us=r.main_rows(cls.p,cls.rec,cls.raw)
        cls.s=tb.aggregate(cls.p,cls.rs,cls.st,cls.us,'complete')
    def first_trial(self,arm='long__long'):
        return next(t for t in self.p['trials'] if t['phase']=='continuation' and t['generator_arm']==arm)
    def ops(self,t):return [o for o in self.p['slots'] if o['trial_id']==t['id']]
    def test_full_synthetic_count(self):self.assertEqual(len(self.raw),3824)
    def test_every_independent_request_byte_identical(self):
        for op in self.p['slots']:
            skip,raw=a.expected_request(self.p,op,self.raw)
            if op['id'] in self.req:self.assertIsNone(skip);self.assertEqual(raw,self.req[op['id']])
            else:self.assertEqual(skip,self.rec[op['id']]['reason'])
    def test_all_640_trial_semantics_agree(self):self.assertTrue(c.exact((self.rs,self.st,self.us),ar.independent_rows(self.p,self.rec,self.raw)))
    def test_phase_denominators(self):
        for arm,g in self.s['groups']['continuation'].items():
            self.assertEqual(g['outcome']['success'],32);self.assertEqual(g['bidirectional']['success'],16)
        g=self.s['groups']['end_to_end']['baseline'];self.assertEqual(g['outcome']['success'],128);self.assertEqual(g['bidirectional']['success'],64);self.assertEqual(g['four_display']['success'],16)
        self.assertEqual(self.s['shared_selection']['planned'],128)
    def test_primary_zero_oracle(self):self.assertEqual(self.s['primary']['mean_delta'],0)
    def test_primary_one_failed_trajectory_is_one_half_family_pair(self):
        rs=deepcopy(self.rs);next(x for x in rs if x['phase']=='continuation' and x['generator_arm']=='atom_alias__short')['continuation_success']=False
        ss=tb.aggregate(self.p,rs,self.st,self.us,'complete');self.assertEqual(ss['primary']['mean_delta'],1/32)
        self.assertEqual(ss['primary']['components'][0]['mean_delta'],1/16)
    def test_primary_direction_not_reversed(self):
        rs=deepcopy(self.rs);next(x for x in rs if x['phase']=='continuation' and x['generator_arm']=='short__short')['continuation_success']=False
        self.assertEqual(tb.aggregate(self.p,rs,self.st,self.us,'complete')['primary']['mean_delta'],-1/32)
    def test_structure_equal_leave_one_out(self):
        rs=deepcopy(self.rs)
        for x in rs:
            if x['phase']=='continuation' and x['problem_id']=='U01' and x['generator_arm'] in ('atom_alias__short','atom_alias__long'):x['continuation_success']=False
        result=tb.aggregate(self.p,rs,self.st,self.us,'complete')['primary'];self.assertEqual(result['mean_delta'],1/8)
        self.assertEqual(next(x['mean_delta'] for x in result['leave_one_structure_out'] if x['omitted_structure']=='U01'),0)
    def test_unobserved_is_not_failure(self):
        rows,st,u=r.main_rows(self.p,{},{});ss=tb.aggregate(self.p,rows,st,u,'crashed')
        self.assertIsNone(ss['primary']['mean_delta'])
        for g in ss['groups']['continuation'].values():self.assertEqual(g['outcome'],dict(planned=32,success=0,failure=0,unobserved=32))
    def test_partial_always_suppresses_effect(self):
        ss=tb.aggregate(self.p,self.rs,self.st,self.us,'crashed');self.assertIsNone(ss['primary']['mean_delta']);self.assertEqual(ss['primary']['leave_one_structure_out'],[])
        self.assertTrue(all(x['mean_delta'] is None for x in ss['secondary']))
    def test_second_request_sees_actual_first_reply(self):
        for t in self.p['trials']:
            if t['phase']!='continuation':continue
            ops=self.ops(t);data=d.data_from(c.load(self.req[ops[1]['id']]));node=c.load(c.load(self.raw[ops[0]['id']])['message']['content'])['node']
            self.assertIn(node,d.history_nodes(data['history']))
    def test_alias_substituted_for_numeric_parent_is_rejected(self):
        t=self.first_trial();op=self.ops(t)[1];data=d.data_from(c.load(self.req[op['id']]));nodes=d.history_nodes(data['history']);node=c.load(c.load(self.raw[op['id']])['message']['content'])['node']
        mapping={n['id']:n['atom'] for n in nodes};node['parents']=[mapping[x] for x in node['parents']];before=deepcopy(node)
        x=rule_check(data['problem'],nodes,node,data['operation']['requested_rule_id'])
        self.assertIn('missing_parent',x['error_codes']);self.assertEqual(node,before);self.assertEqual(x,step_check(data['problem'],nodes,node,data['operation']['requested_rule_id']))
    def test_first_step_success_not_rollout_success(self):
        raw=dict(self.raw);t=self.first_trial();ops=self.ops(t);sid=ops[1]['id'];outer=c.load(raw[sid]);obj=c.load(outer['message']['content']);obj['node']['parents']=['NO_NODE'];outer['message']['content']=c.wire(obj).decode();raw[sid]=c.wire(outer)
        rows,_,_=r.main_rows(self.p,self.rec,raw);row=next(x for x in rows if x['trial_id']==t['id']);self.assertTrue(row['step_checks'][0]['valid']);self.assertFalse(row['continuation_success'])
    def test_current_id_contract_is_distinct_from_graph_semantics(self):
        raw=dict(self.raw);t=self.first_trial();ops=self.ops(t);sid=ops[-2]['id'];fid=ops[-1]['id']
        outer=c.load(raw[sid]);obj=c.load(outer['message']['content']);obj['node']['id']='valid_but_unallocated';outer['message']['content']=c.wire(obj).decode();raw[sid]=c.wire(outer)
        outer=c.load(raw[fid]);outer['message']['content']=c.wire({'final_node_id':'valid_but_unallocated'}).decode();raw[fid]=c.wire(outer)
        rows,_,_=r.main_rows(self.p,self.rec,raw);row=next(x for x in rows if x['trial_id']==t['id'])
        self.assertTrue(row['generator_semantic_success']);self.assertFalse(row['support_contract_success']);self.assertFalse(row['continuation_success'])
        other,_,_=ar.independent_rows(self.p,self.rec,raw);self.assertEqual(row,next(x for x in other if x['trial_id']==t['id']))
    def test_wrong_comparison_not_laundered_by_correct_graph(self):
        raw=dict(self.raw);t=next(x for x in self.p['trials'] if x['phase']=='end_to_end');sid=t['comparison_slot_id']
        x=c.load(raw[sid]);x['message']['content']=c.wire({'target_value':99}).decode();raw[sid]=c.wire(x)
        rows,_,_=r.main_rows(self.p,self.rec,raw);row=next(x for x in rows if x['trial_id']==t['id'])
        self.assertFalse(row['end_to_end_success']);self.assertTrue(row['target_graph_success_without_trace'])
    def test_reference_and_fresh_endpoints_are_separate(self):
        self.assertNotIn('end_to_end_success',next(x for x in self.rs if x['phase']=='continuation'))
        self.assertNotIn('continuation_success',next(x for x in self.rs if x['phase']=='end_to_end'))
    def test_ancestor_is_still_a_direct_premise(self):
        op=next(o for o in self.p['slots'] if o['stage']=='rule' and o['id'] in self.req and d.data_from(c.load(self.req[o['id']]))['operation']['requested_rule_id']=='o51')
        data=d.data_from(c.load(self.req[op['id']]));nodes=d.history_nodes(data['history']);node=c.load(c.load(self.raw[op['id']])['message']['content'])['node'];mapping={x['atom']:x['id'] for x in nodes}
        node['parents']=[mapping['H02'],mapping['H44']];v=rule_check(data['problem'],nodes,node,'o51')
        self.assertFalse(v['valid']);self.assertEqual(v['missing_direct_atoms'],['H15'])
    def test_same_parent_count_can_be_semantically_wrong(self):
        for op in self.p['slots']:
            if op['stage']!='rule' or op['id'] not in self.req:continue
            data=d.data_from(c.load(self.req[op['id']]));nodes=d.history_nodes(data['history']);node=c.load(c.load(self.raw[op['id']])['message']['content'])['node']
            outsiders=[x['id'] for x in nodes if x['atom'] not in data['operation']['requested_rule']['premises']]
            if outsiders:
                node['parents'][0]=outsiders[0];v=rule_check(data['problem'],nodes,node,data['operation']['requested_rule_id'])
                self.assertTrue(v['parent_count_valid']);self.assertIn('premise_counter_mismatch',v['error_codes']);break
        else:self.fail('대조 전제 사례 없음')
    def test_allocation_invariance_128_matched_sets(self):
        out=dg.collect(self.p,self.req,self.raw,self.rs);self.assertEqual(len(out['allocation_invariance']),128)
        self.assertTrue(all(x['same_initial_atom_order'] and x['same_current_output_id'] for x in out['allocation_invariance']))
    def test_risk_sets_exclude_broken_prefixes(self):
        raw=dict(self.raw);t=self.first_trial();ops=self.ops(t);sid=ops[0]['id'];x=c.load(raw[sid]);obj=c.load(x['message']['content']);obj['node']['parents']=['NO_NODE'];x['message']['content']=c.wire(obj).decode();raw[sid]=c.wire(x)
        rows,_,_=r.main_rows(self.p,self.rec,raw);diag=dg.collect(self.p,self.req,raw,rows)
        nextstep=next(x for x in diag['step_risk_sets'] if x['arm']=='long__long' and x['rule_position']==1)
        self.assertEqual(nextstep['eligible'],31)
        first=next(x for x in diag['first_failures'] if x['trial_id']==t['id']);self.assertIn('missing_parent',first['errors'])
    def test_shared_selection_256_calls(self):
        out=dg.collect(self.p,self.req,self.raw,self.rs);self.assertEqual(sum(g['requests'] for k,g in out['groups'].items() if '/shared_selection/' in k),256)
    def test_calibration_expected_cases(self):
        out=calibration();self.assertEqual((out['passed'],out['rule_cases'],out['graph_cases']),(22160,19600,2560));self.assertEqual(out['actual_qwen_calls'],0)
    def test_duplicate_json_keys_rejected(self):
        with self.assertRaises(ValueError):c.load('{"x":1,"x":2}')
    def test_nonfinite_numbers_rejected(self):
        for x in ('{"x":NaN}','{"x":1e999}'):
            with self.subTest(x=x),self.assertRaises(ValueError):c.load(x)
