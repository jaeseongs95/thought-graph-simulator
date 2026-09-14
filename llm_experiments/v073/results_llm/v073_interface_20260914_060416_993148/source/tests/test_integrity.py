"""재해시와 이벤트 체인 갱신 뒤에도 동결 계약 변조가 거부되는지 검사한다."""
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
            p=Path(td)/'altered.zip';p.write_bytes(resign(files))
            with self.assertRaises((verify.VerificationError,ValueError)):verify.verify_bundle(p)
    def request_changed(self,change):
        f=dict(self.files);sid=self.plan['slots'][0]['id'];name='wire/'+sid+'/request.wire.json'
        q=common.load(f[name]);change(q);f[name]=common.wire(q)
        rn='records/'+sid+'.json';r=common.load(f[rn]);r['request_sha256']=common.sha(f[name]);f[rn]=common.wire(r)
        return rechains(f)
    def input_change(self,key,value):
        def change(q):
            prefix,tail=q['messages'][0]['content'].split('\n\ninput: ');data=common.load(tail);data[key]=value
            q['messages'][0]['content']=prefix+'\n\ninput: '+common.wire(data).decode()
        return self.request_changed(change)
    def test_korean_false_graph_claim(self):
        f=dict(self.files);f['summary.ko.md']+='\n전체 D 제어 입증\n'.encode();self.reject(f)
    def test_json_false_graph_claim(self):
        f=dict(self.files);r=common.load(f['summary.json']);r['overall']['end_to_end_graph_D_control']=True
        f['summary.json']=(json.dumps(r,ensure_ascii=False,indent=2)+'\n').encode();self.reject(f)
    def test_direction_drift(self):self.reject(self.input_change('requested_depth','D 값이 더 큰 후보를 선택한다.'))
    def test_candidate_order_drift(self):self.reject(self.input_change('depth_report','{"depths":[2,1]}'))
    def test_same_value_space_drift(self):self.reject(self.input_change('depth_report','{"depths":[1, 2]}'))
    def test_space_normalization(self):self.reject(self.input_change('depth_report',' { "depths" : [1, 2] } '))
    def test_answer_label_leak(self):self.reject(self.input_change('correct_index',0))
    def test_answer_specific_schema(self):
        def change(q):q['format']['properties']['candidate_index']['enum']=[0]
        self.reject(self.request_changed(change))
    def test_schema_removed(self):self.reject(self.request_changed(lambda q:q.pop('format')))
    def test_seed_changed(self):self.reject(self.request_changed(lambda q:q['options'].update(seed=7)))
    def test_temperature_changed(self):self.reject(self.request_changed(lambda q:q['options'].update(temperature=0)))
    def test_response_mutation_without_rescoring(self):
        f=dict(self.files);sid=self.plan['slots'][0]['id'];n='wire/'+sid+'/response.raw.json';e=common.load(f[n]);e['message']['content']='{"candidate_index":1}';f[n]=common.wire(e)
        rn='records/'+sid+'.json';r=common.load(f[rn]);r['response_sha256']=common.sha(f[n]);r['response_b64']=base64.b64encode(f[n]).decode();f[rn]=common.wire(r)
        self.reject(rechains(f))
    def test_execution_after_http_stop(self):
        f=dict(self.files);n='records/'+self.plan['slots'][0]['id']+'.json';r=common.load(f[n]);r['http_status']=503;f[n]=common.wire(r);self.reject(rechains(f))
    def test_source_change(self):
        f=dict(self.files);f['source/report.py']+=b'\n';self.reject(f)
    def test_ledger_change(self):
        f=dict(self.files);f['source/docs/PLAN_LEDGER.ko.md']+='\n계속 반복 실행\n'.encode();self.reject(f)
    def test_baseline_change(self):
        f=dict(self.files);f['baseline/v072_evidence.zip']+=b'x';self.reject(f)
    def test_extra_file(self):
        f=dict(self.files);f['extra.txt']=b'x';self.reject(f)
    def test_missing_response(self):
        f=dict(self.files);f.pop('wire/'+self.plan['slots'][0]['id']+'/response.raw.json');self.reject(f)
    def test_wrong_count(self):
        f=dict(self.files);r=common.load(f['status.json']);r['inference_calls']=65;f['status.json']=(json.dumps(r,indent=2)+'\n').encode();self.reject(f)
    def test_bool_count(self):
        f=dict(self.files);r=common.load(f['status.json']);r['inference_calls']=True;f['status.json']=(json.dumps(r,indent=2)+'\n').encode();self.reject(f)
    def test_truncated_event(self):
        f=dict(self.files);f['records/events.jsonl']=f['records/events.jsonl'][:-7];self.reject(f)
    def test_rehashed_plan_format_switch(self):
        f=dict(self.files);p=common.load(f['plan.json']);p['slots'][0]['format']='comma_space';p.pop('plan_sha256');p['plan_sha256']=common.sha(common.wire(p));f['plan.json']=(json.dumps(p,ensure_ascii=False,indent=2)+'\n').encode();self.reject(f)
