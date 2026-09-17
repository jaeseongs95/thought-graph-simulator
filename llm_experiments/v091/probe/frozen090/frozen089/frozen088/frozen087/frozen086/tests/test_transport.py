"""실제 urllib HTTP 경로를 loopback 합성 서버로 검사한다. Ollama는 호출하지 않는다."""
from pathlib import Path
import sys,unittest,threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core086 as c,run086 as run
from fixtures086 import fake_exchange,plan

class Transport(unittest.TestCase):
    def test_local_synthetic_http_transport(self):
        ex=fake_exchange();received=[]
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):self.reply(None)
            def do_POST(self):self.reply(self.rfile.read(int(self.headers['Content-Length'])))
            def reply(self,body):
                received.append((self.command,self.path,body))
                code,raw,_,_=ex('synthetic',self.path,body,30)
                self.send_response(code);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            endpoint=f'http://127.0.0.1:{server.server_port}'
            for path,body in [('/api/version',None),('/api/tags',None),('/api/show',c.wire({'model':c.spec()['model']}))]:
                code,raw,error,elapsed=run.exchange(endpoint,path,body,10)
                self.assertEqual(code,200);self.assertIsNone(error);self.assertGreaterEqual(elapsed,0);self.assertIsInstance(c.load(raw),dict)
            import design086
            p=plan();op=next(o for o in p['slots'] if o['stage']=='select');body=c.wire(design086.request_for(p,op,{}))
            code,raw,error,elapsed=run.exchange(endpoint,'/api/chat',body,10)
            self.assertEqual(code,200);self.assertIsNone(error);self.assertEqual(c.load(raw)['model'],c.spec()['model'])
            self.assertEqual(received[-1][2],body);self.assertEqual(ex.count['chat'],1)
        finally:server.shutdown();server.server_close();thread.join(timeout=5)
