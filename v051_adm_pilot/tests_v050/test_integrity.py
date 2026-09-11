from __future__ import annotations
import copy,os,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from criterion_probe_v050.audit import audit_run
from criterion_probe_v050.contracts import *
from criterion_probe_v050.evidence import bundle_run,safe_unpack
from .fixtures import copied

class Integrity(unittest.TestCase):
    def test_mutated_response_rejected(self):
        with copied() as (_,p,run,_):
            next((run/'calls').glob('*/response.raw.json')).write_bytes(b'{}')
            with self.assertRaises(ContractError):audit_run(p,run)
    def test_mutated_request_rejected(self):
        with copied() as (_,p,run,_):
            next((run/'calls').glob('*/request.wire.json')).write_bytes(b'{}')
            with self.assertRaises(ContractError):audit_run(p,run)
    def test_unregistered_raw_file_rejected(self):
        with copied() as (_,p,run,_):
            (run/'calls/hidden.json').write_bytes(b'{}')
            with self.assertRaises(ContractError):audit_run(p,run)
    def test_source_snapshot_change_rejected(self):
        with copied() as (_,p,run,_):
            next((run/'source_snapshot').rglob('*.py')).write_text('# changed',encoding='utf-8')
            with self.assertRaises(ContractError):audit_run(p,run)
    def test_external_snapshot_alias_rejected(self):
        with copied() as (_,_,run,_):
            with self.assertRaises(ContractError):audit_run(run/'plan.snapshot.json',run)
    def test_external_hardlink_rejected(self):
        with copied() as (root,_,run,_):
            alias=root/'alias.json';os.link(run/'plan.snapshot.json',alias)
            with self.assertRaises(ContractError):audit_run(alias,run)
    def test_stale_pass_is_overwritten_on_failed_reaudit(self):
        with copied() as (_,p,run,_):
            next((run/'calls').glob('*/response.raw.json')).write_bytes(b'{}')
            with self.assertRaises(ContractError):audit_run(p,run,write_report=True)
            self.assertFalse(read_json(run/'summary.json')['data_integrity'])
    def test_bundle_reaudits_actual_frozen_bytes(self):
        with copied() as (root,p,run,_):
            old=audit_run
            def alter(pp,rr,**kw):
                r=old(pp,rr,**kw)
                if Path(rr)==run:next((run/'calls').glob('*/response.raw.json')).write_bytes(b'{}')
                return r
            with patch('criterion_probe_v050.audit.audit_run',side_effect=alter):
                with self.assertRaises(ContractError):bundle_run(p,run,root/'e.zip')
            self.assertFalse((root/'e.zip').exists())
    def test_bundle_roundtrip_reaudit(self):
        with copied() as (root,p,run,_):
            r=bundle_run(p,run,root/'e.zip');new=root/'unpack';m=safe_unpack((root/'e.zip').read_bytes(),new)
            self.assertEqual(m['contract'],'v050-evidence-bundle-r1')
            self.assertEqual(audit_run(new/'external_plan/v050.plan.json',new/'run'),r)
    def test_no_overwrite_zip(self):
        with copied() as (root,p,run,_):
            out=root/'existing.zip';out.write_bytes(b'keep')
            with self.assertRaises(ContractError):bundle_run(p,run,out)
            self.assertEqual(out.read_bytes(),b'keep')
    def test_recorded_score_not_source_of_truth(self):
        with copied() as (_,p,run,f):
            write_json(run/'summary.json',{'invented':'PASS'})
            self.assertEqual(audit_run(p,run),f['report'])
    def test_wrong_parent_link_even_with_rehashed_chain_rejected(self):
        with copied() as (_,p,run,_):
            events=[strict_json(l) for l in (run/'events.jsonl').read_bytes().splitlines()]
            e=next(x for x in events if x['slot']['stage']=='proof');e['parents'][0]['id']='unrelated'
            prev=read_json(p)['plan_sha256']
            for e in events:e['previous_hash']=prev;e['event_hash']=digest({k:v for k,v in e.items() if k!='event_hash'});prev=e['event_hash']
            (run/'events.jsonl').write_bytes(b'\n'.join(wire(e) for e in events)+b'\n')
            st=read_json(run/'status.json');st['event_tip']=prev;write_json(run/'status.json',st)
            with self.assertRaises(ContractError):audit_run(p,run)
    def test_real_not_response_cannot_be_replaced_by_gold_child_input(self):
        with copied() as (_,p,run,_):
            events=[strict_json(l) for l in (run/'events.jsonl').read_bytes().splitlines()]
            par=next(x for x in events if x['slot']['stage']=='not');folder=run/'calls'/par['slot']['id']
            raw=read_json(folder/'response.raw.json');payload=strict_json(raw['message']['content']);payload['value']=not payload['value'];raw['message']['content']=wire(payload).decode()
            new=wire(raw);(folder/'response.raw.json').write_bytes(new);par['response_sha256']=sha(new)
            for e in events:
                for parent in e['parents']:
                    if parent['id']==par['slot']['id']:parent['response_sha256']=par['response_sha256']
            prev=read_json(p)['plan_sha256']
            for e in events:e['previous_hash']=prev;e['event_hash']=digest({k:v for k,v in e.items() if k!='event_hash'});prev=e['event_hash']
            (run/'events.jsonl').write_bytes(b'\n'.join(wire(e) for e in events)+b'\n')
            st=read_json(run/'status.json');st['event_tip']=prev;write_json(run/'status.json',st)
            with self.assertRaises(ContractError):audit_run(p,run)
    def test_empty_extra_source_file_rejected(self):
        with copied() as (_,p,run,_):
            (run/'source_snapshot'/'extra.txt').write_bytes(b'')
            with self.assertRaises(ContractError):audit_run(p,run)
