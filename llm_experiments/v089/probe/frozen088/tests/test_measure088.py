from pathlib import Path
from copy import deepcopy
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core088 as c,design088 as d,audit088 as a,fixtures088 as f,rows088 as r,audit_rows088 as ar,tables088 as tb,diagnostics088 as dg
from calibrate088 import calibration
from rows087 import rule_check
from audit_rows087 import step_check

class Measurement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p=f.plan();cls.rec,cls.raw,cls.req=f.response_set(cls.p);cls.rs,cls.st,cls.us=r.main_rows(cls.p,cls.rec,cls.raw)
        cls.s=tb.aggregate(cls.p,cls.rs,cls.st,cls.us,'complete')
    def test_full_synthetic_count(self):self.assertEqual(len(self.raw),3136)
    def test_all_independent_requests(self):
        for o in self.p['slots']:
            skip,raw=a.expected_request(self.p,o,self.raw)
            if o['id']in self.req:self.assertIsNone(skip);self.assertEqual(raw,self.req[o['id']])
            else:self.assertEqual(skip,self.rec[o['id']]['reason'])
    def test_independent_semantics_all_944(self):self.assertTrue(c.exact((self.rs,self.st,self.us),ar.independent_rows(self.p,self.rec,self.raw)))
    def test_expected_phase_counts(self):
        expected={'rename_probe':(140,None),'continuation':(32,16),'end_to_end':(128,64)}
        for phase,(n,np)in expected.items():
            for arm,g in self.s['groups'][phase].items():
                self.assertEqual(g['outcome']['success'],n)
                if np is not None:self.assertEqual(g['bidirectional']['success'],np)
        self.assertEqual(self.s['shared_selection']['planned'],128);self.assertEqual(self.s['shared_selection']['success'],128)
    def test_primary_and_interaction_zero_oracle(self):self.assertEqual(self.s['primary']['mean_delta'],0);self.assertEqual(self.s['interaction']['mean_delta'],0)
    def test_expected_primary_effect_when_one_condition_fails(self):
        rows=deepcopy(self.rs);target=next(x for x in rows if x['phase']=='continuation'and x['generator_arm']=='long_mixed');target['continuation_success']=False
        ss=tb.aggregate(self.p,rows,self.st,self.us,'complete');self.assertEqual(ss['primary']['mean_delta'],1/16)
        self.assertEqual(ss['primary']['improved'],1)
    def test_unobserved_primary_not_zero(self):
        rr,st,u=r.main_rows(self.p,{},{});ss=tb.aggregate(self.p,rr,st,u,'crashed')
        self.assertIsNone(ss['primary']['mean_delta']);self.assertEqual(ss['groups']['continuation']['short_mixed']['outcome']['unobserved'],32)
    def test_short_long_prefix_alpha_invariance(self):
        for anchor in d.anchors():
            old=d.data_from(anchor['request_body'])
            for style in ('short','legacy_long'):
                h,_=d.rename_history(old['history'],style);body=d.render_body(anchor['request_body'],dict(old,history=h));obj=c.load(c.load(f.answer(body))['message']['content'])['node'];before=d.history_nodes(h)
                self.assertTrue(rule_check(old['problem'],before,obj,anchor['rule_id'])['valid'])
    def test_atom_instead_of_existing_node_id_rejected(self):
        t=next(t for t in self.p['trials']if t['phase']=='rename_probe'and t['generator_arm']=='legacy_long');o=next(o for o in self.p['slots']if o['trial_id']==t['id'])
        da=d.data_from(c.load(self.req[o['id']]));ns=d.history_nodes(da['history']);obj=c.load(c.load(self.raw[o['id']])['message']['content'])['node']
        by={n['id']:n['atom']for n in ns};obj['parents']=[by[x]for x in obj['parents']];snapshot=deepcopy(obj)
        v=rule_check(da['problem'],ns,obj,da['operation']['requested_rule_id']);self.assertFalse(v['valid']);self.assertIn('missing_parent',v['error_codes']);self.assertEqual(snapshot,obj)
        self.assertEqual(v,step_check(da['problem'],ns,obj,da['operation']['requested_rule_id']))
    def test_actual_second_step_sees_first_new_allocated_id(self):
        for t in self.p['trials']:
            if t['phase']!='continuation':continue
            ops=[o for o in self.p['slots']if o['trial_id']==t['id']]
            da=d.data_from(c.load(self.req[ops[1]['id']]));first=c.load(c.load(self.raw[ops[0]['id']])['message']['content'])['node']
            self.assertIn(first,d.history_nodes(da['history']));self.assertEqual(first['id'],d.continuation_seed(t)[1][0])
    def test_first_rule_success_does_not_imply_rollout_success(self):
        raw=dict(self.raw);t=next(t for t in self.p['trials']if t['phase']=='continuation'and t['generator_arm']=='long_uniform');ops=[o for o in self.p['slots']if o['trial_id']==t['id']]
        oid=ops[1]['id'];x=c.load(raw[oid]);obj=c.load(x['message']['content']);obj['node']['parents']=['NOT_A_NODE'];x['message']['content']=c.wire(obj).decode();raw[oid]=c.wire(x)
        rr,st,u=r.main_rows(self.p,self.rec,raw);row=next(x for x in rr if x['trial_id']==t['id']);self.assertTrue(row['step_checks'][0]['valid']);self.assertFalse(row['continuation_success'])
    def test_invalid_id_contract_distinct_from_semantics(self):
        raw=dict(self.raw);t=next(t for t in self.p['trials']if t['phase']=='continuation');ops=[o for o in self.p['slots']if o['trial_id']==t['id']]
        rid=ops[-2]['id'];fid=ops[-1]['id'];x=c.load(raw[rid]);obj=c.load(x['message']['content']);obj['node']['id']='valid_but_not_allocated';x['message']['content']=c.wire(obj).decode();raw[rid]=c.wire(x)
        x=c.load(raw[fid]);x['message']['content']=c.wire({'final_node_id':'valid_but_not_allocated'}).decode();raw[fid]=c.wire(x)
        rr,_,_=r.main_rows(self.p,self.rec,raw);row=next(x for x in rr if x['trial_id']==t['id'])
        self.assertTrue(row['generator_semantic_success']);self.assertFalse(row['support_contract_success']);self.assertFalse(row['continuation_success'])
        ia,_,_=ar.independent_rows(self.p,self.rec,raw);self.assertEqual(row,next(x for x in ia if x['trial_id']==t['id']))
    def test_wrong_comparison_does_not_become_end_to_end_success(self):
        raw=dict(self.raw);t=next(t for t in self.p['trials']if t['phase']=='end_to_end');sid=t['comparison_slot_id'];x=c.load(raw[sid]);x['message']['content']=c.wire({'target_value':99}).decode();raw[sid]=c.wire(x)
        rr,_,_=r.main_rows(self.p,self.rec,raw);row=next(x for x in rr if x['trial_id']==t['id'])
        self.assertFalse(row['end_to_end_success']);self.assertTrue(row['target_graph_success_without_trace'])
    def test_same_facts_request_in_monitor(self):
        for u in self.p['protocol']['units']:self.assertEqual(self.req[u['unit_id']+'_baseline_facts'],self.req[u['unit_id']+'_allocated_id_facts'])
    def test_reference_and_full_endpoints_not_combined(self):
        self.assertNotIn('end_to_end_success',next(x for x in self.rs if x['phase']=='continuation'))
        self.assertNotIn('continuation_success',next(x for x in self.rs if x['phase']=='end_to_end'))
    def test_local_no_fixed_output_id(self):
        for t in self.p['trials']:
            if t['phase']!='rename_probe':continue
            o=next(o for o in self.p['slots']if o['trial_id']==t['id']);b=c.load(self.req[o['id']]);self.assertNotIn('enum',b['format']['properties']['node']['properties']['id'])
    def test_rules_not_parents_forced_in_continuation(self):
        for t in self.p['trials']:
            if t['phase']!='continuation':continue
            o=next(o for o in self.p['slots']if o['trial_id']==t['id']);b=c.load(self.req[o['id']]);sc=b['format']['properties']['node']['properties'];ref=d.anchor_for(t)['request_body']['format']['properties']['node']['properties']
            for key in ('parents','atom','rule'):self.assertEqual(sc[key],ref[key])
    def test_calibration_expected_1504(self):
        out=calibration();self.assertEqual(out['passed'],1504);self.assertEqual(out['rule_cases'],1120);self.assertEqual(out['graph_cases'],384)
    def test_bad_json_keys_rejected(self):
        with self.assertRaises(ValueError):c.load('{"x":1,"x":2}')
    def test_nonfinite_json_rejected(self):
        for raw in ('{"x":NaN}','{"x":1e999}'):
            with self.subTest(raw=raw),self.assertRaises(ValueError):c.load(raw)
    def test_diagnostics_long_prefixes_present(self):
        out=dg.collect(self.p,self.req,self.raw,self.rs);states=[x for x in out['input_states']if x['phase']=='rename_probe'and x['arm']=='legacy_long']
        self.assertEqual(len(states),140);self.assertTrue(all(x['prior_long_ids']>0 for x in states))
    def test_shared_selection_requests_count_once(self):
        out=dg.collect(self.p,self.req,self.raw,self.rs);groups=[g for k,g in out['groups'].items()if '/shared_selection/'in k];self.assertEqual(sum(g['requests']for g in groups),256)
    def test_parent_count_is_not_semantics(self):
        anchor=next(a for a in d.anchors()if a['rule_id']=='j64');da=d.data_from(anchor['request_body']);ns=d.history_nodes(da['history']);n=c.load(c.load(f.answer(anchor['request_body']))['message']['content'])['node'];by={x['atom']:x['id']for x in ns};n['parents']=[by['C87'],by['C77']]
        v=rule_check(da['problem'],ns,n,'j64');self.assertTrue(v['parent_count_valid']);self.assertFalse(v['valid'])
    def test_ancestor_still_required_as_direct_parent(self):
        anchor=next(a for a in d.anchors()if a['rule_id']=='o51');da=d.data_from(anchor['request_body']);ns=d.history_nodes(da['history']);n=c.load(c.load(f.answer(anchor['request_body']))['message']['content'])['node'];by={x['atom']:x['id']for x in ns};n['parents']=[by['H02'],by['H44']]
        v=rule_check(da['problem'],ns,n,'o51');self.assertFalse(v['valid']);self.assertEqual(v['missing_direct_atoms'],['H15'])

    def test_initial_scope_reports_same_output_id_not_offset_confound(self):
        out=dg.collect(self.p,self.req,self.raw,self.rs);pairs=out['continuation_scope_pairs']
        self.assertEqual(len(pairs),64);self.assertTrue(all(x['same_current_output_id'] and x['same_atom_sequence']for x in pairs))
        self.assertEqual(len(out['continuation_initial_conditions']),128)
    def test_diagnostic_error_codes_not_silently_empty(self):
        raw=dict(self.raw);t=next(t for t in self.p['trials']if t['phase']=='continuation');o=next(o for o in self.p['slots']if o['trial_id']==t['id'])
        x=c.load(raw[o['id']]);obj=c.load(x['message']['content']);obj['node']['parents']=['NOT_A_NODE'];x['message']['content']=c.wire(obj).decode();raw[o['id']]=c.wire(x)
        rr,_,_=r.main_rows(self.p,self.rec,raw);diag=dg.collect(self.p,self.req,raw,rr);failure=next(x for x in diag['failures']if x['trial_id']==t['id'])
        self.assertIn('missing_parent',failure['graph_errors'])
    def test_partial_batch_suppresses_whole_effect_even_if_known_failures(self):
        ss=tb.aggregate(self.p,self.rs,self.st,self.us,'crashed');self.assertIsNone(ss['primary']['mean_delta']);self.assertIsNone(ss['interaction']['mean_delta'])
