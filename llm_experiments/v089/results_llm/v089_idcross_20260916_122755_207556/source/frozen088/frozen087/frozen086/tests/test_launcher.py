"""배포 바이트·무덮어쓰기·CheckOnly 라우팅. 모델 또는 외부 서비스 호출 없음."""
from pathlib import Path
import sys,unittest,tempfile,base64,re,contextlib,io
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core086 as c,launch,build_release,build_auto
from fixtures086 import BASELINE

class Launcher(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='v086_release_test_');cls.root=Path(cls.tmp.name)
        cls.zip=cls.root/'release.zip';build_release.build(cls.zip)
        cls.fs=c.unzip(cls.zip.read_bytes());release=cls.root/'release'
        for n,b in cls.fs.items():c.write(release/n,b)
        cls.source=release/'llm_experiments/v086/probe'
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_deterministic_release_and_manifest(self):
        target=self.root/'second.zip';build_release.build(target);self.assertEqual(self.zip.read_bytes(),target.read_bytes())
        build_release.check(target)
    def test_embedded_payload_matches_source(self):
        p=self.root/'Run-v086-Auto.ps1';build_auto.build(self.zip,p);raw=p.read_bytes();self.assertTrue(raw.startswith(b'\xef\xbb\xbf'))
        text=raw.decode('utf-8-sig');payload=text.split("$EmbeddedSource=@'\n",1)[1].split("\n'@",1)[0]
        self.assertEqual(base64.b64decode(payload),self.zip.read_bytes())
        self.assertIn("$ExpectedSha256='"+c.sha(self.zip.read_bytes())+"'",text)
    def test_install_preserves_prior_version_and_rejects_modified_new_source(self):
        repo=self.root/'install_repo';repo.mkdir();old=repo/'llm_experiments/v085/results_llm/sentinel.txt';c.write(old,b'preserve')
        target=launch.install(self.source,repo);self.assertEqual(old.read_bytes(),b'preserve')
        self.assertEqual(launch.install(self.source,repo),target)
        (target/'README.md').write_bytes(b'modified')
        with self.assertRaises(launch.LaunchError):launch.install(self.source,repo)
        self.assertEqual(old.read_bytes(),b'preserve')
    @unittest.skipUnless(BASELINE.is_file(),'v085 evidence required')
    def test_checkonly_never_routes_to_execute(self):
        repo=self.root/'check_repo';repo.mkdir();calls=[]
        def record(args,cwd,log,env):calls.append([str(x) for x in args])
        with patch.object(launch,'invoke',record),contextlib.redirect_stdout(io.StringIO()):
            result=launch.workflow(self.source,repo,BASELINE,True,True,'v086_check_contract',no_open=True)
        self.assertTrue(result['check_only']);self.assertFalse(any('execute' in x for x in calls))
        self.assertTrue(any('prepare' in x for x in calls));self.assertTrue(any('selftest086.py' in x for x in calls))
        self.assertFalse((repo/'llm_experiments/v086/results_llm/frozen_batch.started.json').exists())
    @unittest.skipUnless(BASELINE.is_file(),'v085 evidence required')
    def test_guard_blocks_new_runname_before_install_or_call(self):
        repo=self.root/'guard_repo';repo.mkdir();guard=repo/'llm_experiments/v086/results_llm/frozen_batch.started.json';c.write(guard,b'{}')
        with patch.object(launch,'invoke',side_effect=AssertionError('no child process')):
            with self.assertRaises(launch.LaunchError):launch.workflow(self.source,repo,BASELINE,run_name='v086_other')
        self.assertFalse((repo/'llm_experiments/v086/probe').exists());self.assertEqual(guard.read_bytes(),b'{}')
