from __future__ import annotations
import unittest
from adm_pilot_v051.audit import audit_run
from .fixtures import shared,copied,executed

class Execution(unittest.TestCase):
    def test_full_synthetic_240_calls(self):
        r=shared()['report'];self.assertTrue(r['data_complete']);self.assertEqual(r['inference_calls'],240)
        self.assertEqual({a['role_match'] for a in r['roles'].values()},{20})
    def test_offline_report_identical(self):
        with copied() as (_,p,run,f):self.assertEqual(audit_run(p,run),f['report'])
    def test_ignored_roles_not_scored_from_request_labels(self):
        with executed('ignore_roles') as (_,_,_,_,r,_):
            self.assertTrue(r['data_complete']);self.assertEqual(sum(x['role_match'] for x in r['roles'].values()),20)
            self.assertEqual(sum(x['strict_valid'] for x in r['roles'].values()),240)
            self.assertEqual(sum(x['clean_requested_axis_change'] for x in r['paired']),0)
    def test_true_goal_without_proof_not_accepted(self):
        with executed('false_goal_fact') as (_,_,_,_,r,_):
            self.assertEqual(sum(x['goal_string_correct'] for x in r['roles'].values()),240)
            self.assertEqual(sum(x['strict_valid'] for x in r['roles'].values()),0)
    def test_false_M2_not_mixed_with_AD(self):
        with executed('wrong_m2') as (_,_,_,_,r,_):
            self.assertEqual(sum(x['strict_valid'] for x in r['roles'].values()),160)
            self.assertEqual(sum(x['proof_valid'] for x in r['roles'].values()),240)
            self.assertEqual(sum(x['representation_valid'] for x in r['roles'].values()),240)
    def test_bad_schema_not_fixed(self):
        with executed('wrong_schema') as (_,_,_,_,r,_):
            self.assertEqual(sum(x['role_match'] for x in r['roles'].values()),120)
            self.assertEqual(sum(x['proof_valid'] for x in r['roles'].values()),240)
    def test_all_format_failures_complete_but_no_hypothesis_pass(self):
        with executed('invalid_json') as (_,_,_,_,r,_):
            self.assertTrue(r['data_complete']);self.assertEqual(sum(x['format_valid'] for x in r['roles'].values()),0)
            self.assertFalse(r['all_requested_roles_succeeded'])
    def test_transport_error_no_retry_no_false_model_error(self):
        with executed('http_error') as (_,_,_,_,r,s):
            self.assertFalse(r['data_complete']);self.assertEqual(len(s.requests),1)
            self.assertEqual(sum(x['assessable'] for x in r['roles'].values()),0)
            self.assertIsNone(r['all_requested_roles_succeeded']);self.assertTrue(all(x['rate_over_assigned'] is None for x in r['paired']))
    def test_wrong_model_stops(self):
        with executed('wrong_model') as (_,_,_,_,r,s):self.assertFalse(r['data_complete']);self.assertEqual(len(s.requests),1)
    def test_identity_error_sends_no_inference(self):
        with executed('before_identity_error') as (_,_,_,_,r,s):self.assertFalse(r['data_complete']);self.assertEqual(len(s.requests),0)
    def test_runtime_drift_stops_before_second_round(self):
        with executed('runtime_drift') as (_,_,_,_,r,_):self.assertFalse(r['data_complete']);self.assertEqual(r['inference_calls'],120)
    def test_length_finish_is_not_full_model_output(self):
        with executed('truncated') as (_,_,_,_,r,_):self.assertEqual(sum(x['format_valid'] for x in r['roles'].values()),0)
    def test_missing_cost_is_not_zero(self):
        with executed('missing_usage') as (_,_,_,_,r,_):self.assertIsNone(r['unique_execution_usage']['prompt_eval_count'])
    def test_perfect_paired_counts(self):
        r=shared()['report']
        self.assertEqual({x['clean_requested_axis_change'] for x in r['paired']},{20})
        self.assertEqual({a:sum(x['assigned_pairs'] for x in r['paired'] if x['axis']==a) for a in ('A','D','M')},{'A':120,'D':120,'M':240})
