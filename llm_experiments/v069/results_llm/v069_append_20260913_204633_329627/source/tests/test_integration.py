"""합성 로컬 HTTP와 중단·미측정 경계. 실제 Qwen 추론은 호출하지 않는다."""
import unittest,contextlib,io
from unittest.mock import patch
from fixtures import *
class Integration(unittest.TestCase):
    def test_perfect_constructor_not_D_control(self):
        with executed() as (_,pp,p,f,r,res,state):
            self.assertEqual(state['calls'],54);self.assertEqual(r['overall']['successes'],12);self.assertTrue(r['overall']['positive_control_ready'])
            self.assertIsNone(r['overall']['D_instruction_control']);self.assertTrue(verify.verify_bundle(Path(res['evidence_zip']))['verified'])
    def test_fixed_short_preserves_partial(self):
        with executed('fixed_short') as (_,pp,p,f,r,res,state):self.assertEqual(r['overall']['successes'],6);self.assertEqual(r['overall']['next_decision'],'append_partial_close_branch')
    def test_wrong_final_zero_closes(self):
        with executed('wrong_final') as (_,pp,p,f,r,res,state):self.assertEqual(r['overall']['successes'],0);self.assertEqual(r['overall']['next_decision'],'append_zero_close_branch')
    def test_bad_early_step_not_rescued_by_final(self):
        with executed('bad_early_rule') as (_,pp,p,f,r,res,state):
            self.assertEqual(r['overall']['successes'],0);self.assertTrue(all(t['stage_contract_valid'] is False for t in r['trials']))
    def test_extra_nodes_not_deleted(self):
        with executed('extra_fact') as (_,pp,p,f,r,res,state):
            self.assertEqual(r['overall']['successes'],0);self.assertTrue(all(t['proof_valid'] is True and t['strict_valid'] is False for t in r['trials']))
    def test_stage_contract_independent_of_valid_final_graph(self):
        with executed('cross_stage_smuggling') as (_,pp,p,f,r,res,state):
            self.assertEqual(r['overall']['successes'],10)
            for t in r['trials']:
                if t['problem_id']=='E01_shared_fork' and t['condition']=='reference_long':self.assertTrue(t['strict_valid']);self.assertFalse(t['stage_contract_valid'])
    def test_invalid_initial_json_passed_raw_no_retry(self):
        with executed('facts_parse_error') as (_,pp,p,f,r,res,state):
            self.assertEqual(state['calls'],54);self.assertEqual(r['overall']['unmeasured'],12)
            for q,s in zip(state['requests'],p['slots']):
                history=common.load(q['messages'][0]['content'].split('\n\nhistory: ')[1])
                if history:self.assertEqual(history[0]['content'],' { broken JSON\n ')
    def test_invalid_rule_json_remains_in_full_history(self):
        with executed('rule_parse_error') as (_,pp,p,f,r,res,state):
            self.assertEqual(state['calls'],54);self.assertEqual(r['overall']['unmeasured'],12)
            for q,s in zip(state['requests'],p['slots']):
                if s['stage']=='final':
                    hist=common.load(q['messages'][0]['content'].split('\n\nhistory: ')[1]);self.assertEqual(hist[1]['content'],' { broken JSON\n ')
    def test_extra_field_not_removed(self):
        with executed('facts_extra_field') as (_,pp,p,f,r,res,state):self.assertEqual(r['overall']['unmeasured'],12);self.assertIsNone(r['overall']['positive_control_ready'])
    def test_http_stop_once(self):
        with executed('http_error') as (_,pp,p,f,r,res,state):self.assertEqual(state['calls'],1);self.assertEqual(r['state'],'stopped');self.assertIsNone(r['overall']['positive_control_ready'])
    def test_http_partial_preserves_finished_trial(self):
        with executed('late_http') as (_,pp,p,f,r,res,state):self.assertEqual(state['calls'],4);self.assertEqual(r['overall']['successes'],1);self.assertIsNone(r['overall']['positive_control_ready'])
    def test_metadata_failure_zero_inference(self):
        with executed('bad_metadata') as (_,pp,p,f,r,res,state):self.assertEqual(state['calls'],0);self.assertEqual(r['state'],'stopped')
    def test_later_identity_failure(self):
        with executed('late_metadata') as (_,pp,p,f,r,res,state):self.assertEqual(state['calls'],9);self.assertEqual(r['state'],'stopped')
    def test_response_identity_stop(self):
        with executed('wrong_model') as (_,pp,p,f,r,res,state):self.assertEqual(state['calls'],1);self.assertEqual(r['state'],'stopped')
    def test_generation_budget_stop_unmeasured(self):
        with executed('over_budget') as (_,pp,p,f,r,res,state):self.assertEqual(state['calls'],1);self.assertEqual(r['rows'][0]['status'],'generation_budget_exceeded');self.assertEqual(r['overall']['measured'],0)
    def test_length_termination_distinct_from_logic(self):
        with executed('incomplete') as (_,pp,p,f,r,res,state):self.assertEqual(state['calls'],54);self.assertEqual(r['overall']['unmeasured'],12);self.assertEqual(r['rows'][0]['done_reason'],'length')
    def test_missing_usage_not_zero(self):
        with executed('missing_usage') as (_,pp,p,f,r,res,state):
            for usage in r['usage_by_stage'].values():self.assertIsNone(usage['eval_count']);self.assertIsNone(usage['prompt_eval_count'])
    def test_same_plan_and_output_not_reexecuted(self):
        with executed() as (root,pp,p,f,r,res,state):
            with self.assertRaises(FileExistsError):run.execute(pp,baseline_path(),root/'v069_fixture','http://127.0.0.1:1')
    def test_pending_response_preserved_unmeasured(self):
        original=run.write
        def broken(path,raw):
            if str(path).endswith('b00_p0_reference_short_facts.json'):raise KeyboardInterrupt()
            return original(path,raw)
        with contextlib.redirect_stderr(io.StringIO()),executed(patcher=patch('run.write',side_effect=broken)) as (_,pp,p,f,r,res,state):
            receipt=common.load(Path(res['independent_verification']).read_bytes());self.assertEqual(state['calls'],1);self.assertEqual(receipt['inference_calls'],1);self.assertEqual(r['observed_calls'],0);self.assertIsNotNone(receipt['pending_action'])
    def test_pre_dispatch_failure_no_fake_response(self):
        original=design.request_for
        def broken(plan,slot,history_raw=None):
            if slot['stage']=='rule':raise ValueError('synthetic request budget')
            return original(plan,slot,history_raw)
        with contextlib.redirect_stderr(io.StringIO()),executed(patcher=patch('design.request_for',side_effect=broken)) as (_,pp,p,f,r,res,state):
            receipt=common.load(Path(res['independent_verification']).read_bytes());self.assertEqual(state['calls'],1);self.assertEqual(receipt['inference_calls'],2);self.assertEqual(r['observed_calls'],1);self.assertEqual(receipt['pending_action']['artifact_names'],[])
    def test_transport_error_not_logic_failure(self):
        original=run.exchange
        def timeout(endpoint,path,body,seconds):
            if path=='/api/chat':return None,b'','TimeoutError',1
            return original(endpoint,path,body,seconds)
        with executed(patcher=patch('run.exchange',side_effect=timeout)) as (_,pp,p,f,r,res,state):
            self.assertEqual(state['calls'],0);self.assertEqual(r['state'],'stopped');self.assertEqual(r['rows'][0]['status'],'transport_error');self.assertIsNone(r['trials'][0]['proof_valid'])
