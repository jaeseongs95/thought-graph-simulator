"""설치 무결성, 해시 검색, 검사 전용 경계, 기존 파일 보존."""
import unittest,shutil
from unittest.mock import patch
from fixtures import *
import launch,build_release

class Launcher(unittest.TestCase):
    def make_release(self,root):
        p=root/'source.zip';build_release.build(p)
        for name,raw in common.unzip(p.read_bytes()).items():common.write(root/'release'/name,raw)
        return root/'release'/build_release.PREFIX
    def test_rebuild_deterministic(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);a=root/'a.zip';b=root/'b.zip';build_release.build(a);build_release.build(b)
            self.assertEqual(a.read_bytes(),b.read_bytes());build_release.check(a)
    def test_install_leaves_old_version_unchanged(self):
        with tempfile.TemporaryDirectory(prefix='v073 한글 설치 ') as td:
            root=Path(td);source=self.make_release(root);repo=root/'repository';old=repo/'llm_experiments/v072/probe/old.txt';common.write(old,b'old untouched')
            target=launch.install(source,repo);self.assertEqual(old.read_bytes(),b'old untouched');self.assertTrue((target/'docs/PLAN_LEDGER.ko.md').is_file())
            self.assertEqual(target,launch.install(source,repo))
    def test_modified_install_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=self.make_release(root);repo=root/'repository';repo.mkdir();target=launch.install(source,repo)
            (target/'design.py').write_bytes(b'modified source')
            with self.assertRaises(launch.LaunchError):launch.install(source,repo)
            self.assertEqual((target/'design.py').read_bytes(),b'modified source')
    def test_bad_baseline_refused(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p=root/'wrong.zip';p.write_bytes(b'bad')
            with self.assertRaises(launch.LaunchError):launch.choose_baseline(root,p)
    def test_renamed_baseline_content_match(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);folder=root/'llm_experiments/v072/results_llm';folder.mkdir(parents=True);p=folder/'v072_gemma_evidence(1).zip';shutil.copyfile(baseline_path(),p)
            self.assertEqual(launch.choose_baseline(root),p.resolve())
    def test_workflow_guard_refuses_new_name_before_install(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);repo=root/'repo';repo.mkdir();common.write(repo/'llm_experiments/v073/results_llm/frozen_batch.started.json',b'{}')
            with self.assertRaises(launch.LaunchError):launch.workflow(ROOT,repo,baseline_path(),run_name='v073_again',no_open=True)
    def test_prepare_is_offline(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'p.json'
            with patch('run.exchange',side_effect=AssertionError('network forbidden')),contextlib.redirect_stdout(io.StringIO()):
                result=run.main(['prepare','--baseline',str(baseline_path()),'--run-name','v073_check','--out',str(path)])
            self.assertEqual(result,0);self.assertEqual(common.load(path.read_bytes())['protocol']['max_inference_calls'],64)
            self.assertFalse((Path(td)/'frozen_batch.started.json').exists())
