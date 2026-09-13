"""manifest와 event chain까지 재해시한 변조가 동결 계약/독립 계산을 통과하지 못하는지 확인."""
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
    def request_changed(self,sid,change):
        f=dict(self.files);name='wire/'+sid+'/request.wire.json';q=common.load(f[name]);change(q);f[name]=common.wire(q)
        rn='records/'+sid+'.json';r=common.load(f[rn]);r['request_sha256']=common.sha(f[name]);f[rn]=common.wire(r);return rechains(f)
    def test_korean_report_changed(self):
        f=dict(self.files);f['summary.ko.md']+='\n성공으로 바꾸기\n'.encode();self.reject(f)
    def test_summary_false_D_claim(self):
        f=dict(self.files);r=common.load(f['summary.json']);r['overall']['D_instruction_control']=True;f['summary.json']=(json.dumps(r,ensure_ascii=False,indent=2)+'\n').encode();f['summary.ko.md']=report.render(r).encode();self.reject(f)
    def test_reference_order_request_drift(self):
        sid=next(s['id'] for s in self.plan['slots'] if s['stage']=='rule')
        def change(q):q['messages'][0]['content']=q['messages'][0]['content'].replace('"rule_ids":["r83"]','"rule_ids":["r69"]')
        self.reject(self.request_changed(sid,change))
    def test_per_step_rule_request_drift(self):
        sid=next(s['id'] for s in self.plan['slots'] if s['stage']=='rule')
        def change(q):q['messages'][0]['content']=q['messages'][0]['content'].replace('"requested_rule_id":"r83"','"requested_rule_id":"r69"')
        self.reject(self.request_changed(sid,change))
    def test_earlier_raw_history_replaced(self):
        sid=next(s['id'] for s in self.plan['slots'] if s['stage']=='final')
        def change(q):
            head,tail=q['messages'][0]['content'].split('\n\nhistory: ');h=common.load(tail);h[0]['content']='{"nodes":[]}';q['messages'][0]['content']=head+'\n\nhistory: '+common.wire(h).decode()
        self.reject(self.request_changed(sid,change))
    def test_earlier_history_omitted(self):
        sid=next(s['id'] for s in self.plan['slots'] if s['stage']=='final')
        def change(q):
            head,tail=q['messages'][0]['content'].split('\n\nhistory: ');h=common.load(tail);q['messages'][0]['content']=head+'\n\nhistory: '+common.wire(h[1:]).decode()
        self.reject(self.request_changed(sid,change))
    def test_history_hash_forged(self):
        sid=next(s['id'] for s in self.plan['slots'] if s['stage']=='final')
        def change(q):
            head,tail=q['messages'][0]['content'].split('\n\nhistory: ');h=common.load(tail);h[0]['response_sha256']='0'*64;q['messages'][0]['content']=head+'\n\nhistory: '+common.wire(h).decode()
        self.reject(self.request_changed(sid,change))
    def test_answer_enum_not_allowed(self):
        sid=next(s['id'] for s in self.plan['slots'] if s['stage']=='final')
        def change(q):q['format']['properties']['final_node_id']['enum']=['node_Lg']
        self.reject(self.request_changed(sid,change))
    def test_seed_drift(self):
        self.reject(self.request_changed(self.plan['slots'][0]['id'],lambda q:q['options'].update(seed=1)))
    def test_final_response_rehashed_but_unearned_success_rejected(self):
        f=dict(self.files);sid=next(s['id'] for s in self.plan['slots'] if s['stage']=='final');name='wire/'+sid+'/response.raw.json'
        env=common.load(f[name]);env['message']['content']='{"final_node_id":"absent"}';f[name]=common.wire(env)
        rn='records/'+sid+'.json';r=common.load(f[rn]);r['response_sha256']=common.sha(f[name]);r['response_b64']=base64.b64encode(f[name]).decode();f[rn]=common.wire(r);self.reject(rechains(f))
    def test_call_after_http_error_rejected(self):
        f=dict(self.files);name='records/'+self.plan['slots'][0]['id']+'.json';r=common.load(f[name]);r['http_status']=503;f[name]=common.wire(r);self.reject(rechains(f))
    def test_changed_source_rejected(self):
        f=dict(self.files);f['source/stages.py']+=b'\n';self.reject(f)
    def test_changed_baseline_rejected(self):
        f=dict(self.files);f['baseline/v068_evidence.zip']+=b'x';self.reject(f)
    def test_unknown_file_rejected(self):
        f=dict(self.files);f['extra.txt']=b'x';self.reject(f)
    def test_missing_response_rejected(self):
        f=dict(self.files);f.pop('wire/'+self.plan['slots'][0]['id']+'/response.raw.json');self.reject(f)
    def test_wrong_inference_count(self):
        f=dict(self.files);r=common.load(f['status.json']);r['inference_calls']=55;f['status.json']=(json.dumps(r,indent=2)+'\n').encode();self.reject(f)
    def test_bool_inference_count(self):
        f=dict(self.files);r=common.load(f['status.json']);r['inference_calls']=True;f['status.json']=(json.dumps(r,indent=2)+'\n').encode();self.reject(f)
    def test_torn_event_not_repaired(self):
        f=dict(self.files);f['records/events.jsonl']=f['records/events.jsonl'][:-8];self.reject(f)
    def test_model_metadata_tamper(self):
        f=dict(self.files);name='metadata/b00_before/1.response.raw.json';x=common.load(f[name]);x['models'][0]['digest']='0'*64;f[name]=common.wire(x)
        rn='records/b00_before.json';r=common.load(f[rn]);r['items'][1]['response_b64']=base64.b64encode(f[name]).decode();r['identity_ok']=False;f[rn]=common.wire(r);self.reject(rechains(f))
    def test_plan_hash_recomputed_still_frozen_contract(self):
        f=dict(self.files);p=common.load(f['plan.json']);p['slots'][1]['requested_rule_id']='r69';p.pop('plan_sha256');p['plan_sha256']=common.sha(common.wire(p));f['plan.json']=(json.dumps(p,ensure_ascii=False,indent=2)+'\n').encode();self.reject(f)
