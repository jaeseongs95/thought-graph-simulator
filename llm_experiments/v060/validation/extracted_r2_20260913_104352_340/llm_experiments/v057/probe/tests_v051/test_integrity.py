from __future__ import annotations
import copy,json,os,unittest,zipfile
from pathlib import Path
from adm_pilot_v051.audit import audit_run
from adm_pilot_v051.contracts import ContractError,read_json,write_json,strict_json,wire,sha,digest
from adm_pilot_v051.evidence import bundle_run,import_v050,safe_unpack
from .fixtures import copied,shared


def rehash(run):
    events=[strict_json(x) for x in (run/'events.jsonl').read_bytes().splitlines()]
    prev=read_json(run/'plan.snapshot.json')['plan_sha256']
    for e in events:
        folder=run/'calls'/e['slot']['id']
        for name,field in [('request.wire.json','request_sha256'),('response.raw.json','response_sha256')]:e[field]=sha((folder/name).read_bytes())
        e['previous_hash']=prev;e['event_hash']=digest({k:v for k,v in e.items() if k!='event_hash'});prev=e['event_hash']
    (run/'events.jsonl').write_bytes(b'\n'.join(wire(e) for e in events)+b'\n')
    status=read_json(run/'status.json');status['event_tip']=prev;write_json(run/'status.json',status)

class Integrity(unittest.TestCase):
    def test_raw_response_change_without_hash_rejected(self):
        with copied() as (_,p,run,_):
            next((run/'calls').glob('*/response.raw.json')).write_bytes(b'{}')
            with self.assertRaises(ContractError):audit_run(p,run)
    def test_request_change_even_rehashed_rejected(self):
        with copied() as (_,p,run,_):
            path=next((run/'calls').glob('*/request.wire.json'));q=read_json(path);q['messages'][1]['content']+=' changed';path.write_bytes(wire(q));rehash(run)
            with self.assertRaises(ContractError):audit_run(p,run)
    def test_extra_call_file_rejected(self):
        with copied() as (_,p,run,_):
            folder=next((run/'calls').iterdir());(folder/'unregistered.txt').write_text('extra')
            with self.assertRaises(ContractError):audit_run(p,run)
    def test_missing_raw_file_rejected(self):
        with copied() as (_,p,run,_):
            next((run/'calls').glob('*/response.raw.json')).unlink()
            with self.assertRaises(OSError):audit_run(p,run)
    def test_source_snapshot_change_rejected(self):
        with copied() as (_,p,run,_):
            path=run/'source_snapshot/adm_pilot_v051/measure.py';path.write_text('changed')
            with self.assertRaises(ContractError):audit_run(p,run)
    def test_extra_source_snapshot_file_rejected(self):
        with copied() as (_,p,run,_):
            (run/'source_snapshot/other.py').write_text('extra')
            with self.assertRaises(ContractError):audit_run(p,run)
    def test_external_snapshot_not_accepted(self):
        with copied() as (_,_,run,_):
            with self.assertRaises(ContractError):audit_run(run/'plan.snapshot.json',run)
    def test_snapshot_hardlink_not_external_anchor(self):
        with copied() as (root,_,run,_):
            path=root/'alias.json'
            try:os.link(run/'plan.snapshot.json',path)
            except OSError:self.skipTest('hardlink unsupported')
            with self.assertRaises(ContractError):audit_run(path,run)
    def test_symlink_in_results_rejected(self):
        with copied() as (_,p,run,_):
            try:(run/'alias').symlink_to(run/'summary.json')
            except OSError:self.skipTest('symlink unsupported')
            with self.assertRaises(ContractError):audit_run(p,run)
    def test_bad_audit_invalidates_stale_pass(self):
        with copied() as (_,p,run,_):
            next((run/'calls').glob('*/response.raw.json')).write_bytes(b'{}')
            with self.assertRaises(ContractError):audit_run(p,run,write_report=True)
            self.assertFalse(read_json(run/'audit.json')['data_integrity']);self.assertFalse(read_json(run/'summary.json')['data_integrity'])
    def test_missing_event_cannot_claim_complete(self):
        with copied() as (_,p,run,_):
            lines=(run/'events.jsonl').read_bytes().splitlines();(run/'events.jsonl').write_bytes(b'\n'.join(lines[:-1])+b'\n')
            with self.assertRaises(ContractError):audit_run(p,run)
    def test_modified_response_can_be_consistent_but_not_true(self):
        # 원문 전체와 해시를 다시 만든 자료를 외부 실행으로 인증한다는 보장은 없다.
        with copied() as (_,p,run,_):
            path=next((run/'calls').glob('*M2/response.raw.json'));env=read_json(path);body=strict_json(env['message']['content']);body['reviews'][0]['finding']['gap_detected']=False;env['message']['content']=wire(body).decode();path.write_bytes(wire(env));rehash(run)
            r=audit_run(p,run);self.assertTrue(r['data_integrity']);self.assertEqual(sum(x['role_match'] for x in r['roles'].values()),239)
    def test_roundtrip_bundle_external_anchor(self):
        with copied() as (root,p,run,_):
            r=bundle_run(p,run,root/'evidence.zip');target=root/'unpacked';safe_unpack((root/'evidence.zip').read_bytes(),target)
            self.assertEqual(audit_run(target/'external_plan/v051.plan.json',target/'run'),r)
    def test_bundle_inside_result_rejected(self):
        with copied() as (_,p,run,_):
            with self.assertRaises(ContractError):bundle_run(p,run,run/'inside.zip')
    def test_bundle_overwrite_rejected(self):
        with copied() as (root,p,run,_):
            out=root/'existing.zip';out.write_bytes(b'keep')
            with self.assertRaises(ContractError):bundle_run(p,run,out)
            self.assertEqual(out.read_bytes(),b'keep')
    def test_raw_bundle_manifest_corruption_rejected(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);old=shared()['bundle'];out=root/'bad.zip'
            with zipfile.ZipFile(old) as z,zipfile.ZipFile(out,'w') as w:
                for n in z.namelist():w.writestr(n,b'{}' if n=='run/summary.json' else z.read(n))
            with self.assertRaises(ContractError):import_v050(out)
