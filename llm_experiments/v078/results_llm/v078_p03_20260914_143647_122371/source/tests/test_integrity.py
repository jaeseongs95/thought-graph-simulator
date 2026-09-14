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
    fs['MANIFEST.json']=common.wire({'contract':'v078-evidence-r1','file_hashes':{n:common.sha(b) for n,b in fs.items() if n!='MANIFEST.json'}})

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
        cls.td=tempfile.TemporaryDirectory(prefix='v078_integrity_');root=Path(cls.td.name);p=plan('v078_integrity');pp=root/'plan.json';common.save(pp,p);s=Synth()
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
            x=common.load(fs['summary.json']);x['arms']['base']['model_trace']['successes']=99;fs['summary.json']=common.wire(x)
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
        self.rejected(lambda fs:fs.update({'baseline/v077_evidence.zip':fs['baseline/v077_evidence.zip']+b'x'}),'baseline hash')

    def test_tight_fact_schema_cannot_be_widened_after_dispatch(self):
        sid=next(s['id'] for s in self.p['slots'] if s['stage']=='facts' and next(t for t in self.p['trials'] if t['id']==s['trial_id'])['variant']=='base')
        self.rejected(lambda fs:change_request(fs,sid,lambda o:o['format']['properties']['nodes']['items']['properties'].update(rule={'type':'string'})),'request drift')
    def test_tight_fact_count_cannot_be_forged(self):
        sid=next(s['id'] for s in self.p['slots'] if s['stage']=='facts' and next(t for t in self.p['trials'] if t['id']==s['trial_id'])['variant']=='base')
        self.rejected(lambda fs:change_request(fs,sid,lambda o:o['format']['properties']['nodes'].update(maxItems=16)),'request drift')
    def test_double_counted_shared_selection_rejected(self):
        def edit(fs):
            x=common.load(fs['summary.json']);x['shared_model_selection']['assigned']=48;fs['summary.json']=common.wire(x)
        self.rejected(edit,'summary/semantics')
    def test_stratum_effect_forgery_rejected(self):
        def edit(fs):
            x=common.load(fs['summary.json']);x['strata']['inverted_rule_count']['model_trace']['successes']=24;fs['summary.json']=common.wire(x)
        self.rejected(edit,'summary/semantics')
    def test_prompt_schema_and_api_schema_mismatch_rejected(self):
        self.rejected(lambda fs:change_request(fs,self.fact,lambda o:o['messages'][0].update(content=o['messages'][0]['content'].replace('"maxItems":2','"maxItems":16'))),'request drift')
    def test_shared_selector_forced_answer_schema_rejected(self):
        self.rejected(lambda fs:change_request(fs,self.select,lambda o:o['format']['properties']['candidate_id'].update(enum=['route_0'])),'request drift')
    def test_generator_history_cross_arm_edit_rejected(self):
        sid=next(s['id'] for s in self.p['slots'] if s['stage']=='rule')
        self.rejected(lambda fs:change_request(fs,sid,lambda o:o['messages'][0].update(content=o['messages'][0]['content'].replace('source_slot_id','foreign_slot_id'))),'request drift')


    def parent_slot(self):
        return next(s['id'] for s in self.p['slots'] if s['stage']=='rule' and
            next(t for t in self.p['trials'] if t['id']==s['trial_id'])['variant']=='base')
    def test_extra_binding_schema_rejected(self):
        self.rejected(lambda fs:change_request(fs,self.parent_slot(),lambda o:o['format']['properties'].update(bindings={'type':'array'})),'request drift')
    def test_forced_correct_parent_ids_rejected(self):
        self.rejected(lambda fs:change_request(fs,self.parent_slot(),lambda o:o['format']['properties']['node']['properties']['parents']['items'].update(enum=['f0'])),'request drift')
    def test_audit_hash_reintroduced_into_model_input_rejected(self):
        self.rejected(lambda fs:change_request(fs,self.parent_slot(),lambda o:o['messages'][0].update(content=o['messages'][0]['content']+'\nresponse_sha256: 0000')),'request drift')
    def test_parent_diagnostic_forgery_rejected(self):
        def edit(fs):
            s=common.load(fs['summary.json']);s['arms']['base']['count_correct_but_step_wrong']=99
            fs['summary.json']=common.wire(s)
        self.rejected(edit,'summary/semantics')
    def test_original_response_hash_still_verified(self):
        def edit(fs):
            name='wire/'+self.fact+'/response.raw.json'
            raw=common.load(fs[name]);raw['created_at']='changed without updating its record'
            fs[name]=common.wire(raw)
        self.rejected(edit,'response bytes|wire hashes')

    def test_answer_atom_enum_injected_rejected(self):
        self.rejected(lambda fs:change_request(fs,self.parent_slot(),lambda o:o['format']['properties']['node']['properties']['atom'].update(enum=['forged_answer'])),'request drift')
    def test_node_changed_without_forwarding_rejected(self):
        def edit(fs):
            def mutate(o):
                obj=common.load(o['message']['content']);obj['node']['atom']='invented';o['message']['content']=common.wire(obj).decode()
            change_response(fs,self.parent_slot(),mutate)
        self.rejected(edit,'request drift')
    def test_wrong_node_with_consistent_forwarding_cannot_keep_success(self):
        def edit(fs):
            def mutate(o):
                obj=common.load(o['message']['content']);obj['node']['atom']='invented';o['message']['content']=common.wire(obj).decode()
            change_response(fs,self.parent_slot(),mutate)
            import design
            raw={}
            for slot in self.p['slots']:
                rn='wire/'+slot['id']+'/response.raw.json'
                if rn not in fs:continue
                req=design.request_for(self.p,slot,raw)
                change_request(fs,slot['id'],lambda o,req=req:(o.clear(),o.update(req)))
                raw[slot['id']]=fs[rn]
        self.rejected(edit,'summary/semantics')
    def test_stratum_pair_score_forgery_rejected(self):
        def edit(fs):
            s=common.load(fs['summary.json']);s['strata']['equal_rule_count']['model_pairs']['successes']=-1;fs['summary.json']=common.wire(s)
        self.rejected(edit,'summary/semantics')
    def test_graph_only_score_forgery_rejected(self):
        def edit(fs):
            s=common.load(fs['summary.json']);s['arms']['base']['model_trace']['successes']=0;fs['summary.json']=common.wire(s)
        self.rejected(edit,'summary/semantics')

if __name__=='__main__':unittest.main()

