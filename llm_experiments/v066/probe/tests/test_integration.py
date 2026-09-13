import contextlib,io,tempfile,unittest,socket
from unittest.mock import patch
from pathlib import Path
from fixtures import *
class Integration(unittest.TestCase):
    def test_complete_independent(self):
        with executed() as (_,p,plan,f,r,res,s):
            self.assertEqual(s['chats'],36);self.assertTrue(all(a['all_pairs_pass'] for a in r['arms'].values()));self.assertTrue(verify.verify_bundle(Path(res['evidence_zip']))['verified'])
    def test_raw_parent_every_construct_bound(self):
        with executed() as (_,p,plan,f,r,res,s):
            for t in s['transfers']:
                raw=f['wire/'+t['source_slot_id']+'/response.raw.json'];self.assertEqual(t['content'],common.load(raw)['message']['content']);self.assertEqual(t['response_sha256'],common.sha(raw))
    def test_fixed_path_no_control(self):
        with executed('same_path') as (_,p,plan,f,r,res,s):
            for a in r['arms'].values():self.assertEqual(a['selective_successes'],0);self.assertFalse(a['all_pairs_pass'])
    def test_staged_only_wins(self):
        with executed('staged_only') as (_,p,plan,f,r,res,s):self.assertEqual((r['arms']['direct']['selective_successes'],r['arms']['staged']['selective_successes']),(0,6))
    def test_direct_can_win(self):
        with executed('direct_only') as (_,p,plan,f,r,res,s):self.assertEqual((r['arms']['direct']['selective_successes'],r['arms']['staged']['selective_successes']),(6,0))
    def test_wrong_plan_correct_graph_not_end_to_end(self):
        with executed('bad_plan_correct_graph') as (_,p,plan,f,r,res,s):self.assertEqual(r['arms']['staged']['final_D_only_successes'],12);self.assertEqual(r['arms']['staged']['end_to_end_successes'],0);self.assertEqual(r['planner']['valid_plans'],0)
    def test_wrong_direction_corrected_by_model_not_end_to_end(self):
        with executed('wrong_direction_correct_graph') as (_,p,plan,f,r,res,s):self.assertEqual(r['planner']['valid_plans'],12);self.assertEqual(r['planner']['direction_successes'],0);self.assertEqual(r['arms']['staged']['final_D_only_successes'],12);self.assertEqual(r['arms']['staged']['end_to_end_successes'],0)
    def test_wrong_plan_preserved_even_if_wrong(self):
        with executed('wrong_plan_preserved') as (_,p,plan,f,r,res,s):self.assertEqual(sum(x['follows_actual_plan'] is True for x in r['rows']),12);self.assertEqual(r['arms']['staged']['end_to_end_successes'],0)
    def test_plan_success_preserved_after_graph_error(self):
        with executed('plan_only') as (_,p,plan,f,r,res,s):self.assertEqual(r['planner']['direction_successes'],12);self.assertEqual(r['arms']['staged']['end_to_end_successes'],0)
    def test_parse_plan_exact_content_not_measured(self):
        with executed('parse_plan_correct_graph') as (_,p,plan,f,r,res,s):
            self.assertTrue(all(t['content']=='{잘못된 JSON\n그대로 보존' for t in s['transfers']));self.assertIsNone(r['arms']['staged']['all_pairs_pass']);self.assertEqual(r['arms']['staged']['final_D_only_successes'],12)
    def test_absent_plan_content_null_not_fabricated(self):
        with executed('missing_plan_content') as (_,p,plan,f,r,res,s):self.assertTrue(all(t['content'] is None for t in s['transfers']));self.assertIsNone(r['arms']['staged']['all_pairs_pass'])
    def test_strict_only_not_logic_error(self):
        with executed('extra_nodes') as (_,p,plan,f,r,res,s):
            for row in r['rows']:
                if row['stage']!='plan':self.assertTrue(row['proof_valid']);self.assertFalse(row['strict_valid']);self.assertIn('extra_unused_node',row['error_codes'])
    def test_reverse_nodes_strict_only(self):
        with executed('reverse_nodes') as (_,p,plan,f,r,res,s):self.assertTrue(all(x['proof_valid'] is True and x['strict_valid'] is False for x in r['rows'] if x['stage']!='plan'))
    def test_http_one_no_retry(self):
        with executed('http_error') as (_,p,plan,f,r,res,s):self.assertEqual(s['chats'],1);self.assertEqual(r['state'],'stopped');self.assertTrue(all(x['outcome']=='not_comparable' for x in r['contrasts']))
    def test_construct_http_plan_retained(self):
        with executed('construct_http') as (_,p,plan,f,r,res,s):self.assertEqual(s['chats'],3);self.assertEqual(r['planner']['direction_successes'],1);self.assertEqual(r['state'],'stopped')
    def test_model_identity_zero_calls(self):
        with executed('metadata_error') as (_,p,plan,f,r,res,s):self.assertEqual(s['chats'],0);self.assertEqual(r['observed_calls'],0)
    def test_block_drift_stop(self):
        with executed('late_metadata') as (_,p,plan,f,r,res,s):self.assertEqual(s['chats'],6);self.assertEqual(r['state'],'stopped')
    def test_wrong_model_stop(self):
        with executed('wrong_model') as (_,p,plan,f,r,res,s):self.assertEqual(s['chats'],1)
    def test_budget_stop_preserves_record(self):
        with executed('over_budget') as (_,p,plan,f,r,res,s):self.assertEqual(s['chats'],1);self.assertTrue(verify.verify_bundle(Path(res['evidence_zip']))['verified'])
    def test_missing_usage_not_zero(self):
        with executed('missing_usage') as (_,p,plan,f,r,res,s):self.assertTrue(all(a['usage']['eval_count'] is None for a in r['arms'].values()))
    def test_parse_error_not_logic(self):
        with executed('parse_error') as (_,p,plan,f,r,res,s):self.assertTrue(all(x['proof_valid'] is None for x in r['rows']));self.assertTrue(all(x['all_pairs_pass'] is None for x in r['arms'].values()))
    def test_same_plan_reexecution_rejected(self):
        with executed() as (root,p,plan,f,r,res,s):
            with self.assertRaises(FileExistsError):run.execute(p,baseline_path(),root/'v066_test','http://127.0.0.1:1')
    def test_prepare_no_network(self):
        with patch.object(socket.socket,'connect',side_effect=AssertionError('no network')):p=design.build_plan(baseline_path(),'v066_offline')
        self.assertEqual(len(p['slots']),36)
    def test_pending_construct_unmeasured(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);plan=design.build_plan(baseline_path(),'v066_pending','synthetic');pp=root/'p.json';common.save(pp,plan)
            with server(plan) as (ep,st):
                orig=run.exchange
                def broken(base,path,body,timeout):
                    if path=='/api/chat' and '\\nroute_plan_response: ' in body.decode():raise KeyboardInterrupt()
                    return orig(base,path,body,timeout)
                with patch('run.exchange',side_effect=broken),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):res=run.execute(pp,baseline_path(),root/'v066_pending',ep)
            ind=verify.verify_bundle(Path(res['evidence_zip']));self.assertEqual(ind['inference_calls'],3);self.assertEqual(ind['observed_calls'],2);self.assertEqual(st['chats'],2);self.assertIsNotNone(ind['pending_action'])
