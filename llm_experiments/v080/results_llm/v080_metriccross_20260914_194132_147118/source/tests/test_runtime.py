"""실제 HTTP가 아닌 합성 교환기로 완료·오류·중단·변조·재시도 금지를 검사한다."""
import unittest,contextlib,io,tempfile,base64,os,subprocess,shutil
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import core080 as core
import design080,run080,verify080,previous080
from fixtures080 import plan,BASELINE,fake_exchange


def rechained(fs):
    """변조 시험에서 manifest만 맞춘 부정한 증거도 검산기가 거부해야 한다."""
    p=core.load(fs['plan.json']);tip=p['plan_sha256'];events=[]
    for old in fs['records/events.jsonl'].splitlines():
        e=core.load(old);sid=e['action']['id'];e['record_sha256']=core.sha(fs['records/'+sid+'.json'])
        e['previous_hash']=tip;e.pop('event_hash');e['event_hash']=core.sha(core.wire(e));tip=e['event_hash'];events.append(core.wire(e))
    fs['records/events.jsonl']=b'\n'.join(events)+b'\n'
    fs['MANIFEST.json']=core.wire({'contract':'v080-evidence-r1','file_hashes':{n:core.sha(b) for n,b in fs.items() if n!='MANIFEST.json'}})
    return core.zip_bytes(fs)


@unittest.skipUnless(BASELINE.is_file(),'v079 evidence 없음: 실행기와 기존 evidence 회귀 검사 건너뜀')
class Runtime(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='v080_test_');cls.root=Path(cls.tmp.name)
        cls.p=plan();cls.pp=cls.root/'plan.json';core.save(cls.pp,cls.p)
        cls.out=cls.root/cls.p['run_name']
        with contextlib.redirect_stdout(io.StringIO()),patch.object(run080,'exchange',side_effect=fake_exchange()):
            cls.result=run080.execute(cls.pp,BASELINE,cls.out,'http://127.0.0.1:11434')
        cls.bundle=Path(cls.result['evidence_zip']);cls.fs=core.unzip(cls.bundle.read_bytes())
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def reject(self,fs):
        path=self.root/'tampered.zip';path.write_bytes(rechained(fs))
        with self.assertRaises((ValueError,KeyError)):verify080.verify_bundle(path)
    def test_complete_and_independent(self):
        r=verify080.verify_bundle(self.bundle)
        self.assertEqual((r['state'],r['completed_actions'],r['inference_calls'],r['observed_calls']),('complete',796,748,748))
        self.assertEqual(r['differences'],[]);self.assertFalse(r['production_imports'])
    def test_original_v079_reaudit(self):
        r=previous080.audit(BASELINE.read_bytes());self.assertTrue(r['verified']);self.assertEqual(r['observed_calls'],580)
    def test_guard_rejects_second_start(self):
        before=(self.root/'frozen_batch.started.json').read_bytes()
        with self.assertRaises(FileExistsError):run080.execute(self.pp,BASELINE,self.out,'http://127.0.0.1:11434')
        self.assertEqual(before,(self.root/'frozen_batch.started.json').read_bytes())
    def test_new_runname_cannot_bypass_guard(self):
        p=design080.make_plan(BASELINE,'v080_other','synthetic',False);pp=self.root/'other.plan.json';core.save(pp,p)
        with self.assertRaises(FileExistsError):run080.execute(pp,BASELINE,self.root/'v080_other','http://127.0.0.1:11434')
    def test_cli_cannot_send_synthetic_plan_to_real_server(self):
        with patch.object(run080,'exchange') as x,contextlib.redirect_stderr(io.StringIO()):
            rc=run080.main(['execute','--baseline',str(BASELINE),'--plan',str(self.pp),'--out',str(self.root/'v080_illegal')])
        self.assertEqual(rc,2);x.assert_not_called()
    def test_changed_request_even_rehashed_rejected(self):
        fs=dict(self.fs);sid=next(op['id'] for op in self.p['slots'] if op['stage']=='select');prefix='wire/'+sid+'/'
        b=core.load(fs[prefix+'request.wire.json']);b['options']['seed']+=1;raw=core.wire(b);fs[prefix+'request.wire.json']=raw
        rec=core.load(fs['records/'+sid+'.json']);rec['request_sha256']=core.sha(raw);fs['records/'+sid+'.json']=core.wire(rec)
        marker=core.load(fs[prefix+'dispatch.started.json']);marker['request_sha256']=core.sha(raw);fs[prefix+'dispatch.started.json']=core.wire(marker)
        self.reject(fs)
    def test_changed_score_even_rehashed_rejected(self):
        fs=dict(self.fs);s=core.load(fs['summary.json']);s['totals']['D']['metric_end_to_end']['successes']=0;fs['summary.json']=core.wire(s);self.reject(fs)
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
        fs=dict(self.fs);fs['source/report080.py']+=b'\n# altered\n';self.reject(fs)
    def scenario(self,**kwargs):
        root=self.root/('case_'+str(len(list(self.root.iterdir()))));root.mkdir()
        p=plan();pp=root/'plan.json';core.save(pp,p);exchange=fake_exchange(**kwargs)
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()),patch.object(run080,'exchange',side_effect=exchange):
            result=run080.execute(pp,BASELINE,root/p['run_name'],'http://127.0.0.1:11434')
        return result,verify080.verify_bundle(Path(result['evidence_zip'])),exchange.count,root
    def test_http_error_stops_once(self):
        result,r,count,root=self.scenario(http_at=1)
        self.assertEqual((result['state'],count['chat']),('stopped',1));self.assertIsNone(r['pending_action'])
    def test_identity_error_before_any_inference(self):
        result,r,count,root=self.scenario(identity_error=True)
        self.assertEqual((result['state'],count['chat']),('stopped',0));self.assertTrue((root/'frozen_batch.started.json').exists())
    def test_crash_preserves_unobserved_dispatch(self):
        result,r,count,root=self.scenario(crash_at=1)
        self.assertEqual((r['state'],r['inference_calls'],r['observed_calls']),('crashed',1,0));self.assertIsNotNone(r['pending_action'])
        s=core.load((root/'v080_synthetic_test'/'summary.json').read_bytes());self.assertEqual(s['totals']['D']['metric_end_to_end']['unmeasured'],64)


class Interface(unittest.TestCase):
    def test_reject_nonlocal_endpoints(self):
        for endpoint in ['https://127.0.0.1:11434','http://evil.example','http://localhost/path','http://user:pass@localhost:11434','http://localhost?x=1']:
            with self.assertRaises(ValueError):run080.endpoint_ok(endpoint)
    def test_accept_local_endpoint(self):self.assertEqual(run080.endpoint_ok('http://127.0.0.1:11434/'),'http://127.0.0.1:11434')
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

if __name__=='__main__':unittest.main()
