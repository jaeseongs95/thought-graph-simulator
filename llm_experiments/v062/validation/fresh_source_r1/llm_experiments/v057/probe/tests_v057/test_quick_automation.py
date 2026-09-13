import contextlib,hashlib,io,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import auto_run_v057 as auto
from package_check_v057 import verify_package

def make_stage(root):
    root.mkdir();(root/'source.py').write_bytes(b'original\n');m={'contract':'v057-source-package-r1','file_hashes':{'source.py':hashlib.sha256(b'original\n').hexdigest()}}
    (root/'PACKAGE_MANIFEST.json').write_text(json.dumps(m));return root

class Automation(unittest.TestCase):
    def test_same_manifest_changed_bytes_not_reused(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);stage=make_stage(root/'stage');repo=root/'repo';repo.mkdir();target,_=auto.install(stage,repo);(target/'source.py').write_bytes(b'changed')
            with contextlib.redirect_stdout(io.StringIO()):got,changed=auto.install(stage,repo)
            self.assertTrue(changed);self.assertEqual((got/'source.py').read_bytes(),b'original\n');self.assertEqual(len(list(repo.glob('*.backup_*'))),1);self.assertEqual(next(repo.glob('*.backup_*')).joinpath('source.py').read_bytes(),b'changed')
    def test_identical_source_reused(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);s=make_stage(root/'stage');r=root/'repo';r.mkdir();auto.install(s,r);_,changed=auto.install(s,r);self.assertFalse(changed)
    def test_extra_file_not_trusted(self):
        with tempfile.TemporaryDirectory() as td:
            s=make_stage(Path(td)/'stage');(s/'extra.py').write_text('changed')
            with self.assertRaises(ValueError):verify_package(s)
    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            s=make_stage(Path(td)/'stage')
            try:(s/'linked').symlink_to(s/'source.py')
            except OSError:self.skipTest('OS disallows symlink')
            with self.assertRaises(ValueError):verify_package(s)
    def test_pycache_allowed_but_source_checked(self):
        with tempfile.TemporaryDirectory() as td:
            s=make_stage(Path(td)/'stage');(s/'__pycache__').mkdir();(s/'__pycache__/junk.pyc').write_bytes(b'cache');verify_package(s)
    def test_existing_results_preserved_name_increments(self):
        with tempfile.TemporaryDirectory() as td:
            r=Path(td);(r/'v057_selection_01.plan.baseline.zip').write_bytes(b'evidence');self.assertEqual(auto.free_name(r),'v057_selection_02');self.assertEqual((r/'v057_selection_01.plan.baseline.zip').read_bytes(),b'evidence')
    def test_requested_existing_name_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            r=Path(td);(r/'keep.plan.json').write_text('{}')
            with self.assertRaises(auto.StepError):auto.free_name(r,'keep')
    def test_unsafe_name_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(auto.StepError):auto.free_name(Path(td),'../unsafe')
    def test_subprocess_nonzero_not_retry(self):
        with tempfile.TemporaryDirectory() as td,contextlib.redirect_stdout(io.StringIO()):
            r=Path(td);flag=r/'flag';cmd=[sys.executable,'-c',f'from pathlib import Path; p=Path({str(flag)!r}); p.write_text(p.read_text()+"x" if p.exists() else "x"); raise SystemExit(3)']
            with self.assertRaises(auto.StepError):auto.run_step(cmd,r,r/'log')
            self.assertEqual(flag.read_text(),'x');self.assertIn(b'EXIT 3',(r/'log').read_bytes())
    def test_spaces_korean_native_stderr_kept(self):
        with tempfile.TemporaryDirectory(prefix='space ') as td,contextlib.redirect_stdout(io.StringIO()):
            r=Path(td);auto.run_step([sys.executable,'-c','import sys; print("검증"); print("오류가 아닌 stderr",file=sys.stderr)'],r,r/'log');self.assertIn('오류가 아닌 stderr',(r/'log').read_text())
    def test_both_model_presence_checked_by_metadata_not_pull(self):
        source=Path(auto.__file__).read_text();self.assertNotIn("['pull'",source);self.assertNotIn('ollama show',source);self.assertIn('preflight_v057.py',source)
    def test_external_endpoint_rejected(self):
        with self.assertRaises(auto.StepError):auto.ensure_server('http://example.com:11434',Path('/tmp'))
    def test_alive_server_does_not_start(self):
        with patch.object(auto,'server_version',return_value={'version':'test'}),patch.object(auto.subprocess,'Popen',side_effect=AssertionError('must not spawn')):
            self.assertEqual(auto.ensure_server('http://127.0.0.1:11434',Path('/tmp')),{'version':'test'})
    def test_no_model_download_when_server_missing(self):
        with tempfile.TemporaryDirectory() as td,patch.object(auto,'server_version',side_effect=OSError()),patch.object(auto.shutil,'which',return_value=None),patch.dict(os.environ,{'LOCALAPPDATA':td}):
            with self.assertRaises(auto.StepError):auto.ensure_server('http://127.0.0.1:11434',Path(td))
    def test_lock_released(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'lock'
            with auto.experiment_lock(p):pass
            with auto.experiment_lock(p):pass
    def test_second_lock_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'lock'
            with auto.experiment_lock(p):
                with self.assertRaises(auto.StepError):
                    with auto.experiment_lock(p):pass
