"""v0.3 회귀: 사용자가 실행한 14응답 재판정 + 게이트/보고/프롬프트 계약.

실제 Ollama 연결이나 모델 생성은 하지 않는다. run()의 API 경로는 Mock으로만 시험한다.
"""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

from local_llm import calibration
from local_llm.client import Reply
from local_llm.common import PACKAGE, REPO, ContractError, load_core, read_json, wire_json, write_json
from local_llm.design import build_plan, reference_depths
from local_llm.gate import validate_gate
from local_llm.prompts_v3 import messages, calibration_messages
from local_llm.report import build_summary, read_records
from local_llm.runner import assess_response, request_body, run


class V03Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core, cls.info = load_core()
        cls.problems = read_json(REPO / "examples/problems.json")
        cls.examples = read_json(PACKAGE / "tests/fixtures/v02_observations.json")["examples"]
        cls.config = copy.deepcopy(cls.examples[0]["config"])
        cls.config["prompt_profile"] = "legacy-v2"

    def assess(self, item):
        return assess_response(self.core, item["problem"], item["case"], reference_depths(item["problem"]),
                               item["body"], item["response"])[0]

    def gate_fixture(self, dest):
        with zipfile.ZipFile(PACKAGE / "tests/fixtures/v02_smoke_gate.zip") as archive:
            for info in archive.infolist():
                self.assertTrue((dest / info.filename).resolve().is_relative_to(dest.resolve()))
            archive.extractall(dest)
        return dest

    def next_plan(self):
        return build_plan(self.core, self.problems, "pilot", 1, 1729)

    def test_fourteen_original_semantic_verdicts_unchanged(self):
        for item in self.examples:
            with self.subTest(case=item["case"]["role_id"]):
                result = self.assess(item)
                self.assertEqual(result["status"], item["expected_status"])
                self.assertEqual(result["audit"]["valid_completion"], item["expected_audit"]["valid_completion"])
                self.assertEqual(result["audit"].get("task_checks"), item["expected_audit"].get("task_checks"))

    def test_fourteen_legacy_request_bytes_identical(self):
        for item in self.examples:
            with self.subTest(case=item["case"]["role_id"]):
                generated = request_body(self.config, item["case"], item["problem"])
                self.assertEqual(wire_json(generated), wire_json(item["body"]))

    def test_inputs_unchanged_after_assessment(self):
        before = copy.deepcopy(self.examples)
        for item in self.examples:
            self.assess(item)
        self.assertEqual(before, self.examples)

    def test_selected_depths_correct_but_whole_proofs_still_fail(self):
        values = [item for item in self.examples if item["case"].get("task") == "proof"]
        for item, target, extras in zip(values, (1, 2), (["n2", "n3"], ["n1"])):
            result = self.assess(item)
            self.assertEqual(result["status"], "invalid_task")
            selection = result["audit"]["details"]["selection_diagnostic"]
            self.assertEqual(selection["selected_component_depth"], target)
            self.assertEqual(selection["unrelated_node_ids"], extras)
            self.assertTrue(selection["selected_component_depth_matches_target"])
            self.assertFalse(result["audit"]["valid_completion"])

    def test_false_model_boolean_is_not_failed_check_boolean(self):
        item = next(x for x in self.examples if x["case"]["role_id"] == "criterion_non_goal_fact")
        audit = self.assess(item)["audit"]
        field = next(x for x in audit["task_comparisons"] if x["field"] == "proof_and_goal_accepts")
        self.assertFalse(field["actual"])
        self.assertFalse(field["expected"])
        self.assertTrue(field["matches"])
        self.assertTrue(audit["task_checks"]["proof_and_goal_accepts"])

    def test_smoke_partial_axes_do_not_upgrade_strict_contrasts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = self.gate_fixture(Path(temp))
            manifest = read_json(root / "manifest.json")
            records = read_records(root, manifest)
            summary, _, contrasts = build_summary(manifest["frozen"]["plan"], records)
            self.assertEqual(summary["valid_completions"], 5)
            self.assertEqual(summary["role_adherent_cases"], 1)
            self.assertEqual(summary["passed_contrasts"], 0)
            self.assertFalse(any(pair["pass"] for pair in contrasts))
            self.assertEqual({a: b["matched"] for a, b in summary["per_axis_adherence"].items()},
                             {"A": 5, "D": 1, "M": 4})
            self.assertEqual(sum(pair["observational_contrast"] for pair in summary["descriptive_contrasts"]), 2)
            self.assertTrue(summary["execution_completed"])
            self.assertFalse(summary["performance_passed"])

    def test_actual_v02_smoke_ready_despite_five_failures(self):
        with tempfile.TemporaryDirectory() as temp:
            gate = self.gate_fixture(Path(temp))
            verdict = validate_gate(self.core, gate, self.config, self.next_plan())
            self.assertTrue(verdict["passed"])
            self.assertEqual(verdict["model_failures_retained"], 5)
            self.assertEqual(verdict["source_compatibility"], "pinned_v02_legacy_requests")
            self.assertFalse(verdict["model_called"])

    def test_strict_still_rejects_actual_smoke(self):
        with tempfile.TemporaryDirectory() as temp:
            gate = self.gate_fixture(Path(temp))
            with self.assertRaisesRegex(ContractError, "strict"):
                validate_gate(self.core, gate, self.config, self.next_plan(), "strict")

    def test_gate_does_not_trust_summary_flag(self):
        with tempfile.TemporaryDirectory() as temp:
            gate = self.gate_fixture(Path(temp))
            write_json(gate / "summary.json", {"all_assigned_passed": True, "valid_completions": 999})
            verdict = validate_gate(self.core, gate, self.config, self.next_plan())
            self.assertEqual(verdict["model_failures_retained"], 5)

    def test_changed_response_without_rehash_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            gate = self.gate_fixture(Path(temp))
            raw = next((gate / "cases").glob("*/response.raw.json"))
            raw.write_text("{}", encoding="utf-8")
            with self.assertRaises(ContractError):
                validate_gate(self.core, gate, self.config, self.next_plan())

    def test_source_snapshot_change_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            gate = self.gate_fixture(Path(temp))
            path = gate / "source_snapshot/prompts_v2.py"
            path.write_text(path.read_text() + "\n# changed\n")
            with self.assertRaises(ContractError):
                validate_gate(self.core, gate, self.config, self.next_plan())

    def test_missing_completed_case_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            gate = self.gate_fixture(Path(temp))
            next((gate / "cases").glob("*/record.json")).unlink()
            with self.assertRaisesRegex(ContractError, "완료"):
                validate_gate(self.core, gate, self.config, self.next_plan())

    def test_new_prompt_cannot_reuse_legacy_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            gate = self.gate_fixture(Path(temp))
            config = dict(self.config, prompt_profile="explicit-v3")
            with self.assertRaises(ContractError):
                validate_gate(self.core, gate, config, self.next_plan())

    def test_thinking_change_cannot_reuse_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            gate = self.gate_fixture(Path(temp))
            with self.assertRaises(ContractError):
                validate_gate(self.core, gate, dict(self.config, think=True), self.next_plan())

    def test_changed_generation_budget_cannot_reuse_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            gate = self.gate_fixture(Path(temp))
            config = copy.deepcopy(self.config)
            config["options"]["num_predict"] += 1
            with self.assertRaises(ContractError):
                validate_gate(self.core, gate, config, self.next_plan())

    def test_changed_seed_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            gate = self.gate_fixture(Path(temp))
            plan = build_plan(self.core, self.problems, "pilot", 1, 99)
            with self.assertRaises(ContractError):
                validate_gate(self.core, gate, self.config, plan)

    def test_offline_gate_never_calls_generator_or_model(self):
        with tempfile.TemporaryDirectory() as temp:
            gate = self.gate_fixture(Path(temp))
            with patch.object(self.core, "simulate", side_effect=AssertionError("generator prohibited")), \
                 patch("local_llm.runner.OllamaClient", side_effect=AssertionError("network prohibited")):
                self.assertTrue(validate_gate(self.core, gate, self.config, self.next_plan())["passed"])

    def mock_run(self, out, fail_on_model_failure=False):
        plan = build_plan(self.core, self.problems, "smoke", 1, 1729)
        lookup = {x["case"]["case_id"]: x for x in self.examples if x["run"] == "v02_smoke_01"}
        client = Mock()
        tag = {"digest": "offline-only", "details": {}}
        client.inspect.return_value = {"tag": tag, "show": {"capabilities": ["completion"], "model_info": {"general.architecture": "qwen3", "general.finetune": "Instruct", "general.version": "2507"}}, "server": {"version": "mock"}}
        client.tag.return_value = tag
        client.running_model.return_value = tag
        client.chat.side_effect = [Reply(x["response"], wire_json(x["response"]), 1.0)
                                   for case in plan["cases"] for x in [lookup[case["case_id"]]]]
        with patch("local_llm.runner.OllamaClient", return_value=client), \
             patch("local_llm.runner.environment", return_value={"nvidia_smi": None}):
            code = run(self.core, self.info, plan, self.config, out, fail_on_model_failure=fail_on_model_failure)
        return code, client

    def test_completed_failed_experiment_has_zero_exit_by_default(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "run"
            code, client = self.mock_run(out)
            self.assertEqual(code, 0)
            self.assertEqual(client.chat.call_count, 6)
            summary = read_json(out / "summary.json")
            self.assertFalse(summary["performance_passed"])
            self.assertTrue(summary["execution_completed"])

    def test_explicit_ci_failure_exit_remains_available(self):
        with tempfile.TemporaryDirectory() as temp:
            code, _ = self.mock_run(Path(temp) / "run", True)
            self.assertEqual(code, 1)

    def test_live_model_mismatch_stops_before_any_chat(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            gate = self.gate_fixture(root / "gate")
            old = read_json(gate / "manifest.json")["frozen"]
            client = Mock()
            client.inspect.return_value = {"tag": {"digest": "changed"}, "server": old["ollama_server"]}
            with patch("local_llm.runner.OllamaClient", return_value=client), \
                 patch("local_llm.runner.environment", return_value={"nvidia_smi": None}):
                with self.assertRaises(ContractError):  # 모델 메타데이터/모드/태그의 선행 검사에서도 차단 가능
                    run(self.core, self.info, self.next_plan(), self.config, root / "next", gate=gate)
            client.chat.assert_not_called()

    def test_explicit_profile_keeps_common_schema_for_all_roles(self):
        plan = build_plan(self.core, self.problems, "pilot", 1, 1729)
        config = dict(self.config, prompt_profile="explicit-v3")
        bodies = [request_body(config, c, next(p for p in self.problems if p["id"] == c["problem_id"]))
                  for c in plan["cases"]]
        self.assertTrue(all(b["format"] == bodies[0]["format"] for b in bodies))
        self.assertTrue(all(b["options"]["num_predict"] == self.config["options"]["num_predict"] for b in bodies))
        for body in bodies:
            prompt = wire_json(body["messages"])
            self.assertNotIn('"D_target"', prompt)
            self.assertNotIn('"reference_depths"', prompt)

    def test_explicit_calibration_never_includes_case_gold_label(self):
        plan = calibration.build_calibration_plan(self.core)
        ps = {p["id"]: p for p in plan["problems"]}
        for case in plan["cases"]:
            prompt = wire_json(calibration_messages(ps[case["problem_id"]], case))
            self.assertNotIn(case["role_id"], prompt)
            self.assertNotIn('"expected"', prompt)

    def test_unknown_prompt_profile_rejected(self):
        item = self.examples[-1]
        with self.assertRaises(ContractError):
            request_body(dict(self.config, prompt_profile="typo"), item["case"], item["problem"])


if __name__ == "__main__":
    unittest.main()
