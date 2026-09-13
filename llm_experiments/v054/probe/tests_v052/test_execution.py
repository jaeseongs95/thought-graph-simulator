import copy,json,unittest
from adm_diagnostic_v052.audit import audit_run
from adm_diagnostic_v052.evidence import bundle_run
from adm_diagnostic_v052.contracts import read_json,write_json,ContractError
from .fixtures import shared,copied,executed

class Execution(unittest.TestCase):
    def test_real_HTTP_440_complete(self):
        r=shared()['report'];self.assertTrue(r['data_complete']);self.assertEqual(r['inference_calls'],440);self.assertTrue(r['all_primary_roles_succeeded'])
    def test_copy_excluded_from_primary_n(self):
        r=shared()['report'];self.assertEqual(sum(x['primary_assigned'] for x in r['core_results'].values()),240);self.assertEqual(sum(g['copy_exact'] for g in r['groups'].values()),20)
    def test_perfect_neutral_comparison_not_independent_samples(self):
        r=shared()['report'];self.assertEqual(len(r['neutral_comparisons']),20)
        for x in r['neutral_comparisons']:self.assertAlmostEqual(x['neutral_standardized_success'],1/12);self.assertAlmostEqual(x['difference'],11/12)
    def test_role_ignoring_is_not_hypothesis_success(self):
        with executed('ignore_roles') as (_,_,_,_,r,_):
            self.assertTrue(r['data_complete']);self.assertFalse(r['all_primary_roles_succeeded'])
            self.assertEqual(sum(k['assigned_role_success'] for k in r['core_results'].values()),20)
            self.assertEqual(sum(x['strict_selective'] for x in r['paired']),0)
            for c in r['core_results'].values():self.assertEqual(c['neutral_macro_difference'],0)
    def test_false_M2_loses_full_success_not_proof(self):
        with executed('wrong_m2') as (_,_,_,_,r,_):
            self.assertEqual(sum(c['assigned_role_success'] for c in r['core_results'].values()),160)
            self.assertEqual(sum(r['groups'][pid+'/factorial']['layers']['proof_valid']['correct'] for pid in ('K01','T02')),240)
    def test_final_atom_not_auto_repaired(self):
        with executed('bad_final') as (_,_,_,_,r,_):
            self.assertEqual(sum(c['assigned_role_success'] for c in r['core_results'].values()),0)
            self.assertEqual(sum(r['groups'][pid+'/factorial']['layers']['all_local_nodes_valid']['correct'] for pid in ('K01','T02')),240)
            self.assertEqual(sum(r['groups'][pid+'/copy_control']['copy_exact'] for pid in ('K01','T02')),20)
    def test_bare_goal_is_not_valid_proof(self):
        with executed('false_goal_fact') as (_,_,_,_,r,_):self.assertEqual(sum(k['valid_records'] for k in r['core_results'].values()),0)
    def test_http_error_stops_without_retry(self):
        with executed('http_error') as (_,_,_,_,r,s):
            self.assertFalse(r['data_complete']);self.assertEqual(len(s.requests),1);self.assertIsNone(r['all_primary_roles_succeeded']);self.assertTrue(all(x['difference'] is None for x in r['neutral_comparisons']))
    def test_wrong_model_stops(self):
        with executed('wrong_model') as (_,_,_,_,r,s):self.assertFalse(r['data_complete']);self.assertEqual(len(s.requests),1)
    def test_identity_mismatch_stops_before_inference(self):
        with executed('before_identity_error') as (_,_,_,_,r,s):self.assertFalse(r['data_complete']);self.assertEqual(len(s.requests),0)
    def test_generation_length_not_normal(self):
        with executed('truncated') as (_,_,_,_,r,_):self.assertEqual(sum(k['valid_records'] for k in r['core_results'].values()),0)
    def test_missing_usage_not_replaced_by_zero(self):
        with executed('missing_usage') as (_,_,_,_,r,_):self.assertIsNone(r['unique_execution_usage']['prompt_eval_count'])
    def test_offline_report_equal(self):
        with copied() as (_,p,run,f):self.assertEqual(audit_run(p,run),f['report'])
    def test_bad_response_hash_rejected(self):
        with copied() as (_,p,run,_):
            f=next((run/'calls').rglob('response.raw.json'));f.write_bytes(f.read_bytes()+b' ')
            with self.assertRaises(ContractError):audit_run(p,run)
    def test_extra_file_rejected(self):
        with copied() as (_,p,run,_):
            (run/'calls/extra.txt').write_text('x')
            with self.assertRaises(ContractError):audit_run(p,run)
    def test_snapshot_not_external_plan(self):
        with copied() as (_,p,run,_):
            with self.assertRaises(ContractError):audit_run(run/'plan.snapshot.json',run)
    def test_self_modified_source_snapshot_rejected(self):
        with copied() as (_,p,run,_):
            f=run/'source_snapshot/adm_diagnostic_v052/requests.py';f.write_bytes(f.read_bytes()+b'\n')
            with self.assertRaises(ContractError):audit_run(p,run)
    def test_reaudit_failure_removes_stale_PASS(self):
        with copied() as (_,p,run,_):
            (run/'calls/extra.txt').write_text('x')
            with self.assertRaises(ContractError):audit_run(p,run,write_report=True)
            self.assertFalse(read_json(run/'summary.json')['data_integrity'])
    def test_bundle_roundtrip(self):
        from paired_probe_v049.evidence import safe_unpack
        with copied() as (root,p,run,f):
            out=root/'evidence.zip';bundle_run(p,run,out);dest=root/'unpacked';dest.mkdir();m=safe_unpack(out.read_bytes(),dest);self.assertEqual(m['contract'],'v052-evidence-bundle-r1');self.assertEqual(audit_run(dest/'external_plan/v052.plan.json',dest/'run'),f['report'])
    def test_bundle_existing_no_overwrite(self):
        with copied() as (root,p,run,_):
            out=root/'existing.zip';out.write_bytes(b'keep')
            with self.assertRaises(ContractError):bundle_run(p,run,out)
            self.assertEqual(out.read_bytes(),b'keep')
