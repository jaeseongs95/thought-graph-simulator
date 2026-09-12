import tempfile
import unittest
import sys
from pathlib import Path
from test_support.subprocess_text import run_text_process
from .fixtures import shared

ROOT=Path(__file__).resolve().parent.parent

def command(*args):return run_text_process([sys.executable,'-m','paired_probe_v049',*map(str,args)],cwd=ROOT,timeout=45)

class CliTests(unittest.TestCase):
    def test_help(self):
        r=command('--help');self.assertEqual(r.returncode,0);self.assertIn('prepare',r.stdout)
    def test_prepare_requires_bundle(self):
        r=command('prepare','--out','unused');self.assertEqual(r.returncode,2)
    def test_prepare_show_run_audit_bundle_real_subprocess(self):
        f=shared();state=f['state'];state.mode='original_false';state.requests.clear()
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p=root/'external.plan.json';out=root/'run';z=root/'e.zip'
            r=command('prepare','--baseline-bundle',f['bundle'],'--out',p);self.assertEqual(r.returncode,0,r.stderr)
            r=command('show','--plan',p);self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(len(state.requests),0)
            r=command('run','--plan',p,'--out',out);self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(len(state.requests),480)
            r=command('audit','--plan',p,'--run',out);self.assertEqual(r.returncode,0,r.stderr)
            r=command('bundle','--plan',p,'--run',out,'--out',z);self.assertEqual(r.returncode,0,r.stderr);self.assertTrue(z.is_file())
        state.mode='perfect'
    def test_missing_file_gives_explicit_error(self):
        r=command('prepare','--baseline-bundle','missing.zip','--out','unused');self.assertEqual(r.returncode,2);self.assertIn('중단',r.stderr)
