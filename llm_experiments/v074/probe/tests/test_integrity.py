import base64,contextlib,copy,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from fixtures import plan,baseline_path,Synth
import common,run,verify

def rehash(fs):
    p=common.load(fs['plan.json']);events=[common.load(x) for x in fs['records/events.jsonl'].splitlines()];tip=p['plan_sha256']
    for e in events:
        e['record_sha256']=common.sha(fs['records/'+e['action']['id']+'.json']);e['previous_hash']=tip
        e['event_hash']=common.sha(common.wire({k:v for k,v in e.items() if k!='event_hash'}));tip=e['event_hash']
    fs['records/events.jsonl']=b''.join(common.wire(e)+b'\n' for e in events)
    fs['MANIFEST.json']=common.wire({'contract':'v074-evidence-r1','file_hashes':{n:common.sha(b) for n,b in fs.items() if n!='MANIFEST.json'}})

def change_response(fs,sid,transform):
    name=f'wire/{sid}/response.raw.json';o=common.load(fs[name]);transform(o);raw=common.wire(o);fs[name]=raw
    rn=f'records/{sid}.json';r=common.load(fs[rn]);r['response_sha256']=common.sha(raw);r['response_b64']=base64.b64encode(raw).decode();fs[rn]=common.wire(r)

def change_request(fs,sid,transform):
    n=f'wire/{sid}/request.wire.json';o=common.load(fs[n]);transform(o);raw=common.wire(o);fs[n]=raw
    rn=f'records/{sid}.json';r=common.load(fs[rn]);r['request_sha256']=common.sha(raw);fs[rn]=common.wire(r)
    dn=f'wire/{sid}/dispatch.started.json';d=common.load(fs[dn]);d['request_sha256']=common.sha(raw);fs[dn]=common.wire(d)

class Integrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.td=tempfile.TemporaryDirectory(prefix='v074_integrity_');root=Path(cls.td.name);p=plan('v074_integrity');pp=root/'plan.json';common.save(pp,p);s=Synth()
        with patch.object(run,'exchange',s.exchange),contextlib.redirect_stdout(io.StringIO()):res=run.execute(pp,baseline_path(),root/'results'/p['run_name'],'http://127.0.0.1:11434')
        cls.files=common.unzip(Path(res['evidence_zip']).read_bytes());cls.p=p
        cls.select=next(x['id'] for x in p['slots'] if x['stage']=='select')
        cls.fact=next(x['id'] for x in p['slots'] if x['stage']=='facts' and next(t for t in p['trials'] if t['id']==x['trial_id'])['arm']=='model')
        cls.final=next(x['id'] for x in p['slots'] if x['stage']=='final')
    @classmethod
    def tearDownClass(cls):cls.td.cleanup()
    def rejected(self,edit,pattern):
        fs=dict(self.files);edit(fs);rehash(fs)
        path=Path(self.td.name)/('mut_'+self._testMethodName+'.zip');common.write(path,common.zip_bytes(fs))
        with self.assertRaisesRegex(ValueError,pattern):verify.verify_bundle(path)
    def test_request_D_drift_rehashed(self):
        self.rejected(lambda fs:change_request(fs,self.select,lambda o:o['messages'][0].update(content=o['messages'][0]['content'].replace('더 작은','더 큰'))),'request drift')
    def test_request_model_drift_rehashed(self):
        self.rejected(lambda fs:change_request(fs,self.select,lambda o:o.update(model='gemma3:4b')),'request drift')
    def test_request_seed_drift_rehashed(self):
        self.rejected(lambda fs:change_request(fs,self.select,lambda o:o['options'].update(seed=7)),'request drift')
    def test_generator_answer_leak_rehashed(self):
        self.rejected(lambda fs:change_request(fs,self.fact,lambda o:o['messages'][0].update(content=o['messages'][0]['content']+'\n정답 경로는 r83')),'request drift')
    def test_normalized_selector_original_rehashed(self):
        def edit(fs):
            change_response(fs,self.select,lambda o:o['message'].update(content=' '+o['message']['content']+' '))
        self.rejected(edit,'request drift')
    def test_selector_changed_after_generation_rehashed(self):
        def edit(fs):
            def flip(o):
                x=common.load(o['message']['content']);x['candidate_id']='route_1' if x['candidate_id']=='route_0' else 'route_0';o['message']['content']=common.wire(x).decode()
            change_response(fs,self.select,flip)
        self.rejected(edit,'request drift|conditional skip')
    def test_invalid_final_not_masked_by_old_summary(self):
        self.rejected(lambda fs:change_response(fs,self.final,lambda o:o['message'].update(content='{"final_node_id":"wrong"}')),'summary/semantics')
    def test_summary_score_rehashed(self):
        def edit(fs):
            x=common.load(fs['summary.json']);x['model_trace']['successes']=99;fs['summary.json']=common.wire(x)
        self.rejected(edit,'summary/semantics')
    def test_korean_report_rehashed(self):
        self.rejected(lambda fs:fs.update({'summary.ko.md':fs['summary.ko.md']+b'\nforged'}),'Korean report')
    def test_frozen_ledger_rehashed(self):
        self.rejected(lambda fs:fs.update({'source/docs/PLAN_LEDGER.ko.md':b'forged'}),'source snapshot|unexpected')
    def test_source_patch_rehashed(self):
        self.rejected(lambda fs:fs.update({'source/measure.py':fs['source/measure.py']+b'\n# changed'}),'source snapshot')
    def test_status_call_count_rehashed(self):
        def edit(fs):
            x=common.load(fs['status.json']);x['inference_calls']=214;fs['status.json']=common.wire(x)
        self.rejected(edit,'inference dispatch count')
    def test_skip_reason_rehashed(self):
        def edit(fs):
            for n,b in fs.items():
                if n.startswith('records/') and n.endswith('.json') and not n.endswith('.started.json'):
                    x=common.load(b)
                    if x.get('kind')=='skip':x['reason']='unmappable_selection';fs[n]=common.wire(x);return
        self.rejected(edit,'conditional skip')
    def test_unaccounted_response_rehashed(self):
        self.rejected(lambda fs:fs.update({'wire/fake/response.raw.json':b'{}'}),'observed count|unaccounted')
    def test_baseline_changed_rehashed(self):
        self.rejected(lambda fs:fs.update({'baseline/v073_evidence.zip':fs['baseline/v073_evidence.zip']+b'x'}),'baseline hash')

if __name__=='__main__':unittest.main()
