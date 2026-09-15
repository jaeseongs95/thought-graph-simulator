"""r2 재검토 반례: graph 오류 보존과 불완전 HTTP 응답. 실제 Ollama 호출 없음."""
from pathlib import Path
from copy import deepcopy
from email.message import Message
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
import contextlib, io, sys, tempfile, threading, unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core086 as c, design086 as design, run086 as run, report086 as report, audit086
from byte_diagnostics086 import collect
from fixtures086 import plan, response_set, fake_exchange, BASELINE


class FailureDiagnostics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p=plan()
        cls.target=next(o['id'] for o in cls.p['slots'] if o['stage']=='rule' and 'two_stage_values' in o['id'])
        def damage(op,body,raw):
            if op['id']!=cls.target:return raw
            x=c.load(raw);obj=c.load(x['message']['content']);obj['node']['parents']=[]
            x['message']['content']=c.wire(obj).decode();return c.wire(x)
        cls.records,cls.raws,cls.requests=response_set(cls.p,transform=damage)
        cls.summary=report.summarize(cls.p,cls.records,cls.raws,'complete')
        cls.d=collect(cls.p,cls.requests,cls.raws,cls.summary['trials'])
    def test_real_synthetic_failure_keeps_graph_error_codes(self):
        row=next(r for r in self.summary['trials'] if r['generator_success'] is False)
        diag=next(r for r in self.d['generation_failures'] if r['trial_id']==row['trial_id'])
        self.assertIn('premise_counter_mismatch',row['graph_result']['error_codes'])
        self.assertEqual(diag['graph_errors'],row['graph_result']['error_codes'])
    def test_graph_errors_preserve_overlapping_codes(self):
        rows=deepcopy(self.summary['trials']);row=next(r for r in rows if r['generator_success'] is False)
        codes=['duplicate_id','missing_parent','premise_counter_mismatch']
        row['graph_result']['error_codes']=codes[:]
        ds=collect(self.p,self.requests,self.raws,rows)
        diag=next(r for r in ds['generation_failures'] if r['trial_id']==row['trial_id'])
        self.assertEqual(diag['graph_errors'],codes)
        diag['graph_errors'].append('not_an_original_code')
        self.assertEqual(row['graph_result']['error_codes'],codes)
    def test_format_failure_without_graph_stays_separate(self):
        rows=deepcopy(self.summary['trials']);row=next(r for r in rows if r['generator_success'] is False)
        row['graph_result']=None;row['generator_status']='model_output_format_failure'
        ds=collect(self.p,self.requests,self.raws,rows)
        diag=next(r for r in ds['generation_failures'] if r['trial_id']==row['trial_id'])
        self.assertEqual(diag['graph_errors'],[])
        self.assertEqual(diag['generator_status'],'model_output_format_failure')
    def test_primary_scores_independent_on_failure_fixture(self):
        other=audit086.independent_summary(self.p,self.records,self.raws,'complete')
        self.assertTrue(c.exact(self.summary,other))


@contextlib.contextmanager
def server(mode, payload=b'{"ok":true}', model_fixture=None):
    requests=[]
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):self.reply(None)
        def do_POST(self):self.reply(self.rfile.read(int(self.headers.get('Content-Length',0))))
        def reply(self,body):
            requests.append((self.command,self.path,body))
            code,data=200,payload
            chat=self.path=='/api/chat'
            if model_fixture is not None:
                code,data,_,_=model_fixture('synthetic',self.path,body,5)
            if mode=='http_error' and chat:code=503
            self.send_response(code)
            active=mode if chat else 'normal'
            if active in ('chunked','missing_chunk_end'):
                self.send_header('Transfer-Encoding','chunked');self.end_headers()
                self.wfile.write(('%x\r\n'%len(data)).encode()+data+b'\r\n')
                if active=='chunked':self.wfile.write(b'0\r\n\r\n')
            else:
                extra=23 if active=='short_length' else 0
                self.send_header('Content-Length',str(len(data)+extra));self.end_headers();self.wfile.write(data)
            self.wfile.flush();self.close_connection=True
        def log_message(self,*args):pass
    instance=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=instance.serve_forever,daemon=True);thread.start()
    try:yield 'http://127.0.0.1:'+str(instance.server_port),requests
    finally:instance.shutdown();instance.server_close();thread.join(timeout=5)


class HttpFraming(unittest.TestCase):
    def test_content_length_short_body_is_transport_error(self):
        data=b'{"ok":true}'
        with server('short_length',data) as (endpoint,calls):
            code,raw,error,_=run.exchange(endpoint,'/api/chat',b'{}',5)
        self.assertEqual((code,raw),(200,data));self.assertIn('incomplete_http_body',error)
        self.assertEqual(len(calls),1)
    def test_missing_chunk_terminator_preserves_partial_body(self):
        data=b'{"ok":true}'
        with server('missing_chunk_end',data) as (endpoint,calls):
            code,raw,error,_=run.exchange(endpoint,'/api/chat',b'{}',5)
        self.assertEqual((code,raw,error),(200,data,'IncompleteRead'));self.assertEqual(len(calls),1)
    def test_complete_length_response_unchanged(self):
        with server('normal') as (endpoint,calls):
            code,raw,error,_=run.exchange(endpoint,'/api/chat',b'{}',5)
        self.assertEqual((code,raw,error),(200,b'{"ok":true}',None))
    def test_complete_chunked_response_unchanged(self):
        with server('chunked') as (endpoint,calls):
            code,raw,error,_=run.exchange(endpoint,'/api/chat',b'{}',5)
        self.assertEqual((code,raw,error),(200,b'{"ok":true}',None))
    def test_timeout_keeps_already_read_body(self):
        headers=Message();headers['Content-Length']='100'
        outputs=iter([b'partial-json',TimeoutError('synthetic timeout')])
        def read1(n):
            item=next(outputs)
            if isinstance(item,Exception):raise item
            return item
        raw,error=run.read_http_body(SimpleNamespace(headers=headers,read1=read1))
        self.assertEqual((raw,error),(b'partial-json','TimeoutError'))
    def test_oversized_body_stays_bounded(self):
        data=b'x'*(run.MAX_HTTP_BODY+100)
        with server('normal',data) as (endpoint,calls):
            code,raw,error,_=run.exchange(endpoint,'/api/chat',b'{}',5)
        self.assertEqual(len(raw),run.MAX_HTTP_BODY+1);self.assertEqual(error,'response_size_limit')
    def test_http_error_body_is_preserved(self):
        with server('http_error',b'synthetic error') as (endpoint,calls):
            code,raw,error,_=run.exchange(endpoint,'/api/chat',b'{}',5)
        self.assertEqual((code,raw,error),(503,b'synthetic error',None))
    def test_invalid_content_length_never_becomes_success(self):
        headers=Message();headers['Content-Length']='wrong'
        parts=iter([b'{}',b''])
        raw,error=run.read_http_body(SimpleNamespace(headers=headers,read1=lambda n:next(parts)))
        self.assertEqual((raw,error),(b'{}','invalid_content_length'))
    def test_conflicting_lengths_never_become_success(self):
        headers=Message();headers.add_header('Content-Length','2');headers.add_header('Content-Length','3')
        parts=iter([b'{}',b''])
        raw,error=run.read_http_body(SimpleNamespace(headers=headers,read1=lambda n:next(parts)))
        self.assertEqual((raw,error),(b'{}','conflicting_content_length'))
    @unittest.skipUnless(BASELINE.is_file(),'v085 evidence required')
    def test_short_body_stops_batch_and_keeps_verified_evidence(self):
        self.check_stopped_batch('short_length')
    @unittest.skipUnless(BASELINE.is_file(),'v085 evidence required')
    def test_chunked_interruption_stops_batch_and_keeps_verified_evidence(self):
        self.check_stopped_batch('missing_chunk_end')
    def check_stopped_batch(self,mode):
        from verify086 import verify_bundle
        with tempfile.TemporaryDirectory(prefix='v086_transport_review_') as tmp:
            root=Path(tmp);p=design.make_plan(BASELINE,'v086_'+mode,'synthetic',audit_previous=False)
            pp=root/'plan.json';c.save(pp,p)
            with server(mode,model_fixture=fake_exchange()) as (endpoint,requests):
                with contextlib.redirect_stdout(io.StringIO()):
                    result=run.execute(pp,BASELINE,root/p['run_name'],endpoint)
            receipt=verify_bundle(result['evidence_zip'])
            self.assertEqual((receipt['state'],receipt['inference_calls'],receipt['observed_calls']),('stopped',1,1))
            self.assertTrue(receipt['verified']);self.assertIsNone(receipt['pending_action'])
            self.assertEqual(sum(path=='/api/chat' for _,path,_ in requests),1)
            saved=list((root/p['run_name']/'wire').glob('*/response.raw.json'))
            self.assertEqual(len(saved),1);self.assertGreater(saved[0].stat().st_size,0)
            status=c.load((root/p['run_name']/'status.json').read_bytes());self.assertEqual(status['reason'],'transport_error')

if __name__=='__main__':unittest.main()
