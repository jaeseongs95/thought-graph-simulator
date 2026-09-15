"""실제 HTTP가 아닌 합성 교환기로 완료·오류·중단·변조·재시도 금지를 검사한다."""
import unittest,contextlib,io,tempfile,base64,os,subprocess,shutil
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import core081 as core
import design081,run081,verify081,previous081
from fixtures081 import plan,BASELINE,fake_exchange


def rechained(fs):
    """변조 시험에서 manifest만 맞춘 부정한 증거도 검산기가 거부해야 한다."""
    p=core.load(fs['plan.json']);tip=p['plan_sha256'];events=[]
    for old in fs['records/events.jsonl'].splitlines():
        e=core.load(old);sid=e['action']['id'];e['record_sha256']=core.sha(fs['records/'+sid+'.json'])
        e['previous_hash']=tip;e.pop('event_hash');e['event_hash']=core.sha(core.wire(e));tip=e['event_hash'];events.append(core.wire(e))
    fs['records/events.jsonl']=b'\n'.join(events)+b'\n'
    fs['MANIFEST.json']=core.wire({'contract':'v081-evidence-r1','file_hashes':{n:core.sha(b) for n,b in fs.items() if n!='MANIFEST.json'}})
    return core.zip_bytes(fs)


@unittest.skipUnless(BASELINE.is_file(),'v080 evidence 없음: 실행기와 기존 evidence 회귀 검사 건너뜀')
class Runtime(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='v081_test_');cls.root=Path(cls.tmp.name)
        cls.p=plan();cls.pp=cls.root/'plan.json';core.save(cls.pp,cls.p)
        cls.out=cls.root/cls.p['run_name']
        with contextlib.redirect_stdout(io.StringIO()),patch.object(run081,'exchange',side_effect=fake_exchange()):
            cls.result=run081.execute(cls.pp,BASELINE,cls.out,'http://127.0.0.1:11434')
        cls.bundle=Path(cls.result['evidence_zip']);cls.fs=core.unzip(cls.bundle.read_bytes())
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def reject(self,fs):
        path=self.root/'tampered.zip';path.write_bytes(rechained(fs))
        with self.assertRaises((ValueError,KeyError)):verify081.verify_bundle(path)
    def test_complete_and_independent(self):
        r=verify081.verify_bundle(self.bundle)
        self.assertEqual((r['state'],r['completed_actions'],r['inference_calls'],r['observed_calls']),('complete',1484,1404,1404))
        self.assertEqual(r['differences'],[]);self.assertFalse(r['production_imports'])
    def test_original_v080_reaudit(self):
        r=previous081.audit(BASELINE.read_bytes());self.assertTrue(r['verified']);self.assertEqual(r['observed_calls'],739)
    def test_guard_rejects_second_start(self):
        before=(self.root/'frozen_batch.started.json').read_bytes()
        with self.assertRaises(FileExistsError):run081.execute(self.pp,BASELINE,self.out,'http://127.0.0.1:11434')
        self.assertEqual(before,(self.root/'frozen_batch.started.json').read_bytes())
    def test_new_runname_cannot_bypass_guard(self):
        p=design081.make_plan(BASELINE,'v081_other','synthetic',False);pp=self.root/'other.plan.json';core.save(pp,p)
        with self.assertRaises(FileExistsError):run081.execute(pp,BASELINE,self.root/'v081_other','http://127.0.0.1:11434')
    def test_cli_cannot_send_synthetic_plan_to_real_server(self):
        with patch.object(run081,'exchange') as x,contextlib.redirect_stderr(io.StringIO()):
            rc=run081.main(['execute','--baseline',str(BASELINE),'--plan',str(self.pp),'--out',str(self.root/'v081_illegal')])
        self.assertEqual(rc,2);x.assert_not_called()
    def test_changed_request_even_rehashed_rejected(self):
        fs=dict(self.fs);sid=next(op['id'] for op in self.p['slots'] if op['stage']=='select');prefix='wire/'+sid+'/'
        b=core.load(fs[prefix+'request.wire.json']);b['options']['seed']+=1;raw=core.wire(b);fs[prefix+'request.wire.json']=raw
        rec=core.load(fs['records/'+sid+'.json']);rec['request_sha256']=core.sha(raw);fs['records/'+sid+'.json']=core.wire(rec)
        marker=core.load(fs[prefix+'dispatch.started.json']);marker['request_sha256']=core.sha(raw);fs[prefix+'dispatch.started.json']=core.wire(marker)
        self.reject(fs)
    def test_changed_score_even_rehashed_rejected(self):
        fs=dict(self.fs);s=core.load(fs['summary.json']);s['groups']['candidate_id']['totals']['D']['metric_end_to_end']['successes']=0;fs['summary.json']=core.wire(s);self.reject(fs)
    def test_changed_raw_parent_even_rehashed_rejected(self):
        fs=dict(self.fs);sid=next(op['id'] for op in self.p['slots'] if op['stage']=='rule');prefix='wire/'+sid+'/'
        o=core.load(fs[prefix+'response.raw.json']);x=core.load(o['message']['content']);x['node']['parents']=[];o['message']['content']=core.wire(x).decode();raw=core.wire(o)
        fs[prefix+'response.raw.json']=raw;rec=core.load(fs['records/'+sid+'.json']);rec['response_sha256']=core.sha(raw);rec['response_b64']=base64.b64encode(raw).decode();fs['records/'+sid+'.json']=core.wire(rec);self.reject(fs)
    def test_false_complete_status_rejected(self):
        fs=dict(self.fs);s=core.load(fs['status.json']);s['observed_calls']-=1;fs['status.json']=core.wire(s);self.reject(fs)
    def test_unaccounted_file_rejected(self):
        fs=dict(self.fs);fs['hidden_answer.json']=b'{}';self.reject(fs)
    def test_changed_presentation_mapping_rejected(self):
        fs=dict(self.fs);p=core.load(fs['plan.json']);p['trials'][2]['id_assignment_index']^=1;fs['plan.json']=core.wire(p);self.reject(fs)
    def test_changed_source_rejected(self):
        fs=dict(self.fs);fs['source/report081.py']+=b'\n# altered\n';self.reject(fs)
    def scenario(self,**kwargs):
        root=self.root/('case_'+str(len(list(self.root.iterdir()))));root.mkdir()
        p=plan();pp=root/'plan.json';core.save(pp,p);exchange=fake_exchange(**kwargs)
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()),patch.object(run081,'exchange',side_effect=exchange):
            result=run081.execute(pp,BASELINE,root/p['run_name'],'http://127.0.0.1:11434')
        return result,verify081.verify_bundle(Path(result['evidence_zip'])),exchange.count,root
    def test_http_error_stops_once(self):
        result,r,count,root=self.scenario(http_at=1)
        self.assertEqual((result['state'],count['chat']),('stopped',1));self.assertIsNone(r['pending_action'])
    def test_identity_error_before_any_inference(self):
        result,r,count,root=self.scenario(identity_error=True)
        self.assertEqual((result['state'],count['chat']),('stopped',0));self.assertTrue((root/'frozen_batch.started.json').exists())
    def test_crash_preserves_unobserved_dispatch(self):
        result,r,count,root=self.scenario(crash_at=1)
        self.assertEqual((r['state'],r['inference_calls'],r['observed_calls']),('crashed',1,0));self.assertIsNotNone(r['pending_action'])
        s=core.load((root/'v081_synthetic_test'/'summary.json').read_bytes());self.assertEqual(s['groups']['candidate_id']['totals']['D']['metric_end_to_end']['unmeasured'],64)


class Interface(unittest.TestCase):
    def test_reject_nonlocal_endpoints(self):
        for endpoint in ['https://127.0.0.1:11434','http://evil.example','http://localhost/path','http://user:pass@localhost:11434','http://localhost?x=1']:
            with self.assertRaises(ValueError):run081.endpoint_ok(endpoint)
    def test_accept_local_endpoint(self):self.assertEqual(run081.endpoint_ok('http://127.0.0.1:11434/'),'http://127.0.0.1:11434')
    def test_nonfinite_and_duplicate_JSON_rejected(self):
        for value in [b'{"a":1,"a":2}',b'{"a":NaN}',b'{"a":1e999}']:
            with self.assertRaises(ValueError):core.load(value)
    def test_unsafe_archive_names_rejected(self):
        for name in ['../a','/root/a','a\\b','CON.txt','a/../b']:
            with self.assertRaises(ValueError):core.safe_name(name)
    @unittest.skipUnless(shutil.which('pwsh') or shutil.which('powershell'),'Windows PowerShell 네이티브 구문 검사 도구 없음')
    def test_powershell_syntax(self):
        exe=shutil.which('pwsh') or shutil.which('powershell');p=core.ROOT/'windows/Auto.template.ps1'
        command="$e=$null;$t=$null;[System.Management.Automation.Language.Parser]::ParseFile('"+str(p).replace("'","''")+"',[ref]$t,[ref]$e)>$null;if($e.Count){$e|Out-String|Write-Error;exit 1}"
        r=subprocess.run([exe,'-NoProfile','-Command',command],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)



class _ExtraIntegrity:
    """추가 불변식. inherited 시험도 같은 완료 번들을 대상으로 실행한다."""
    def test_changed_rule_ids_response_even_rehashed_rejected(self):
        fs=dict(self.fs)
        sid=next(op['id'] for op in self.p['slots'] if op['stage']=='select' and op['id'].endswith('_rule_ids_select'))
        prefix='wire/'+sid+'/'
        outer=core.load(fs[prefix+'response.raw.json']);obj=core.load(outer['message']['content'])
        obj['rule_ids'].reverse();outer['message']['content']=core.wire(obj).decode();raw=core.wire(outer)
        fs[prefix+'response.raw.json']=raw
        rec=core.load(fs['records/'+sid+'.json']);rec['response_sha256']=core.sha(raw);rec['response_b64']=base64.b64encode(raw).decode()
        fs['records/'+sid+'.json']=core.wire(rec);self.reject(fs)

    def test_false_copy_diagnostic_rejected(self):
        fs=dict(self.fs);s=core.load(fs['summary.json'])
        s['copy_diagnostic_counts']['order_mismatch']=100
        fs['summary.json']=core.wire(s);self.reject(fs)

    def test_false_pair_advantage_rejected(self):
        fs=dict(self.fs);s=core.load(fs['summary.json'])
        s['paired_trials']['D']['metric_end_to_end']['rule_ids_only']+=1
        fs['summary.json']=core.wire(s);self.reject(fs)

    def test_false_reference_duplication_rejected(self):
        fs=dict(self.fs);s=core.load(fs['summary.json']);s['reference']['assigned']=32
        fs['summary.json']=core.wire(s);self.reject(fs)

    def test_reordered_output_schema_rejected(self):
        fs=dict(self.fs);sid=next(o['id'] for o in self.p['slots'] if o['stage']=='select' and not o['id'].endswith('_rule_ids_select'))
        prefix='wire/'+sid+'/'
        req=core.load(fs[prefix+'request.wire.json']);req['format']['properties']['candidate_id']['enum'].reverse()
        raw=core.wire(req);fs[prefix+'request.wire.json']=raw
        rec=core.load(fs['records/'+sid+'.json']);rec['request_sha256']=core.sha(raw);fs['records/'+sid+'.json']=core.wire(rec)
        marker=core.load(fs[prefix+'dispatch.started.json']);marker['request_sha256']=core.sha(raw);fs[prefix+'dispatch.started.json']=core.wire(marker)
        self.reject(fs)

    def test_changed_raw_history_or_selection_not_hidden_by_hash(self):
        fs=dict(self.fs);sid=next(o['id'] for o in self.p['slots'] if o['stage']=='rule')
        prefix='wire/'+sid+'/'
        req=core.load(fs[prefix+'request.wire.json'])
        req['messages'][0]['content']=req['messages'][0]['content'].replace('selection_original','corrected_selection')
        raw=core.wire(req);fs[prefix+'request.wire.json']=raw
        rec=core.load(fs['records/'+sid+'.json']);rec['request_sha256']=core.sha(raw);fs['records/'+sid+'.json']=core.wire(rec)
        marker=core.load(fs[prefix+'dispatch.started.json']);marker['request_sha256']=core.sha(raw);fs[prefix+'dispatch.started.json']=core.wire(marker)
        self.reject(fs)

    def test_resume_does_not_reissue_calls(self):
        with patch.object(run081,'exchange') as calls,contextlib.redirect_stdout(io.StringIO()):
            result=run081.finalize(self.out)
        self.assertEqual(result,self.result);calls.assert_not_called()

    def test_crash_after_raw_saved_counts_observation_not_scored(self):
        root=self.root/'after_response';root.mkdir()
        p=plan();pp=root/'plan.json';core.save(pp,p)
        real_write=core.write;flag={'raised':False}
        def interrupt_after_response(path,raw):
            real_write(path,raw)
            if str(path).endswith('response.raw.json') and '/wire/' in str(path).replace('\\','/') and not flag['raised']:
                flag['raised']=True
                raise KeyboardInterrupt('synthetic interrupt after response bytes saved')
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()),patch.object(run081,'exchange',side_effect=fake_exchange()),patch.object(core,'write',side_effect=interrupt_after_response):
            result=run081.execute(pp,BASELINE,root/p['run_name'],'http://127.0.0.1:11434')
        receipt=verify081.verify_bundle(Path(result['evidence_zip']))
        self.assertEqual((receipt['state'],receipt['inference_calls'],receipt['observed_calls']),('crashed',1,1))
        self.assertTrue(receipt['pending_action']['response_saved'])
        summary=core.load((root/p['run_name']/'summary.json').read_bytes())
        self.assertTrue(all(r['actual_D'] is None for r in summary['trials']))

    def test_plan_changed_before_guard_or_network_rejected(self):
        root=self.root/'bad_plan';root.mkdir();p=plan();p['protocol']['seeds'][0]+=1
        pp=root/'plan.json';core.save(pp,p)
        with patch.object(run081,'exchange') as calls,self.assertRaises(ValueError):
            run081.execute(pp,BASELINE,root/p['run_name'],'http://127.0.0.1:11434')
        self.assertFalse((root/'frozen_batch.started.json').exists());calls.assert_not_called()


for _name, _method in vars(_ExtraIntegrity).items():
    if _name.startswith("test_"):
        setattr(Runtime, _name, _method)

if __name__ == "__main__":
    unittest.main()
