import io,json,sys,tempfile,unittest,zipfile
from pathlib import Path
from .fixtures import shared,executed
from selection_probe_v057.evidence import bundle_run
from selection_probe_v057.contracts import sha,wire
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from independent_verify_v057 import verify

class Independent(unittest.TestCase):
    def check(self,mode):
        with executed(mode) as (root,p,r,report,state):
            out=root/'evidence.zip';bundle_run(p,r,out);ind=verify(out);self.assertFalse(ind['differences']);self.assertEqual(ind['observed_calls'],report['inference_calls']);return ind
    def test_perfect(self):
        b=shared()
        with tempfile.TemporaryDirectory() as td:
            z=Path(td)/'e.zip';bundle_run(b['root']/'v57.plan',b['root']/'v57.run',z);self.assertEqual(verify(z)['observed_calls'],480)
    def test_choice_only(self):self.check('choice_only')
    def test_graph_only(self):self.check('graph_only')
    def test_first_branch(self):self.check('first_branch')
    def test_invalid_rule(self):self.check('invalid_rule')
    def test_syntax_unmeasured(self):self.check('syntax_error')
    def test_partial_first_http(self):self.assertEqual(self.check('http_error')['observed_calls'],1)
    def test_partial_candidate_http(self):self.assertEqual(self.check('candidate_http')['observed_calls'],25)
    def test_rehashed_stored_score_tamper_rejected(self):
        b=shared()
        with tempfile.TemporaryDirectory() as td:
            z=Path(td)/'e.zip';bundle_run(b['root']/'v57.plan',b['root']/'v57.run',z)
            with zipfile.ZipFile(z) as zz:d={n:zz.read(n) for n in zz.namelist()}
            report=json.loads(d['run/summary.json']);report['models']['reference']['modes']['choice']['selective_success']=0;d['run/summary.json']=wire(report)
            m=json.loads(d['BUNDLE_MANIFEST.json']);m['file_hashes']['run/summary.json']=sha(d['run/summary.json']);d['BUNDLE_MANIFEST.json']=wire(m)
            bad=Path(td)/'bad.zip'
            with zipfile.ZipFile(bad,'w',compression=zipfile.ZIP_DEFLATED) as zz:
                for n,raw in d.items():zz.writestr(n,raw)
            with self.assertRaises(ValueError):verify(bad)
