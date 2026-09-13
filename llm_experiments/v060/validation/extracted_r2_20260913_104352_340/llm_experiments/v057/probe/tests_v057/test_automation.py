import contextlib,hashlib,io,json,shutil,sys,tempfile,unittest
from pathlib import Path
from .fixtures import shared
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from auto_run_v057 import automate,StepError
from preflight_v057 import preflight

class WholeAutomation(unittest.TestCase):
    def test_actual_child_process_pipeline_on_synthetic_server(self):
        b=shared();b['state'].mode='perfect';before=len(b['state'].requests)
        with tempfile.TemporaryDirectory(prefix='v057 automated space ') as td:
            root=Path(td);repo=root/'repo';repo.mkdir();stage=root/'stage'
            shutil.copytree(Path(__file__).resolve().parents[1],stage,ignore=shutil.ignore_patterns('__pycache__','PACKAGE_MANIFEST.json'))
            hashes={p.relative_to(stage).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in stage.rglob('*') if p.is_file()}
            (stage/'PACKAGE_MANIFEST.json').write_text(json.dumps({'contract':'v057-source-package-r1','file_hashes':hashes}))
            with contextlib.redirect_stdout(io.StringIO()):result=automate(stage,repo,b['bundle'],open_result=False)
            self.assertEqual(len(b['state'].requests)-before,480);self.assertTrue(result['completed']);self.assertTrue(Path(result['bundle']).is_file());self.assertTrue(Path(result['independent']).is_file())
            self.assertEqual(json.loads(Path(result['independent']).read_text())['differences'],[])
    def test_preflight_checks_candidate_before_any_inference(self):
        b=shared();state=b['state'];state.mode='missing_candidate';before=len(state.requests)
        try:
            with tempfile.TemporaryDirectory() as td:
                out=Path(td)/'preflight.json'
                with self.assertRaises(ValueError):preflight(b['root']/'v57.plan',out)
                r=json.loads(out.read_text());self.assertEqual(r['failure']['model_key'],'candidate');self.assertEqual(r['inference_calls'],0);self.assertEqual(len(state.requests),before)
        finally:state.mode='perfect'
