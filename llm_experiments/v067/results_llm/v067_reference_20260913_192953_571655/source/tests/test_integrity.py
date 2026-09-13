import base64,copy,tempfile,unittest
from pathlib import Path
from fixtures import *
class Integrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with executed() as (_,p,plan,files,r,result,state):cls.files=files;cls.plan=plan
    def reject(self,files):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'modified.zip';common.write(p,resign(files))
            with self.assertRaises((ValueError,KeyError)):verify.verify_bundle(p)
    def test_false_D_success_after_rehash(self):
        f=dict(self.files);s=common.load(f['summary.json']);s['overall']['D_instruction_control']='success';f['summary.json']=common.wire(s);self.reject(f)
    def test_false_A_M_gate_after_rehash(self):
        f=dict(self.files);s=common.load(f['summary.json']);s['overall']['A_or_M_gate']=True;f['summary.json']=common.wire(s);self.reject(f)
    def test_human_report_tamper_after_rehash(self):
        f=dict(self.files);f['summary.ko.md']=f['summary.ko.md'].replace('자율적인 D 제어'.encode(),'성공한 D 제어'.encode());self.reject(f)
    def test_provided_reference_mutated_in_request(self):
        f=dict(self.files);sid='b00_p0_reference_short';n='wire/'+sid+'/request.wire.json';q=common.load(f[n]);q['messages'][0]['content']=q['messages'][0]['content'].replace('"rule_ids":["r83"]','"rule_ids":["r69"]');f[n]=common.wire(q);rn='records/'+sid+'.json';r=common.load(f[rn]);r['request_sha256']=common.sha(f[n]);f[rn]=common.wire(r);self.reject(rechains(f))
    def test_model_provenance_not_forged(self):
        f=dict(self.files);p=common.load(f['plan.json']);p['slots'][0]['reference_origin']='model_generated';f['plan.json']=common.wire(p);self.reject(f)
    def test_changed_raw_response_rehashed_not_same_report(self):
        f=dict(self.files);n='wire/b00_p0_reference_short/response.raw.json';e=common.load(f[n]);g=common.load(e['message']['content']);g['nodes'][-1]['parents']=[];e['message']['content']=common.wire(g).decode();f[n]=common.wire(e);rn='records/b00_p0_reference_short.json';r=common.load(f[rn]);r['response_sha256']=common.sha(f[n]);r['response_b64']=base64.b64encode(f[n]).decode();f[rn]=common.wire(r);self.reject(rechains(f))
    def test_no_extra_call_after_http_error(self):
        f=dict(self.files);n='records/b00_p0_reference_short.json';r=common.load(f[n]);r['http_status']=503;f[n]=common.wire(r);self.reject(rechains(f))
    def test_changed_source_rejected(self):
        f=dict(self.files);f['source/reference.py']+=b'\n';self.reject(f)
    def test_changed_baseline_rejected(self):
        f=dict(self.files);f['baseline/v066_evidence.zip']+=b'changed';self.reject(f)
    def test_unknown_file_not_ignored(self):
        f=dict(self.files);f['extra.txt']=b'unknown';self.reject(f)
    def test_deleted_response_not_empty_success(self):
        f=dict(self.files);f.pop('wire/b00_p0_reference_short/response.raw.json');self.reject(f)
    def test_wrong_count_not_accepted(self):
        f=dict(self.files);s=common.load(f['status.json']);s['inference_calls']=13;f['status.json']=common.wire(s);self.reject(f)
    def test_torn_event_not_repaired(self):
        f=dict(self.files);f['records/events.jsonl']=f['records/events.jsonl'][:-8];self.reject(f)
    def test_metadata_wrong_identity_resigned(self):
        f=dict(self.files);n='metadata/b00_before/1.response.raw.json';x=common.load(f[n]);x['models'][0]['digest']='0'*64;f[n]=common.wire(x);rn='records/b00_before.json';r=common.load(f[rn]);r['items'][1]['response_b64']=base64.b64encode(f[n]).decode();r['identity_ok']=False;f[rn]=common.wire(r);self.reject(rechains(f))
