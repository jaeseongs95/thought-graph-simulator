import contextlib,io,unittest,tempfile
from pathlib import Path
from .fixtures import shared,executed
from selection_probe_v057.audit import audit_run
from selection_probe_v057.plan import prepare
from selection_probe_v057.contracts import read_json,ContractError

class Execution(unittest.TestCase):
    def test_real_http_480_complete(self):
        r=shared()['report'];self.assertEqual(r['inference_calls'],480);self.assertTrue(r['data_complete'])
        for m in r['models'].values():
            self.assertEqual(m['modes']['graph']['selective_success'],40);self.assertEqual(m['modes']['choice']['selective_success'],40)
    def test_prepare_no_inference(self):
        b=shared();before=len(b['state'].requests)
        with tempfile.TemporaryDirectory() as td:prepare(b['bundle'],Path(td)/'p.json')
        self.assertEqual(len(b['state'].requests),before)
    def test_offline_report_equal(self):
        b=shared();self.assertEqual(audit_run(b['root']/'v57.plan',b['root']/'v57.run'),b['report'])
    def test_choice_only_not_graph_success(self):
        with executed('choice_only') as (_,p,out,r,state):
            for m in r['models'].values():self.assertEqual(m['task_contrast']['choice_only'],40);self.assertEqual(m['modes']['graph']['full_proof_D_control_success'],0)
    def test_graph_only_is_retained(self):
        with executed('graph_only') as (_,p,out,r,state):
            for m in r['models'].values():self.assertEqual(m['task_contrast']['graph_only'],40)
    def test_first_branch_not_control(self):
        with executed('first_branch') as (_,p,out,r,state):
            for m in r['models'].values():
                for x in m['modes'].values():self.assertEqual(x['selective_success'],0);self.assertEqual(x['task_valid'],120)
    def test_invalid_rule_not_repaired(self):
        with executed('invalid_rule') as (_,p,out,r,state):
            for m in r['models'].values():
                for x in m['modes'].values():self.assertEqual(x['task_valid'],0)
    def test_syntax_is_unmeasured(self):
        with executed('syntax_error') as (_,p,out,r,state):
            for t in r['trials']:
                self.assertIsNone(t['measurement']['proof_valid'])
                if t['mode']=='choice':self.assertIsNone(t['measurement']['choice_valid'])
    def test_http_no_retry(self):
        with executed('http_error') as (_,p,out,r,state):self.assertEqual(r['inference_calls'],1);self.assertEqual(len(state.requests),1);self.assertEqual(r['failure_kind'],'transport_error');self.assertFalse(r['data_complete'])
    def test_second_model_http_no_false_neither(self):
        with executed('candidate_http') as (_,p,out,r,state):
            self.assertEqual(r['inference_calls'],25);self.assertEqual(len(state.requests),25)
            self.assertEqual(r['models']['candidate']['task_contrast']['neither'],0);self.assertIsNone(r['models']['candidate']['choice_minus_graph_rate'])
    def test_metadata_error_no_calls(self):
        with executed('metadata_http') as (_,p,out,r,state):self.assertEqual(r['inference_calls'],0);self.assertEqual(len(state.requests),0)
    def test_model_drift_stops(self):
        with executed('drift') as (_,p,out,r,state):self.assertEqual(r['inference_calls'],24);self.assertEqual(r['failure_kind'],'runtime_identity_error')
    def test_wrong_response_model_stops(self):
        with executed('wrong_model') as (_,p,out,r,state):self.assertEqual(r['inference_calls'],1);self.assertEqual(r['failure_kind'],'response_identity_error')
    def test_truncated_never_success(self):
        with executed('truncated') as (_,p,out,r,state):
            self.assertTrue(r['data_complete'])
            for m in r['models'].values():
                for x in m['modes'].values():self.assertEqual(x['task_valid'],0)
    def test_missing_usage_stays_missing(self):
        with executed('missing_usage') as (_,p,out,r,state):
            for c in r['calls']:self.assertIsNone(c['prompt_eval_count'])
    def test_existing_result_rejected(self):
        from selection_probe_v057.runner import execute
        b=shared()
        with self.assertRaises(ContractError):execute(b['root']/'v57.plan',b['root']/'v57.run')
