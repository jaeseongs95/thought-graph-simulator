"""합성 HTTP 전체 실행/중단/pending. 실제 Gemma 호출은 하지 않는다."""
import unittest
from unittest.mock import patch
from fixtures import *

class Integration(unittest.TestCase):
    def test_perfect_64_calls_96_actions(self):
        with executed() as (_,pp,p,f,r,res,state):
            receipt=common.load(Path(res['independent_verification']).read_bytes())
            self.assertEqual(state['calls'],64);self.assertEqual(receipt['completed_actions'],96)
            self.assertTrue(r['overall']['interface_ready']);self.assertIsNone(r['overall']['end_to_end_graph_D_control'])
            self.assertEqual(set(state['http_paths']),{'/api/version','/api/tags','/api/show','/api/chat'})
    def test_parse_error_no_repair_no_retry(self):
        with executed('parse_error') as (_,pp,p,f,r,res,state):
            self.assertEqual(state['calls'],64);self.assertEqual(r['overall']['selection']['measured'],0);self.assertIsNone(r['overall']['interface_ready'])
            self.assertTrue(all(common.load(f['wire/'+s['id']+'/response.raw.json'])['message']['content']==' \n {broken JSON\t ' for s in p['slots']))
    def test_http_stop_once(self):
        with executed('http_error') as (_,pp,p,f,r,res,state):
            self.assertEqual(state['calls'],1);self.assertEqual(r['state'],'stopped');self.assertIsNone(r['overall']['interface_ready'])
    def test_late_http_preserves_three_choices(self):
        with executed('late_http') as (_,pp,p,f,r,res,state):
            self.assertEqual(state['calls'],4);self.assertEqual(r['overall']['selection']['successes'],3)
    def test_metadata_identity_zero_inference(self):
        with executed('bad_metadata') as (_,pp,p,f,r,res,state):self.assertEqual(state['calls'],0);self.assertEqual(r['state'],'stopped')
    def test_archived_native_template_changed_zero_inference(self):
        with executed('bad_native') as (_,pp,p,f,r,res,state):self.assertEqual(state['calls'],0);self.assertEqual(r['state'],'stopped')
    def test_after_metadata_mismatch_stops_at_four(self):
        with executed('late_metadata') as (_,pp,p,f,r,res,state):self.assertEqual(state['calls'],4);self.assertEqual(r['state'],'stopped')
    def test_after_native_template_mismatch_stops_at_four(self):
        with executed('late_native') as (_,pp,p,f,r,res,state):self.assertEqual(state['calls'],4);self.assertEqual(r['state'],'stopped')
    def test_response_identity_stops_once(self):
        with executed('wrong_model') as (_,pp,p,f,r,res,state):self.assertEqual(state['calls'],1);self.assertEqual(r['state'],'stopped')
    def test_generation_budget_exceeded_unmeasured(self):
        with executed('over_budget') as (_,pp,p,f,r,res,state):self.assertEqual(state['calls'],1);self.assertEqual(r['rows'][0]['status'],'generation_budget_exceeded');self.assertEqual(r['overall']['unmeasured_calls'],64)
    def test_length_termination_separate(self):
        with executed('length') as (_,pp,p,f,r,res,state):
            self.assertEqual(state['calls'],64);self.assertEqual(r['overall']['selection']['measured'],0);self.assertEqual(r['rows'][0]['status'],'generation_length')
    def test_usage_missing_kept_null(self):
        with executed('missing_usage') as (_,pp,p,f,r,res,state):self.assertIsNone(r['usage']['eval_count']);self.assertTrue(r['overall']['interface_ready'])
    def test_same_plan_or_output_refused(self):
        with executed() as (root,pp,p,f,r,res,state):
            with self.assertRaises(FileExistsError):run.execute(pp,baseline_path(),root/'v073_fixture','http://127.0.0.1:1')
    def test_new_runname_same_folder_refused(self):
        with executed() as (root,pp,p,f,r,res,state):
            new=design.build_plan(baseline_path(),'v073_second','synthetic');np=root/'second.plan.json';common.save(np,new)
            with self.assertRaises(FileExistsError):run.execute(np,baseline_path(),root/'v073_second','http://127.0.0.1:1')
    def test_uncommitted_response_not_scored(self):
        original=run.write
        def interrupted(path,raw):
            if str(path).endswith('/records/b00_compact_shallow.json'):raise KeyboardInterrupt()
            return original(path,raw)
        with contextlib.redirect_stderr(io.StringIO()),executed(patcher=patch('run.write',side_effect=interrupted)) as (_,pp,p,f,r,res,state):
            receipt=common.load(Path(res['independent_verification']).read_bytes());self.assertEqual(state['calls'],1)
            self.assertEqual(r['observed_calls'],0);self.assertIsNotNone(receipt['pending_action']);self.assertEqual(receipt['inference_calls'],1)
    def test_predispatch_failure_no_fake_response(self):
        original=design.request_for
        def interrupted(plan,slot,history_raw=None):
            if slot['id']=='b00_compact_deep':raise ValueError('synthetic failure before dispatch')
            return original(plan,slot,history_raw)
        with contextlib.redirect_stderr(io.StringIO()),executed(patcher=patch('design.request_for',side_effect=interrupted)) as (_,pp,p,f,r,res,state):
            receipt=common.load(Path(res['independent_verification']).read_bytes());self.assertEqual(state['calls'],1)
            self.assertEqual(receipt['inference_calls'],2);self.assertEqual(r['observed_calls'],1);self.assertEqual(receipt['pending_action']['artifact_names'],[])
    def test_transport_error_not_logical_failure(self):
        original=run.exchange
        def broken(endpoint,path,body,timeout):
            if path=='/api/chat':return None,b'','TimeoutError',1
            return original(endpoint,path,body,timeout)
        with executed(patcher=patch('run.exchange',side_effect=broken)) as (_,pp,p,f,r,res,state):
            self.assertEqual(state['calls'],0);self.assertEqual(r['rows'][0]['status'],'transport_error');self.assertIsNone(r['rows'][0]['selection_success'])
