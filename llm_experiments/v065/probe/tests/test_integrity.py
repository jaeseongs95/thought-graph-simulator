import copy,json,tempfile,unittest
from pathlib import Path
from fixtures import *

class Integrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name)
        with executed() as (_,p,plan,files,r,result,state):cls.plan=plan;cls.files=files
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def reject(self,files):
        p=self.root/('bad_'+str(len(list(self.root.iterdir())))+'.zip');p.write_bytes(resign(files))
        with self.assertRaises(ValueError):verify.verify_bundle(p)
    def test_rehashed_wrong_request(self):
        f=dict(self.files);n=next(n for n in f if n.startswith('wire/') and n.endswith('request.wire.json'));f[n]+=b' ';self.reject(f)
    def test_rehashed_wrong_response(self):
        f=dict(self.files);n=next(n for n in f if n.startswith('wire/') and n.endswith('response.raw.json'));f[n]+=b' ';self.reject(f)
    def test_extra_file_rejected(self):
        f=dict(self.files);f['extra.txt']=b'x';self.reject(f)
    def test_source_bytes_changed(self):
        f=dict(self.files);f['source/measure.py']+=b'\n';self.reject(f)
    def test_baseline_changed(self):
        f=dict(self.files);f['baseline/v064_evidence.zip']+=b'x';self.reject(f)
    def test_rehashed_korean_false_summary(self):
        f=dict(self.files);f['summary.ko.md']='# 무조건 D 제어 성공'.encode();self.reject(f)
    def test_rehashed_json_false_gate(self):
        f=dict(self.files);s=common.load(f['summary.json']);s['overall']['bounded_A_or_M_pilot']=True;f['summary.json']=(json.dumps(s,ensure_ascii=False,indent=2)+'\n').encode();self.reject(f)
    def test_stale_status_count_rejected(self):
        f=dict(self.files);s=common.load(f['status.json']);s['inference_calls']=11;f['status.json']=(json.dumps(s,ensure_ascii=False,indent=2)+'\n').encode();self.reject(f)
    def test_continued_after_rehashed_first_metadata_failure(self):
        f=dict(self.files);name='records/b00_before.json';record=common.load(f[name]);item=record['items'][1]
        tags=common.load(base64.b64decode(item['response_b64']));tags['models'][0]['digest']='0'*64;raw=common.wire(tags);item['response_b64']=base64.b64encode(raw).decode();record['identity_ok']=False
        f['metadata/b00_before/1.response.raw.json']=raw;f[name]=common.wire(record);f=rebuild_event_report(f,self.plan);self.reject(f)
    def test_torn_event_rejected_not_repaired(self):
        f=dict(self.files);f['records/events.jsonl']=f['records/events.jsonl'][:-4];self.reject(f)
    def test_missing_response_not_silently_empty(self):
        f=dict(self.files);f.pop(next(n for n in f if n.startswith('wire/') and n.endswith('response.raw.json')));self.reject(f)
