"""검토에서 제기한 자료 경계 반례. 실패를 실제 재현한 뒤 교정한다."""
from __future__ import annotations
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from paired_probe_v049.audit import audit_run
from paired_probe_v049.contracts import ContractError,read_json,sha,wire
from paired_probe_v049.evidence import bundle_run,safe_unpack
from .fixtures import copied

class ReviewRegressions(unittest.TestCase):
    def test_bundle_rechecks_the_bytes_it_actually_packages(self):
        with copied() as (root,p,out,_):
            original=audit_run
            def mutate_after_audit(pp,rr,**kw):
                report=original(pp,rr,**kw)
                if Path(rr)==out:
                    next((out/'calls').glob('*/response.raw.json')).write_bytes(b'{}')
                return report
            with patch('paired_probe_v049.audit.audit_run',side_effect=mutate_after_audit):
                with self.assertRaises(ContractError):bundle_run(p,out,root/'e.zip')
            self.assertFalse((root/'e.zip').exists())
    def test_unregistered_raw_response_file_is_rejected(self):
        with copied() as (_,p,out,_):
            (out/'calls'/'unregistered.response.json').write_bytes(b'{}')
            with self.assertRaises(ContractError):audit_run(p,out)
    def test_windows_reserved_device_filename_is_rejected(self):
        raw=b'{}';names={'run/CON.json':sha(raw)};mem=io.BytesIO()
        with zipfile.ZipFile(mem,'w') as z:
            z.writestr('run/CON.json',raw)
            z.writestr('BUNDLE_MANIFEST.json',wire({'file_hashes':names}))
        with tempfile.TemporaryDirectory() as td,self.assertRaises(ContractError):safe_unpack(mem.getvalue(),Path(td))
