"""로컬 HTTP로 두 모델을 실제 호출하고, 원문·실패 계층·분모를 검사한다."""
import contextlib,copy,io,json,unittest
from unittest.mock import patch
from model_probe_v055.audit import audit_run
from model_probe_v055.evidence import bundle_run
from model_probe_v055.contracts import ContractError,read_json,write_json,digest,sha
from model_probe_v055.__main__ import main
from .fixtures import shared,copied,executed

def selective(report,key):return sum(v['direction_selective_success'] for v in report['models'][key]['core_results'].values())
class Execution(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.base=shared()
    def test_perfect_both(self):
        r=self.base['report'];self.assertTrue(r['data_complete']);self.assertEqual(r['inference_calls'],240)
        self.assertEqual([selective(r,k) for k in r['models']],[40,40])
    def test_robust_both(self):
        self.assertEqual([sum(x['both_orders_selective_success'] for x in m['robust_results'].values()) for m in self.base['report']['models'].values()],[20,20])
    def test_primary_neutral_denominators(self):
        r=self.base['report'];self.assertEqual((r['primary_directed_assigned'],r['neutral_assigned']),(160,80))
    def test_cross_delta_zero_for_equal_models(self):self.assertTrue(all(c['candidate_minus_reference_rate']==0 for c in self.base['report']['cross_model_results'].values()))
    def test_offline_report_exact(self):
        with copied() as (_,p,r,_):
            with patch('model_probe_v055.runner.OllamaHTTP',side_effect=AssertionError('network forbidden')):self.assertEqual(audit_run(p,r),read_json(r/'summary.json'))
    def test_order_effect_not_control(self):
        with executed('first_branch') as (_,p,run,r,state):
            self.assertEqual(len(state.requests),240);self.assertEqual([selective(r,k) for k in r['models']],[0,0]);self.assertTrue(r['data_complete'])
            self.assertEqual([sum(x['depth_changed'] for x in m['order_results'].values()) for m in r['models'].values()],[60,60])
    def test_v054_like_reference_vs_perfect_candidate(self):
        with executed('v054_vs_perfect') as (_,p,run,r,state):
            self.assertEqual([selective(r,k) for k in r['models']],[0,40])
            self.assertTrue(all(c['candidate_only']==10 for c in r['cross_model_results'].values()))
            self.assertEqual(sum(t['measurement']['strict_valid'] for t in r['trials'] if t['model_key']=='reference'),90)
    def test_candidate_can_lose_fairly(self):
        with executed('candidate_first') as (_,p,run,r,state):
            self.assertEqual([selective(r,k) for k in r['models']],[40,0]);self.assertTrue(all(c['reference_only']==10 for c in r['cross_model_results'].values()))
    def test_same_depth_not_success(self):
        with executed('same_depth') as (_,p,run,r,state):self.assertEqual([selective(r,k) for k in r['models']],[0,0])
    def test_wrong_direction_not_success(self):
        with executed('inverse') as (_,p,run,r,state):self.assertEqual([selective(r,k) for k in r['models']],[0,0])
    def test_bad_final_not_repaired(self):
        with executed('bad_final') as (_,p,run,r,state):self.assertEqual(sum(t['measurement']['strict_valid'] for t in r['trials']),0)
    def test_unknown_rule_keeps_reference_existence(self):
        with executed('invalid_rule') as (_,p,run,r,state):
            self.assertTrue(all(t['measurement']['final_ref_valid'] is True and t['measurement']['proof_valid'] is False and t['measurement']['D'] is None for t in r['trials']))
    def test_http_stops_one_no_retry(self):
        with executed('http_error') as (_,p,run,r,state):
            self.assertFalse(r['data_complete']);self.assertEqual(r['inference_calls'],1);self.assertEqual(len(state.requests),1);self.assertEqual(r['failure_kind'],'transport_error')
            self.assertTrue(all(v['candidate_minus_reference_rate'] is None for v in r['cross_model_results'].values()))
    def test_second_model_failure_keeps_first_model_raw(self):
        with executed('candidate_http') as (_,p,run,r,state):
            self.assertEqual(r['inference_calls'],13);self.assertEqual(sum(t['observed'] for t in r['trials']),13);self.assertEqual(sum(t['status']=='unexecuted' for t in r['trials']),227)
    def test_preflight_identity_zero_calls(self):
        with executed('before_identity') as (_,p,run,r,state):self.assertEqual(r['inference_calls'],0);self.assertEqual(r['failure_kind'],'runtime_identity_error')
    def test_metadata_transport_zero_calls_and_raw(self):
        with executed('metadata_http') as (_,p,run,r,state):
            self.assertEqual(r['inference_calls'],0);self.assertEqual(r['failure_kind'],'runtime_metadata_error');self.assertEqual(len(list((run/'metadata').glob('*.json'))),1)
    def test_bad_metadata_json_zero_calls_and_raw(self):
        with executed('metadata_json') as (_,p,run,r,state):self.assertEqual(r['inference_calls'],0);self.assertEqual(r['failure_kind'],'runtime_metadata_error')
    def test_wrong_model_is_execution_not_answer_error(self):
        with executed('wrong_model') as (_,p,run,r,state):self.assertEqual(r['inference_calls'],1);self.assertEqual(r['failure_kind'],'response_identity_error')
    def test_postblock_drift_stops_at_twelve(self):
        with executed('drift') as (_,p,run,r,state):self.assertEqual(r['inference_calls'],12);self.assertEqual(r['failure_kind'],'runtime_identity_error')
    def test_truncated_proof_is_unmeasured(self):
        with executed('truncated') as (_,p,run,r,state):self.assertTrue(r['data_complete']);self.assertTrue(all(t['measurement']['proof_valid'] is None for t in r['trials']))
    def test_invalid_json_proof_is_unmeasured(self):
        with executed('syntax_error') as (_,p,run,r,state):self.assertTrue(r['data_complete']);self.assertTrue(all(t['measurement']['proof_valid'] is None for t in r['trials']))
    def test_missing_usage_not_zero(self):
        with executed('missing_usage') as (_,p,run,r,state):self.assertTrue(all(m['unique_execution_usage']['prompt_eval_count'] is None for m in r['models'].values()))
    def test_cli_exit_three_preserves_cause(self):
        r=copy.deepcopy(self.base['report']);r.update(data_complete=False,run_error='synthetic connection refused',failure_kind='transport_error')
        out=io.StringIO();err=io.StringIO()
        with patch('model_probe_v055.runner.execute',return_value=r),contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):code=main(['run','--plan','p','--out','r'])
        self.assertEqual(code,3);self.assertIn('synthetic connection refused',err.getvalue())
    def test_bundle_offline_exact(self):
        from paired_probe_v049.evidence import safe_unpack
        with copied() as (root,p,run,b):
            result=bundle_run(p,run,root/'b.zip');dest=root/'unpack';dest.mkdir();safe_unpack((root/'b.zip').read_bytes(),dest)
            self.assertEqual(audit_run(dest/'external_plan/v055.plan.json',dest/'run'),result)
    def test_do_not_overwrite_bundle(self):
        with copied() as (root,p,run,b):
            z=root/'keep.zip';z.write_bytes(b'keep')
            with self.assertRaises(ContractError):bundle_run(p,run,z)
            self.assertEqual(z.read_bytes(),b'keep')
