"""Independent semantic checks use hand-constructed counterexamples."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import warnings
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("v057_raw_analysis", ROOT / "tools" / "analyze_v057.py")
analysis = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(analysis)

PROBLEM = {"id": "K01", "facts": ["Ca"], "rules": [
    {"id": "k10", "premises": ["Ca"], "conclusion": "Cb"},
    {"id": "k17", "premises": ["Cb"], "conclusion": "Cc"},
    {"id": "k03", "premises": ["Ca"], "conclusion": "Cc"}], "goal": "Cc"}
SHALLOW = {"nodes": [
    {"id": "a", "atom": "Ca", "rule": None, "parents": []},
    {"id": "c", "atom": "Cc", "rule": "k03", "parents": ["a"]}], "final_node_id": "c"}
DEEP = {"nodes": [
    {"id": "a", "atom": "Ca", "rule": None, "parents": []},
    {"id": "b", "atom": "Cb", "rule": "k10", "parents": ["a"]},
    {"id": "c", "atom": "Cc", "rule": "k17", "parents": ["b"]}], "final_node_id": "c"}


class AnalysisTests(unittest.TestCase):
    def test_depth_is_support_depth(self):
        self.assertEqual(analysis.depth_options(PROBLEM), ({1, 2}, {"k17": {2}, "k03": {1}}))
        for payload, expected in [(SHALLOW, 1), (DEEP, 2)]:
            result = analysis.graph_diagnostics(PROBLEM, payload)
            self.assertEqual(result["errors"], [])
            self.assertEqual(result["actual_depth"], expected)

    def test_dangling_path_cannot_be_silently_pruned(self):
        payload = deepcopy(SHALLOW)
        payload["nodes"].append({"id": "unused", "atom": "Cb", "rule": "k10", "parents": ["a"]})
        result = analysis.graph_diagnostics(PROBLEM, payload)
        self.assertIn("extraneous_nodes", result["errors"])
        self.assertIsNone(result["actual_depth"])

    def test_final_rule_does_not_substitute_for_support(self):
        payload = deepcopy(DEEP)
        payload["nodes"][-1]["parents"] = ["a"]
        result = analysis.graph_diagnostics(PROBLEM, payload)
        self.assertEqual(result["final_rule_id"], "k17")
        self.assertIn("premise_mismatch", result["errors"])
        self.assertIsNone(result["actual_depth"])

    def test_parent_identity_and_order(self):
        for parents, expected in [(["Ca"], "missing_or_forward_parent"), (["a", "a"], "duplicate_parent"), (["c"], "missing_or_forward_parent")]:
            payload = deepcopy(SHALLOW)
            payload["nodes"][-1]["parents"] = parents
            self.assertIn(expected, analysis.graph_diagnostics(PROBLEM, payload)["errors"])
        payload = deepcopy(SHALLOW)
        payload["nodes"].reverse()
        self.assertIn("missing_or_forward_parent", analysis.graph_diagnostics(PROBLEM, payload)["errors"])

    def test_missing_final_and_unsupported_fact(self):
        payload = deepcopy(SHALLOW)
        payload["final_node_id"] = "Cc"
        self.assertIn("final_missing", analysis.graph_diagnostics(PROBLEM, payload)["errors"])
        payload = {"nodes": [{"id": "c", "atom": "Cc", "rule": None, "parents": []}], "final_node_id": "c"}
        self.assertIn("unsupported_fact", analysis.graph_diagnostics(PROBLEM, payload)["errors"])

    def test_duplicate_ids_and_unknown_rules(self):
        payload = deepcopy(DEEP)
        payload["nodes"][1]["id"] = "a"
        self.assertIn("duplicate_node_id", analysis.graph_diagnostics(PROBLEM, payload)["errors"])
        payload = deepcopy(DEEP)
        payload["nodes"][-1]["rule"] = "k16"
        self.assertIn("unknown_rule", analysis.graph_diagnostics(PROBLEM, payload)["errors"])

    def test_strict_json_input(self):
        for data in ['{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', '{"x":1e999}']:
            with self.assertRaises(ValueError):
                analysis.parse(data)

    def test_duplicate_zip_member_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "duplicate.zip"
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                with zipfile.ZipFile(path, "w") as archive:
                    archive.writestr("external_plan/v057.plan.json", "{}")
                    archive.writestr("external_plan/v057.plan.json", "{}")
            with self.assertRaisesRegex(ValueError, "duplicate archive"):
                analysis.analyze(path)

    def test_missing_response_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "missing.zip"
            plan = {"slots": [{"id": "example"}], "actions": [{"kind": "call", "id": "example", "index": 0}]}
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("external_plan/v057.plan.json", json.dumps(plan))
                archive.writestr("run/calls/example/request.wire.json", "{}")
            with self.assertRaisesRegex(ValueError, "missing or unexpected"):
                analysis.analyze(path)


if __name__ == "__main__":
    unittest.main()
