import contextlib,io,json,tempfile,threading,unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from fixtures import plan,baseline_path,Synth
import common,run,verify,design

class Integration(unittest.TestCase):
    def execute_mode(self,mode,extra=None):
        td=tempfile.TemporaryDirectory(prefix='v079_integration_');self.addCleanup(td.cleanup)
        root=Path(td.name);p=plan('v079_integration');pp=root/'plan.json';common.save(pp,p);s=Synth(mode)
        with patch.object(run,'exchange',s.exchange),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            result=run.execute(pp,baseline_path(),root/'results'/p['run_name'],'http://127.0.0.1:11434')
        receipt=common.load(Path(result['independent_json']).read_bytes())
        summary=common.load((root/'results'/p['run_name']/'summary.json').read_bytes())
        return result,receipt,summary,root,p,pp,s
    def test_complete_dynamic_calls_verified(self):
        result,r,s,*_=self.execute_mode('correct');self.assertEqual(r['inference_calls'],584);self.assertEqual(r['completed_actions'],616);self.assertTrue(r['verified']);self.assertTrue(s['end_to_end_baseline_ready'])
    def test_maximum_budget_600(self):
        result,r,s,*_=self.execute_mode('max_rules');self.assertEqual(r['inference_calls'],600);self.assertFalse(s['end_to_end_baseline_ready'])
    def test_minimum_mapped_budget_568(self):
        result,r,s,*_=self.execute_mode('min_rules');self.assertEqual(r['inference_calls'],568)
    def test_blocked_dependencies_no_fake_inference(self):
        result,r,s,*_=self.execute_mode('invalid_selector');self.assertEqual(r['inference_calls'],216);self.assertEqual(s['skipped_action_slots']['unmappable_selection'],384);self.assertIsNone(s['end_to_end_baseline_ready'])
    def test_http_error_stops_without_retry(self):
        result,r,s,*_=self.execute_mode('http_error');self.assertEqual(r['state'],'stopped');self.assertEqual(r['inference_calls'],1);self.assertEqual(r['observed_calls'],1)
    def test_transport_error_stops_without_retry(self):
        result,r,s,*_=self.execute_mode('transport_error');self.assertEqual(r['state'],'stopped');self.assertEqual(r['inference_calls'],1)
    def test_wrong_response_identity_stops(self):
        result,r,s,*_=self.execute_mode('wrong_identity');self.assertEqual(r['state'],'stopped');self.assertEqual(r['inference_calls'],1)
    def test_budget_excess_stops(self):
        result,r,s,*_=self.execute_mode('budget_exceeded');self.assertEqual(r['state'],'stopped');self.assertEqual(r['inference_calls'],1)
    def test_metadata_mismatch_stops_before_inference(self):
        result,r,s,*_=self.execute_mode('metadata_mismatch');self.assertEqual(r['state'],'stopped');self.assertEqual(r['inference_calls'],0)
    def test_interrupt_keeps_pending_dispatch(self):
        result,r,s,*_=self.execute_mode('interrupt');self.assertEqual(r['state'],'crashed');self.assertEqual(r['inference_calls'],1);self.assertEqual(r['observed_calls'],0);self.assertTrue(r['pending_action']['dispatch_marked']);self.assertFalse(r['pending_action']['response_saved'])
    def test_failure_before_dispatch_has_no_inference(self):
        with patch.object(design,'request_for',side_effect=ValueError('request limit fixture')):
            result,r,s,*_=self.execute_mode('correct')
        self.assertEqual(r['state'],'crashed');self.assertEqual(r['inference_calls'],0);self.assertFalse(r['pending_action']['dispatch_marked'])
    def test_new_run_name_cannot_restart_same_batch(self):
        result,r,s,root,p,pp,_=self.execute_mode('http_error')
        p2=plan('v079_second');q=root/'second.plan.json';common.save(q,p2)
        with self.assertRaises(FileExistsError):run.execute(q,baseline_path(),root/'results'/'v079_second','http://127.0.0.1:11434')
    def test_finalize_is_offline_and_idempotent(self):
        result,r,s,root,p,*_=self.execute_mode('correct')
        with patch.object(run,'exchange',side_effect=AssertionError('network forbidden')):
            again=run.finalize(root/'results'/p['run_name'])
        self.assertEqual(result,again)
    def test_remote_endpoints_rejected(self):
        for url in ['https://127.0.0.1:11434','http://example.com','http://u:p@localhost','http://localhost/x','http://localhost?x=1']:
            with self.assertRaises(ValueError):run.endpoint_ok(url)
    def test_synthetic_real_http_exchange(self):
        synth=Synth('correct')
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):self.respond()
            def do_POST(self):self.respond()
            def log_message(self,*args):pass
            def respond(self):
                body=self.rfile.read(int(self.headers.get('Content-Length','0'))) if self.command=='POST' else None
                code,raw,err,ns=synth.exchange('',self.path,body,1)
                self.send_response(code);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(raw)
        srv=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=srv.serve_forever,daemon=True);thread.start()
        self.addCleanup(srv.server_close);self.addCleanup(srv.shutdown)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p=plan('v079_http');pp=root/'plan.json';common.save(pp,p)
            with contextlib.redirect_stdout(io.StringIO()):result=run.execute(pp,baseline_path(),root/'results'/p['run_name'],f'http://127.0.0.1:{srv.server_port}')
            self.assertEqual(result['inference_calls'],584)
            self.assertEqual(synth.calls,584);self.assertTrue(verify.verify_bundle(Path(result['evidence_zip']))['verified'])

if __name__=='__main__':unittest.main()
