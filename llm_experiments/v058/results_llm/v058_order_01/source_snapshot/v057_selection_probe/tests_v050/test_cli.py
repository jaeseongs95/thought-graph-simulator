from __future__ import annotations
import json,sys,tempfile,unittest
from pathlib import Path
from test_support.subprocess_text import run_text_process
from .fixtures import shared,copied
ROOT=Path(__file__).resolve().parents[1]

def command(*args):return run_text_process([sys.executable,'-m','criterion_probe_v050',*map(str,args)],cwd=ROOT,timeout=40)

class CLI(unittest.TestCase):
    def test_help(self):self.assertEqual(command('--help').returncode,0)
    def test_show_plan(self):
        r=command('show','--plan',shared()['root']/'v50.plan');self.assertEqual(r.returncode,0,r.stderr);self.assertIn('560',r.stdout)
    def test_prepare_with_korean_filename(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'한글 계획.json';r=command('prepare','--baseline-bundle',shared()['bundle'],'--out',out)
            self.assertEqual(r.returncode,0,r.stderr);self.assertTrue(out.is_file())
    def test_prepare_missing_bundle(self):
        with tempfile.TemporaryDirectory() as td:
            r=command('prepare','--baseline-bundle',Path(td)/'missing.zip','--out',Path(td)/'out.json');self.assertEqual(r.returncode,2)
    def test_audit_cli(self):
        with copied() as (_,p,run,_):
            r=command('audit','--plan',p,'--run',run);self.assertEqual(r.returncode,0,r.stderr)
    def test_bundle_cli(self):
        with copied() as (root,p,run,_):
            r=command('bundle','--plan',p,'--run',run,'--out',root/'e.zip');self.assertEqual(r.returncode,0,r.stderr);self.assertTrue((root/'e.zip').exists())
    def test_snapshot_cli_rejected(self):
        with copied() as (_,p,run,_):self.assertEqual(command('audit','--plan',run/'plan.snapshot.json','--run',run).returncode,2)
    def test_run_does_not_overwrite_existing(self):
        with copied() as (_,p,run,_):self.assertEqual(command('run','--plan',p,'--out',run).returncode,2)
