from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import os,sys,unittest,tempfile,io,contextlib,json,zipfile,threading,socketserver,time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core088 as c,design088 as d,fixtures088 as f,run088 as run,verify088 as verify

BASE=Path(os.environ.get('V088_BASELINE',str(Path.home()/'Downloads'/c.spec()['baseline_name'])))

class Runtime(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='v088_runtime_test_');cls.root=Path(cls.tmp.name);cls.p=d.make_plan(BASE,'v088_complete_synthetic','synthetic',False);c.save(cls.root/'plan.json',cls.p)
        with patch.object(run,'exchange',f.fake_exchange()),contextlib.redirect_stdout(io.StringIO()):
            cls.result=run.execute(cls.root/'plan.json',BASE,cls.root/cls.p['run_name'],'http://127.0.0.1:11434')
        cls.fs=c.unzip(Path(cls.result['evidence_zip']).read_bytes());cls.receipt=c.load(Path(cls.result['independent_json']).read_bytes())
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_complete_dispatch_response_preserved(self):self.assertEqual((self.receipt['state'],self.receipt['inference_calls'],self.receipt['observed_calls']),('complete',3136,3136))
    def test_independent_full_evidence(self):self.assertTrue(self.receipt['verified']);self.assertEqual(self.receipt['differences'],[]);self.assertFalse(self.receipt['production_imports'])
    def test_status_completeness(self):self.assertEqual(self.receipt['completed_actions'],3232);self.assertEqual(self.receipt['started_actions'],3232);self.assertIsNone(self.receipt['pending_action'])
    def test_frozen_guard_blocks_new_name(self):
        p=deepcopy(self.p);p['run_name']='v088_new_name';p.pop('plan_sha256');p['plan_sha256']=c.sha(c.wire(p));c.save(self.root/'new.plan.json',p)
        with patch.object(run,'exchange',side_effect=AssertionError('must not call')),self.assertRaises(FileExistsError):run.execute(self.root/'new.plan.json',BASE,self.root/p['run_name'],'http://127.0.0.1:11434')
    def test_finalize_is_idempotent(self):
        out=self.root/self.p['run_name'];hash_before=c.sha(Path(self.result['evidence_zip']).read_bytes());result=run.finalize(out);self.assertEqual(hash_before,c.sha(Path(result['evidence_zip']).read_bytes()))
    def mutated(self,change):
        fs=dict(self.fs);change(fs);fs['MANIFEST.json']=c.wire({'contract':'v088-evidence-r1','file_hashes':{n:c.sha(b)for n,b in fs.items()if n!='MANIFEST.json'}})
        p=self.root/'mutated.zip'
        if p.exists():p.unlink()
        c.write(p,c.zip_bytes(fs));return p
    def test_summary_tamper_rejected_even_if_manifest_updated(self):
        def change(fs):
            x=c.load(fs['summary.json']);x['groups']['end_to_end']['baseline']['outcome']['success']=127;fs['summary.json']=c.wire(x)
        with self.assertRaises(ValueError):verify.verify_bundle(self.mutated(change))
    def test_support_diagnostic_tamper_rejected(self):
        def change(fs):
            x=c.load(fs['summary.json']);x['rows'][0]['rule_check']['error_codes']=['fabricated'];fs['summary.json']=c.wire(x)
        with self.assertRaises(ValueError):verify.verify_bundle(self.mutated(change))
    def test_source_snapshot_tamper_rejected(self):
        with self.assertRaises(ValueError):verify.verify_bundle(self.mutated(lambda fs:fs.__setitem__('source/design088.py',fs['source/design088.py']+b'\n# changed')))
    def test_unaccounted_file_rejected(self):
        with self.assertRaises(ValueError):verify.verify_bundle(self.mutated(lambda fs:fs.__setitem__('extra.txt',b'ignored?')))
    def test_request_byte_tamper_rejected(self):
        name=next(n for n in self.fs if n.startswith('wire/')and n.endswith('/request.wire.json'))
        with self.assertRaises(ValueError):verify.verify_bundle(self.mutated(lambda fs:fs.__setitem__(name,fs[name]+b' ')))
    def test_wire_response_tamper_rejected(self):
        name=next(n for n in self.fs if n.startswith('wire/')and n.endswith('/response.raw.json'))
        with self.assertRaises(ValueError):verify.verify_bundle(self.mutated(lambda fs:fs.__setitem__(name,fs[name]+b' ')))
    def scenario(self,ex,write_hook=None):
        temp=tempfile.TemporaryDirectory(prefix='v088_failure_');self.addCleanup(temp.cleanup);root=Path(temp.name);p=d.make_plan(BASE,'v088_failure_synthetic','synthetic',False);c.save(root/'plan.json',p)
        with patch.object(run,'exchange',ex),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            if write_hook is None:result=run.execute(root/'plan.json',BASE,root/p['run_name'],'http://127.0.0.1:11434')
            else:
                orig=run.common.write
                def wrapped(path,raw):
                    if write_hook(Path(path)):raise OSError('injected before record commit')
                    return orig(path,raw)
                with patch.object(run.common,'write',wrapped):result=run.execute(root/'plan.json',BASE,root/p['run_name'],'http://127.0.0.1:11434')
        return c.load(Path(result['independent_json']).read_bytes()),c.unzip(Path(result['evidence_zip']).read_bytes())
    def test_http_failure_no_retry(self):
        ex=f.fake_exchange(http_at=1);receipt,fs=self.scenario(ex);self.assertEqual(ex.count['chat'],1);self.assertEqual(receipt['state'],'stopped');self.assertEqual(c.load(fs['status.json'])['reason'],'http_error')
    def test_transport_partial_body_preserved(self):
        ex=f.fake_exchange(transport_at=1);receipt,fs=self.scenario(ex);raws=[b for n,b in fs.items()if n.startswith('wire/')and n.endswith('/response.raw.json')];self.assertEqual(raws,[b'{partial']);self.assertEqual(receipt['state'],'stopped')
    def test_identity_mismatch_before_inference(self):
        ex=f.fake_exchange(identity_error=True);receipt,fs=self.scenario(ex);self.assertEqual(ex.count['chat'],0);self.assertEqual(receipt['inference_calls'],0);self.assertEqual(receipt['state'],'stopped')
    def test_crash_after_dispatch_is_pending_not_wrong_answer(self):
        receipt,fs=self.scenario(f.fake_exchange(crash_at=1));self.assertEqual((receipt['inference_calls'],receipt['observed_calls']),(1,0));self.assertTrue(receipt['pending_action']['dispatch_marked']);s=c.load(fs['summary.json']);self.assertIsNone(s['primary']['mean_delta'])
    def test_response_saved_before_record_commit_survives_windows_path_logic(self):
        sid=next(o['id']for o in self.p['slots']);receipt,fs=self.scenario(f.fake_exchange(),lambda p:p.parent.name=='records'and p.name==sid+'.json')
        self.assertEqual((receipt['state'],receipt['inference_calls'],receipt['observed_calls']),('crashed',1,1));self.assertTrue(receipt['pending_action']['response_saved'])
    def test_remote_endpoint_rejected(self):
        for ep in ('https://127.0.0.1:11434','http://example.com','http://user@localhost','http://localhost/x','http://localhost/?x=1'):
            with self.subTest(endpoint=ep),self.assertRaises(ValueError):run.endpoint_ok(ep)
    def test_local_endpoints_accepted(self):
        for ep in ('http://127.0.0.1:11434','http://localhost:11434','http://[::1]:11434'):self.assertEqual(run.endpoint_ok(ep),ep)
    def test_archive_paths_rejected(self):
        for n in ('../bad','/tmp/bad','C:/bad','CON.json','bad\\path'):
            with self.subTest(path=n),self.assertRaises(ValueError):c.safe_name(n)
    def test_frozen_transport_code_regression(self):
        old=(c.ROOT/'frozen087/run087.py').read_text();new=(c.ROOT/'run088.py').read_text();begin='def read_http_body(';end='def identity_matches(';self.assertEqual(old[old.index(begin):old.index(end)],new[new.index(begin):new.index(end)])

class HTTP(unittest.TestCase):
    def exchange_bytes(self,reply):
        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                self.request.recv(65536);self.request.sendall(reply)
        class Server(socketserver.TCPServer):allow_reuse_address=True
        server=Server(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.handle_request,daemon=True);thread.start()
        try:return run.exchange('http://127.0.0.1:'+str(server.server_address[1]),'/test',None,3)
        finally:thread.join(5);server.server_close()
    def test_normal_content_length(self):
        code,raw,error,_=self.exchange_bytes(b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}');self.assertEqual((code,raw,error),(200,b'{}',None))
    def test_short_content_length(self):
        code,raw,error,_=self.exchange_bytes(b'HTTP/1.1 200 OK\r\nContent-Length: 9\r\nConnection: close\r\n\r\n{}');self.assertEqual(raw,b'{}');self.assertIn('incomplete_http_body',error)
    def test_complete_chunked(self):
        code,raw,error,_=self.exchange_bytes(b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n2\r\n{}\r\n0\r\n\r\n');self.assertEqual((code,raw,error),(200,b'{}',None))
    def test_incomplete_chunked_retains_body(self):
        code,raw,error,_=self.exchange_bytes(b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n2\r\n{}\r\n');self.assertEqual(raw,b'{}');self.assertIsNotNone(error)
    def test_HTTP_error_body_retained(self):
        code,raw,error,_=self.exchange_bytes(b'HTTP/1.1 503 Error\r\nContent-Length: 3\r\nConnection: close\r\n\r\nbad');self.assertEqual((code,raw),(503,b'bad'))
    def test_redirect_is_not_followed(self):
        code,raw,error,_=self.exchange_bytes(b'HTTP/1.1 302 Found\r\nLocation: http://example.invalid\r\nContent-Length: 0\r\nConnection: close\r\n\r\n');self.assertEqual(code,302)
