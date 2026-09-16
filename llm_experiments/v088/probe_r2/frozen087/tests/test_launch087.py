from pathlib import Path
import sys,os,unittest,tempfile,json,shutil,importlib.util
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core087 as c
spec=importlib.util.spec_from_file_location('_launch087',c.ROOT/'launch.py');launch=importlib.util.module_from_spec(spec);spec.loader.exec_module(launch)
BASE=Path(os.environ.get('V087_BASELINE',str(Path.home()/'Downloads'/c.spec()['baseline_name'])))

class Installation(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='v087_install_');self.addCleanup(self.temp.cleanup);self.repo=Path(self.temp.name)/'repo';self.repo.mkdir()
    def test_install_and_hash_check(self):
        p=launch.install(c.ROOT,self.repo);_,hs=launch.manifest_at(c.ROOT);launch.verify_tree(p,hs);self.assertEqual(p,self.repo/'llm_experiments/v087/probe')
    def test_second_identical_install_does_not_replace(self):
        p=launch.install(c.ROOT,self.repo);stamp=(p/'design087.py').stat().st_mtime_ns;self.assertEqual(launch.install(c.ROOT,self.repo),p);self.assertEqual((p/'design087.py').stat().st_mtime_ns,stamp)
    def test_modified_source_not_overwritten(self):
        p=launch.install(c.ROOT,self.repo);(p/'design087.py').write_text('# user modified')
        with self.assertRaises(launch.LaunchError):launch.install(c.ROOT,self.repo)
        self.assertEqual((p/'design087.py').read_text(),'# user modified')
    def test_prior_v086_untouched(self):
        old=self.repo/'llm_experiments/v086/results_llm';old.mkdir(parents=True);(old/'keep.txt').write_text('original');launch.install(c.ROOT,self.repo);self.assertEqual((old/'keep.txt').read_text(),'original')
    def test_bare_started_guard_blocks_install(self):
        root=self.repo/'llm_experiments/v087/results_llm';root.mkdir(parents=True);(root/'frozen_batch.started.json').write_text('{}')
        with self.assertRaises(launch.LaunchError):launch.install(c.ROOT,self.repo)
    def test_explicit_baseline_verifies_hash(self):self.assertEqual(launch.choose_baseline(self.repo,BASE),BASE.resolve())
    def test_wrong_baseline_rejected(self):
        wrong=self.repo/'wrong.zip';wrong.write_bytes(b'wrong')
        with self.assertRaises(launch.LaunchError):launch.choose_baseline(self.repo,wrong)
    def test_auto_baseline_over_100mb_is_found(self):
        d=self.repo/'llm_experiments/v086/results_llm';d.mkdir(parents=True);dest=d/c.spec()['baseline_name']
        try:os.link(BASE,dest)
        except OSError:shutil.copyfile(BASE,dest)
        self.assertGreater(dest.stat().st_size,100*1024**2);self.assertEqual(launch.choose_baseline(self.repo),dest.resolve())
    def test_lock_blocks_parallel_workflow(self):
        p=self.repo/'lock'
        with launch.lock(p):
            with self.assertRaises(launch.LaunchError):
                with launch.lock(p):pass
    def test_generated_run_not_named_holdout(self):self.assertIn("'v087_genfactor_'",(c.ROOT/'launch.py').read_text())
