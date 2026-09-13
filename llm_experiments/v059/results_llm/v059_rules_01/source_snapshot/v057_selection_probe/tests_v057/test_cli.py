import contextlib,io,tempfile,unittest
from pathlib import Path
from selection_probe_v057.__main__ import main
class Cli(unittest.TestCase):
    def test_missing_plan_nonzero(self):
        with contextlib.redirect_stderr(io.StringIO()):self.assertEqual(main(['show','--plan','missing.json']),2)
    def test_empty_test_combination_rejected(self):
        with contextlib.redirect_stderr(io.StringIO()):self.assertEqual(main(['selftest','--all','--quick']),2)
    def test_missing_baseline_explicit(self):
        with tempfile.TemporaryDirectory() as td,contextlib.redirect_stderr(io.StringIO()):self.assertEqual(main(['prepare','--baseline-bundle',str(Path(td)/'absent'),'--out',str(Path(td)/'p')]),2)
