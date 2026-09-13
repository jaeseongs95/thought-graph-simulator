from __future__ import annotations
import copy,unittest
from criterion_probe_v050.contracts import read_json,strict_json
from criterion_probe_v050.audit import audit_run
from .fixtures import shared,executed,copied

class Execution(unittest.TestCase):
    def test_full_560_http_exchange(self):
        r=shared()['report'];self.assertTrue(r['comparative_analysis_ready']);self.assertEqual(r['inference_calls'],560)
        self.assertEqual({v['strict_trace_correct'] for v in r['arms'].values()},{80})
    def test_oneshot_original_errors_not_repaired(self):
        with executed('original_false') as (_,_,_,_,r,_):
            self.assertEqual(r['arms']['oneshot_original']['finding_correct'],60)
            self.assertEqual(r['arms']['oneshot_commuted']['finding_correct'],80)
            self.assertEqual(r['arms']['staged_pipeline']['strict_trace_correct'],80)
    def test_wrong_extract_propagates_and_is_not_hidden(self):
        with executed('wrong_extract') as (_,_,_,_,r,_):
            self.assertTrue(r['data_complete'])
            self.assertEqual(r['arms']['staged_commuted']['primitives_correct'],0)
            self.assertEqual(r['arms']['staged_commuted']['finding_correct'],40)
            self.assertEqual(r['arms']['staged_commuted']['strict_trace_correct'],0)
    def test_observed_error_not_conflated_with_final(self):
        with executed('wrong_observed') as (_,_,_,_,r,_):
            self.assertEqual(r['arms']['staged_commuted']['finding_correct'],80)
            self.assertEqual(r['arms']['staged_commuted']['strict_trace_correct'],0)
    def test_wrong_not_masked_final_is_not_trace_success(self):
        with executed('wrong_not') as (_,_,_,_,r,_):
            self.assertEqual(r['arms']['staged_pipeline']['finding_correct'],40)
            self.assertEqual(r['arms']['staged_pipeline']['strict_trace_correct'],0)
    def test_invalid_extract_blocks_all_four_children(self):
        with executed('invalid_extract') as (_,_,_,_,r,_):
            self.assertTrue(r['data_complete']);self.assertEqual(r['inference_calls'],240)
            self.assertEqual(r['call_status_counts']['blocked'],320)
    def test_invalid_not_blocks_only_gap_and(self):
        with executed('invalid_not') as (_,_,_,_,r,_):
            self.assertEqual(r['inference_calls'],480);self.assertEqual(r['arms']['staged_pipeline']['strict_trace_correct'],0)
            self.assertEqual(r['arms']['staged_commuted']['strict_trace_correct'],80)
    def test_truncation_not_accepted(self):
        with executed('truncated') as (_,_,_,_,r,_):
            self.assertEqual(r['inference_calls'],240)
            self.assertEqual({a['strict_trace_correct'] for a in r['arms'].values()},{0})
    def test_http_error_no_retry(self):
        with executed('http_error') as (_,_,_,_,r,s):
            self.assertFalse(r['data_complete']);self.assertEqual(len(s.requests),1);self.assertEqual(r['inference_calls'],1)
            for comparisons in r['paired'].values():self.assertTrue(all(v is None for v in comparisons.values()))
    def test_wrong_model_stops(self):
        with executed('wrong_model') as (_,_,_,_,r,s):
            self.assertFalse(r['data_complete']);self.assertEqual(len(s.requests),1)
    def test_identity_drift_prevents_complete(self):
        with executed('runtime_drift') as (_,_,_,_,r,_):
            self.assertFalse(r['data_complete']);self.assertEqual(r['inference_calls'],280)
    def test_identity_failure_no_inference(self):
        with executed('before_identity_error') as (_,_,_,_,r,s):
            self.assertFalse(r['data_complete']);self.assertEqual(len(s.requests),0)
    def test_missing_usage_stays_unknown(self):
        with executed('missing_usage') as (_,_,_,_,r,_):
            self.assertIsNone(r['unique_execution_usage']['prompt_eval_count'])
            self.assertIsNone(r['arms']['staged_pipeline']['path_usage']['prompt_eval_count'])
    def test_shared_cost_not_added_as_unique_cost(self):
        r=shared()['report'];self.assertEqual(r['unique_execution_usage']['calls'],560)
        self.assertEqual(r['arms']['staged_commuted']['path_usage']['actual_referenced_calls'],240)
        self.assertEqual(r['arms']['staged_pipeline']['path_usage']['actual_referenced_calls'],320)
        self.assertEqual(sum(a['path_usage']['actual_referenced_calls'] for a in r['arms'].values()),720)
    def test_offline_full_report_equality(self):
        with copied() as (_,p,run,f):self.assertEqual(audit_run(p,run),f['report'])
