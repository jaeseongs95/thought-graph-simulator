import base64,contextlib,copy,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from fixtures import *

class Integration(unittest.TestCase):
    def test_complete_perfect_and_independent(self):
        with executed() as (root,p,plan,files,r,result,state):
            self.assertEqual(state['chats'],12);self.assertEqual(r['overall']['construction_successes'],12);self.assertTrue(r['overall']['prescribed_construction_ready']);self.assertIsNone(r['overall']['bounded_A_or_M_pilot']);self.assertEqual(r['overall']['D_instruction_control'],'not_measured')
            self.assertTrue(verify.verify_bundle(Path(result['evidence_zip']))['verified']);self.assertEqual(report.render(r),files['summary.ko.md'].decode())
    def test_fixed_path_not_prescribed_readiness(self):
        with executed('fixed') as (_,p,plan,f,r,res,s):self.assertEqual(r['overall']['construction_successes'],6);self.assertFalse(r['overall']['prescribed_construction_ready'])
    def test_opposite_path_is_zero(self):
        with executed('reversed') as (_,p,plan,f,r,res,s):self.assertEqual(r['overall']['construction_successes'],0)
    def test_matching_name_wrong_graph_not_success(self):
        with executed('name_only') as (_,p,plan,f,r,res,s):self.assertEqual(sum(x['rule_name_matches'] for x in r['groups']),12);self.assertEqual(r['overall']['construction_successes'],6);self.assertFalse(r['overall']['prescribed_construction_ready'])
    def test_extras_not_logic_but_fail_strict(self):
        with executed('extra') as (_,p,plan,f,r,res,s):self.assertEqual(r['failure_layers']['proof_failures'],0);self.assertEqual(r['failure_layers']['strict_only_failures'],12);self.assertEqual(r['overall']['construction_successes'],0)
    def test_reverse_nodes_strict_only(self):
        with executed('reverse_nodes') as (_,p,plan,f,r,res,s):self.assertEqual(r['failure_layers']['strict_only_failures'],12)
    def test_bad_parent_logic_failure(self):
        with executed('bad_parent') as (_,p,plan,f,r,res,s):self.assertEqual(r['failure_layers']['proof_failures'],12)
    def test_parse_error_unmeasured(self):
        with executed('parse_error') as (_,p,plan,f,r,res,s):self.assertEqual(r['observed_calls'],12);self.assertIsNone(r['overall']['prescribed_construction_ready']);self.assertEqual(r['failure_layers']['proof_failures'],0)
    def test_http_fail_no_retry(self):
        with executed('http_error') as (_,p,plan,f,r,res,s):self.assertEqual(s['chats'],1);self.assertEqual(r['state'],'stopped');self.assertIsNone(r['overall']['construction_rate']);self.assertEqual(r['failure_layers']['unobserved'],11)
    def test_late_http_keeps_prefix(self):
        with executed('late_http') as (_,p,plan,f,r,res,s):self.assertEqual(s['chats'],4);self.assertEqual(r['overall']['construction_successes'],3);self.assertIsNone(r['overall']['prescribed_construction_ready'])
    def test_model_identity_stops_before_inference(self):
        with executed('metadata_error') as (_,p,plan,f,r,res,s):self.assertEqual(s['chats'],0);self.assertEqual(r['observed_calls'],0)
    def test_late_metadata_no_next_block(self):
        with executed('late_metadata') as (_,p,plan,f,r,res,s):self.assertEqual(s['chats'],2);self.assertEqual(r['state'],'stopped')
    def test_response_identity_stops(self):
        with executed('wrong_model') as (_,p,plan,f,r,res,s):self.assertEqual(s['chats'],1);self.assertEqual(r['state'],'stopped')
    def test_over_budget_record_is_preserved(self):
        with executed('over_budget') as (_,p,plan,f,r,res,s):self.assertEqual(s['chats'],1);self.assertEqual(r['state'],'stopped');self.assertTrue(verify.verify_bundle(Path(res['evidence_zip']))['verified'])
    def test_missing_usage_is_not_zero(self):
        with executed('missing_usage') as (_,p,plan,f,r,res,s):self.assertIsNone(r['usage']['eval_count'])
    def test_same_plan_cannot_be_executed_twice(self):
        with executed() as (root,p,plan,f,r,res,s):
            with self.assertRaises(FileExistsError):run.execute(p,baseline_path(),root/'v065_test','http://127.0.0.1:1')
    def test_prepare_reuses_exact_baseline_no_network(self):
        with patch('urllib.request.urlopen',side_effect=AssertionError('no HTTP')):p=design.build_plan(baseline_path(),'v065_offline')
        self.assertEqual(len(p['slots']),12)
    def test_request_problem_schema_options_preserved(self):
        p=design.build_plan(baseline_path(),'v065_same');old=common.unzip(baseline_path().read_bytes());prior=common.load(old['plan.json'])
        for s in p['slots']:
            direction='shallow' if s['condition']=='prescribed_short' else 'deep';sid=next(x['id'] for x in prior['slots'] if x['problem_id']==s['problem_id'] and x['seed']==s['seed'] and x['direction']==direction)
            a=common.load(old['wire/'+sid+'/request.wire.json']);b=design.request_for(p,s)
            self.assertEqual({k:v for k,v in a.items() if k!='messages'},{k:v for k,v in b.items() if k!='messages'})
            at,ap=a['messages'][0]['content'].split('\n\nproblem: ');bt,bp=b['messages'][0]['content'].split('\n\nproblem: ');self.assertEqual(ap,bp)
            self.assertEqual(at.split('\n경로 지시:\n')[0],bt.split('\n경로 지시:\n')[0]);self.assertEqual(at.split('\nJSON 객체')[1],bt.split('\nJSON 객체')[1])
    def test_pending_request_preserved_unmeasured(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p=design.build_plan(baseline_path(),'v065_pending','synthetic');pp=root/'p.json';common.save(pp,p)
            with server(p) as (endpoint,state):
                real=run.exchange
                def broken(base,path,body,timeout):
                    if path=='/api/chat':raise KeyboardInterrupt()
                    return real(base,path,body,timeout)
                with patch('run.exchange',side_effect=broken),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):res=run.execute(pp,baseline_path(),root/'v065_pending',endpoint)
            receipt=verify.verify_bundle(Path(res['evidence_zip']));self.assertEqual(receipt['inference_calls'],1);self.assertEqual(receipt['observed_calls'],0);self.assertIsNotNone(receipt['pending_action']);self.assertEqual(state['chats'],0)
