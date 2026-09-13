"""별도 구현의 재검산과 잘못된 성공/미측정 분류에 대한 반례."""
import copy, sys, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'tools'))
from independent_verify_v055 import measure, verify, payload_from
from model_probe_v055.evidence import bundle_run
from model_probe_v055.contracts import read_json,write_json
from .fixtures import copied,executed

K={'id':'K01','facts':['Ca'],'goal':'Cc','rules':[
 {'id':'k10','premises':['Ca'],'conclusion':'Cb'},
 {'id':'k17','premises':['Cb'],'conclusion':'Cc'},
 {'id':'k03','premises':['Ca'],'conclusion':'Cc'}]}
def shallow():
    return {'nodes':[{'id':'f','atom':'Ca','rule':None,'parents':[]},
        {'id':'z','atom':'Cc','rule':'k03','parents':['f']}],'final_node_id':'z'}
def deep():
    return {'nodes':[{'id':'f','atom':'Ca','rule':None,'parents':[]},
        {'id':'b','atom':'Cb','rule':'k10','parents':['f']},
        {'id':'z','atom':'Cc','rule':'k17','parents':['b']}],'final_node_id':'z'}

class Semantic(unittest.TestCase):
    def test_shallow(self):self.assertEqual(measure(K,shallow())['D'],1)
    def test_deep(self):self.assertEqual(measure(K,deep())['D'],2)
    def test_requested_role_not_parameter(self):
        import inspect
        self.assertEqual(list(inspect.signature(measure).parameters),['problem','payload'])
    def test_none_is_unmeasured(self):self.assertIsNone(measure(K,None)['proof_valid'])
    def test_missing_final(self):
        p=deep();p['final_node_id']='absent';m=measure(K,p);self.assertFalse(m['final_ref_valid']);self.assertFalse(m['proof_valid'])
    def test_wrong_rule_keeps_reference(self):
        p=deep();p['nodes'][-1]['rule']='unknown';m=measure(K,p);self.assertTrue(m['final_ref_valid']);self.assertFalse(m['proof_valid']);self.assertIsNone(m['D'])
    def test_wrong_parent_not_repaired(self):
        p=deep();p['nodes'][-1]['parents']=['f'];m=measure(K,p);self.assertFalse(m['proof_valid']);self.assertTrue(m['final_ref_valid'])
    def test_extra_top_field_separates_format_proof(self):
        p=deep();p['extra']='irrelevant';m=measure(K,p);self.assertFalse(m['format_valid']);self.assertTrue(m['proof_valid']);self.assertFalse(m['strict_valid']);self.assertEqual(m['D'],2)
    def test_duplicate_id_not_overwritten(self):
        p=deep();p['nodes'].append(copy.deepcopy(p['nodes'][-1]));m=measure(K,p);self.assertFalse(m['proof_valid']);self.assertFalse(m['final_ref_valid'])
    def test_two_paths_not_pruned(self):
        p=deep();p['nodes'].insert(-1,{'id':'other','atom':'Cc','rule':'k03','parents':['f']});self.assertFalse(measure(K,p)['proof_valid'])
    def test_unreachable_fact_rejected(self):
        p=shallow();p['nodes'][0]['atom']='Cx';self.assertFalse(measure(K,p)['proof_valid'])
    def test_schema_constraints_not_inferred(self):
        p=shallow();p['nodes'][-1]['id']='z'*129;p['final_node_id']='z'*129;self.assertFalse(measure(K,p)['format_valid'])
    def test_production_cross_check_defined_mutations(self):
        from order_probe_v054.measure import measure as production
        cases=[None,shallow(),deep(),{},[],{'nodes':[],'final_node_id':'z'}]
        for change in ('extra','wrong_rule','bad_parent','duplicate','bad_goal'):
            p=deep()
            if change=='extra':p['extra']=True
            if change=='wrong_rule':p['nodes'][-1]['rule']='k1_7'
            if change=='bad_parent':p['nodes'][-1]['parents']=['f']
            if change=='duplicate':p['nodes'].append(copy.deepcopy(p['nodes'][0]))
            if change=='bad_goal':p['final_node_id']='b'
            cases.append(p)
        for p in cases:
            with self.subTest(payload=p):
                a,b=measure(K,p),production(K,p)
                for f in ('format_valid','proof_valid','strict_valid','D','final_ref_valid'):self.assertEqual(a[f],b[f])
    def test_bad_envelope_not_proof_error(self):
        self.assertIsNone(payload_from(b'{','q'));self.assertIsNone(payload_from(b'[]','q'))
    def test_envelope_error_is_not_answer(self):
        self.assertIsNone(payload_from(b'{"error":"server"}','q',503))

class Evidence(unittest.TestCase):
    def test_perfect_independent_offline(self):
        with copied() as (root,p,run,b):
            bundle_run(p,run,root/'e.zip')
            with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('offline')):r=verify(root/'e.zip')
            self.assertEqual(r['observed_responses'],240);self.assertEqual(r['models']['candidate']['selective_pairs'],40)
    def test_invalid_order_like_v054_independent(self):
        with executed('v054_vs_perfect') as (root,p,run,r,s):
            bundle_run(p,run,root/'e.zip');v=verify(root/'e.zip')
            self.assertEqual(v['models']['reference']['valid_proofs'],90);self.assertEqual(v['models']['reference']['selective_pairs'],0)
    def test_partial_no_neither_success_independent(self):
        with executed('candidate_http') as (root,p,run,r,s):
            bundle_run(p,run,root/'e.zip');v=verify(root/'e.zip');self.assertFalse(v['data_complete'])
            self.assertEqual(sum(c['neither_success'] for c in r['cross_model_results'].values()),0)
    def test_stored_score_tamper_rejected(self):
        import zipfile,json
        from forensic_v054 import checked_zip,sha,canonical
        with copied() as (root,p,run,b):
            bundle_run(p,run,root/'e.zip');data,m=checked_zip(root/'e.zip');r=read_json(run/'summary.json')
            r['cross_model_results']['K01/original']['candidate_only']=10
            data['run/summary.json']=canonical(r)
            m['file_hashes']['run/summary.json']=sha(data['run/summary.json']);data['BUNDLE_MANIFEST.json']=canonical(m)
            with zipfile.ZipFile(root/'changed.zip','w') as z:
                for name,raw in data.items():z.writestr(name,raw)
            with self.assertRaises(ValueError):verify(root/'changed.zip')
