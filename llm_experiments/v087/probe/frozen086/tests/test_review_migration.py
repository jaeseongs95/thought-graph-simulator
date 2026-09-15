"""r2 설치에서 알려진 미시작 r1만 보존 후 교체하고 시작·변경 흔적은 거부한다."""
from pathlib import Path
import tempfile,unittest,sys,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core086 as c,launch

class ReviewMigration(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='v086_r2_migration_')
        self.root=Path(self.tmp.name);self.repo=self.root/'repo';self.repo.mkdir()
        self.source=self.root/'release/probe';self.source.mkdir(parents=True)
        self.version=self.repo/'llm_experiments/v086';self.target=self.version/'probe'
        self.target.mkdir(parents=True)
        (self.target/'code.py').write_bytes(b'# original r1\n')
        old={'contract':'v086-source-release-r1','file_hashes':{launch.PREFIX+'code.py':c.sha(b'# original r1\n')}}
        self.oldraw=c.wire(old)
        (self.version/'RELEASE_MANIFEST.json').write_bytes(self.oldraw)
        (self.source/'code.py').write_bytes(b'# revised r2\n')
        anchor=self.source/'data/v086_r1_release_manifest.json';anchor.parent.mkdir();anchor.write_bytes(self.oldraw)
        new={'contract':'v086-source-release-r1','revision':'r2-review-fixes','file_hashes':{
            launch.PREFIX+'code.py':c.sha(b'# revised r2\n'),launch.PREFIX+'data/v086_r1_release_manifest.json':c.sha(self.oldraw)}}
        (self.source.parent/'RELEASE_MANIFEST.json').write_bytes(c.wire(new))
    def tearDown(self):self.tmp.cleanup()
    def test_exact_unstarted_r1_is_backed_up_then_updated(self):
        got=launch.install(self.source,self.repo);self.assertEqual(got,self.target)
        self.assertEqual((got/'code.py').read_bytes(),b'# revised r2\n')
        self.assertEqual((self.version/'probe.pre_r2_review/code.py').read_bytes(),b'# original r1\n')
        self.assertEqual((self.version/'RELEASE_MANIFEST.pre_r2_review.json').read_bytes(),self.oldraw)
        self.assertEqual(launch.install(self.source,self.repo),got)
    def test_modified_r1_is_not_replaced(self):
        (self.target/'code.py').write_bytes(b'# user edited\n')
        with self.assertRaises(launch.LaunchError):launch.install(self.source,self.repo)
        self.assertEqual((self.target/'code.py').read_bytes(),b'# user edited\n')
        self.assertFalse((self.version/'probe.pre_r2_review').exists())
    def _block(self,relative):
        marker=self.version/relative;marker.parent.mkdir(parents=True,exist_ok=True);marker.write_bytes(b'preserve')
        with self.assertRaises(launch.LaunchError):launch.install(self.source,self.repo)
        self.assertEqual(marker.read_bytes(),b'preserve')
        self.assertEqual((self.target/'code.py').read_bytes(),b'# original r1\n')
        self.assertFalse((self.version/'probe.pre_r2_review').exists())
    def test_started_guard_blocks_source_migration(self):self._block('results_llm/frozen_batch.started.json')
    def test_plan_started_marker_blocks_even_without_global_guard(self):self._block('experiments/v086_run.plan.json.started')
    def test_existing_run_plan_blocks_even_without_global_guard(self):self._block('results_llm/v086_run/plan.json')
    def test_old_backup_is_never_overwritten(self):
        backup=self.version/'probe.pre_r2_review';backup.mkdir();(backup/'sentinel').write_bytes(b'preserve')
        with self.assertRaises(launch.LaunchError):launch.install(self.source,self.repo)
        self.assertEqual((backup/'sentinel').read_bytes(),b'preserve')
        self.assertEqual((self.target/'code.py').read_bytes(),b'# original r1\n')

if __name__=='__main__':unittest.main()
