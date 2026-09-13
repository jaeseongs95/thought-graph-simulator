import contextlib,hashlib,io,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from fixtures import *
import launch

def staged_source(parent):
    # 실제 소스 파일들을 별도 폴더에 담는다. 배포 검사와 동일한 경로 prefix를 사용.
    stage=parent/'stage';probe=stage/'llm_experiments/v066/probe';probe.mkdir(parents=True)
    files=common.sources()
    for name,raw in files.items():common.write(probe/name,raw)
    (stage/'RELEASE_MANIFEST.json').write_text(json.dumps({'contract':'v066-source-release-r1','file_hashes':{launch.PREFIX+n:common.sha(v) for n,v in files.items()}}))
    return probe

class Launch(unittest.TestCase):
    def test_modified_installed_source_is_backed_up(self):
        with tempfile.TemporaryDirectory() as td:
            r=Path(td);stage=staged_source(r);repo=r/'repo';repo.mkdir()
            target=launch.install(stage,repo);(target/'measure.py').write_bytes(b'changed')
            with contextlib.redirect_stdout(io.StringIO()):new=launch.install(stage,repo)
            self.assertEqual((new/'measure.py').read_bytes(),(stage/'measure.py').read_bytes());self.assertEqual(len(list(target.parent.glob('probe.backup_*'))),1)
    def test_unchanged_source_is_reused(self):
        with tempfile.TemporaryDirectory() as td:
            r=Path(td);s=staged_source(r);repo=r/'repo';repo.mkdir();a=launch.install(s,repo);b=launch.install(s,repo);self.assertEqual(a,b);self.assertFalse(list(a.parent.glob('probe.backup_*')))
    def test_nonzero_child_once_and_stderr_logged(self):
        with tempfile.TemporaryDirectory() as td,contextlib.redirect_stdout(io.StringIO()):
            p=Path(td);log=p/'log';flag=p/'counter'
            script=f"from pathlib import Path; import sys; p=Path({str(flag)!r}); p.write_text(p.read_text()+'x' if p.exists() else 'x'); print('stderr 기록',file=sys.stderr);sys.exit(3)"
            with self.assertRaises(launch.LaunchError):launch.invoke([sys.executable,'-X','utf8','-c',script],p,log,dict(os.environ,PYTHONIOENCODING='utf-8'))
            self.assertEqual(flag.read_text(),'x');self.assertIn('stderr 기록',log.read_text())
    def test_success_stderr_is_not_failure(self):
        with tempfile.TemporaryDirectory() as td,contextlib.redirect_stdout(io.StringIO()):
            p=Path(td);launch.invoke([sys.executable,'-c',"import sys; print('stderr-not-failure',file=sys.stderr)"],p,p/'log',os.environ.copy());self.assertIn('EXIT 0',(p/'log').read_text())
    def test_lock_released(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'lock'
            with launch.lock(p):pass
            with launch.lock(p):pass
    def test_offline_pipeline_no_network(self):
        with tempfile.TemporaryDirectory(prefix='launch 한글 space ') as td,contextlib.redirect_stdout(io.StringIO()):
            p=Path(td);stage=staged_source(p);repo=p/'repo';repo.mkdir()
            result=launch.workflow(stage,repo,baseline_path(),check_only=True,run_name='v066_offline')
            self.assertTrue(result['check_only']);self.assertTrue(Path(result['plan']).exists());self.assertFalse(list(repo.rglob('*_evidence.zip')))
    def test_actual_subprocess_synthetic_complete(self):
        with tempfile.TemporaryDirectory(prefix='launch 한글 space ') as td,contextlib.redirect_stdout(io.StringIO()):
            p=Path(td);stage=staged_source(p);repo=p/'repo';repo.mkdir();plan=design.build_plan(baseline_path(),'v066_server','synthetic')
            with server(plan) as (endpoint,state):result=launch.workflow(stage,repo,baseline_path(),run_name='v066_pipeline',endpoint=endpoint,synthetic=True,no_open=True)
            self.assertEqual(state['chats'],36);receipt=json.loads(Path(result['receipt']).read_text());self.assertTrue(receipt['verified']);self.assertEqual(receipt['provenance'],'synthetic')
