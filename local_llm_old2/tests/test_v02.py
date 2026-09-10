"""v0.2 오프라인 회귀시험. 실제 Ollama·모델·네트워크를 사용하지 않는다."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from local_llm import calibration as cal
from local_llm.audit import evaluate_trace
from local_llm.client import OllamaClient, Reply
from local_llm.common import (PACKAGE, REPO, ContractError, bytes_hash, load_core, read_json,
                              write_json, write_text, wire_json)
from local_llm.design import all_roles, build_plan, reference_depths
from local_llm.diagnostics import raw_diagnostics, reanalyze
from local_llm.prompts_v2 import DEMO_PROBLEM, DEMO_INSTANCE, DEMO_SCHEMA
from local_llm.protocol import TRANSPORT_SCHEMA as OLD_SCHEMA
from local_llm.protocol_v2 import (PROTOCOL, TRANSPORT_SCHEMA, parse_payload, to_trace)
from local_llm.report import read_records, build_summary
from local_llm.runner import (assess_response, request_body, recover_case, run, save_record,
                              validate_gate)
from local_llm.selfcheck import selfcheck


def v2_payload(trace):
    nodes = []
    for node in trace["nodes"]:
        view = copy.deepcopy(trace["views"][node["id"]])
        if view["kind"] == "universal_schema":
            view["bindings"] = [{"variable": v, "atom": a} for v, a in view.pop("binding").items()]
            view["clauses"] = view.pop("assumptions")
            view["conclusion_var"] = view.pop("conclusion")
        nodes.append({"node_id": node["id"], "atom": node["atom"], "rule_id": node["rule"],
                      "parent_node_ids": copy.deepcopy(node["parents"]), "view": view})
    reviews = copy.deepcopy(trace["reviews"])
    for r in reviews:
        if r["target_kind"] == "argument":
            r["target_node_id"] = r.pop("target")
            r["evidence_node_ids"] = r.pop("evidence")
    return {"nodes": nodes, "selected_final_node_id": trace["final"], "verification_reviews": reviews}


def config():
    return {"protocol": PROTOCOL, "model": "qwen3:4b", "endpoint": "http://127.0.0.1:11434",
            "timeout_seconds": 300, "think": False,
            "options": {"temperature": 0.2, "num_ctx": 8192, "num_predict": 4096}}


def response(payload):
    return {"model": "qwen3:4b", "done": True, "done_reason": "stop",
            "message": {"role": "assistant", "content": wire_json(payload)},
            "prompt_eval_count": 100, "eval_count": 50, "eval_duration": 1_000_000_000}


class V02Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core, cls.info = load_core()
        cls.problems = read_json(REPO / "examples/problems.json")
        cls.problem = cls.problems[0]

    def fixture(self, a="instance", d="shallow", m=0):
        role = {"kind": "directed", "A": a, "D_policy": d, "M": m}
        trace = self.core.simulate(self.problem, a, d, m)
        case = {"role": role, "seed": 1729}
        return trace, case, request_body(config(), case, self.problem)

    def assess(self, payload, case, body):
        return assess_response(self.core, self.problem, case, reference_depths(self.problem), body, response(payload))

    def test_v2_roundtrip_36_role_fixtures(self):
        for p in self.problems:
            for role in all_roles()[1:]:
                with self.subTest(p=p["id"], role=role):
                    trace = self.core.simulate(p, role["A"], role["D_policy"], role["M"])
                    payload = v2_payload(trace)
                    before = copy.deepcopy(payload)
                    result = to_trace(self.core, p, parse_payload(wire_json(payload)))
                    self.assertEqual(trace, result)
                    self.assertEqual(payload, before)
                    case = {"role": role, "seed": 1729}
                    body = request_body(config(), case, p)
                    audit, _ = assess_response(self.core, p, case, reference_depths(p), body, response(payload))
                    self.assertEqual(audit["status"], "accepted")

    def test_examples_and_selfcheck_are_valid(self):
        for payload in (DEMO_INSTANCE, DEMO_SCHEMA):
            trace = to_trace(self.core, DEMO_PROBLEM, payload)
            self.assertTrue(self.core.verify(DEMO_PROBLEM, trace)["valid"])
        self.assertTrue(selfcheck(self.core)["passed"])

    def test_common_schema_does_not_force_role_answer(self):
        bodies = [request_body(config(), {"role": r, "seed": 1729}, self.problem) for r in all_roles()]
        self.assertTrue(all(b["format"] == TRANSPORT_SCHEMA for b in bodies))
        self.assertTrue(all(b["messages"][0] == bodies[0]["messages"][0] for b in bodies))
        self.assertTrue(all(b["options"] == bodies[0]["options"] for b in bodies))
        self.assertTrue(all("reference_depths" not in wire_json(b["messages"]) for b in bodies))

    def test_names_keep_nodes_before_final_even_when_sorted(self):
        keys = list(TRANSPORT_SCHEMA["properties"])
        self.assertEqual(keys, ["nodes", "selected_final_node_id", "verification_reviews"])
        self.assertEqual(keys, sorted(keys))

    def test_http_bytes_preserve_nested_schema_order(self):
        client = OllamaClient()
        holder = {}
        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, limit): return b'{"ok":true}'
        class FakeOpener:
            def open(self, req, timeout):
                holder["bytes"] = req.data
                return FakeResponse()
        client.opener = FakeOpener()
        body = {"format": {"properties": {"z": {"type": "string"}, "a": {"type": "string"}}}}
        client.request("/api/chat", body)
        self.assertEqual(holder["bytes"], wire_json(body).encode("utf-8"))
        self.assertEqual(list(json.loads(holder["bytes"])["format"]["properties"]), ["z", "a"])

    def test_goal_atom_is_not_autocorrected_to_node_id(self):
        trace, case, body = self.fixture()
        payload = v2_payload(trace)
        payload["selected_final_node_id"] = self.problem["goal"]
        result, actual = self.assess(payload, case, body)
        self.assertEqual(result["status"], "invalid_trace")
        self.assertFalse(result["raw_diagnostics"]["final_reference_exists"])
        self.assertTrue(result["raw_diagnostics"]["all_local_steps_valid"])
        self.assertEqual(actual["final"], self.problem["goal"])
        self.assertIsNone(result["audit"]["representation_valid"])
        self.assertIsNone(result["audit"]["review_valid"])

    def test_atom_parent_is_not_autocorrected(self):
        trace, case, body = self.fixture()
        payload = v2_payload(trace)
        payload["nodes"][-1]["parent_node_ids"] = [self.problem["facts"][0]]
        result, _ = self.assess(payload, case, body)
        self.assertEqual(result["status"], "invalid_trace")
        self.assertTrue(result["raw_diagnostics"]["missing_parent_node_ids"])

    def test_unused_alternative_is_not_pruned(self):
        trace, case, body = self.fixture()
        payload = v2_payload(trace)
        payload["nodes"].append({"node_id": "extra", "atom": self.problem["facts"][0],
                                 "rule_id": None, "parent_node_ids": [],
                                 "view": {"kind": "instance", "atom": self.problem["facts"][0]}})
        result, actual = self.assess(payload, case, body)
        self.assertEqual(result["status"], "invalid_trace")
        self.assertIn("extra", result["raw_diagnostics"]["unrelated_node_ids"])
        self.assertEqual(len(actual["nodes"]), len(payload["nodes"]))

    def test_empty_binding_list_rejected_but_graph_diagnosed(self):
        trace, case, body = self.fixture("schema")
        payload = v2_payload(trace)
        payload["nodes"][-1]["view"]["bindings"] = []
        result, actual = self.assess(payload, case, body)
        self.assertEqual(result["status"], "protocol_error")
        self.assertIsNone(actual)
        self.assertTrue(result["raw_diagnostics"]["all_local_steps_valid"])
        self.assertTrue(result["raw_diagnostics"]["empty_binding_node_ids"])

    def test_duplicate_binding_cannot_silently_overwrite(self):
        trace, _, _ = self.fixture("schema")
        for field in ("variable", "atom"):
            payload = v2_payload(trace)
            pairs = payload["nodes"][-1]["view"]["bindings"]
            pairs[1][field] = pairs[0][field]
            with self.subTest(field=field), self.assertRaises(ContractError):
                parse_payload(wire_json(payload))

    def test_invalid_schema_content_is_not_repaired(self):
        trace, case, body = self.fixture("schema")
        payload = v2_payload(trace)
        payload["nodes"][-1]["view"]["clauses"].pop()
        result, _ = self.assess(payload, case, body)
        self.assertEqual(result["status"], "invalid_trace")
        self.assertTrue(result["audit"]["proof_valid"])
        self.assertFalse(result["audit"]["representation_valid"])

    def test_m2_inverted_criterion_is_rejected(self):
        trace, case, body = self.fixture(m=2)
        payload = v2_payload(trace)
        payload["verification_reviews"][1]["finding"]["answer_only_accepts"] = False
        result, _ = self.assess(payload, case, body)
        self.assertEqual(result["status"], "invalid_trace")
        self.assertTrue(result["audit"]["proof_valid"])
        self.assertFalse(result["audit"]["review_valid"])

    def test_unexpected_m1_under_m0_is_role_failure(self):
        trace, _, _ = self.fixture(m=1)
        _, case, body = self.fixture(m=0)
        result, _ = self.assess(v2_payload(trace), case, body)
        self.assertEqual(result["status"], "role_mismatch")

    def test_partial_or_malformed_content_diagnostics_never_repair(self):
        for value in (None, "[", "```json\n{}\n```", '{"nodes":[null]}', '{"nodes":[{}]}'):
            with self.subTest(value=value):
                diagnostic = raw_diagnostics(self.problem, value, v2=True)
                self.assertFalse(diagnostic["schema_valid"])

    def test_uploaded_failure_regressions_reproduced(self):
        fixtures = read_json(PACKAGE / "tests/fixtures/legacy_regressions.json")["examples"]
        for item in fixtures:
            with self.subTest(case=item["case"]["case_id"]):
                body = {"model": "qwen3:4b", "think": False, "format": OLD_SCHEMA}
                result, _ = assess_response(self.core, item["problem"], item["case"],
                    reference_depths(item["problem"]), body, item["response"])
                self.assertEqual(result["status"], item["expected_status"])
                self.assertEqual(result["error"], item["expected_error"])
                self.assertFalse(result["raw_diagnostics"]["final_reference_exists"])

    def calibration_payload(self, p, case):
        task = case["task"]
        if task == "proof":
            trace = self.core.simulate(p, "instance", case["depth_policy"], 0)
            value = v2_payload(trace)
            del value["verification_reviews"]
            for node in value["nodes"]: del node["view"]
            return value
        if task == "schema":
            value = v2_payload(self.core.simulate(p, "schema", "deep", 0))
            return {"node_views": [{"node_id": n["node_id"], "view": n["view"]} for n in value["nodes"]]}
        if task == "review":
            valid = case["role_id"] == "review_valid_proof"
            return {"checked_node_ids": [n["node_id"] for n in case["provided_proof"]["nodes"]],
                    "support_valid": valid, "goal_match": True, "proof_and_goal_accepts": valid}
        return {"criterion_unsupported_goal": {"answer_only_accepts": True, "proof_and_goal_accepts": False, "gap_detected": True},
                "criterion_non_goal_fact": {"answer_only_accepts": False, "proof_and_goal_accepts": False, "gap_detected": False},
                "criterion_supported_goal": {"answer_only_accepts": True, "proof_and_goal_accepts": True, "gap_detected": False}}[case["role_id"]]

    def test_all_eight_calibration_positive_fixtures_pass(self):
        plan = cal.build_calibration_plan(self.core)
        self.assertEqual(plan["assigned_calls"], 8)
        ps = {p["id"]: p for p in plan["problems"]}
        for case in plan["cases"]:
            p = ps[case["problem_id"]]
            with self.subTest(task=case["role_id"]):
                audit = cal.assess_payload(self.core, p, case, self.calibration_payload(p, case))
                self.assertTrue(audit["valid_completion"], audit)
                self.assertIsNone(audit["role_adherent"])

    def test_calibration_false_findings_rejected(self):
        plan = cal.build_calibration_plan(self.core)
        ps = {p["id"]: p for p in plan["problems"]}
        for case in plan["cases"]:
            if case["task"] not in {"review", "criterion"}: continue
            p = ps[case["problem_id"]]
            payload = self.calibration_payload(p, case)
            field = "support_valid" if case["task"] == "review" else "gap_detected"
            payload[field] = not payload[field]
            with self.subTest(task=case["role_id"]):
                self.assertFalse(cal.assess_payload(self.core, p, case, payload)["valid_completion"])

    def test_calibration_prompt_does_not_include_labels_or_expected_verdict(self):
        plan = cal.build_calibration_plan(self.core)
        ps = {p["id"]: p for p in plan["problems"]}
        for case in plan["cases"]:
            messages = wire_json(cal.messages(ps[case["problem_id"]], case))
            self.assertNotIn(case["role_id"], messages)
            self.assertNotIn('"expected"', messages)

    def test_calibration_report_not_counted_as_ADM(self):
        plan = cal.build_calibration_plan(self.core)
        records = []
        for case in plan["cases"]:
            records.append({"case": case, "status": "accepted", "audit": {"valid_completion": True, "role_adherent": None}})
        summary, _, contrasts = build_summary(plan, records)
        self.assertEqual(summary["experiment_kind"], "calibration")
        self.assertEqual(summary["directed_cases"], 0)
        self.assertEqual(summary["planned_contrasts"], 0)
        self.assertEqual(summary["valid_completions"], 8)
        self.assertTrue(summary["all_assigned_passed"])
        self.assertEqual(contrasts, [])

    def mocked_run(self, out, calibration=False):
        plan = cal.build_calibration_plan(self.core) if calibration else build_plan(self.core, self.problems, "smoke", 1, 1729)
        problems = {p["id"]: p for p in plan["problems"]}
        replies = []
        for case in plan["cases"]:
            p = problems[case["problem_id"]]
            if calibration:
                payload = self.calibration_payload(p, case)
            else:
                r = case["role"]
                trace = self.core.simulate(p, r["A"] or "instance", r["D_policy"] or "shallow", r["M"] or 0)
                payload = v2_payload(trace)
            value = response(payload)
            replies.append(Reply(value, wire_json(value), 1.0))
        client = Mock()
        tag = {"digest": "mock-offline-only", "details": {"format": "gguf"}}
        client.inspect.return_value = {"tag": tag, "show": {}, "server": {"version": "mock"}}
        client.tag.return_value = tag
        client.running_model.return_value = {"digest": "mock-offline-only"}
        client.chat.side_effect = replies
        with patch("local_llm.runner.OllamaClient", return_value=client), patch("local_llm.runner.environment", return_value={"nvidia_smi": None}):
            exit_code = run(self.core, self.info, plan, config(), out)
        return exit_code, client, plan

    def test_mocked_full_runner_and_offline_reanalysis(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "mock_smoke"
            code, client, _ = self.mocked_run(out)
            self.assertEqual(code, 0)
            self.assertEqual(client.chat.call_count, 6)
            summary = read_json(out / "summary.json")
            self.assertEqual(summary["valid_completions"], 6)
            result = reanalyze(self.core, out, Path(temp) / "reanalysis")
            self.assertEqual(result["counts"]["original_decision_reproduced"], 6)
            self.assertFalse(result["model_called"])
            for folder in (out / "cases").iterdir():
                request = read_json(folder / "request.json")
                wire = (folder / "request.wire.json").read_bytes()
                self.assertEqual(request["wire_sha256"], bytes_hash(wire))
                self.assertEqual(wire, wire_json(request["body"]).encode("utf-8"))

    def test_mocked_calibration_runner(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "mock_calibration"
            code, client, _ = self.mocked_run(out, calibration=True)
            self.assertEqual(code, 0)
            self.assertEqual(client.chat.call_count, 8)
            self.assertEqual(read_json(out / "summary.json")["valid_completions"], 8)
            self.assertIn("분리 교정", (out / "summary.md").read_text(encoding="utf-8"))

    def test_gate_replays_instead_of_trusting_summary(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "mock_smoke"
            _, _, plan = self.mocked_run(out)
            write_json(out / "summary.json", {"all_assigned_passed": False})
            next_plan = build_plan(self.core, self.problems, "pilot", 1, 1729)
            validate_gate(self.core, out, config(), next_plan)
            folder = out / "cases" / plan["cases"][0]["case_id"]
            raw = read_json(folder / "response.raw.json")
            value = json.loads(raw["message"]["content"])
            value["selected_final_node_id"] = "nonexistent"
            raw["message"]["content"] = wire_json(value)
            write_json(folder / "response.raw.json", raw)
            record = read_json(folder / "record.json")
            save_record(folder, record)  # 내부 해시를 다시 만들어도 재판정에서 실패해야 한다.
            write_json(out / "summary.json", {"all_assigned_passed": True})
            with self.assertRaises(ContractError): validate_gate(self.core, out, config(), next_plan)

    def test_empty_artifact_manifest_cannot_hide_saved_response(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "mock_smoke"
            _, _, plan = self.mocked_run(out)
            file = out / "cases" / plan["cases"][0]["case_id"] / "record.json"
            record = read_json(file)
            record["artifacts_sha256"] = {}
            write_json(file, record)
            with self.assertRaises(ContractError): read_records(out, read_json(out / "manifest.json"))

    def test_v2_request_only_resume_does_not_recall_model(self):
        plan = build_plan(self.core, self.problems, "smoke", 1, 1729)
        case, p = plan["cases"][0], plan["problems"][0]
        manifest = {"run_sha256": "fixture", "frozen": {"plan": plan, "config": config()}}
        body = request_body(config(), case, p)
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            wire = wire_json(body)
            write_json(out / "request.json", {"case_id": case["case_id"], "run_sha256": "fixture",
                                               "body": body, "wire_sha256": bytes_hash(wire.encode("utf-8"))})
            write_text(out / "request.wire.json", wire)
            with patch.object(OllamaClient, "chat", side_effect=AssertionError("추론 금지")):
                record = recover_case(self.core, out, manifest, p, case)
            self.assertEqual(record["status"], "interrupted_unknown")


if __name__ == "__main__":
    unittest.main()
