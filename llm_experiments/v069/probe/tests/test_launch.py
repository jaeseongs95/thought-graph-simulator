import contextlib,io,json,os,sys,tempfile,unittest
from pathlib import Path
from fixtures import *
import launch,build_release

def staged_source(parent):
    root=parent/'stage';probe=root/'llm_experiments/v069/probe';files=common.sources()
    for n,b in files.items():common.write(probe/n,b)
    common.save(root/'RELEASE_MANIFEST.json',{'contract':'v069-source-release-r1','file_hashes':{launch.PREFIX+n:common.sha(b) for n,b in files.items()}})
    return probe
class Launcher(unittest.TestCase):
    def test_offline_check_in_real_child(self):
        with tempfile.TemporaryDirectory(prefix='v069 오프라인 경로 ') as td,contextlib.redirect_stdout(io.StringIO()):
            root=Path(td);repo=root/'repo';repo.mkdir();src=staged_source(root);result=launch.workflow(src,repo,baseline_path(),check_only=True,run_name='v069_offline');self.assertTrue(result['check_only']);self.assertTrue(Path(result['plan']).is_file());self.assertFalse(list(repo.rglob('*_evidence.zip')))
    def test_end_to_end_child_on_synthetic_server(self):
        p=design.build_plan(baseline_path(),'v069_server','synthetic')
        with tempfile.TemporaryDirectory(prefix='v069 실행 한글 ') as td,server(p) as (endpoint,state),contextlib.redirect_stdout(io.StringIO()):
            root=Path(td);repo=root/'repo';repo.mkdir();src=staged_source(root);result=launch.workflow(src,repo,baseline_path(),run_name='v069_pipeline',endpoint=endpoint,synthetic=True,no_open=True);self.assertEqual(state['calls'],54);self.assertTrue(Path(result['bundle']).is_file());self.assertTrue(common.load(Path(result['receipt']).read_bytes())['verified'])
    def test_stderr_exit_zero_is_success(self):
        with tempfile.TemporaryDirectory() as td,contextlib.redirect_stdout(io.StringIO()):
            root=Path(td);launch.invoke([sys.executable,'-c','import sys; print("stderr message",file=sys.stderr)'],root,root/'log',os.environ.copy());self.assertIn('EXIT 0',(root/'log').read_text())
    def test_nonzero_exit_not_retried(self):
        with tempfile.TemporaryDirectory() as td,contextlib.redirect_stdout(io.StringIO()):
            root=Path(td);args=[sys.executable,'-c','from pathlib import Path; p=Path("counter"); p.write_text(p.read_text()+"x" if p.exists() else "x");raise SystemExit(3)']
            with self.assertRaises(launch.LaunchError):launch.invoke(args,root,root/'log',os.environ.copy())
            self.assertEqual((root/'counter').read_text(),'x')
    def test_modified_install_backed_up(self):
        with tempfile.TemporaryDirectory() as td,contextlib.redirect_stdout(io.StringIO()):
            root=Path(td);repo=root/'repo';repo.mkdir();src=staged_source(root);target=launch.install(src,repo);(target/'reference.py').write_text('changed');launch.install(src,repo);self.assertEqual((target/'reference.py').read_bytes(),(src/'reference.py').read_bytes());self.assertEqual(len(list(target.parent.glob('probe.backup_*'))),1)
    def test_existing_run_preserved(self):
        with tempfile.TemporaryDirectory() as td,contextlib.redirect_stdout(io.StringIO()):
            root=Path(td);repo=root/'repo';repo.mkdir();src=staged_source(root);(repo/'llm_experiments/v069/results_llm/v069_same').mkdir(parents=True)
            with self.assertRaises(launch.LaunchError):launch.workflow(src,repo,baseline_path(),check_only=True,run_name='v069_same')
    def test_deterministic_build_here(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);build_release.build(root/'a.zip');build_release.build(root/'b.zip');self.assertEqual((root/'a.zip').read_bytes(),(root/'b.zip').read_bytes())
