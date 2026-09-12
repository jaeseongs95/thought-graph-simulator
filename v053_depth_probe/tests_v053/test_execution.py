"""합성 HTTP 실행과 오프라인 재감사·오류 주입을 검사한다."""
import contextlib
import copy
import io
import json
import unittest
from unittest.mock import patch
from depth_probe_v053.audit import audit_run
from depth_probe_v053.evidence import bundle_run
from depth_probe_v053.contracts import ContractError,read_json,write_json,digest,sha
from depth_probe_v053.__main__ import main
from .fixtures import shared,copied,executed

class Execution(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.base=shared()
    def test_complete_perfect_run(self):
        r=self.base['report'];self.assertTrue(r['data_complete']);self.assertEqual(r['inference_calls'],120)
        self.assertEqual(sum(v['direction_selective_success'] for v in r['core_results'].values()),40)
    def test_primary_denominator_excludes_neutral(self):
        r=self.base['report'];self.assertEqual(r['primary_directed_assigned'],80);self.assertEqual(r['neutral_assigned'],40)
    def test_neutral_one_output_not_two_calls(self):
        r=self.base['report'];self.assertEqual(len(r['neutral_comparisons']),40)
        self.assertTrue(all(x['neutral_standardized_success']==0.5 for x in r['neutral_comparisons']))
    def test_no_fabricated_definition_improvement(self):
        r=self.base['report'];self.assertTrue(all(x['defined_minus_original_pair_success']==0 for x in r['definition_contrasts']))
    def test_offline_report_exact(self):
        with copied() as (root,p,run,b):
            with patch('depth_probe_v053.runner.OllamaHTTP',side_effect=AssertionError('network forbidden')):
                self.assertEqual(audit_run(p,run),read_json(run/'summary.json'))
    def test_always_same_depth_is_not_control(self):
        with executed('ignore_roles') as (root,p,run,r,state):
            self.assertEqual(r['inference_calls'],120);self.assertEqual(len(state.requests),120)
            self.assertTrue(all(x['both_valid_pairs']==10 and x['direction_selective_success']==0 for x in r['core_results'].values()))
            self.assertTrue(all(x['mean_directed_minus_neutral']==0 for x in r['core_results'].values()))
    def test_bad_final_not_repaired(self):
        with executed('bad_final') as (root,p,run,r,state):
            self.assertTrue(r['data_complete']);self.assertTrue(all(x['both_valid_pairs']==0 for x in r['core_results'].values()))
    def test_infra_failure_stops_one_call(self):
        with executed('http_error') as (root,p,run,r,state):
            self.assertFalse(r['data_complete']);self.assertEqual(r['inference_calls'],1);self.assertEqual(len(state.requests),1)
            self.assertEqual(r['failure_kind'],'transport_error');self.assertTrue(all(x['rate_over_assigned'] is None for x in r['core_results'].values()))
    def test_identity_failure_before_inference(self):
        with executed('before_identity_error') as (root,p,run,r,state):
            self.assertFalse(r['data_complete']);self.assertEqual(r['inference_calls'],0);self.assertEqual(len(state.requests),0)
            self.assertEqual(r['failure_stage'],'preflight_identity')
    def test_wrong_model_stops_one_call(self):
        with executed('wrong_model') as (root,p,run,r,state):
            self.assertFalse(r['data_complete']);self.assertEqual(r['inference_calls'],1);self.assertEqual(r['failure_kind'],'response_identity_error')
    def test_truncated_generation_is_not_unexecuted(self):
        with executed('truncated') as (root,p,run,r,state):
            self.assertTrue(r['data_complete']);self.assertEqual(r['inference_calls'],120)
            self.assertTrue(all(x['measurement']['proof_valid'] is None for x in r['trials']))
    def test_raw_tamper_rejected(self):
        with copied() as (root,p,run,b):
            raw=next((run/'calls').glob('*/response.raw.json'));raw.write_bytes(raw.read_bytes()+b' ')
            with self.assertRaises(ContractError):audit_run(p,run)
    def test_resealed_request_tamper_rejected(self):
        with copied() as (root,p,run,b):
            events=[json.loads(x) for x in (run/'events.jsonl').read_text().splitlines()];first=events[0]
            raw=run/'calls'/first['slot']['id']/'request.wire.json';raw.write_bytes(raw.read_bytes()+b' ');first['request_sha256']=sha(raw.read_bytes())
            previous=read_json(p)['plan_sha256']
            for event in events:
                event['previous_hash']=previous;event['event_hash']=digest({k:v for k,v in event.items() if k!='event_hash'});previous=event['event_hash']
            (run/'events.jsonl').write_text('\n'.join(json.dumps(e) for e in events)+'\n')
            status=read_json(run/'status.json');status['event_tip']=previous;write_json(run/'status.json',status)
            with self.assertRaises(ContractError):audit_run(p,run)
    def test_added_call_file_rejected(self):
        with copied() as (root,p,run,b):
            (run/'calls'/'unregistered.txt').write_text('x')
            with self.assertRaises(ContractError):audit_run(p,run)
    def test_source_snapshot_change_rejected(self):
        with copied() as (root,p,run,b):
            q=next((run/'source_snapshot').rglob('*.py'));q.write_bytes(q.read_bytes()+b'\n')
            with self.assertRaises(ContractError):audit_run(p,run)
    def test_runtime_drift_rejected(self):
        with executed('runtime_drift') as (root,p,run,r,state):
            self.assertFalse(r['data_complete']);self.assertEqual(r['failure_stage'],'postflight_identity')
    def test_failed_audit_invalidates_old_summary(self):
        with copied() as (root,p,run,b):
            raw=next((run/'calls').glob('*/response.raw.json'));raw.write_bytes(b'{}')
            with self.assertRaises(ContractError):audit_run(p,run,write_report=True)
            self.assertFalse(read_json(run/'summary.json')['data_integrity'])
    def test_report_prints_depth_and_pair_tables(self):
        text=(self.base['root']/'v53.run/summary.ko.md').read_text()
        self.assertIn('요청 깊이 일치',text);self.assertIn('선택적 제어',text);self.assertIn('중립',text)
    def test_bundle_reauditable(self):
        from paired_probe_v049.evidence import safe_unpack
        with copied() as (root,p,run,b):
            z=root/'evidence.zip';r=bundle_run(p,run,z);target=root/'unpack';target.mkdir();safe_unpack(z.read_bytes(),target)
            self.assertEqual(audit_run(target/'external_plan/v053.plan.json',target/'run'),r)
    def test_existing_bundle_not_overwritten(self):
        with copied() as (root,p,run,b):
            z=root/'evidence.zip';z.write_bytes(b'keep')
            with self.assertRaises(ContractError):bundle_run(p,run,z)
            self.assertEqual(z.read_bytes(),b'keep')
    def test_cli_exit3_surfaces_failure(self):
        r=copy.deepcopy(self.base['report']);r.update(data_complete=False,failure_stage='preflight_metadata',failure_kind='runtime_metadata_error',run_error='synthetic connection refused')
        out=io.StringIO();err=io.StringIO()
        with patch('depth_probe_v053.runner.execute',return_value=r),contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
            code=main(['run','--plan','plan','--out','run'])
        self.assertEqual(code,3);self.assertIn('synthetic connection refused',err.getvalue())
