"""초기 구현에서 실제 재현한 감사/참조 우회에 대한 회귀 시험."""
from __future__ import annotations
import os
import shutil
import unittest
from unittest.mock import patch
from paired_probe_v048.audit import audit_run
from paired_probe_v048.contracts import ContractError, read_json
from paired_probe_v048.plan import prepare
from paired_probe_v047.audit import audit_run as old_audit
from tests_v048.fixtures import experiment


class AdversarialTests(unittest.TestCase):
    def test_reaudit_failure_replaces_previous_pass_reports(self):
        with experiment() as (_,_,path,_,out,_):
            target=next((out/"calls").rglob("response.raw.json"));target.write_bytes(b"{}")
            with self.assertRaises(ContractError): audit_run(path,out,write_report=True)
            self.assertFalse(read_json(out/"audit.json")["data_integrity"])
            self.assertFalse(read_json(out/"summary.json")["comparative_analysis_ready"])
            self.assertIn("감사 실패",(out/"summary.ko.md").read_text(encoding="utf-8"))
    def test_internal_plan_alias_not_external_anchor(self):
        with experiment() as (root,_,_,_,_,_):
            oldrun=root/"v047.run";alias=oldrun/"external_alias.json"
            shutil.copyfile(oldrun/"plan.snapshot.json",alias)
            with self.assertRaises(ContractError): prepare(oldrun,root/"alias_new.json",baseline_plan=alias)
    def test_hardlinked_snapshot_not_external_anchor(self):
        with experiment() as (root,_,_,_,_,_):
            oldrun=root/"v047.run";alias=root/"hardlink_alias.json"
            os.link(oldrun/"plan.snapshot.json",alias)
            with self.assertRaises(ContractError): prepare(oldrun,root/"hard_new.json",baseline_plan=alias)
    def test_v048_audit_cannot_use_own_snapshot_as_external(self):
        with experiment() as (_,_,_,_,out,_):
            with self.assertRaises(ContractError): audit_run(out/"plan.snapshot.json",out)
    def test_reference_changed_during_audit_is_rejected(self):
        with experiment() as (root,_,_,_,_,_):
            oldrun=root/"v047.run"
            target=next((oldrun/"calls").rglob("response.raw.json"))
            def change_after_audit(*args,**kwargs):
                report=old_audit(*args,**kwargs)
                target.write_bytes(target.read_bytes()+b" ")
                return report
            with patch("paired_probe_v047.audit.audit_run",side_effect=change_after_audit):
                with self.assertRaises(ContractError): prepare(oldrun,root/"race.json",baseline_plan=root/"v047.external.plan.json")
