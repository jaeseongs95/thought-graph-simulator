from pathlib import Path
import sys,os,unittest,tempfile,json,shutil,importlib.util
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core091 as c
spec=importlib.util.spec_from_file_location('_launch091',c.ROOT/'launch.py');launch=importlib.util.module_from_spec(spec);spec.loader.exec_module(launch)
BASE=Path(os.environ.get('V091_BASELINE',str(Path.home()/'Downloads'/c.spec()['baseline_name'])))

class Installation(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='v091_install_');self.addCleanup(self.temp.cleanup);self.repo=Path(self.temp.name)/'repo';self.repo.mkdir()
    def test_install_and_recheck_installed_manifest(self):
        p=launch.install(c.ROOT,self.repo);m,hs=launch.manifest_at(p);launch.verify_tree(p,hs);self.assertEqual(p,self.repo/'llm_experiments/v091/probe')
    def test_second_identical_install_no_replacement(self):
        p=launch.install(c.ROOT,self.repo);stamp=(p/'design091.py').stat().st_mtime_ns;self.assertEqual(launch.install(c.ROOT,self.repo),p);self.assertEqual((p/'design091.py').stat().st_mtime_ns,stamp)
    def test_modified_source_not_overwritten(self):
        p=launch.install(c.ROOT,self.repo);(p/'design091.py').write_text('# user modified')
        with self.assertRaises(launch.LaunchError):launch.install(c.ROOT,self.repo)
        self.assertEqual((p/'design091.py').read_text(),'# user modified')
    def test_all_v090_state_untouched(self):
        version=self.repo/'llm_experiments/v090';files=['RELEASE_MANIFEST.json','RELEASE_MANIFEST_r2.json','probe_r2/keep.py','results_llm/frozen_batch_r2.started.json','results_llm/automation_logs/failed/run.log','results_llm/completed_evidence.zip']
        for name in files:
            p=version/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'old:'+name.encode())
        before={x.relative_to(version).as_posix():x.read_bytes() for x in version.rglob('*') if x.is_file()}
        launch.install(c.ROOT,self.repo)
        self.assertEqual(before,{x.relative_to(version).as_posix():x.read_bytes() for x in version.rglob('*') if x.is_file()})
    def test_v091_guard_blocks_install(self):
        root=self.repo/'llm_experiments/v091/results_llm';root.mkdir(parents=True);(root/'frozen_batch.started.json').write_text('{}')
        with self.assertRaises(launch.LaunchError):launch.install(c.ROOT,self.repo)
    def test_installed_manifest_not_unrelated_parent_manifest(self):
        p=launch.install(c.ROOT,self.repo);(p.parent/'RELEASE_MANIFEST.json').write_text('{"contract":"v090-source-release-r1"}')
        m,_=launch.manifest_at(p);self.assertEqual(m['contract'],'v091-source-release-r1')
    def test_bad_installed_manifest_cannot_fallback(self):
        p=launch.install(c.ROOT,self.repo);m,_=launch.manifest_at(p);(self.repo/'RELEASE_MANIFEST.json').write_text(json.dumps(m))
        (p.parent/launch.INSTALLED_MANIFEST).write_text('{"contract":"bad"}')
        with self.assertRaises(launch.LaunchError):launch.manifest_at(p)
    def test_missing_installed_manifest_not_silently_rebuilt(self):
        p=launch.install(c.ROOT,self.repo);(p.parent/launch.INSTALLED_MANIFEST).unlink()
        with self.assertRaises(launch.LaunchError):launch.install(c.ROOT,self.repo)
    def test_explicit_baseline_hash(self):self.assertEqual(launch.choose_baseline(self.repo,BASE),BASE.resolve())
    def test_wrong_baseline_rejected(self):
        wrong=self.repo/'wrong.zip';wrong.write_bytes(b'wrong')
        with self.assertRaises(launch.LaunchError):launch.choose_baseline(self.repo,wrong)
    def test_auto_large_baseline_is_found(self):
        folder=self.repo/'llm_experiments/v090/results_llm';folder.mkdir(parents=True);dest=folder/c.spec()['baseline_name']
        try:os.link(BASE,dest)
        except OSError:shutil.copyfile(BASE,dest)
        self.assertGreater(dest.stat().st_size,100*1024**2);self.assertEqual(launch.choose_baseline(self.repo),dest.resolve())
    def test_lock_prevents_parallel_workflow(self):
        with launch.lock(self.repo/'lock'):
            with self.assertRaises(launch.LaunchError):
                with launch.lock(self.repo/'lock'):pass
    def test_receipt_records_actual_installed_sources(self):
        p=launch.install(c.ROOT,self.repo);out=self.repo/'logs';out.mkdir();launch.write_installation_receipt(c.ROOT,p,out)
        value=json.loads((out/'installation.json').read_text());self.assertEqual(value['source_hashes']['launch.py'],launch.digest(p/'launch.py'));self.assertEqual(value['max_inference_calls'],10944)
    def test_run_name_is_new_version(self):self.assertIn("'v091_structural_'",(c.ROOT/'launch.py').read_text())
