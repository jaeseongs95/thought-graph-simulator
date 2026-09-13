import contextlib,copy,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from layout_probe_v056.contracts import ContractError,read_json,write_json
from layout_probe_v056.audit import audit_run
from layout_probe_v056.evidence import bundle_run,safe_unpack
from .fixtures import shared,copied,executed
from .test_quick_reporting import counts

class Execution(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.base=shared()
    def test_real_http_480_perfect(self):
        r=self.base['report'];self.assertTrue(r['data_complete']);self.assertEqual(r['inference_calls'],480);self.assertEqual(counts(r),[40,40,40,40])
    def test_prepare_and_show_do_not_infer(self):
        from layout_probe_v056.plan import prepare
        b=self.base;n=len(b['state'].requests)
        with tempfile.TemporaryDirectory() as td:
            prepare(b['bundle'],Path(td)/'plan.json')
        self.assertEqual(len(b['state'].requests),n)
    def test_all_request_text_preserved_on_wire(self):
        from layout_probe_v056.contracts import strict_json,unb64
        p=self.base['plan'];run=self.base['root']/'v56.run'
        for s in p['slots']:
            raw=(run/'calls'/s['id']/'request.wire.json').read_bytes();old=unb64(p['reference']['request_bank'][s['reference_slot_id']])
            if s['layout']=='split':self.assertEqual(raw,old)
            else:
                q=strict_json(raw);orig=strict_json(old);messages=orig.pop('messages');qms=q.pop('messages');self.assertEqual(q,orig);self.assertEqual(qms[0]['content'],messages[0]['content']+'\n\n'+messages[1]['content'])
    def test_offline_report_exact(self):
        with copied() as (_,p,r,_),patch('layout_probe_v056.runner.OllamaHTTP',side_effect=AssertionError('offline')):self.assertEqual(audit_run(p,r),read_json(r/'summary.json'))
    def test_first_path_not_control(self):
        with executed('first_branch') as (_,p,r,report,state):self.assertEqual(counts(report),[0,0,0,0]);self.assertEqual(len(state.requests),480)
    def test_merged_can_win(self):
        with executed('merged_only') as (_,p,r,report,state):self.assertEqual(counts(report),[0,0,40,40]);self.assertTrue(all(c['merged_only']==10 for c in report['layout_results'].values()))
    def test_split_can_win(self):
        with executed('split_only') as (_,p,r,report,state):self.assertEqual(counts(report),[40,40,0,0]);self.assertTrue(all(c['split_only']==10 for c in report['layout_results'].values()))
    def test_validity_only_is_not_control(self):
        with executed('validity_only') as (_,p,r,report,state):self.assertEqual(counts(report),[0,0,0,0]);self.assertTrue(all(c['merged_only_valid']==120 for c in report['validity_contrasts'].values()))
    def test_http_stops_no_retry_one(self):
        with executed('http_error') as (_,p,r,report,state):self.assertEqual(report['inference_calls'],1);self.assertEqual(len(state.requests),1);self.assertFalse(report['data_complete']);self.assertTrue(all(c['merged_minus_split_rate'] is None for c in report['layout_results'].values()))
    def test_second_model_failure_preserves_24(self):
        with executed('candidate_http') as (_,p,r,report,state):self.assertEqual(report['inference_calls'],25);self.assertEqual(sum(t['observed'] for t in report['trials']),25)
    def test_metadata_error_zero_inference(self):
        with executed('metadata_http') as (_,p,r,report,state):self.assertEqual(report['inference_calls'],0);self.assertEqual(report['failure_kind'],'runtime_metadata_error')
    def test_identity_mismatch_zero_inference(self):
        with executed('before_identity') as (_,p,r,report,state):self.assertEqual(report['inference_calls'],0);self.assertEqual(report['failure_kind'],'runtime_identity_error')
    def test_postblock_drift_stops_after_24(self):
        with executed('drift') as (_,p,r,report,state):self.assertEqual(report['inference_calls'],24);self.assertEqual(report['failure_kind'],'runtime_identity_error')
    def test_response_wrong_model_not_answer_error(self):
        with executed('wrong_model') as (_,p,r,report,state):self.assertEqual(report['inference_calls'],1);self.assertEqual(report['failure_kind'],'response_identity_error')
    def test_truncated_not_incorrect(self):
        with executed('truncated') as (_,p,r,report,state):self.assertTrue(report['data_complete']);self.assertTrue(all(t['measurement']['proof_valid'] is None for t in report['trials']))
    def test_invalid_json_not_incorrect(self):
        with executed('syntax_error') as (_,p,r,report,state):self.assertTrue(report['data_complete']);self.assertTrue(all(t['measurement']['proof_valid'] is None for t in report['trials']))
    def test_bundle_offline_reaudit(self):
        with copied() as (root,p,r,b):
            report=bundle_run(p,r,root/'evidence.zip');dest=root/'unpack';dest.mkdir();safe_unpack((root/'evidence.zip').read_bytes(),dest)
            self.assertEqual(audit_run(dest/'external_plan/v056.plan.json',dest/'run'),report)
    def test_existing_bundle_not_overwritten(self):
        with copied() as (root,p,r,b):
            out=root/'keep.zip';out.write_bytes(b'keep')
            with self.assertRaises(ContractError):bundle_run(p,r,out)
            self.assertEqual(out.read_bytes(),b'keep')
