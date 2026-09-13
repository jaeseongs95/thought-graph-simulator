import contextlib,io,json,sys,tempfile,unittest,zipfile
from pathlib import Path
from layout_probe_v056.evidence import bundle_run
from .fixtures import shared,executed
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from independent_verify_v056 import verify,bounds
from independent_graph_forensic import canonical,sha

class Independent(unittest.TestCase):
    def test_perfect_full_zip(self):
        b=shared()
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'perfect.zip';bundle_run(b['root']/'v56.plan',b['root']/'v56.run',out);r=verify(out)
            self.assertEqual(r['observed_calls'],480);self.assertEqual([v['selective_pairs'] for v in r['results'].values()],[40]*4)
    def test_first_branch_zero(self):
        with executed('first_branch') as (root,p,run,report,state):
            out=root/'evidence.zip';bundle_run(p,run,out);r=verify(out);self.assertEqual([v['selective_pairs'] for v in r['results'].values()],[0]*4)
    def test_merged_only(self):
        with executed('merged_only') as (root,p,run,report,state):
            out=root/'evidence.zip';bundle_run(p,run,out);r=verify(out);self.assertEqual([v['selective_pairs'] for v in r['results'].values()],[0,0,40,40])
    def test_partial_first_call(self):
        with executed('http_error') as (root,p,run,report,state):
            out=root/'evidence.zip';bundle_run(p,run,out);r=verify(out);self.assertEqual(r['observed_calls'],1);self.assertFalse(r['complete'])
    def test_partial_second_model(self):
        with executed('candidate_http') as (root,p,run,report,state):
            out=root/'evidence.zip';bundle_run(p,run,out);r=verify(out);self.assertEqual(r['observed_calls'],25)
    def test_truncated_unmeasured(self):
        with executed('truncated') as (root,p,run,report,state):
            out=root/'evidence.zip';bundle_run(p,run,out);r=verify(out);self.assertTrue(all(v['valid']==0 for v in r['results'].values()))
    def test_resealed_report_semantics_rejected(self):
        b=shared()
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'base.zip';bundle_run(b['root']/'v56.plan',b['root']/'v56.run',out)
            with zipfile.ZipFile(out) as z:files={n:z.read(n) for n in z.namelist()}
            summary=json.loads(files['run/summary.json']);summary['layout_results']['reference/K01/original']['merged_only']=10;files['run/summary.json']=canonical(summary)
            manifest=json.loads(files['BUNDLE_MANIFEST.json']);manifest['file_hashes']['run/summary.json']=sha(files['run/summary.json']);files['BUNDLE_MANIFEST.json']=canonical(manifest)
            changed=Path(td)/'changed.zip'
            with zipfile.ZipFile(changed,'w') as z:
                for n,v in files.items():z.writestr(n,v)
            with self.assertRaises(ValueError):verify(changed)
    def test_depth_bounds_not_imported(self):
        self.assertEqual(bounds({'facts':['X'],'rules':[{'id':'a','premises':['X'],'conclusion':'Y'},{'id':'b','premises':['Y'],'conclusion':'Z'},{'id':'c','premises':['X'],'conclusion':'Z'}],'goal':'Z'}),(1,2))
