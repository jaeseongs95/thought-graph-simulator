"""값을 다시 해시한 변조·자료 누락·추가·출처 바꿔치기를 검사한다."""
import copy,json,unittest
from model_probe_v055.audit import audit_run
from model_probe_v055.contracts import ContractError,read_json,write_json,digest,sha
from .fixtures import copied

def reseal(run,events):
    tip=read_json(run/'plan.snapshot.json')['plan_sha256']
    for e in events:
        e['previous_hash']=tip;e['event_hash']=digest({k:v for k,v in e.items() if k!='event_hash'});tip=e['event_hash']
    (run/'events.jsonl').write_text('\n'.join(json.dumps(e) for e in events)+'\n')
    s=read_json(run/'status.json');s['event_tip']=tip;write_json(run/'status.json',s)

class Integrity(unittest.TestCase):
    def test_raw_tamper(self):
        with copied() as (_,p,run,_):
            f=next((run/'calls').glob('*/response.raw.json'));f.write_bytes(f.read_bytes()+b' ')
            with self.assertRaises(ContractError):audit_run(p,run)
    def test_resealed_request_tamper(self):
        with copied() as (_,p,run,_):
            es=[json.loads(x) for x in (run/'events.jsonl').read_text().splitlines()];e=next(e for e in es if e['action']['kind']=='call');f=run/'calls'/e['action']['id']/'request.wire.json';f.write_bytes(f.read_bytes()+b' ');e['request_sha256']=sha(f.read_bytes());reseal(run,es)
            with self.assertRaises(ContractError):audit_run(p,run)
    def test_resealed_model_swap(self):
        with copied() as (_,p,run,_):
            es=[json.loads(x) for x in (run/'events.jsonl').read_text().splitlines()];e=next(e for e in es if e['action']['kind']=='call');e['action']['slot']['model_key']='candidate';reseal(run,es)
            with self.assertRaises(ContractError):audit_run(p,run)
    def test_unregistered_file(self):
        with copied() as (_,p,run,_):
            (run/'extra.txt').write_text('x')
            with self.assertRaises(ContractError):audit_run(p,run)
    def test_source_snapshot_modified(self):
        with copied() as (_,p,run,_):
            f=next((run/'source_snapshot').rglob('*.py'));f.write_bytes(f.read_bytes()+b'\n')
            with self.assertRaises(ContractError):audit_run(p,run)
    def test_deleted_model_evidence(self):
        with copied() as (_,p,run,_):
            next((run/'calls').glob('candidate*/*response*')).unlink()
            with self.assertRaises((ContractError,OSError)):audit_run(p,run)
    def test_fake_completion_rejected(self):
        with copied() as (_,p,run,_):
            s=read_json(run/'status.json');s['inference_calls']=239;write_json(run/'status.json',s)
            with self.assertRaises(ContractError):audit_run(p,run)
    def test_resealed_metadata_drift_rejected(self):
        from model_probe_v055.contracts import b64,unb64
        with copied() as (_,p,run,_):
            es=[json.loads(x) for x in (run/'events.jsonl').read_text().splitlines()];e=es[0];f=run/'metadata'/(e['action']['id']+'.json');d=read_json(f);x=json.loads(unb64(d['requests'][-1]['response_b64']));x['template']='changed';d['requests'][-1]['response_b64']=b64(json.dumps(x).encode());write_json(f,d);e['metadata_sha256']=sha(f.read_bytes());reseal(run,es)
            with self.assertRaises(ContractError):audit_run(p,run)
    def test_stale_pass_invalidated(self):
        with copied() as (_,p,run,_):
            next((run/'calls').glob('*/response.raw.json')).write_bytes(b'{}')
            with self.assertRaises(ContractError):audit_run(p,run,write_report=True)
            self.assertFalse(read_json(run/'summary.json')['data_integrity'])
    def test_stored_summary_not_source_of_truth(self):
        with copied() as (_,p,run,b):
            write_json(run/'summary.json',{'fake':'all passed'})
            r=audit_run(p,run);self.assertEqual(r,b['report']);self.assertNotIn('fake',r)
    def test_false_live_label_rejected(self):
        with copied() as (_,p,run,_):
            m=read_json(run/'run_manifest.json');m['evidence_kind']='live_source_artifacts';m['new_model_inference']=True;write_json(run/'run_manifest.json',m)
            with self.assertRaises(ContractError):audit_run(p,run)
