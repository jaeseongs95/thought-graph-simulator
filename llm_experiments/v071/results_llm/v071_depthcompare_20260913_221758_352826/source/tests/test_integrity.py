"""재해시 뒤에도 요청/원문 전달/가짜 성공/부분 실행 변조가 거부되는지 검사한다."""
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
    def request_changed(self,change,stage='select',arm=None):
        f=dict(self.files);s=next(s for s in self.plan['slots'] if s['stage']==stage and (arm is None or s['arm']==arm));sid=s['id']
        name='wire/'+sid+'/request.wire.json';q=common.load(f[name]);change(q);f[name]=common.wire(q)
        rn='records/'+sid+'.json';r=common.load(f[rn]);r['request_sha256']=common.sha(f[name]);f[rn]=common.wire(r)
        return rechains(f)
    def input_change(self,key,value,stage='select',arm=None):
        def change(q):
            prefix,tail=q['messages'][0]['content'].split('\n\ninput: ');data=common.load(tail);data[key]=value
            q['messages'][0]['content']=prefix+'\n\ninput: '+common.wire(data).decode()
        return self.request_changed(change,stage,arm)
    def test_korean_report_false_claim(self):
        f=dict(self.files);f['summary.ko.md']+='\n전체 D 제어 입증\n'.encode();self.reject(f)
    def test_json_report_false_graph_success(self):
        f=dict(self.files);r=common.load(f['summary.json']);r['overall']['end_to_end_graph_D_control']=True
        f['summary.json']=(json.dumps(r,ensure_ascii=False,indent=2)+'\n').encode();self.reject(f)
    def test_candidate_order_drift(self):
        self.reject(self.input_change('candidate_rule_ids',[['r21','r57','r04','r69'],['r83']],'estimate'))
    def test_D_direction_drift(self):
        self.reject(self.input_change('requested_depth','D 값이 더 큰 후보를 선택한다.'))
    def test_oracle_depth_corruption(self):
        self.reject(self.input_change('depth_report','{"depths":[4,1]}',arm='oracle_depth'))
    def test_model_raw_whitespace_normalization_rejected(self):
        self.reject(self.input_change('depth_report',' { "depths" : [1, 4] } ',arm='model_depth'))
    def test_model_raw_replacement_by_other_content_rejected(self):
        self.reject(self.input_change('depth_report','{"depths":[0,0]}',arm='model_depth'))
    def test_oracle_label_leak_into_estimator_rejected(self):
        self.reject(self.input_change('correct_depths',[1,4],'estimate'))
    def test_answer_specific_enum_rejected(self):
        def change(q):q['format']['properties']['candidate_index']['enum']=[0]
        self.reject(self.request_changed(change))
    def test_seed_drift(self):self.reject(self.request_changed(lambda q:q['options'].update(seed=71)))
    def test_response_mutation_with_updated_hash_and_chain_rejected(self):
        f=dict(self.files);sid=self.plan['slots'][0]['id'];n='wire/'+sid+'/response.raw.json';e=common.load(f[n]);e['message']['content']='{"candidate_index":1}';f[n]=common.wire(e)
        rn='records/'+sid+'.json';r=common.load(f[rn]);r['response_sha256']=common.sha(f[n]);r['response_b64']=base64.b64encode(f[n]).decode();f[rn]=common.wire(r)
        self.reject(rechains(f))
    def test_execution_after_http_stop_rejected(self):
        f=dict(self.files);n='records/'+self.plan['slots'][0]['id']+'.json';r=common.load(f[n]);r['http_status']=503;f[n]=common.wire(r);self.reject(rechains(f))
    def test_source_change_rejected(self):
        f=dict(self.files);f['source/depths.py']+=b'\n';self.reject(f)
    def test_baseline_change_rejected(self):
        f=dict(self.files);f['baseline/v070_evidence.zip']+=b'x';self.reject(f)
    def test_unknown_file_rejected(self):
        f=dict(self.files);f['extra.txt']=b'x';self.reject(f)
    def test_missing_response_rejected(self):
        f=dict(self.files);f.pop('wire/'+self.plan['slots'][0]['id']+'/response.raw.json');self.reject(f)
    def test_wrong_count_rejected(self):
        f=dict(self.files);r=common.load(f['status.json']);r['inference_calls']=101;f['status.json']=(json.dumps(r,indent=2)+'\n').encode();self.reject(f)
    def test_bool_count_rejected(self):
        f=dict(self.files);r=common.load(f['status.json']);r['inference_calls']=True;f['status.json']=(json.dumps(r,indent=2)+'\n').encode();self.reject(f)
    def test_truncated_event_not_auto_repaired(self):
        f=dict(self.files);f['records/events.jsonl']=f['records/events.jsonl'][:-7];self.reject(f)
    def test_rehashed_plan_arm_switch_rejected(self):
        f=dict(self.files);p=common.load(f['plan.json']);p['slots'][0]['arm']='model_depth';p.pop('plan_sha256');p['plan_sha256']=common.sha(common.wire(p));f['plan.json']=(json.dumps(p,ensure_ascii=False,indent=2)+'\n').encode();self.reject(f)
