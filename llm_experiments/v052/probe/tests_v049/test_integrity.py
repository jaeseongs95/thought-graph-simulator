from __future__ import annotations
import copy
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from paired_probe_v049.audit import audit_run
from paired_probe_v049.contracts import ContractError,decode_response,digest,read_json,sha,strict_json,wire,write_json
from paired_probe_v049.evidence import safe_unpack,import_v048
from .fixtures import copied,shared

def events(out):return [strict_json(x) for x in (out/'events.jsonl').read_bytes().splitlines()]
def reseal(out,es):
    tip=read_json(out/'plan.snapshot.json')['plan_sha256']
    for e in es:
        e['previous_hash']=tip;e.pop('event_hash',None);e['event_hash']=digest(e);tip=e['event_hash']
    (out/'events.jsonl').write_bytes(b''.join(wire(e)+b'\n' for e in es))
    status=read_json(out/'status.json');status['event_tip']=tip;write_json(out/'status.json',status)

def altered_zip(raw,change):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:fs={n:z.read(n) for n in z.namelist()}
    change(fs)
    manifest=strict_json(fs['BUNDLE_MANIFEST.json'])
    manifest['file_hashes']={n:sha(b) for n,b in fs.items() if n!='BUNDLE_MANIFEST.json'}
    fs['BUNDLE_MANIFEST.json']=wire(manifest);out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        for n,b in fs.items():z.writestr(n,b)
    return out.getvalue()

class IntegrityTests(unittest.TestCase):
    def test_external_snapshot_not_accepted_as_anchor(self):
        with copied() as (_,_,out,_),self.assertRaises(ContractError):audit_run(out/'plan.snapshot.json',out)
    def test_external_hardlink_not_accepted(self):
        with copied() as (root,_,out,_):
            path=root/'linked.plan.json'
            try:os.link(out/'plan.snapshot.json',path)
            except OSError:self.skipTest('하드링크 미지원 환경')
            with self.assertRaises(ContractError):audit_run(path,out)
    def test_mutated_response_rejected_and_old_pass_invalidated(self):
        with copied() as (_,p,out,_):
            next((out/'calls').glob('*/response.raw.json')).write_bytes(b'{}')
            with self.assertRaises(ContractError):audit_run(p,out,write_report=True)
            self.assertFalse(read_json(out/'summary.json')['data_integrity'])
            self.assertIn('감사 실패',(out/'summary.ko.md').read_text(encoding='utf-8'))
    def test_mutated_request_rejected(self):
        with copied() as (_,p,out,_):
            next((out/'calls').glob('*/request.wire.json')).write_bytes(b'{}')
            with self.assertRaises(ContractError):audit_run(p,out)
    def test_summary_is_not_used_as_evidence(self):
        with copied() as (_,p,out,f):
            write_json(out/'summary.json',{'arms':{'original':{'final_correct':999999}}})
            self.assertEqual(audit_run(p,out)['arms'],f['report']['arms'])
    def test_event_order_rejected_even_after_hash_reseal(self):
        with copied() as (_,p,out,_):
            es=events(out);es[0],es[1]=es[1],es[0];reseal(out,es)
            with self.assertRaises(ContractError):audit_run(p,out)
    def test_source_snapshot_change_rejected(self):
        with copied() as (_,p,out,_):
            q=out/'source_snapshot/paired_probe_v049/runner.py';q.write_bytes(q.read_bytes()+b'\n# changed\n')
            with self.assertRaises(ContractError):audit_run(p,out)
    def test_duplicate_envelope_key_is_invalid_response(self):
        from tests_v048.fixtures import MODEL
        with self.assertRaises(ContractError):decode_response(b'{"model":"a","model":"b"}',MODEL)
    def test_invalid_payloads_do_not_coerce_to_boolean(self):
        from tests_v048.fixtures import MODEL,envelope
        for content in ('{"value":1}','{"value":"true"}','{"value":null}','{"value":true,"value":false}',
                        '{"value":true,"extra":0}','{"value":NaN}','{"value":[]}','{"value":{}}'):
            with self.subTest(content=content),self.assertRaises(ContractError):decode_response(wire(envelope(content=content)),MODEL)
    def test_final_only_masked_error_is_not_trace_success(self):
        with copied() as (_,p,out,_):
            es=events(out)
            parent=next(e for e in es if e['slot']['stage']=='not' and not e['slot']['a'] and not e['slot']['b'])
            block=parent['slot']['block_id'];child=next(e for e in es if e['slot']['id']==block+'__and')
            pp=out/'calls'/parent['slot']['id']/'response.raw.json';payload=read_json(pp)
            payload['message']['content']='{"value":false}';pp.write_bytes(wire(payload));parent['response_sha256']=sha(pp.read_bytes())
            child['parent']['response_sha256']=parent['response_sha256']
            rp=out/'calls'/child['slot']['id']/'request.wire.json';body=read_json(rp);inp=strict_json(body['messages'][1]['content'][7:]);inp['b']=False
            body['messages'][1]['content']='input: '+wire(inp).decode();rp.write_bytes(wire(body));child['request_sha256']=sha(rp.read_bytes())
            reseal(out,es);r=audit_run(p,out)
            self.assertTrue(r['data_integrity']);self.assertEqual(r['arms']['pipeline']['final_correct'],80)
            self.assertEqual(r['arms']['pipeline']['strict_trace_correct'],79)
    def test_host_replacement_of_wrong_parent_is_rejected(self):
        with copied() as (_,p,out,_):
            es=events(out);parent=next(e for e in es if e['slot']['stage']=='not' and e['slot']['a'] and not e['slot']['b'])
            child=next(e for e in es if e['slot']['id']==parent['slot']['block_id']+'__and')
            rp=out/'calls'/parent['slot']['id']/'response.raw.json';body=read_json(rp);body['message']['content']='{"value":false}'
            rp.write_bytes(wire(body));parent['response_sha256']=sha(rp.read_bytes());child['parent']['response_sha256']=parent['response_sha256'];reseal(out,es)
            with self.assertRaises(ContractError):audit_run(p,out)
    def test_direct_wrong_bool_reduces_score_not_integrity(self):
        with copied() as (_,p,out,_):
            es=events(out);e=next(e for e in es if e['slot']['stage']=='commuted_open' and e['slot']['a'] and not e['slot']['b'])
            rp=out/'calls'/e['slot']['id']/'response.raw.json';b=read_json(rp);b['message']['content']='{"value":false}'
            rp.write_bytes(wire(b));e['response_sha256']=sha(rp.read_bytes());reseal(out,es)
            r=audit_run(p,out);self.assertTrue(r['data_integrity']);self.assertEqual(r['arms']['commuted_open']['final_correct'],79)
    def test_bundle_outer_rehash_cannot_hide_inner_response_change(self):
        raw=shared()['bundle'].read_bytes()
        def change(fs):fs[next(n for n in fs if n.endswith('/response.raw.json'))]=b'{}'
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'bad.zip';p.write_bytes(altered_zip(raw,change))
            with self.assertRaises(ValueError):import_v048(p)
    def test_invalid_zip_path_traversal_rejected(self):self._badpath('../escape.json')
    def test_invalid_zip_backslash_rejected(self):self._badpath('run\\escaped.json')
    def test_invalid_zip_absolute_rejected(self):self._badpath('/escape.json')
    def test_invalid_zip_windows_drive_rejected(self):self._badpath('C:/escape.json')
    def test_invalid_zip_windows_trailing_dot_rejected(self):self._badpath('run/escaped.')
    def test_invalid_zip_windows_trailing_space_rejected(self):self._badpath('run/escaped ')
    def test_invalid_zip_windows_stream_rejected(self):self._badpath('run/name:stream')
    def _badpath(self,name):
        mem=io.BytesIO()
        with zipfile.ZipFile(mem,'w') as z:
            z.writestr(name,b'{}');z.writestr('BUNDLE_MANIFEST.json',wire({'file_hashes':{name:sha(b'{}')}}))
        with tempfile.TemporaryDirectory() as td,self.assertRaises(ContractError):safe_unpack(mem.getvalue(),Path(td))
    def test_zip_manifest_missing_entry_rejected(self):
        mem=io.BytesIO()
        with zipfile.ZipFile(mem,'w') as z:z.writestr('unlisted.json',b'{}');z.writestr('BUNDLE_MANIFEST.json',wire({'file_hashes':{}}))
        with tempfile.TemporaryDirectory() as td,self.assertRaises(ContractError):safe_unpack(mem.getvalue(),Path(td))
    def test_zip_symlink_rejected(self):
        mem=io.BytesIO();info=zipfile.ZipInfo('run/link');info.create_system=3;info.external_attr=0o120777<<16
        with zipfile.ZipFile(mem,'w') as z:z.writestr(info,b'target');z.writestr('BUNDLE_MANIFEST.json',wire({'file_hashes':{'run/link':sha(b'target')}}))
        with tempfile.TemporaryDirectory() as td,self.assertRaises(ContractError):safe_unpack(mem.getvalue(),Path(td))
    def test_zip_case_collision_rejected(self):
        mem=io.BytesIO();names={'run/a.json':sha(b'{}'),'run/A.json':sha(b'{}')}
        with zipfile.ZipFile(mem,'w') as z:
            for n in names:z.writestr(n,b'{}')
            z.writestr('BUNDLE_MANIFEST.json',wire({'file_hashes':names}))
        with tempfile.TemporaryDirectory() as td,self.assertRaises(ContractError):safe_unpack(mem.getvalue(),Path(td))
