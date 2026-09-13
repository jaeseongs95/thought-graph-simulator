import copy,io,json,tempfile,unittest,zipfile
from pathlib import Path
from .fixtures import copied
from selection_probe_v057.audit import audit_run
from selection_probe_v057.contracts import ContractError,read_json,write_json,wire,sha,read_plan_json
from selection_probe_v057.evidence import safe_unpack

class Integrity(unittest.TestCase):
    def test_raw_mutation_rejected(self):
        with copied() as (_,p,r,b):
            f=next((r/'calls').glob('*/response.raw.json'));f.write_bytes(f.read_bytes()+b' ')
            with self.assertRaises(ContractError):audit_run(p,r)
    def test_request_mutation_rejected(self):
        with copied() as (_,p,r,b):
            f=next((r/'calls').glob('*/request.wire.json'));f.write_bytes(f.read_bytes()+b' ')
            with self.assertRaises(ContractError):audit_run(p,r)
    def test_extra_file_rejected(self):
        with copied() as (_,p,r,b):
            (r/'extra').write_text('x')
            with self.assertRaises(ContractError):audit_run(p,r)
    def test_missing_raw_rejected(self):
        with copied() as (_,p,r,b):
            next((r/'calls').glob('*/response.raw.json')).unlink()
            with self.assertRaises(OSError):audit_run(p,r)
    def test_bad_reaudit_clears_stale_success(self):
        with copied() as (_,p,r,b):
            next((r/'calls').glob('*/response.raw.json')).write_bytes(b'{}')
            with self.assertRaises(ContractError):audit_run(p,r,write_report=True)
            self.assertFalse(read_json(r/'summary.json')['data_integrity'])
    def test_source_snapshot_modified_rejected(self):
        with copied() as (_,p,r,b):
            f=next((r/'source_snapshot').rglob('*.py'));f.write_bytes(f.read_bytes()+b'\n')
            with self.assertRaises(ContractError):audit_run(p,r)
    def test_baseline_modified_rejected(self):
        with copied() as (_,p,r,b):
            f=r/'baseline/v056_evidence.zip';f.write_bytes(f.read_bytes()+b'x')
            with self.assertRaises(ContractError):audit_run(p,r)
    def test_source_snapshot_not_external_plan(self):
        with copied() as (_,p,r,b):
            with self.assertRaises(ContractError):audit_run(r/'plan.snapshot.json',r)
    def test_status_count_modified_rejected(self):
        with copied() as (_,p,r,b):
            s=read_json(r/'status.json');s['inference_calls']=479;write_json(r/'status.json',s)
            with self.assertRaises(ContractError):audit_run(p,r)

class ArchiveBounds(unittest.TestCase):
    def archive(self,name,data):
        f=io.BytesIO()
        with zipfile.ZipFile(f,'w',compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr(name,data);z.writestr('BUNDLE_MANIFEST.json',wire({'contract':'test','file_hashes':{name:sha(data)}}))
        return f.getvalue()
    def test_previous_nested_baseline_over8mb_allowed(self):
        raw=self.archive('run/baseline/v055_evidence.zip',b'a'*(8*1024*1024+1))
        with tempfile.TemporaryDirectory() as td:safe_unpack(raw,Path(td))
    def test_current_nested_baseline_over8mb_allowed(self):
        raw=self.archive('run/baseline/v056_evidence.zip',b'a'*(8*1024*1024+1))
        with tempfile.TemporaryDirectory() as td:safe_unpack(raw,Path(td))
    def test_response_limit_not_raised(self):
        raw=self.archive('run/calls/x/response.raw.json',b'a'*(8*1024*1024+1))
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ContractError):safe_unpack(raw,Path(td))
    def test_other_zip_not_blanket_exception(self):
        raw=self.archive('run/evil.zip',b'a'*(8*1024*1024+1))
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ContractError):safe_unpack(raw,Path(td))
    def test_path_traversal(self):
        raw=self.archive('../escape.py',b'print(1)')
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ContractError):safe_unpack(raw,Path(td))
    def test_duplicate_zip_members(self):
        f=io.BytesIO()
        with zipfile.ZipFile(f,'w') as z:z.writestr('x',b'a');z.writestr('X',b'b')
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ContractError):safe_unpack(f.getvalue(),Path(td))
    def test_plan_duplicate_keys(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'p';p.write_bytes(b'{"a":1,"a":2}')
            with self.assertRaises(ContractError):read_plan_json(p)
