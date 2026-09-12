"""사용자가 실행할 오프라인 테스트. 네트워크·모델·GPU를 사용하지 않는다.

simulate()는 테스트 픽스처를 만드는 데만 사용한다. 이 파일의 결과는 LLM 실험이 아니다.
"""
from __future__ import annotations

import ast
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_llm.audit import evaluate_trace
from local_llm.client import APIError, NoRedirect, OllamaClient, local_endpoint, reject_remote_metadata
from local_llm.common import PACKAGE, REPO, ContractError, digest, load_core, read_json, strict_json, write_json
from local_llm.design import all_roles, build_plan, reference_depths
from local_llm.protocol import TRANSPORT_SCHEMA, parse_payload, to_trace, validate_schema
from local_llm.report import build_summary, read_records, write_report
from local_llm.runner import assess_response, recover_case, request_body, run_lock, save_record, usage


def as_payload(trace: dict) -> dict:
    return {"nodes": [dict(copy.deepcopy(n), view=copy.deepcopy(trace["views"][n["id"]]))
                      for n in trace["nodes"]], "final": trace["final"],
            "reviews": copy.deepcopy(trace["reviews"])}


def config() -> dict:
    return {"model": "qwen3:4b", "think": False,
            "options": {"num_ctx": 8192, "num_predict": 4096, "temperature": 0.2}}


def reply(payload: dict) -> dict:
    return {"model": "qwen3:4b", "done": True, "done_reason": "stop",
            "message": {"role": "assistant", "content": json.dumps(payload)},
            "prompt_eval_count": 100, "eval_count": 200, "eval_duration": 2_000_000_000}


class OfflineContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.core, cls.info = load_core()
        cls.problems = read_json(REPO / "examples" / "problems.json")
        cls.problem = cls.problems[1]

    def fixture(self, a="instance", d="shallow", m=0):
        trace = self.core.simulate(self.problem, a, d, m)
        role = {"kind": "directed", "A": a, "D_policy": d, "M": m}
        case = {"role": role, "seed": 1729}
        body = request_body(config(), case, self.problem)
        return trace, role, case, body

    def test_round_trip_all_roles_preserves_trace(self):
        for role in all_roles()[1:]:
            with self.subTest(role=role):
                trace = self.core.simulate(self.problem, role["A"], role["D_policy"], role["M"])
                payload = parse_payload(json.dumps(as_payload(trace)))
                self.assertEqual(trace, to_trace(self.core, self.problem, payload))

    def test_all_role_fixtures_are_accepted(self):
        for problem in self.problems:
            for role in all_roles()[1:]:
                with self.subTest(problem=problem["id"], role=role):
                    trace = self.core.simulate(problem, role["A"], role["D_policy"], role["M"])
                    result = evaluate_trace(self.core, problem, trace, role, reference_depths(problem))
                    self.assertTrue(result["valid_completion"])
                    self.assertTrue(result["role_adherent"])
                    self.assertTrue(result["negative_controls_ok"])

    def test_reference_extrema_match_baseline(self):
        for problem in self.problems:
            ref = reference_depths(problem)
            for policy, field in (("shallow", "minimum"), ("deep", "maximum")):
                trace = self.core.simulate(problem, "instance", policy, 0)
                self.assertEqual(ref[field], self.core.verify(problem, trace)["metrics"]["D"])

    def test_depth_is_not_number_of_nodes(self):
        problem = self.problems[2]
        trace = self.core.simulate(problem, "instance", "deep", 0)
        self.assertEqual(self.core.verify(problem, trace)["metrics"]["D"], 4)
        self.assertNotEqual(len(trace["nodes"]), 4)

    def test_response_assessment_accepts_valid_payload(self):
        trace, _, case, body = self.fixture("schema", "deep", 2)
        outcome, converted = assess_response(self.core, self.problem, case,
            reference_depths(self.problem), body, reply(as_payload(trace)))
        self.assertEqual(outcome["status"], "accepted")
        self.assertEqual(converted, trace)

    def test_fixed_goal_without_support_is_rejected(self):
        trace, role, _, _ = self.fixture()
        trace["nodes"][-1].update(rule=None, parents=[])
        before = copy.deepcopy(trace)
        result = evaluate_trace(self.core, self.problem, trace, role, reference_depths(self.problem))
        self.assertTrue(result["fixed_goal_match"])
        self.assertFalse(result["valid_completion"])
        self.assertEqual(trace, before)

    def test_false_meta_finding_preserves_target_level_but_fails(self):
        trace, role, _, _ = self.fixture("schema", "deep", 2)
        trace["reviews"][1]["finding"]["proof_and_goal_accepts"] = True
        result = evaluate_trace(self.core, self.problem, trace, role, reference_depths(self.problem))
        self.assertEqual(result["observed"]["M_target"], 2)
        self.assertTrue(result["proof_valid"])
        self.assertFalse(result["review_valid"])
        self.assertFalse(result["valid_completion"])

    def test_wrong_A_is_role_mismatch_not_a_valid_A_change(self):
        trace, _, case, body = self.fixture("instance", "shallow", 0)
        case["role"]["A"] = "schema"
        result, _ = assess_response(self.core, self.problem, case,
            reference_depths(self.problem), body, reply(as_payload(trace)))
        self.assertEqual(result["status"], "role_mismatch")
        self.assertTrue(result["audit"]["valid_completion"])
        self.assertFalse(result["audit"]["role_adherent"])

    def test_duplicate_json_key_is_rejected(self):
        with self.assertRaises(ContractError):
            strict_json('{"nodes": [], "nodes": [1]}')

    def test_nonfinite_json_is_rejected(self):
        for text in ('{"x": NaN}', '{"x": Infinity}', '{"x": 1e9999}'):
            with self.subTest(text=text), self.assertRaises(ContractError):
                strict_json(text)

    def test_markdown_is_not_silently_repaired(self):
        trace, _, _, _ = self.fixture()
        with self.assertRaises(ContractError):
            parse_payload("```json\n" + json.dumps(as_payload(trace)) + "\n```")

    def test_coordinate_injection_is_rejected(self):
        trace, _, _, _ = self.fixture()
        payload = as_payload(trace)
        payload["A"] = 4
        with self.assertRaises(ContractError):
            parse_payload(json.dumps(payload))

    def test_missing_view_is_not_synthesized(self):
        trace, _, _, _ = self.fixture()
        payload = as_payload(trace)
        del payload["nodes"][0]["view"]
        with self.assertRaises(ContractError):
            parse_payload(json.dumps(payload))

    def test_duplicate_node_does_not_overwrite_view(self):
        trace, _, _, _ = self.fixture()
        payload = as_payload(trace)
        payload["nodes"].append(copy.deepcopy(payload["nodes"][0]))
        with self.assertRaises(ContractError):
            to_trace(self.core, self.problem, payload)

    def test_findings_require_boolean_not_integer(self):
        trace, _, _, _ = self.fixture("instance", "shallow", 1)
        payload = as_payload(trace)
        payload["reviews"][0]["finding"]["grounded"] = 1
        with self.assertRaises(ContractError):
            validate_schema(payload, TRANSPORT_SCHEMA)

    def test_output_schema_identical_across_roles(self):
        bodies = [request_body(config(), {"role": role, "seed": 42}, self.problem) for role in all_roles()]
        self.assertTrue(all(body["format"] == bodies[0]["format"] for body in bodies))
        self.assertTrue(all(body["options"] == bodies[0]["options"] for body in bodies))
        self.assertTrue(all("tools" not in body for body in bodies))
        self.assertTrue(all("reference_depths" not in json.dumps(body["messages"]) for body in bodies))

    def test_truncated_response_is_not_accepted_even_when_json_is_complete(self):
        trace, _, case, body = self.fixture()
        response = reply(as_payload(trace))
        response["done_reason"] = "length"
        result, converted = assess_response(self.core, self.problem, case,
            reference_depths(self.problem), body, response)
        self.assertEqual(result["status"], "truncated")
        self.assertIsNone(converted)
        self.assertEqual(result["usage"]["eval_count"], 200)

    def test_wrong_model_is_rejected(self):
        trace, _, case, body = self.fixture()
        response = reply(as_payload(trace))
        response["model"] = "other:model"
        result, _ = assess_response(self.core, self.problem, case,
            reference_depths(self.problem), body, response)
        self.assertEqual(result["status"], "protocol_error")

    def test_unexpected_thinking_is_rejected(self):
        trace, _, case, body = self.fixture()
        response = reply(as_payload(trace))
        response["message"]["thinking"] = "unexpected"
        result, _ = assess_response(self.core, self.problem, case,
            reference_depths(self.problem), body, response)
        self.assertEqual(result["status"], "protocol_error")

    def test_tool_calls_are_never_executed(self):
        trace, _, case, body = self.fixture()
        response = reply(as_payload(trace))
        response["message"]["tool_calls"] = [{"function": {"name": "delete_files"}}]
        result, _ = assess_response(self.core, self.problem, case,
            reference_depths(self.problem), body, response)
        self.assertEqual(result["status"], "protocol_error")

    def test_cycle_unrolling_is_not_a_deep_policy_success(self):
        problem = {"id": "cycle", "facts": ["p"], "goal": "g", "rules": [
            {"id": "a", "premises": ["p"], "conclusion": "q"},
            {"id": "b", "premises": ["q"], "conclusion": "r"},
            {"id": "c", "premises": ["r"], "conclusion": "q"},
            {"id": "d", "premises": ["q"], "conclusion": "g"}]}
        nodes = [{"id": f"n{i}", "atom": atom, "rule": rule,
                  "parents": [] if i == 0 else [f"n{i-1}"]}
                 for i, (atom, rule) in enumerate(zip(["p", "q", "r", "q", "g"], [None, "a", "b", "c", "d"]))]
        trace = {"version": 1, "problem_id": "cycle", "problem_sha256": self.core.digest(problem),
                 "nodes": nodes, "final": "n4", "reviews": [],
                 "views": {n["id"]: {"kind": "instance", "atom": n["atom"]} for n in nodes}}
        role = {"kind": "directed", "A": "instance", "D_policy": "deep", "M": 0}
        result = evaluate_trace(self.core, problem, trace, role, reference_depths(problem))
        self.assertTrue(result["baseline_trace_valid"])
        self.assertFalse(result["simple_support_paths"])
        self.assertFalse(result["role_adherent"])

    def test_profile_call_counts(self):
        for profile, expected in (("smoke", 6), ("pilot", 39), ("full", 117)):
            plan = build_plan(self.core, self.problems, profile, None, 1729)
            self.assertEqual(len(plan["cases"]), expected)

    def test_seeded_design_is_reproducible(self):
        one = build_plan(self.core, self.problems, "full", None, 1729)
        two = build_plan(self.core, self.problems, "full", None, 1729)
        self.assertEqual(one, two)
        self.assertEqual(len({case["case_id"] for case in one["cases"]}), 117)

    def test_unreachable_problem_is_not_excluded(self):
        problem = {"id": "unreachable", "facts": ["p"], "goal": "g", "rules": []}
        plan = build_plan(self.core, [problem], "pilot", 1, 42)
        self.assertFalse(plan["reference_depths"]["unreachable"]["reachable"])
        self.assertEqual(plan["assigned_calls"], 13)
        summary, _, contrasts = build_summary(plan, [])
        self.assertEqual(summary["valid_rate_all_assigned"], 0)
        self.assertEqual(len(contrasts), 20)

    def test_empty_results_keep_all_assigned_denominators(self):
        plan = build_plan(self.core, self.problems, "pilot", 1, 42)
        summary, rows, contrasts = build_summary(plan, [])
        self.assertEqual(len(rows), 39)
        self.assertEqual(len(contrasts), 60)
        self.assertEqual(summary["not_recorded_cases"], 39)
        self.assertFalse(summary["all_assigned_passed"])

    def synthetic_records(self, plan):
        problems = {p["id"]: p for p in plan["problems"]}
        records = []
        for case in plan["cases"]:
            problem, role = problems[case["problem_id"]], case["role"]
            trace = (self.core.simulate(problem) if role["kind"] == "neutral" else
                     self.core.simulate(problem, role["A"], role["D_policy"], role["M"]))
            audit = evaluate_trace(self.core, problem, trace, role, reference_depths(problem))
            records.append({"case": case, "status": "accepted", "audit": audit,
                            "api_attempted": False, "usage": {}, "gpu": {},
                            "source": "synthetic_unit_test_not_model_output"})
        return records

    def test_synthetic_complete_design_has_sixty_contrasts(self):
        plan = build_plan(self.core, self.problems, "pilot", 1, 42)
        summary, _, _ = build_summary(plan, self.synthetic_records(plan))
        self.assertEqual(summary["passed_contrasts"], 60)
        self.assertTrue(summary["all_assigned_passed"])

    def test_transport_failure_with_retained_audit_is_not_success(self):
        plan = build_plan(self.core, self.problems, "pilot", 1, 42)
        records = self.synthetic_records(plan)
        for record in records:
            record["status"] = "transport_error"
        summary, _, _ = build_summary(plan, records)
        self.assertEqual(summary["valid_completions"], 0)
        self.assertEqual(summary["passed_contrasts"], 0)

    def test_unknown_tokens_are_not_recorded_as_known_zero(self):
        self.assertIsNone(usage({})["eval_count"])
        self.assertEqual(usage({"eval_count": 0})["eval_count"], 0)
        self.assertEqual(usage({"eval_count": 200, "eval_duration": 2_000_000_000})["tokens_per_second"], 100)

    def test_resume_does_not_recall_request_with_missing_response(self):
        plan = build_plan(self.core, self.problems, "smoke", 1, 42)
        case = plan["cases"][0]
        problem = plan["problems"][0]
        manifest = {"run_sha256": "test", "frozen": {"plan": plan, "config": config()}}
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            write_json(folder / "request.json", {"case_id": case["case_id"], "run_sha256": "test",
                       "body": request_body(config(), case, problem)})
            with patch.object(OllamaClient, "chat", side_effect=AssertionError("모델을 호출하면 안 됨")):
                result = recover_case(self.core, folder, manifest, problem, case)
            self.assertEqual(result["status"], "interrupted_unknown")
            self.assertIsNone(result["api_attempted"])

    def test_artifact_change_is_detected(self):
        plan = build_plan(self.core, self.problems, "smoke", 1, 42)
        manifest = {"frozen": {"plan": plan}, "run_sha256": digest({"plan": plan})}
        case = plan["cases"][0]
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            folder = out / "cases" / case["case_id"]
            write_json(folder / "request.json", {"example": True})
            record = {"case": case, "run_sha256": manifest["run_sha256"], "status": "interrupted"}
            save_record(folder, record)
            write_json(folder / "request.json", {"example": False})
            with self.assertRaises(ContractError):
                read_records(out, manifest)

    def test_report_files_are_written_without_model(self):
        plan = build_plan(self.core, self.problems, "smoke", 1, 42)
        frozen = {"plan": plan}
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            write_json(out / "manifest.json", {"frozen": frozen, "run_sha256": digest(frozen)})
            result = write_report(out)
            self.assertEqual(result["assigned_cases"], 6)
            self.assertTrue((out / "metrics.csv").read_bytes().startswith(b"\xef\xbb\xbf"))
            self.assertIn("| 역할 |", (out / "summary.md").read_text(encoding="utf-8"))

    def test_stale_lock_requires_explicit_operator_action(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            (out / ".run.lock").write_text("pid=unknown")
            with self.assertRaises(ContractError), run_lock(out):
                self.fail("잠금이 있는데 실행됨")

    def test_runtime_never_calls_simulate_or_download_endpoint(self):
        for path in PACKAGE.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    name = getattr(node.func, "attr", getattr(node.func, "id", ""))
                    self.assertNotIn(name, {"simulate", "_plans"}, str(path))
            self.assertNotIn('"/api/pull"', path.read_text(encoding="utf-8"))


class NetworkBoundaryTests(unittest.TestCase):
    def test_localhost_is_normalized_without_dns(self):
        self.assertEqual(local_endpoint("http://localhost:11434"), "http://127.0.0.1:11434")
        self.assertEqual(local_endpoint("http://[::1]:11434/"), "http://[::1]:11434")

    def test_external_url_proxy_paths_and_credentials_are_rejected(self):
        for url in ("https://api.example.com", "http://192.168.1.2:11434", "http://0.0.0.0:11434",
                    "http://127.0.0.1:11434/api", "http://user:pass@127.0.0.1:11434",
                    "http://127.0.0.1:11434/?target=cloud"):
            with self.subTest(url=url), self.assertRaises(ContractError):
                local_endpoint(url)

    def test_remote_metadata_is_rejected(self):
        with self.assertRaises(ContractError):
            reject_remote_metadata({"details": {"remote_host": "cloud.example"}})

    def test_redirect_is_rejected(self):
        with self.assertRaises(APIError):
            NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://cloud.example")

    def test_missing_model_does_not_trigger_download(self):
        client = OllamaClient()
        with patch.object(client, "request") as mocked:
            mocked.return_value.value = {"models": []}
            with self.assertRaises(ContractError):
                client.tag("qwen3:4b")
            self.assertEqual(mocked.call_args.args[0], "/api/tags")
            self.assertEqual(mocked.call_count, 1)

    def test_cloud_model_name_is_rejected_before_network(self):
        client = OllamaClient()
        with patch.object(client, "request", side_effect=AssertionError("네트워크 호출 금지")):
            with self.assertRaises(ContractError):
                client.tag("some-model:cloud")


if __name__ == "__main__":
    unittest.main()
