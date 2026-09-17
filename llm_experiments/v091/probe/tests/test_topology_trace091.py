from pathlib import Path
from copy import deepcopy
import unittest,sys,json,os,zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core091 as c,design091 as d,fixtures091 as f,audit_corpus091 as ac,topology091 as top
from diagnostics091 import trace_features,normalize_source_ids_for_audit,collect
from report091 import summarize
from audit_metrics091 import check_aggregate
from audit091 import validate_protocol


class TopologyAndTrace(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p,cls.rec,cls.raw,cls.req=f.oracle_cache()
        cls.corpus=c.load((c.ROOT/'data/corpus.json').read_bytes())
        cls.old=c.load((c.ROOT/'data/protocol_v090_snapshot.json').read_bytes())
        cls.summary=summarize(cls.p,cls.rec,cls.raw,'complete')
    def test_independent_corpus_topology_check(self):
        result=ac.validate(self.corpus,self.old);self.assertEqual(result['new_routes'],16);self.assertEqual(result['independent_isomorphism_comparisons'],744)
    def test_corpus_reproducible_without_model(self):
        import build_corpus091 as build
        self.assertEqual(build.build(),self.corpus)
    def test_all_relabels_are_invertible_and_same_D_W(self):
        ps={p['id']:p for p in self.corpus['problems']}
        for m in self.corpus['renamings']:
            inv=top.inverse_rename(ps[m['renamed']],m['atom_map'],m['rule_map']);inv['id']=m['original'];self.assertEqual(inv,ps[m['original']])
            for label in self.old['reference_conditions']:
                self.assertEqual(top.signature(ps[m['original']],self.corpus['reference_plans'][m['original']][label]),top.signature(ps[m['renamed']],self.corpus['reference_plans'][m['renamed']][label]))
    def test_new_routes_not_old_signatures_or_each_other(self):
        values=[r['signature'] for r in self.corpus['novel_acceptance']]
        self.assertEqual(len(set(values)),16);self.assertFalse(set(values)&set(self.corpus['prior_bank']['route_signatures']))
    def test_relabel_semantic_change_rejected(self):
        x=deepcopy(self.corpus);p=next(p for p in x['problems'] if p['id']=='U01_R1');p['rules'][0]['premises']=p['facts'][:1]
        with self.assertRaises(ValueError):ac.validate(x,self.old)
    def test_duplicate_atom_extension_rejected(self):
        x=deepcopy(self.corpus);p=next(p for p in x['problems'] if p['id']=='V01');p['rules'][0]['conclusion']=p['facts'][0]
        with self.assertRaises((ValueError,KeyError)):ac.validate(x,self.old)
    def test_physical_and_logical_id_confusion_rejected(self):
        x=deepcopy(self.corpus);x['units'][1]['input_unit_id']='changed_trace'
        with self.assertRaises(ValueError):ac.validate(x,self.old)
    def test_primary_cannot_switch_to_known_population(self):
        x=c.spec();x['primary_cohort']='known_original'
        with self.assertRaises(ValueError):validate_protocol(x)
    def test_cohort_rows_pairs_not_pooled(self):
        self.assertEqual(len(self.summary['rows']),1536);self.assertEqual(len(self.summary['pairs']),768)
        for sub in self.summary['cohorts'].values():
            self.assertEqual(sub['shared_selection']['planned'],128)
            for g in sub['groups']['end_to_end'].values():self.assertEqual(g['outcome']['planned'],128)
    def test_known_failures_do_not_change_holdout_primary(self):
        rows=deepcopy(self.summary['rows'])
        for r in rows:
            if r['cohort']!='new_topology' and r['generator_arm']=='atom_alias':r['end_to_end_success']=False
        import tables091
        ss=tables091.aggregate(self.p,rows,{}, {},'complete');check_aggregate(self.p,rows,ss,'complete')
        self.assertEqual(ss['primary']['mean_delta'],0);self.assertEqual(ss['cohorts']['known_original']['primary']['mean_delta'],-1)
    def test_renaming_primary_negative_when_only_renamed_alias_fails(self):
        rows=deepcopy(self.summary['rows'])
        for r in rows:
            if r['cohort']=='known_renamed' and r['generator_arm']=='atom_alias':r['end_to_end_success']=False
        import tables091
        ss=tables091.aggregate(self.p,rows,{}, {},'complete');check_aggregate(self.p,rows,ss,'complete')
        item=next(x for x in ss['renaming_contrasts'] if x['generator_arm']=='atom_alias');self.assertEqual(item['mean_delta'],-1)
    def test_original_and_relabel_have_same_trace_ids(self):
        for t in self.p['trials']:
            if t['cohort']!='known_original':continue
            other=next(x for x in self.p['trials'] if x['cohort']=='known_renamed' and x['topology_id']==t['topology_id'] and x['seed']==t['seed'] and x['condition']==t['condition'] and x['presentation_id']==t['presentation_id'] and x['generator_arm']==t['generator_arm'])
            self.assertEqual(t['input_unit_id'],other['input_unit_id']);self.assertNotEqual(t['id'],other['id'])
    def test_cohort_metadata_not_visible_to_model(self):
        forbidden={'cohort','topology_id','renaming_id','replicate_id','execution_id','sampling_seed','presentation_id'}
        for raw in self.req.values():
            data=d.data_from(c.load(raw));self.assertFalse(forbidden&set(data))
            self.assertNotIn('_R1',data.get('problem',{}).get('id',''))
    def test_source_hash_normalization_keeps_all_response_content(self):
        for op in self.p['slots']:
            if op['stage'] not in ('facts','rule','final') or op['id'] not in self.req:continue
            raw=self.req[op['id']];before=d.data_from(c.load(raw));after=d.data_from(c.load(normalize_source_ids_for_audit(raw)))
            self.assertEqual(before['selection_original']['content'],after['selection_original']['content'])
            self.assertEqual([h['content'] for h in before['history']],[h['content'] for h in after['history']])
    def specimen(self,parents,required=('I91','I43')):
        nodes=[dict(id=x,atom=x,parents=[],rule=None) for x in ('I77','I11','I91')]
        previous=dict(id='I43',atom='I43',rule='p96',parents=['I77','I11'])
        current=dict(id='I32',atom='I32',rule='p22',parents=list(parents))
        data=dict(history=[dict(content=c.wire(dict(nodes=nodes)).decode()),dict(content=c.wire(dict(node=previous)).decode())],operation=dict(requested_rule=dict(id='p22',premises=list(required),conclusion='I32')))
        return data,dict(node=current)
    def test_u07_stale_parent_pattern_and_ancestor_diagnostic(self):
        data,obj=self.specimen(['I77','I11']);r=trace_features(data,obj,1,False,True)
        self.assertTrue(r['current_rule_correct_but_parents_stale']);self.assertTrue(r['wrong_parents_are_ancestors_of_required_parent'])
    def test_legitimate_same_parents_not_stale_error(self):
        data,obj=self.specimen(['I77','I11'],('I77','I11'));r=trace_features(data,obj,1,True,True)
        self.assertTrue(r['parents_equal_previous_rule']);self.assertFalse(r['current_rule_correct_but_parents_stale']);self.assertFalse(r['incorrect_prior_parents_reuse'])
    def test_non_parent_error_with_correct_reused_parents_not_stale(self):
        data,obj=self.specimen(['I77','I11'],('I77','I11'))
        obj['node']['id']='I43'  # 중복 node ID 오류지만 직접 전제는 정확하다.
        value=trace_features(data,obj,1,False,True)
        self.assertTrue(value['parent_atoms_match_current_rule'])
        self.assertFalse(value['current_rule_correct_but_parents_stale'])
        self.assertFalse(value['incorrect_prior_parents_reuse'])
    def test_wrong_rule_not_called_current_rule_stale(self):
        data,obj=self.specimen(['I77','I11']);obj['node']['rule']='wrong';self.assertFalse(trace_features(data,obj,1,False,True)['current_rule_correct_but_parents_stale'])
    def test_empty_first_rule_after_facts(self):
        data,obj=self.specimen([]);data['history']=data['history'][:1]
        self.assertTrue(trace_features(data,obj,0,False,True)['first_rule_empty_after_facts'])
    def test_malformed_prior_history_does_not_crash_observational_diagnostic(self):
        data,obj=self.specimen(['I77','I11'])
        data['history'].insert(0,dict(content='{"nodes":[null,1,"bad",{"id":"x","atom":[],"parents":null}]}'))
        data['history'].insert(0,dict(content='[null]'))
        value=trace_features(data,obj,1,False,False)
        self.assertTrue(value['current_rule_correct_but_parents_stale'])
        self.assertFalse(value['prefix_valid_before'])
    def test_missing_validity_is_not_declared_stale_failure(self):
        data,obj=self.specimen(['I77','I11'])
        self.assertFalse(trace_features(data,obj,1,None,False)['current_rule_correct_but_parents_stale'])
    def test_no_diagnostic_posthoc_mutation(self):
        data,obj=self.specimen(['I77','I11']);before=deepcopy((data,obj));trace_features(data,obj,1,False,True);self.assertEqual((data,obj),before)
    def test_full_valid_oracle_does_not_create_stale_errors(self):
        diag=collect(self.p,self.req,self.raw,self.summary['rows'])
        self.assertEqual(len(diag['trace_diagnostics']),6720)
        self.assertTrue(all(not x['current_rule_correct_but_parents_stale'] for x in diag['trace_diagnostics']))
    def test_partial_primary_unavailable_not_zero(self):
        rows=deepcopy(self.summary['rows'])
        for r in rows:r['end_to_end_success']=None
        import tables091
        ss=tables091.aggregate(self.p,rows,{}, {},'crashed')
        self.assertIsNone(ss['primary']['mean_delta']);self.assertTrue(all(x['mean_delta'] is None for x in ss['renaming_contrasts']))
