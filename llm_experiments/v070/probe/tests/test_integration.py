"""합성 HTTP 전체 실행, 오류 중단, 원문 보존. 실제 모델 호출 없음."""
import unittest
from unittest.mock import patch
from fixtures import *
class Integration(unittest.TestCase):
    def test_perfect_40_calls_not_graph_control(self):
        with executed() as (_,pp,p,f,r,res,state):
            self.assertEqual(state['calls'],40);self.assertTrue(r['overall']['selector_ready']);self.assertIsNone(r['overall']['end_to_end_graph_D_control']);self.assertTrue(verify.verify_bundle(Path(res['evidence_zip']))['verified'])
    def test_fixed_first_has_no_pair_success(self):
        with executed('first') as (_,pp,p,f,r,res,state):self.assertEqual(r['overall']['paired_successes'],0);self.assertFalse(r['overall']['selector_ready'])
    def test_parse_error_not_corrected_or_retried(self):
        with executed('parse_error') as (_,pp,p,f,r,res,state):self.assertEqual(state['calls'],40);self.assertEqual(r['overall']['unmeasured'],40)
    def test_http_stop_once(self):
        with executed('http_error') as (_,pp,p,f,r,res,state):self.assertEqual(state['calls'],1);self.assertEqual(r['state'],'stopped');self.assertIsNone(r['overall']['selector_ready'])
    def test_late_http_preserves_successes(self):
        with executed('late_http') as (_,pp,p,f,r,res,state):self.assertEqual(state['calls'],4);self.assertEqual(r['overall']['successes'],3)
    def test_metadata_identity_zero_inference(self):
        with executed('bad_metadata') as (_,pp,p,f,r,res,state):self.assertEqual(state['calls'],0);self.assertEqual(r['state'],'stopped')
    def test_late_metadata_stop(self):
        with executed('late_metadata') as (_,pp,p,f,r,res,state):self.assertEqual(state['calls'],4);self.assertEqual(r['state'],'stopped')
    def test_response_identity_stop(self):
        with executed('wrong_model') as (_,pp,p,f,r,res,state):self.assertEqual(state['calls'],1);self.assertEqual(r['state'],'stopped')
    def test_generation_budget_not_semantic_failure(self):
        with executed('over_budget') as (_,pp,p,f,r,res,state):self.assertEqual(state['calls'],1);self.assertEqual(r['overall']['measured'],0)
    def test_length_separate_from_logic(self):
        with executed('incomplete') as (_,pp,p,f,r,res,state):self.assertEqual(state['calls'],40);self.assertEqual(r['rows'][0]['done_reason'],'length');self.assertIsNone(r['overall']['selector_ready'])
    def test_missing_usage_remains_null(self):
        with executed('missing_usage') as (_,pp,p,f,r,res,state):self.assertIsNone(r['usage']['eval_count']);self.assertTrue(r['overall']['selector_ready'])
    def test_same_plan_not_reexecuted(self):
        with executed() as (root,pp,p,f,r,res,state):
            with self.assertRaises(FileExistsError):run.execute(pp,baseline_path(),root/'v070_fixture','http://127.0.0.1:1')
    def test_pending_response_not_counted_success(self):
        original=run.write
        def broken(path,raw):
            if str(path).endswith('/records/b00_o0_shallow.json'):raise KeyboardInterrupt()
            return original(path,raw)
        with contextlib.redirect_stderr(io.StringIO()),executed(patcher=patch('run.write',side_effect=broken)) as (_,pp,p,f,r,res,state):
            receipt=common.load(Path(res['independent_verification']).read_bytes());self.assertEqual(state['calls'],1);self.assertEqual(receipt['inference_calls'],1);self.assertEqual(r['observed_calls'],0);self.assertIsNotNone(receipt['pending_action'])
    def test_pre_dispatch_failure_no_fake_observation(self):
        original=design.request_for
        def broken(plan,slot,history_raw=None):
            if slot['id']=='b00_o0_deep':raise ValueError('synthetic predispatch failure')
            return original(plan,slot,history_raw)
        with contextlib.redirect_stderr(io.StringIO()),executed(patcher=patch('design.request_for',side_effect=broken)) as (_,pp,p,f,r,res,state):
            receipt=common.load(Path(res['independent_verification']).read_bytes());self.assertEqual(state['calls'],1);self.assertEqual(receipt['inference_calls'],2);self.assertEqual(r['observed_calls'],1);self.assertEqual(receipt['pending_action']['artifact_names'],[])
    def test_transport_failure_not_logic(self):
        original=run.exchange
        def fail(endpoint,path,body,seconds):
            if path=='/api/chat':return None,b'','TimeoutError',1
            return original(endpoint,path,body,seconds)
        with executed(patcher=patch('run.exchange',side_effect=fail)) as (_,pp,p,f,r,res,state):self.assertEqual(state['calls'],0);self.assertEqual(r['rows'][0]['status'],'transport_error');self.assertIsNone(r['rows'][0]['selection_success'])
