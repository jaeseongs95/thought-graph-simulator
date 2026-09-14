import json,tempfile,unittest
from pathlib import Path
from fixtures import ROOT
import common,inspect_state

class StateInspection(unittest.TestCase):
    def setUp(self):
        self.td=tempfile.TemporaryDirectory();self.addCleanup(self.td.cleanup);self.root=Path(self.td.name)/'v078'
    def guard(self,name='v078_case'):
        common.save(self.root/'results_llm/frozen_batch.started.json',{'run_name':name,'plan_sha256':'fixture','automatic_retry':False})
        return self.root/'results_llm'/name
    def snapshot(self):return {p.relative_to(self.root).as_posix():p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
    def test_no_guard_does_not_create_folders(self):
        r=inspect_state.inspect(self.root);self.assertEqual(r['classification'],'not_started_by_this_launcher');self.assertFalse(self.root.exists())
    def test_guard_is_not_inference_evidence(self):
        self.guard();before=self.snapshot();r=inspect_state.inspect(self.root)
        self.assertEqual(r['classification'],'guard_before_observed_dispatch');self.assertEqual(r['dispatch_markers'],0);self.assertEqual(before,self.snapshot())
    def test_stopped_metadata_is_zero_dispatch(self):
        run=self.guard();common.save(run/'status.json',{'state':'stopped','reason':'metadata_identity_error'})
        r=inspect_state.inspect(self.root);self.assertEqual(r['classification'],'stopped_before_inference_dispatch')
    def test_pending_dispatch_not_counted_as_observed_response(self):
        run=self.guard();common.save(run/'wire/s1/dispatch.started.json',{'id':'s1'})
        before=self.snapshot();r=inspect_state.inspect(self.root)
        self.assertEqual((r['dispatch_markers'],r['preserved_responses']),(1,0));self.assertEqual(r['classification'],'interrupted_status_missing');self.assertEqual(before,self.snapshot())
    def test_complete_claim_is_not_independent_verification(self):
        run=self.guard();common.save(run/'status.json',{'state':'complete'})
        r=inspect_state.inspect(self.root);self.assertEqual(r['classification'],'complete_recorded');self.assertIsNone(r['independent_json'])
    def test_path_traversal_in_guard_rejected(self):
        self.guard('../old_result')
        with self.assertRaises(ValueError):inspect_state.inspect(self.root)

if __name__=='__main__':unittest.main()
