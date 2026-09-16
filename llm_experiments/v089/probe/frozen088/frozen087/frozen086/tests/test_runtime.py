"""로컬 실행기 전체 합성 실행, 중단 보존, 변조 검사. 실제 모델 서버 호출 없음."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import unittest,sys,tempfile,io,contextlib,base64,os,subprocess,shutil
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core086 as c,run086 as run,design086 as d,verify086 as verify
from fixtures086 import BASELINE,fake_exchange

@unittest.skipUnless(BASELINE.is_file(),'v085 evidence required')
class Runtime(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='v086_test_');cls.root=Path(cls.tmp.name)
        cls.plan=d.make_plan(BASELINE,'v086_synthetic_full','synthetic',audit_previous=False)
        pp=cls.root/'plan.json';c.save(pp,cls.plan);out=cls.root/cls.plan['run_name']
        cls.exchange=fake_exchange('reported')
        with patch.object(run,'exchange',cls.exchange),contextlib.redirect_stdout(io.StringIO()):
            cls.result=run.execute(pp,BASELINE,out,'http://127.0.0.1:11434')
        cls.bundle=Path(cls.result['evidence_zip']);cls.fs=c.unzip(cls.bundle.read_bytes())
        export=os.environ.get('V086_VALIDATION_EXPORT')
        if export:
            folder=Path(export);folder.mkdir(parents=True,exist_ok=True)
            receipt=c.load(Path(cls.result['independent_json']).read_bytes()) if 'independent_json' in cls.result else verify.verify_bundle(cls.bundle)
            c.save(folder/'synthetic_full_independent.json',receipt)
            c.write(folder/'synthetic_full_summary.json',cls.fs['summary.json'])
            c.write(folder/'synthetic_full_diagnostics.json',cls.fs['diagnostics.json'])
            c.write(folder/'synthetic_full_summary.ko.md',cls.fs['summary.ko.md'])
            c.write(folder/'synthetic_full_diagnostics.ko.md',cls.fs['diagnostics.ko.md'])
            c.save(folder/'synthetic_full_bundle_record.json',{'sha256':c.sha(cls.bundle.read_bytes()),'bytes':cls.bundle.stat().st_size,'manifest_files':len(c.load(cls.fs['MANIFEST.json'])['file_hashes']),'source_hashes':cls.plan['source_hashes'],'provenance':'synthetic','actual_qwen_calls':0})

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def rewrite(self,fs):
        fs=dict(fs);fs['MANIFEST.json']=c.wire({'contract':'v086-evidence-r1','file_hashes':{k:c.sha(v) for k,v in fs.items() if k!='MANIFEST.json'}})
        p=self.root/'mutated.zip';p.write_bytes(c.zip_bytes(fs));return p
    def rechain(self,fs):
        events=[c.load(x) for x in fs['records/events.jsonl'].splitlines()];tip=c.load(fs['plan.json'])['plan_sha256']
        for e in events:
            sid=e['action']['id'];e['previous_hash']=tip;e['record_sha256']=c.sha(fs['records/'+sid+'.json'])
            e.pop('event_hash');e['event_hash']=c.sha(c.wire(e));tip=e['event_hash']
        fs['records/events.jsonl']=b''.join(c.wire(e)+b'\n' for e in events)
    def test_full_workflow(self):
        rec=verify.verify_bundle(self.bundle)
        self.assertTrue(rec['verified']);self.assertEqual(rec['observed_calls'],3612)
        self.assertEqual(rec['completed_actions'],3740);self.assertEqual(rec['provenance'],'synthetic')
        s=c.load(self.fs['summary.json']);self.assertEqual(s['groups']['correct_values']['totals']['D']['selection_success']['successes'],128)
    def test_manifest_mutation(self):
        fs=dict(self.fs);fs['MANIFEST.json']=b'{}';p=self.root/'badmanifest.zip';p.write_bytes(c.zip_bytes(fs))
        with self.assertRaises(ValueError):verify.verify_bundle(p)
    def test_semantic_score_and_report_tampering(self):
        for name in ('summary.json','summary.ko.md'):
            fs=dict(self.fs)
            if name.endswith('.json'):
                s=c.load(fs[name]);s['groups']['correct_values']['totals']['D']['selection_success']['successes']-=1;fs[name]=c.wire(s)
            else:fs[name]+=b'wrong'
            with self.assertRaises(ValueError):verify.verify_bundle(self.rewrite(fs))
    def test_auxiliary_diagnostics_tampering_rejected(self):
        for name in ('diagnostics.json','diagnostics.ko.md'):
            fs=dict(self.fs)
            if name.endswith('.json'):
                x=c.load(fs[name]);x['distinct_request_counts'][0]['request_files']+=1;fs[name]=c.wire(x)
            else:fs[name]+=b'tampered'
            with self.assertRaises(ValueError):verify.verify_bundle(self.rewrite(fs))
    def test_unaccounted_file_rejected(self):
        fs=dict(self.fs);fs['hidden.txt']=b'injected'
        with self.assertRaises(ValueError):verify.verify_bundle(self.rewrite(fs))
    def test_wrong_request_even_with_updated_all_hashes(self):
        slot=next(o for o in self.plan['slots'] if o['stage']=='select' and o['id'].endswith('correct_values_select'))
        sid=slot['id'];prefix='wire/'+sid+'/'
        for kind in ('seed','control_value'):
            fs=dict(self.fs);body=c.load(fs[prefix+'request.wire.json'])
            if kind=='seed':body['options']['seed']+=1
            else:
                before,text=body['messages'][0]['content'].split('\n\ninput: ');data=c.load(text)
                item=data['candidate_measurements'][0];value=c.load(item['content']);value['goal_depth']+=1;item['content']=c.wire(value).decode()
                body['messages'][0]['content']=before+'\n\ninput: '+c.wire(data).decode()
            fs[prefix+'request.wire.json']=c.wire(body);h=c.sha(c.wire(body))
            marker=c.load(fs[prefix+'dispatch.started.json']);marker['request_sha256']=h;fs[prefix+'dispatch.started.json']=c.wire(marker)
            rec=c.load(fs['records/'+sid+'.json']);rec['request_sha256']=h;fs['records/'+sid+'.json']=c.wire(rec);self.rechain(fs)
            with self.assertRaises(ValueError):verify.verify_bundle(self.rewrite(fs))
    def test_response_tampering_even_with_updated_hashes(self):
        sid=next(o['id'] for o in self.plan['slots'] if o['stage']=='select' and 'correct_values' in o['id'])
        fs=dict(self.fs);name='wire/'+sid+'/response.raw.json';outer=c.load(fs[name]);obj=c.load(outer['message']['content'])
        obj['candidate_id']='route_1' if obj['candidate_id']=='route_0' else 'route_0';outer['message']['content']=c.wire(obj).decode();raw=c.wire(outer);fs[name]=raw
        rec=c.load(fs['records/'+sid+'.json']);rec['response_sha256']=c.sha(raw);rec['response_b64']=base64.b64encode(raw).decode();fs['records/'+sid+'.json']=c.wire(rec)
        self.rechain(fs)
        with self.assertRaises(ValueError):verify.verify_bundle(self.rewrite(fs))
    def test_status_source_and_schedule_mutations(self):
        for kind in ('counts','source','schedule','provenance'):
            fs=dict(self.fs)
            if kind=='counts':
                st=c.load(fs['status.json']);st['observed_calls']-=1;fs['status.json']=c.wire(st)
            elif kind=='source':fs['source/design086.py']+=b'\n#tamper\n'
            else:
                p=c.load(fs['plan.json'])
                if kind=='schedule':p['trials'][0]['generate']=False
                else:p['provenance']='live'
                fs['plan.json']=c.wire(p)
            with self.assertRaises(ValueError):verify.verify_bundle(self.rewrite(fs))
    def test_second_run_blocked_by_guard(self):
        with self.assertRaises(FileExistsError):run.execute(self.root/'plan.json',BASELINE,self.root/'different','http://127.0.0.1:11434')
        p=d.make_plan(BASELINE,'v086_synthetic_newname','synthetic',audit_previous=False);pp=self.root/'plan2.json';c.save(pp,p)
        with self.assertRaises(FileExistsError):run.execute(pp,BASELINE,self.root/p['run_name'],'http://127.0.0.1:11434')
    def run_fault(self,exchange,tag,write_fault=False):
        folder=self.root/tag;folder.mkdir();p=d.make_plan(BASELINE,'v086_synthetic_'+tag,'synthetic',audit_previous=False);pp=folder/'plan.json';c.save(pp,p)
        out=folder/p['run_name'];target=p['slots'][1]['id'];original_write=c.write
        def fail_write(path,raw):
            # Path 객체의 구성요소로 비교해 Windows('\\')/POSIX('/') 구분자에 독립적으로 fault를 주입한다.
            if path.parent.name=='records' and path.name==target+'.json':raise OSError('synthetic after raw saved')
            return original_write(path,raw)
        with patch.object(run,'exchange',exchange),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            if write_fault:
                with patch.object(c,'write',fail_write):result=run.execute(pp,BASELINE,out,'http://127.0.0.1:11434')
            else:result=run.execute(pp,BASELINE,out,'http://127.0.0.1:11434')
        receipt=verify.verify_bundle(result['evidence_zip']);return receipt,out
    def test_http_no_retry(self):
        ex=fake_exchange(http_at=3);r,out=self.run_fault(ex,'http')
        self.assertEqual((r['state'],r['inference_calls'],ex.count['chat']),('stopped',3,3));self.assertIsNone(r['pending_action'])
    def test_identity_before_inference(self):
        ex=fake_exchange(identity_error=True);r,_=self.run_fault(ex,'identity');self.assertEqual(r['inference_calls'],0);self.assertEqual(r['state'],'stopped')
    def test_crash_after_dispatch_preserved(self):
        r,_=self.run_fault(fake_exchange(crash_at=3),'crash');self.assertEqual(r['state'],'crashed');self.assertEqual(r['inference_calls'],3);self.assertEqual(r['observed_calls'],2);self.assertIsNotNone(r['pending_action'])
    def test_response_before_record_commit_preserved(self):
        r,out=self.run_fault(fake_exchange(),'commit',True);self.assertEqual(r['state'],'crashed');self.assertEqual(r['inference_calls'],r['observed_calls']);self.assertTrue(r['pending_action']['response_saved'])
    def test_comparison_http_failure_stops_before_lookup(self):
        original=fake_exchange();seen={'failed':False}
        def exchange(endpoint,path,body,timeout):
            if path=='/api/chat':
                data=c.load(c.load(body)['messages'][0]['content'].split('\n\ninput: ',1)[1])
                if 'values' in data:
                    seen['failed']=True
                    return 503,b'synthetic comparison HTTP failure',None,1
            return original(endpoint,path,body,timeout)
        rec,out=self.run_fault(exchange,'compare_http')
        self.assertTrue(seen['failed']);self.assertEqual(rec['state'],'stopped')
        slot=next(o for o in self.plan['slots'] if o['stage']=='compare')
        t=d.trial_for(self.plan,slot)
        self.assertTrue((out/'records'/(slot['id']+'.json')).is_file())
        self.assertFalse((out/'records'/(t['selection_slot_id']+'.json')).exists())

    def test_lookup_request_value_tamper_even_after_rehash(self):
        slot=next(o for o in self.plan['slots'] if o['stage']=='select' and 'two_stage_values' in o['id'])
        sid=slot['id'];prefix='wire/'+sid+'/';fs=dict(self.fs)
        body=c.load(fs[prefix+'request.wire.json']);before,text=body['messages'][0]['content'].split('\n\ninput: ')
        data=c.load(text);data['value_original']=c.wire({'target_value':99}).decode()
        body['messages'][0]['content']=before+'\n\ninput: '+c.wire(data).decode()
        fs[prefix+'request.wire.json']=c.wire(body);h=c.sha(c.wire(body))
        marker=c.load(fs[prefix+'dispatch.started.json']);marker['request_sha256']=h;fs[prefix+'dispatch.started.json']=c.wire(marker)
        record=c.load(fs['records/'+sid+'.json']);record['request_sha256']=h;fs['records/'+sid+'.json']=c.wire(record);self.rechain(fs)
        with self.assertRaises(ValueError):verify.verify_bundle(self.rewrite(fs))

    def test_record_fault_path_match_is_separator_independent(self):
        from pathlib import PurePosixPath,PureWindowsPath
        target='slot_001'
        for path in (PurePosixPath('/tmp/run/records/slot_001.json'),PureWindowsPath(r'C:\run\records\slot_001.json')):
            self.assertEqual((path.parent.name,path.name),('records',target+'.json'))
    def test_finalize_idempotent(self):
        before=self.bundle.read_bytes();r=run.finalize(self.root/self.plan['run_name']);self.assertEqual(Path(r['evidence_zip']).read_bytes(),before)

class InputSafety(unittest.TestCase):
    def test_endpoint_restrictions(self):
        for addr in ('https://localhost:11434','http://evil.example','http://127.0.0.1/path','http://a:b@localhost','http://localhost?x=1'):
            with self.assertRaises(ValueError):run.endpoint_ok(addr)
        self.assertEqual(run.endpoint_ok('http://127.0.0.1:11434'),'http://127.0.0.1:11434')
    def test_json_duplicate_nonfinite(self):
        for raw in (b'{"a":1,"a":2}',b'{"x":NaN}',b'{"x":1e999}'):
            with self.assertRaises(ValueError):c.load(raw)
    def test_zip_path_restrictions(self):
        for name in ('../a','/a','C:/x','x\\y','CON','a/../b','a./file'):
            with self.assertRaises(ValueError):c.safe_name(name)
    def test_runname_restrictions(self):
        for name in ('v082_x','v086_../../x','v086_한글','v086_'):
            with self.assertRaises(ValueError):c.check_run_name(name)
    def test_synthetic_cli_cannot_call_live(self):
        with tempfile.TemporaryDirectory() as tmp:
            pp=Path(tmp)/'plan.json';c.save(pp,{'provenance':'synthetic'})
            with patch.object(run,'execute',side_effect=AssertionError('must not call')):
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(run.main(['execute','--plan',str(pp),'--baseline',str(pp),'--out',str(Path(tmp)/'out')]),2)
    @unittest.skipUnless(shutil.which('pwsh') or shutil.which('powershell'),'PowerShell native parser unavailable')
    def test_powershell_native_parser(self):
        exe=shutil.which('pwsh') or shutil.which('powershell');p=c.ROOT/'windows/Auto.template.ps1'
        escaped=str(p).replace("'","''")
        code=f"$e=$null;$t=$null;[System.Management.Automation.Language.Parser]::ParseFile('{escaped}',[ref]$t,[ref]$e)>$null;if($e.Count -gt 0){{$e|Out-String|Write-Error;exit 1}}"
        proc=subprocess.run([exe,'-NoProfile','-Command',code],capture_output=True,text=True);self.assertEqual(proc.returncode,0,proc.stderr)
