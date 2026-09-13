import copy,io,json,tempfile,unittest,zipfile
from pathlib import Path
from layout_probe_v056.audit import audit_run
from layout_probe_v056.evidence import safe_unpack,validate_reference_file
from layout_probe_v056.contracts import ContractError,write_json,read_json,digest,sha,wire
from .fixtures import copied

class Integrity(unittest.TestCase):
    def test_modified_response_rejected(self):
        with copied() as (_,p,r,b):
            f=next((r/'calls').glob('*/response.raw.json'));f.write_bytes(f.read_bytes()+b' ')
            with self.assertRaises(ContractError):audit_run(p,r)
    def test_extra_raw_file_rejected(self):
        with copied() as (_,p,r,b):
            (r/'unregistered.txt').write_text('x')
            with self.assertRaises(ContractError):audit_run(p,r)
    def test_changed_source_snapshot_rejected(self):
        with copied() as (_,p,r,b):
            f=r/'source_snapshot/layout_probe_v056/requests.py';f.write_bytes(f.read_bytes()+b'\n#changed\n')
            with self.assertRaises(ContractError):audit_run(p,r)
    def test_changed_baseline_rejected(self):
        with copied() as (_,p,r,b):
            f=r/'baseline/v055_evidence.zip';f.write_bytes(f.read_bytes()+b'changed')
            with self.assertRaises(ContractError):audit_run(p,r)
    def test_missing_external_plan_rejected(self):
        with copied() as (_,p,r,b):
            with self.assertRaises((ContractError,OSError)):audit_run(r/'plan.snapshot.json',r)
    def test_bad_audit_removes_stale_pass(self):
        with copied() as (_,p,r,b):
            f=r/'status.json';s=read_json(f);s['inference_calls']=0;write_json(f,s)
            with self.assertRaises(ContractError):audit_run(p,r,write_report=True)
            self.assertFalse(read_json(r/'summary.json')['data_integrity'])
    def test_self_resealed_fake_request_bank_rejected_against_baseline(self):
        with copied() as (_,p,r,b):
            plan=read_json(p);key=next(iter(plan['reference']['request_bank']));plan['reference']['request_bank'][key]='e30='
            plan['reference']['receipt_sha256']=digest({k:v for k,v in plan['reference'].items() if k!='receipt_sha256'});plan['plan_sha256']=digest({k:v for k,v in plan.items() if k!='plan_sha256'})
            with self.assertRaises(ContractError):validate_reference_file(r/'baseline/v055_evidence.zip',plan)
    def test_zip_traversal_rejected(self):
        data=io.BytesIO()
        with zipfile.ZipFile(data,'w') as z:z.writestr('../escape.txt',b'x');z.writestr('BUNDLE_MANIFEST.json',wire({'file_hashes':{'../escape.txt':sha(b'x')}}))
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ContractError):safe_unpack(data.getvalue(),Path(td))
    def test_zip_8mib_response_still_rejected(self):
        content=b' '*(8*1024**2+1);name='run/calls/x/response.raw.json';data=io.BytesIO()
        with zipfile.ZipFile(data,'w',compression=zipfile.ZIP_DEFLATED) as z:z.writestr(name,content);z.writestr('BUNDLE_MANIFEST.json',wire({'file_hashes':{name:sha(content)}}))
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ContractError):safe_unpack(data.getvalue(),Path(td))
    def test_zip_large_named_plan_allowed(self):
        content=b' '* (8*1024**2+1);name='external_plan/v055.plan.json';data=io.BytesIO()
        with zipfile.ZipFile(data,'w',compression=zipfile.ZIP_DEFLATED) as z:z.writestr(name,content);z.writestr('BUNDLE_MANIFEST.json',wire({'file_hashes':{name:sha(content)}}))
        with tempfile.TemporaryDirectory() as td:
            safe_unpack(data.getvalue(),Path(td));self.assertEqual((Path(td)/name).read_bytes(),content)
    def test_zip_duplicate_case_paths_rejected(self):
        data=io.BytesIO()
        with zipfile.ZipFile(data,'w') as z:
            for n in ['a.txt','A.TXT']:z.writestr(n,b'x')
            z.writestr('BUNDLE_MANIFEST.json',wire({'file_hashes':{n:sha(b'x') for n in ['a.txt','A.TXT']}}))
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ContractError):safe_unpack(data.getvalue(),Path(td))
