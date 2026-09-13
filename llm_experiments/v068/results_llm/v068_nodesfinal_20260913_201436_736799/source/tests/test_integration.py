import unittest,contextlib,io
from unittest.mock import patch
from fixtures import *
class Integration(unittest.TestCase):
    def test_perfect_both_arms_not_D(self):
        with executed() as (_,pp,p,f,r,res,state):
            self.assertEqual(state['calls'],36);self.assertEqual([a['successes'] for a in r['arms']],[12,12]);self.assertEqual(r['pair_counts']['both_success'],12)
            self.assertIsNone(r['overall']['D_instruction_control']);self.assertTrue(verify.verify_bundle(Path(res['evidence_zip']))['verified'])
    def test_fixed_short_preserves_partial(self):
        with executed('fixed_short') as (_,pp,p,f,r,res,state):self.assertEqual([a['successes'] for a in r['arms']],[6,6])
    def test_reversed_paths_zero(self):
        with executed('reversed') as (_,pp,p,f,r,res,state):self.assertEqual([a['successes'] for a in r['arms']],[0,0])
    def test_better_staged_is_not_old_result_repair(self):
        with executed('direct_missing_final') as (_,pp,p,f,r,res,state):
            self.assertEqual([a['successes'] for a in r['arms']],[0,12]);self.assertEqual(r['pair_counts']['staged_only'],12);self.assertEqual(r['overall']['v067_successes_unchanged'],4)
    def test_worse_staged_preserved(self):
        with executed('staged_missing_final') as (_,pp,p,f,r,res,state):self.assertEqual([a['successes'] for a in r['arms']],[12,0]);self.assertEqual(r['pair_counts']['direct_only'],12)
    def test_bad_node_stage_cannot_be_rescued_by_final(self):
        with executed('nodes_bad_parent') as (_,pp,p,f,r,res,state):
            self.assertEqual([a['successes'] for a in r['arms']],[0,0]);self.assertTrue(all('premise_counter_mismatch' in t['error_codes'] for t in r['trials']))
    def test_extra_nodes_not_deleted(self):
        with executed('extra') as (_,pp,p,f,r,res,state):
            self.assertEqual([a['successes'] for a in r['arms']],[0,0]);self.assertTrue(all(t['proof_valid'] is True and t['strict_valid'] is False for t in r['trials']))
    def test_invalid_nodes_json_passed_raw_without_retry(self):
        with executed('nodes_parse_error') as (_,pp,p,f,r,res,state):
            self.assertEqual(state['calls'],36);self.assertEqual(r['arms'][0]['successes'],12);self.assertEqual(r['arms'][1]['unmeasured'],12)
            for q,s in zip(state['requests'],p['slots']):
                if s['stage']=='final':self.assertEqual(common.load(q['messages'][0]['content'].split('\n\nnodes_response: ')[1])['content'],'{ broken JSON')
    def test_extra_field_not_silently_removed(self):
        with executed('nodes_extra_field') as (_,pp,p,f,r,res,state):self.assertEqual(r['arms'][1]['unmeasured'],12);self.assertIsNone(r['arms'][1]['positive_control_ready'])
    def test_http_stop_once(self):
        with executed('http_error') as (_,pp,p,f,r,res,state):self.assertEqual(state['calls'],1);self.assertEqual(r['state'],'stopped');self.assertIsNone(r['arms'][0]['positive_control_ready'])
    def test_http_partial_retains_results(self):
        with executed('late_http') as (_,pp,p,f,r,res,state):self.assertEqual(state['calls'],4);self.assertEqual(sum(a['successes'] for a in r['arms']),2);self.assertFalse(r['overall']['comparison_measured'])
    def test_metadata_failure_zero_inference(self):
        with executed('bad_metadata') as (_,pp,p,f,r,res,state):self.assertEqual(state['calls'],0);self.assertEqual(r['state'],'stopped')
    def test_later_identity_failure(self):
        with executed('late_metadata') as (_,pp,p,f,r,res,state):self.assertEqual(state['calls'],6);self.assertEqual(r['state'],'stopped')
    def test_response_identity_stop(self):
        with executed('wrong_model') as (_,pp,p,f,r,res,state):self.assertEqual(state['calls'],1);self.assertEqual(r['state'],'stopped')
    def test_generation_budget_stop_unmeasured(self):
        with executed('over_budget') as (_,pp,p,f,r,res,state):self.assertEqual(state['calls'],1);self.assertEqual(r['rows'][0]['status'],'generation_budget_exceeded');self.assertEqual(r['arms'][0]['measured'],0)
    def test_length_termination_distinct_from_logic(self):
        with executed('incomplete') as (_,pp,p,f,r,res,state):self.assertEqual(state['calls'],36);self.assertEqual([a['unmeasured'] for a in r['arms']],[12,12]);self.assertEqual(r['rows'][0]['done_reason'],'length')
    def test_missing_usage_not_zero(self):
        with executed('missing_usage') as (_,pp,p,f,r,res,state):
            for usage in r['usage_by_stage'].values():self.assertIsNone(usage['eval_count']);self.assertIsNone(usage['prompt_eval_count'])
    def test_same_plan_and_output_not_reexecuted(self):
        with executed() as (root,pp,p,f,r,res,state):
            with self.assertRaises(FileExistsError):run.execute(pp,baseline_path(),root/'v068_fixture','http://127.0.0.1:1')
    def test_pending_response_preserved_unmeasured(self):
        original=run.write
        def broken(path,raw):
            if str(path).endswith('b00_p0_reference_short_direct.json'):raise KeyboardInterrupt()
            return original(path,raw)
        with contextlib.redirect_stderr(io.StringIO()),executed(patcher=patch('run.write',side_effect=broken)) as (_,pp,p,f,r,res,state):
            receipt=common.load(Path(res['independent_verification']).read_bytes());self.assertEqual(state['calls'],1);self.assertEqual(receipt['inference_calls'],1);self.assertEqual(r['observed_calls'],0);self.assertIsNotNone(receipt['pending_action'])
    def test_pre_dispatch_failure_does_not_make_fake_response(self):
        original=design.request_for
        def broken(plan,slot,parent_raw=None):
            if slot['stage']=='final':raise ValueError('synthetic request limit')
            return original(plan,slot,parent_raw)
        with contextlib.redirect_stderr(io.StringIO()),executed(patcher=patch('design.request_for',side_effect=broken)) as (_,pp,p,f,r,res,state):
            receipt=common.load(Path(res['independent_verification']).read_bytes());self.assertEqual(state['calls'],2);self.assertEqual(receipt['inference_calls'],3);self.assertEqual(r['observed_calls'],2);self.assertEqual(receipt['pending_action']['artifact_names'],[])
    def test_transport_error_not_logic_failure(self):
        original=run.exchange
        def timeout(endpoint,path,body,seconds):
            if path=='/api/chat':return None,b'','TimeoutError',1
            return original(endpoint,path,body,seconds)
        with executed(patcher=patch('run.exchange',side_effect=timeout)) as (_,pp,p,f,r,res,state):
            self.assertEqual(state['calls'],0);self.assertEqual(r['state'],'stopped');self.assertEqual(r['rows'][0]['status'],'transport_error');self.assertIsNone(r['trials'][0]['proof_valid'])
