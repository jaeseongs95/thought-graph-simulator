from __future__ import annotations
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from paired_probe_v049.audit import audit_run
from paired_probe_v049.contracts import ContractError,read_json
from paired_probe_v049.evidence import bundle_run,safe_unpack
from paired_probe_v049.plan import prepare
from paired_probe_v049.runner import execute
from .fixtures import copied,executed,shared

class ExecutionTests(unittest.TestCase):
    def test_full_480_http_calls_and_perfect_trace(self):
        r=shared()['report']
        self.assertEqual(r['inference_calls'],480);self.assertTrue(r['comparative_analysis_ready'])
        for arm,a in r['arms'].items():self.assertEqual(a['final_correct'],80)
        self.assertEqual(r['arms']['pipeline']['strict_trace_correct'],80)
    def test_same_seed_requests_repeated_twice(self):
        r=shared()['report'];self.assertEqual(r['repeated_request_groups'],240)
        self.assertEqual(r['unstable_request_groups'],0)
    def test_perfect_has_zero_factorial_interaction(self):
        r=shared()['report'];self.assertEqual(r['factorial_interaction']['mean'],0)
        self.assertTrue(all(p['final_accuracy_delta']==0 for p in r['paired_final_outcomes'].values()))
    def test_prepare_has_no_network(self):
        with tempfile.TemporaryDirectory() as td,patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('network')):
            prepare(shared()['bundle'],Path(td)/'p.json')
    def test_offline_audit_reproduces_entire_report(self):
        f=shared()
        with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('network')):
            r=audit_run(f['root']/'v049.plan.json',f['root']/'v049.run')
        self.assertEqual(r,f['report'])
    def test_original_false_does_not_fail_data_integrity(self):
        with executed('original_false') as (_,_,_,_,r,s):
            self.assertTrue(r['comparative_analysis_ready']);self.assertEqual(len(s.requests),480)
            self.assertEqual(r['arms']['original']['final_correct'],60)
            self.assertEqual(r['factorial_interaction']['mean'],0.25)
            self.assertEqual(r['paired_final_outcomes']['pipeline-original']['final_accuracy_delta'],0.25)
    def test_wrong_not_propagates_and_prevents_trace_success(self):
        with executed('wrong_not') as (_,_,_,_,r,_):
            p=r['arms']['pipeline'];self.assertEqual(p['not_correct'],0)
            self.assertEqual(p['and_local_correct'],80);self.assertEqual(p['strict_trace_correct'],0)
            self.assertEqual(p['final_correct'],40)
    def test_invalid_not_blocks_only_and_without_retry(self):
        with executed('invalid_not') as (_,_,_,_,r,s):
            self.assertTrue(r['data_complete']);self.assertEqual(len(s.requests),400)
            self.assertEqual(r['arms']['pipeline']['strict_trace_correct'],0)
            self.assertEqual(r['call_status_counts']['blocked'],80)
    def test_transport_failure_is_incomplete_not_480_wrong(self):
        with executed('http_error') as (_,_,_,_,r,s):
            self.assertEqual(len(s.requests),1);self.assertFalse(r['data_complete'])
            self.assertIsNone(r['factorial_interaction']['mean'])
            self.assertTrue(all(p['final_accuracy_delta'] is None for p in r['paired_final_outcomes'].values()))
    def test_wrong_model_stops_and_is_not_model_logic_failure(self):
        with executed('wrong_model') as (_,_,_,_,r,s):
            self.assertEqual(len(s.requests),1);self.assertFalse(r['data_complete'])
            self.assertEqual(r['call_status_counts']['response_identity_error'],1)
    def test_runtime_identity_drift_detected(self):
        with executed('runtime_drift') as (_,_,_,_,r,s):
            self.assertFalse(r['data_complete']);self.assertEqual(len(s.requests),240)
    def test_identity_error_before_inference_calls_zero(self):
        with executed('before_identity_error') as (_,_,_,_,r,s):
            self.assertFalse(r['data_complete']);self.assertEqual(len(s.requests),0)
    def test_missing_usage_is_null_not_zero(self):
        with executed('missing_usage') as (_,_,_,_,r,_):
            self.assertIsNone(r['arms']['original']['costs']['prompt_eval_count']['total'])
    def test_repeat_instability_is_reported(self):
        with executed('repeat_unstable') as (_,_,_,_,r,_):
            self.assertGreater(r['unstable_request_groups'],0)
    def test_output_reuse_refused(self):
        with copied() as (_,p,out,_),self.assertRaises(ContractError):execute(p,out)
    def test_bundle_roundtrip(self):
        with copied() as (root,p,out,_):
            r=bundle_run(p,out,root/'e.zip');unpack=root/'unpacked';unpack.mkdir()
            manifest=safe_unpack((root/'e.zip').read_bytes(),unpack)
            self.assertEqual(manifest['contract'],'v049-evidence-bundle-r1')
            self.assertEqual(audit_run(unpack/'external_plan/v049.plan.json',unpack/'run'),r)
    def test_bundle_refuses_overwrite(self):
        with copied() as (root,p,out,_):
            z=root/'e.zip';z.write_bytes(b'keep')
            with self.assertRaises(ContractError):bundle_run(p,out,z)
            self.assertEqual(z.read_bytes(),b'keep')
    def test_no_bundle_inside_run(self):
        with copied() as (_,p,out,_),self.assertRaises(ContractError):bundle_run(p,out,out/'e.zip')
