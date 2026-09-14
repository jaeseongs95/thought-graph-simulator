"""manifest/event를 재해시해도 요청 변경과 부당한 성공 보고가 거부되는지 확인."""
import unittest
from fixtures import *
class Integrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx=executed();cls.root,cls.pp,cls.plan,cls.files,cls.summary,cls.res,cls.state=cls.ctx.__enter__()
    @classmethod
    def tearDownClass(cls):cls.ctx.__exit__(None,None,None)
    def reject(self,files):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'bad.zip';p.write_bytes(resign(files))
            with self.assertRaises((verify.VerificationError,ValueError)):verify.verify_bundle(p)
    def request_changed(self,change):
        f=dict(self.files);sid=self.plan['slots'][0]['id'];name='wire/'+sid+'/request.wire.json';q=common.load(f[name]);change(q);f[name]=common.wire(q)
        rn='records/'+sid+'.json';r=common.load(f[rn]);r['request_sha256']=common.sha(f[name]);f[rn]=common.wire(r);return rechains(f)
    def test_korean_report_changed(self):
        f=dict(self.files);f['summary.ko.md']+='\n전체 D 제어 입증\n'.encode();self.reject(f)
    def test_summary_false_end_to_end_claim(self):
        f=dict(self.files);r=common.load(f['summary.json']);r['overall']['end_to_end_graph_D_control']=True;f['summary.json']=(json.dumps(r,ensure_ascii=False,indent=2)+'\n').encode();self.reject(f)
    def test_candidate_order_request_drift(self):
        def change(q):
            head,tail=q['messages'][0]['content'].split('\n\ninput: ');data=common.load(tail);data['candidate_rule_ids'].reverse();q['messages'][0]['content']=head+'\n\ninput: '+common.wire(data).decode()
        self.reject(self.request_changed(change))
    def test_depth_request_drift(self):
        def change(q):q['messages'][0]['content']=q['messages'][0]['content'].replace('더 작은 후보','더 큰 후보')
        self.reject(self.request_changed(change))
    def test_answer_label_leak(self):
        self.reject(self.request_changed(lambda q:q['messages'][0].update(content=q['messages'][0]['content']+'\n정답은 r83이다.')))
    def test_answer_enum_not_allowed(self):
        def change(q):q['format']['properties']['rule_ids']['items']['enum']=['r83']
        self.reject(self.request_changed(change))
    def test_seed_drift(self):self.reject(self.request_changed(lambda q:q['options'].update(seed=1)))
    def test_problem_rule_drift(self):
        def change(q):q['messages'][0]['content']=q['messages'][0]['content'].replace('"Lp","Ls"','"Lp"',1)
        self.reject(self.request_changed(change))
    def test_response_changed_success_not_earned(self):
        f=dict(self.files);sid=self.plan['slots'][0]['id'];name='wire/'+sid+'/response.raw.json';env=common.load(f[name]);env['message']['content']='{"rule_ids":["r21","r57","r04","r69"]}';f[name]=common.wire(env)
        rn='records/'+sid+'.json';r=common.load(f[rn]);r['response_sha256']=common.sha(f[name]);r['response_b64']=base64.b64encode(f[name]).decode();f[rn]=common.wire(r);self.reject(rechains(f))
    def test_after_http_error_rejected(self):
        f=dict(self.files);rn='records/'+self.plan['slots'][0]['id']+'.json';r=common.load(f[rn]);r['http_status']=503;f[rn]=common.wire(r);self.reject(rechains(f))
    def test_changed_source(self):
        f=dict(self.files);f['source/selection.py']+=b'\n';self.reject(f)
    def test_changed_baseline(self):
        f=dict(self.files);f['baseline/v069_evidence.zip']+=b'x';self.reject(f)
    def test_unknown_file(self):
        f=dict(self.files);f['extra.txt']=b'x';self.reject(f)
    def test_missing_response(self):
        f=dict(self.files);f.pop('wire/'+self.plan['slots'][0]['id']+'/response.raw.json');self.reject(f)
    def test_wrong_inference_count(self):
        f=dict(self.files);r=common.load(f['status.json']);r['inference_calls']=41;f['status.json']=(json.dumps(r,indent=2)+'\n').encode();self.reject(f)
    def test_bool_inference_count(self):
        f=dict(self.files);r=common.load(f['status.json']);r['inference_calls']=True;f['status.json']=(json.dumps(r,indent=2)+'\n').encode();self.reject(f)
    def test_torn_event_not_repaired(self):
        f=dict(self.files);f['records/events.jsonl']=f['records/events.jsonl'][:-8];self.reject(f)
    def test_metadata_tamper(self):
        f=dict(self.files);name='metadata/b00_before/1.response.raw.json';x=common.load(f[name]);x['models'][0]['digest']='0'*64;f[name]=common.wire(x);rn='records/b00_before.json';r=common.load(f[rn]);r['items'][1]['response_b64']=base64.b64encode(f[name]).decode();r['identity_ok']=False;f[rn]=common.wire(r);self.reject(rechains(f))
    def test_frozen_plan_after_rehash(self):
        f=dict(self.files);p=common.load(f['plan.json']);p['slots'][0]['condition']='deep';p.pop('plan_sha256');p['plan_sha256']=common.sha(common.wire(p));f['plan.json']=(json.dumps(p,ensure_ascii=False,indent=2)+'\n').encode();self.reject(f)
