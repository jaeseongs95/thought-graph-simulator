import json,sys,unittest
from pathlib import Path
from test_support.subprocess_text import run_text_process
from .fixtures import shared,copied
ROOT=Path(__file__).resolve().parent.parent
class CLI(unittest.TestCase):
    def test_actual_subprocess_prepare_show_audit_bundle(self):
        with copied() as (root,oldplan,run,f):
            plan=root/'별도계획.json';out=root/'결과.zip'
            for args in [('prepare','--baseline-bundle',str(f['bundle']),'--out',str(plan)),
                         ('show','--plan',str(plan)),('audit','--plan',str(oldplan),'--run',str(run)),
                         ('bundle','--plan',str(oldplan),'--run',str(run),'--out',str(out))]:
                result=run_text_process([sys.executable,'-m','adm_diagnostic_v052',*args],cwd=ROOT,timeout=180)
                self.assertEqual(result.returncode,0,result.stderr)
            self.assertTrue(out.is_file())
    def test_help_exit_zero(self):
        r=run_text_process([sys.executable,'-m','adm_diagnostic_v052','--help'],cwd=ROOT,timeout=30);self.assertEqual(r.returncode,0)
