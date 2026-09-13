import unittest,contextlib,io,tempfile
from unittest.mock import patch
from fixtures import *
class Integration(unittest.TestCase):
    def test_perfect_positive_control_not_D_success(self):
        with executed() as (_,p,plan,f,r,result,state):
            self.assertEqual(state['calls'],12);self.assertEqual(r['overall']['reconstruction_successes'],12);self.assertTrue(r['overall']['positive_control_ready']);self.assertEqual(r['overall']['D_instruction_control'],'not_measured');self.assertIsNone(r['overall']['A_or_M_gate']);self.assertTrue(verify.verify_bundle(Path(result['evidence_zip']))['verified'])
    def test_fixed_short_is_only_six(self):
        with executed('fixed_short') as (_,p,plan,f,r,result,state):self.assertEqual(r['overall']['reconstruction_successes'],6);self.assertFalse(r['overall']['positive_control_ready'])
    def test_reverse_given_plans_zero(self):
        with executed('reversed') as (_,p,plan,f,r,result,state):self.assertEqual(r['overall']['reconstruction_successes'],0)
    def test_rule_name_only_not_full_graph(self):
        with executed('name_only') as (_,p,plan,f,r,result,state):self.assertEqual(r['overall']['reconstruction_successes'],6)
    def test_extra_nodes_strict_failure_not_logical(self):
        with executed('extra') as (_,p,plan,f,r,result,state):self.assertEqual(r['failure_layers']['proof_failures'],0);self.assertEqual(r['failure_layers']['strict_only_failures'],12)
    def test_bad_parents_fail(self):
        with executed('bad_parent') as (_,p,plan,f,r,result,state):self.assertEqual(r['failure_layers']['proof_failures'],12)
    def test_final_id_not_auto_goal(self):
        with executed('wrong_final') as (_,p,plan,f,r,result,state):self.assertEqual(r['overall']['reconstruction_successes'],0)
    def test_topology_contract_distinct(self):
        with executed('reverse_nodes') as (_,p,plan,f,r,result,state):self.assertEqual(r['failure_layers']['strict_only_failures'],12)
    def test_independent_sibling_order_is_valid_graph_but_not_given_plan(self):
        with executed('reorder_independent') as (_,p,plan,f,r,result,state):self.assertEqual(sum(g['strict_valid'] for g in r['groups']),12);self.assertEqual(r['overall']['reconstruction_successes'],10)
    def test_invalid_json_is_unmeasured(self):
        with executed('parse_error') as (_,p,plan,f,r,result,state):self.assertEqual(state['calls'],12);self.assertIsNone(r['overall']['positive_control_ready']);self.assertEqual(r['failure_layers']['proof_failures'],0)
    def test_schema_invalid_is_not_logic_false(self):
        with executed('invalid_schema') as (_,p,plan,f,r,result,state):self.assertIsNone(r['overall']['positive_control_ready']);self.assertEqual(r['failure_layers']['proof_failures'],0)
    def test_incomplete_unmeasured(self):
        with executed('incomplete') as (_,p,plan,f,r,result,state):self.assertIsNone(r['overall']['positive_control_ready'])
    def test_http_no_retry(self):
        with executed('http_error') as (_,p,plan,f,r,result,state):self.assertEqual(state['calls'],1);self.assertEqual(r['state'],'stopped');self.assertEqual(r['failure_layers']['not_observed'],11)
    def test_http_partial_keeps_three_success(self):
        with executed('late_http') as (_,p,plan,f,r,result,state):self.assertEqual(state['calls'],4);self.assertEqual(r['overall']['reconstruction_successes'],3);self.assertIsNone(r['overall']['positive_control_ready'])
    def test_metadata_no_inference(self):
        with executed('bad_metadata') as (_,p,plan,f,r,result,state):self.assertEqual(state['calls'],0);self.assertEqual(r['state'],'stopped')
    def test_metadata_later_stop(self):
        with executed('late_metadata') as (_,p,plan,f,r,result,state):self.assertEqual(state['calls'],2);self.assertEqual(r['state'],'stopped')
    def test_wrong_response_model_stop(self):
        with executed('wrong_model') as (_,p,plan,f,r,result,state):self.assertEqual(state['calls'],1);self.assertEqual(r['state'],'stopped')
    def test_provider_budget_exceeded_preserved(self):
        with executed('over_budget') as (_,p,plan,f,r,result,state):self.assertEqual(state['calls'],1);self.assertEqual(r['state'],'stopped');self.assertTrue(verify.verify_bundle(Path(result['evidence_zip']))['verified'])
    def test_unknown_usage_not_zero(self):
        with executed('missing_usage') as (_,p,plan,f,r,result,state):self.assertIsNone(r['usage']['eval_count'])
    def test_same_plan_started_never_retry(self):
        with executed() as (root,p,plan,f,r,result,state):
            with self.assertRaises(FileExistsError):run.execute(p,baseline_path(),root/'v067_fixture','http://127.0.0.1:1')
    def test_pending_one_response_unmeasured(self):
        original=run.write
        def broken(path,raw):
            if str(path).endswith('b00_p0_reference_short.json'):raise KeyboardInterrupt()
            return original(path,raw)
        with contextlib.redirect_stderr(io.StringIO()),executed(patcher=patch('run.write',side_effect=broken)) as (_,p,plan,f,r,res,state):
            receipt=common.load(Path(res['independent_verification']).read_bytes());self.assertEqual(receipt['inference_calls'],1);self.assertEqual(r['observed_calls'],0);self.assertIsNotNone(receipt['pending_action']);self.assertIsNone(r['overall']['positive_control_ready'])
