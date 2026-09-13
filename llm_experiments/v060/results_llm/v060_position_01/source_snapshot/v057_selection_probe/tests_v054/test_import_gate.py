"""낮은 실험 점수는 기준선 수입을 막지 않으며 조작된 집계는 거부한다."""
import io, json, tempfile, unittest, zipfile
from pathlib import Path
from order_probe_v054.contracts import ContractError,sha,wire
from order_probe_v054.plan import prepare
from depth_probe_v053.evidence import bundle_run
from tests_v053.fixtures import executed as previous_executed
from .fixtures import shared

class ImportGate(unittest.TestCase):
    def test_zero_control_baseline_accepted(self):
        with previous_executed('ignore_roles') as (root,p,run,r,state):
            self.assertEqual(sum(x['direction_selective_success'] for x in r['core_results'].values()),0)
            z=root/'failed_model_complete.zip';bundle_run(p,run,z)
            plan=prepare(z,root/'next.plan');self.assertEqual(plan['max_calls'],120)
    def test_resealed_false_summary_rejected(self):
        b=shared()
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            with zipfile.ZipFile(b['bundle']) as z:data={n:z.read(n) for n in z.namelist()}
            summary=json.loads(data['run/summary.json']);summary['core_results']['K01/original']['direction_selective_success']=999
            data['run/summary.json']=wire(summary);m=json.loads(data['BUNDLE_MANIFEST.json']);m['file_hashes']['run/summary.json']=sha(data['run/summary.json']);data['BUNDLE_MANIFEST.json']=wire(m)
            output=root/'altered.zip'
            with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
                for n,raw in data.items():z.writestr(n,raw)
            with self.assertRaisesRegex(ContractError,'저장 summary'):prepare(output,root/'new.plan')
    def test_runtime_evidence_is_not_replaced_by_source_snapshot_execution(self):
        import ast
        source=Path(__file__).resolve().parents[1]/'order_probe_v054/evidence.py'
        code=source.read_text();self.assertNotIn('exec(',code);self.assertNotIn('sys.path',code)
        self.assertIn('from depth_probe_v053.audit import audit_run',code)
