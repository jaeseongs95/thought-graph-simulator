import base64,copy,tempfile,unittest
from pathlib import Path
from fixtures import *
class Integrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with executed() as (_,pp,p,f,r,res,state):cls.files=f;cls.plan=p
    def reject(self,f):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'changed.zip';common.write(p,resign(f))
            with self.assertRaises((ValueError,KeyError)):verify.verify_bundle(p)
    def replace_request(self,f,sid,q):
        f=dict(f);name='wire/'+sid+'/request.wire.json';f[name]=common.wire(q);rn='records/'+sid+'.json';r=common.load(f[rn]);r['request_sha256']=common.sha(f[name]);f[rn]=common.wire(r);return rechains(f)
    def test_false_D_promotion_resigned(self):
        f=dict(self.files);s=common.load(f['summary.json']);s['overall']['D_instruction_control']=True;f['summary.json']=common.wire(s);self.reject(f)
    def test_false_A_M_gate_resigned(self):
        f=dict(self.files);s=common.load(f['summary.json']);s['overall']['A_or_M_gate']=True;f['summary.json']=common.wire(s);self.reject(f)
    def test_old_result_changed_to_success(self):
        f=dict(self.files);s=common.load(f['summary.json']);s['overall']['v067_successes_unchanged']=12;f['summary.json']=common.wire(s);self.reject(f)
    def test_korean_report_tamper_resigned(self):
        f=dict(self.files);f['summary.ko.md']+=b'\nTampered\n';self.reject(f)
    def test_reference_changed_in_request_resigned(self):
        sid=self.plan['slots'][0]['id'];q=common.load(self.files['wire/'+sid+'/request.wire.json']);q['messages'][0]['content']=q['messages'][0]['content'].replace('"rule_ids":["r83"]','"rule_ids":["r69"]');self.reject(self.replace_request(self.files,sid,q))
    def test_raw_nodes_changed_in_forwarded_request(self):
        sid=next(s['id'] for s in self.plan['slots'] if s['stage']=='final');q=common.load(self.files['wire/'+sid+'/request.wire.json']);text=q['messages'][0]['content'];head,raw=text.split('\n\nnodes_response: ');transfer=common.load(raw);transfer['content']='{"nodes":[]}';q['messages'][0]['content']=head+'\n\nnodes_response: '+common.wire(transfer).decode();self.reject(self.replace_request(self.files,sid,q))
    def test_source_nodes_hash_forged_in_forwarded_request(self):
        sid=next(s['id'] for s in self.plan['slots'] if s['stage']=='final');q=common.load(self.files['wire/'+sid+'/request.wire.json']);head,raw=q['messages'][0]['content'].split('\n\nnodes_response: ');transfer=common.load(raw);transfer['response_sha256']='0'*64;q['messages'][0]['content']=head+'\n\nnodes_response: '+common.wire(transfer).decode();self.reject(self.replace_request(self.files,sid,q))
    def test_payload_schema_changed_in_request(self):
        sid=next(s['id'] for s in self.plan['slots'] if s['stage']=='final');q=common.load(self.files['wire/'+sid+'/request.wire.json']);q['format']['properties']['final_node_id']['enum']=['node_Lg'];self.reject(self.replace_request(self.files,sid,q))
    def test_raw_response_rehashed_report_not_recomputed(self):
        f=dict(self.files);sid=self.plan['slots'][0]['id'];n='wire/'+sid+'/response.raw.json';env=common.load(f[n]);g=common.load(env['message']['content']);g['nodes'][-1]['parents']=[];env['message']['content']=common.wire(g).decode();f[n]=common.wire(env);rn='records/'+sid+'.json';r=common.load(f[rn]);r['response_sha256']=common.sha(f[n]);r['response_b64']=base64.b64encode(f[n]).decode();f[rn]=common.wire(r);self.reject(rechains(f))
    def test_call_after_http_error_rejected(self):
        f=dict(self.files);n='records/'+self.plan['slots'][0]['id']+'.json';r=common.load(f[n]);r['http_status']=503;f[n]=common.wire(r);self.reject(rechains(f))
    def test_changed_source_rejected(self):
        f=dict(self.files);f['source/stages.py']+=b'\n';self.reject(f)
    def test_changed_baseline_rejected(self):
        f=dict(self.files);f['baseline/v067_evidence.zip']+=b'changed';self.reject(f)
    def test_unknown_file_rejected(self):
        f=dict(self.files);f['extra.txt']=b'ignored?';self.reject(f)
    def test_response_missing_not_empty_success(self):
        f=dict(self.files);f.pop('wire/'+self.plan['slots'][0]['id']+'/response.raw.json');self.reject(f)
    def test_wrong_inference_count_rejected(self):
        f=dict(self.files);s=common.load(f['status.json']);s['inference_calls']=37;f['status.json']=common.wire(s);self.reject(f)
    def test_torn_event_not_repaired(self):
        f=dict(self.files);f['records/events.jsonl']=f['records/events.jsonl'][:-8];self.reject(f)
    def test_metadata_identity_tamper(self):
        f=dict(self.files);n='metadata/b00_before/1.response.raw.json';x=common.load(f[n]);x['models'][0]['digest']='0'*64;f[n]=common.wire(x);rn='records/b00_before.json';r=common.load(f[rn]);r['items'][1]['response_b64']=base64.b64encode(f[n]).decode();r['identity_ok']=False;f[rn]=common.wire(r);self.reject(rechains(f))
