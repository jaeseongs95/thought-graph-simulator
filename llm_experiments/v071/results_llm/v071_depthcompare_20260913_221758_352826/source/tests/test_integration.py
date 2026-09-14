"""합성 HTTP 전체 실행, 중단, 길이 종료, pending 및 원문 전달 시험. 실제 Qwen 호출 없음."""
import unittest
from unittest.mock import patch
from fixtures import *

class Integration(unittest.TestCase):
    def test_perfect_100_calls_140_actions(self):
        with executed() as (_,pp,p,f,r,res,state):
            receipt=common.load(Path(res['independent_verification']).read_bytes())
            self.assertEqual(state['calls'],100);self.assertEqual(receipt['completed_actions'],140)
            self.assertTrue(r['overall']['pipeline_ready']);self.assertIsNone(r['overall']['end_to_end_graph_D_control'])
    def test_parse_error_continues_no_repair_no_retry(self):
        with executed('estimate_parse_error') as (_,pp,p,f,r,res,state):
            self.assertEqual(state['calls'],100);self.assertEqual(r['overall']['depth_reports']['measured'],0)
            self.assertEqual(r['overall']['oracle_selection']['successes'],40);self.assertIsNone(r['overall']['pipeline_ready'])
            for s in p['slots']:
                if s['arm']=='model_depth':
                    raw=common.load(f['wire/'+s['history_ids'][0]+'/response.raw.json'])['message']['content']
                    q=common.load(f['wire/'+s['id']+'/request.wire.json'])
                    self.assertEqual(common.load(q['messages'][0]['content'].split('\n\ninput: ')[1])['depth_report'],raw)
    def test_http_stop_once(self):
        with executed('http_error') as (_,pp,p,f,r,res,state):
            self.assertEqual(state['calls'],1);self.assertEqual(r['state'],'stopped');self.assertIsNone(r['overall']['pipeline_ready'])
    def test_late_http_keeps_committed_estimate_and_choices(self):
        with executed('late_http') as (_,pp,p,f,r,res,state):
            self.assertEqual(state['calls'],5);self.assertEqual(r['overall']['depth_reports']['successes'],1)
            self.assertEqual(r['overall']['oracle_selection']['successes'],2);self.assertEqual(r['overall']['model_pipeline']['successes'],1)
    def test_metadata_identity_zero_inference(self):
        with executed('bad_metadata') as (_,pp,p,f,r,res,state):self.assertEqual(state['calls'],0);self.assertEqual(r['state'],'stopped')
    def test_after_metadata_mismatch_stops_at_5(self):
        with executed('late_metadata') as (_,pp,p,f,r,res,state):self.assertEqual(state['calls'],5);self.assertEqual(r['state'],'stopped')
    def test_response_model_identity_stops(self):
        with executed('wrong_model') as (_,pp,p,f,r,res,state):self.assertEqual(state['calls'],1);self.assertEqual(r['state'],'stopped')
    def test_generation_over_budget_is_unmeasured(self):
        with executed('over_budget') as (_,pp,p,f,r,res,state):self.assertEqual(state['calls'],1);self.assertEqual(r['rows'][0]['status'],'generation_budget_exceeded');self.assertEqual(r['overall']['unmeasured_calls'],100)
    def test_length_terminated_estimate_does_not_count_pipeline(self):
        with executed('estimate_incomplete') as (_,pp,p,f,r,res,state):
            self.assertEqual(state['calls'],100);self.assertEqual(r['overall']['model_selection']['successes'],40)
            self.assertEqual(r['overall']['depth_reports']['measured'],0);self.assertEqual(r['overall']['model_pipeline']['measured'],0)
    def test_missing_usage_kept_null_not_zero(self):
        with executed('missing_usage') as (_,pp,p,f,r,res,state):self.assertIsNone(r['usage']['eval_count']);self.assertTrue(r['overall']['pipeline_ready'])
    def test_same_plan_or_output_cannot_rerun(self):
        with executed() as (root,pp,p,f,r,res,state):
            with self.assertRaises(FileExistsError):run.execute(pp,baseline_path(),root/'v071_fixture','http://127.0.0.1:1')
    def test_uncommitted_response_not_scored(self):
        original=run.write
        def interrupted(path,raw):
            if str(path).endswith('/records/b00_oracle_depth_shallow.json'):raise KeyboardInterrupt()
            return original(path,raw)
        with contextlib.redirect_stderr(io.StringIO()),executed(patcher=patch('run.write',side_effect=interrupted)) as (_,pp,p,f,r,res,state):
            receipt=common.load(Path(res['independent_verification']).read_bytes())
            self.assertEqual(state['calls'],1);self.assertEqual(receipt['inference_calls'],1)
            self.assertEqual(r['observed_calls'],0);self.assertIsNotNone(receipt['pending_action'])
    def test_predispatch_failure_has_no_fake_observation(self):
        original=design.request_for
        def interrupted(plan,slot,history_raw=None):
            if slot['id']=='b00_oracle_depth_deep':raise ValueError('synthetic failure before dispatch')
            return original(plan,slot,history_raw)
        with contextlib.redirect_stderr(io.StringIO()),executed(patcher=patch('design.request_for',side_effect=interrupted)) as (_,pp,p,f,r,res,state):
            receipt=common.load(Path(res['independent_verification']).read_bytes())
            self.assertEqual(state['calls'],1);self.assertEqual(receipt['inference_calls'],2)
            self.assertEqual(receipt['pending_action']['artifact_names'],[]);self.assertEqual(r['observed_calls'],1)
    def test_transport_error_not_logical_failure(self):
        original=run.exchange
        def broken(endpoint,path,body,timeout):
            if path=='/api/chat':return None,b'','TimeoutError',1
            return original(endpoint,path,body,timeout)
        with executed(patcher=patch('run.exchange',side_effect=broken)) as (_,pp,p,f,r,res,state):
            self.assertEqual(state['calls'],0);self.assertEqual(r['rows'][0]['status'],'transport_error');self.assertIsNone(r['rows'][0]['selection_success'])
