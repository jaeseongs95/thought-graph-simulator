from __future__ import annotations
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from paired_probe_v047.audit import audit_run
from paired_probe_v047.contracts import ContractError, digest, read_json, sha, strict_json, wire, write_json
from paired_probe_v047.plan import prepare
from paired_probe_v047.runner import execute
from tests_v047.fixtures import baseline, fake_server

@contextlib.contextmanager
def experiment(mode="perfect", cycles=1, seeds=None):
    with tempfile.TemporaryDirectory() as temp, fake_server(mode) as (state, endpoint):
        root = Path(temp); source = baseline(root, endpoint); plan_path = root / "frozen.plan.json"
        plan = prepare(root, plan_path, cycles=cycles, seeds=seeds)
        out = root / "run"
        with contextlib.redirect_stdout(io.StringIO()):
            report = execute(plan_path, out)
        yield root, state, plan_path, plan, out, report


def reseal_events(out: Path, events: list[dict]):
    previous = read_json(out / "plan.snapshot.json")["plan_sha256"]
    for e in events:
        e["previous_hash"] = previous; e.pop("event_hash", None); e["event_hash"] = digest(e)
        previous = e["event_hash"]
    (out / "events.jsonl").write_bytes(b"".join(wire(e) + b"\n" for e in events))
    status = read_json(out / "status.json"); status["event_tip"] = previous
    write_json(out / "status.json", status)


def events_of(out):
    return [strict_json(line) for line in (out / "events.jsonl").read_bytes().splitlines()]

class IntegrationTests(unittest.TestCase):
    def test_full_six_cycles_96_calls(self):
        with experiment(cycles=6) as (_, state, _, _, _, r):
            self.assertTrue(r["data_integrity"]); self.assertTrue(r["data_complete"])
            self.assertEqual(r["inference_calls"], 96); self.assertEqual(len(state.requests), 96)
            self.assertEqual(r["arms"]["pipeline"]["strict_trace_correct"], 24)
            self.assertEqual(r["arms"]["original"]["four_of_four_repeats"], 6)
    def test_fixture_not_live_inference(self):
        with experiment() as (_, _, _, _, _, r):
            self.assertFalse(r["new_model_inference"]); self.assertEqual(r["evidence_kind"], "synthetic_fixture")
    def test_reproduce_reported_pattern(self):
        with experiment("original_false") as (_, _, _, _, _, r):
            self.assertEqual(r["arms"]["original"]["final_correct"], 3)
            self.assertEqual(r["arms"]["commuted"]["final_correct"], 4)
            self.assertEqual(r["arms"]["pipeline"]["strict_trace_correct"], 4)
            self.assertEqual(r["paired_final_outcomes"]["pipeline-original"]["contender_only"], 1)
    def test_model_failure_does_not_invalidate_collection(self):
        with experiment("original_false") as (_, _, _, _, _, r):
            self.assertTrue(r["comparative_analysis_ready"])
            self.assertEqual(r["arms"]["original"]["final_accuracy"], 0.75)
    def test_positive_case_reported(self):
        with experiment("original_false") as (_, _, _, _, _, r):
            self.assertEqual(r["arms"]["original"]["positive_correct"], 0)
            self.assertEqual(r["arms"]["original"]["balanced_accuracy"], 0.5)
    def test_wrong_parent_not_repaired(self):
        with experiment("wrong_not") as (_, state, _, _, _, r):
            self.assertEqual(r["arms"]["pipeline"]["strict_trace_correct"], 0)
            self.assertEqual(r["arms"]["pipeline"]["final_correct"], 2)
            for i, body in enumerate(state.requests):
                data = strict_json(body["messages"][1]["content"][7:])
                if data["expression"] == '(NOT b)':
                    child = strict_json(state.requests[i + 1]["messages"][1]["content"][7:])
                    self.assertIs(child["b"], data["b"])
    def test_invalid_parent_blocks_child_no_hidden_retry(self):
        with experiment("invalid_not") as (_, state, _, _, _, r):
            self.assertEqual(len(state.requests), 12)
            self.assertEqual(r["recorded_slots"], 16)
            self.assertEqual(r["call_status_counts"]["blocked"], 4)
            self.assertTrue(r["data_complete"])
            self.assertEqual(r["arms"]["pipeline"]["strict_trace_correct"], 0)
    def test_infrastructure_error_not_retried(self):
        with experiment("http_error") as (_, state, _, _, _, r):
            self.assertEqual(len(state.requests), 1)
            self.assertFalse(r["data_complete"]); self.assertFalse(r["comparative_analysis_ready"])
            self.assertIsNone(r["arms"]["original"]["final_accuracy"])
    def test_runtime_drift_not_eligible(self):
        with experiment("runtime_drift") as (_, _, _, _, _, r):
            self.assertFalse(r["comparative_analysis_ready"]); self.assertFalse(r["data_complete"])
    def test_wrong_response_model_rejected(self):
        with experiment("wrong_model") as (_, _, _, _, _, r):
            self.assertTrue(r["data_complete"])
            self.assertEqual(r["arms"]["original"]["valid_final_values"], 0)
            self.assertEqual(r["arms"]["pipeline"]["strict_trace_correct"], 0)
    def test_audit_offline_and_same_result(self):
        with experiment() as (_, state, p, _, out, first):
            n = len(state.requests)
            second = audit_run(p, out)
            self.assertEqual(first, second); self.assertEqual(n, len(state.requests))
    def test_cost_includes_both_calls(self):
        with experiment() as (_, _, _, _, _, r):
            self.assertEqual(r["arms"]["original"]["costs"]["eval_count"]["total"], 20)
            self.assertEqual(r["arms"]["pipeline"]["costs"]["eval_count"]["total"], 40)
            self.assertEqual(r["arms"]["pipeline"]["costs"]["eval_count"]["actual_calls"], 8)
    def test_original_data_unchanged(self):
        with experiment() as (root, _, _, _, _, _):
            before = {p.name: p.read_bytes() for p in (root / "v046_fixture").glob("*.json")}
            self.assertEqual(read_json(root / "v046_fixture" / "manifest.json")["frozen"]["plan"]["probe_contract"],
                             "composition-v046")
            self.assertIn("manifest.json", before)
    def test_no_run_overwrite(self):
        with experiment() as (_, state, p, _, out, _):
            n = len(state.requests)
            with self.assertRaises(ContractError):
                execute(p, out)
            self.assertEqual(n, len(state.requests))
    def test_response_flip_detected(self):
        with experiment() as (_, _, p, _, out, _):
            f = next((out / "calls").rglob("response.raw.json")); raw = read_json(f)
            payload = strict_json(raw["message"]["content"]); payload["value"] = not payload["value"]
            raw["message"]["content"] = wire(payload).decode(); f.write_bytes(wire(raw))
            with self.assertRaises(ContractError):
                audit_run(p, out)
    def test_missing_response_detected(self):
        with experiment() as (_, _, p, _, out, _):
            next((out / "calls").rglob("response.raw.json")).unlink()
            with self.assertRaises(OSError):
                audit_run(p, out)
    def test_missing_event_detected(self):
        with experiment() as (_, _, p, _, out, _):
            events = events_of(out); events.pop()
            reseal_events(out, events)
            with self.assertRaises(ContractError):
                audit_run(p, out)
    def test_duplicated_event_detected(self):
        with experiment() as (_, _, p, _, out, _):
            events = events_of(out); events.append(events[-1]); reseal_events(out, events)
            with self.assertRaises(ContractError):
                audit_run(p, out)
    def test_resealed_request_change_detected(self):
        with experiment() as (_, _, p, _, out, _):
            events = events_of(out); e = next(e for e in events if e["slot"]["stage"] == "original")
            f = out / "calls" / e["slot"]["id"] / "request.wire.json"
            body = read_json(f); body["messages"][1]["content"] += " "
            f.write_bytes(wire(body)); e["request_sha256"] = sha(f.read_bytes()); reseal_events(out, events)
            with self.assertRaises(ContractError):
                audit_run(p, out)
    def test_parent_hash_change_detected_even_resealed(self):
        with experiment() as (_, _, p, _, out, _):
            events = events_of(out); e = next(e for e in events if e["slot"]["stage"] == "and")
            e["parent"]["response_sha256"] = "0" * 64; reseal_events(out, events)
            with self.assertRaises(ContractError):
                audit_run(p, out)
    def test_resealed_local_plan_not_external_plan(self):
        with experiment() as (_, _, p, _, out, _):
            snapshot = read_json(out / "plan.snapshot.json"); snapshot["analysis_policy"]["no_retry"] = False
            snapshot.pop("plan_sha256"); snapshot["plan_sha256"] = digest(snapshot)
            write_json(out / "plan.snapshot.json", snapshot)
            with self.assertRaises(ContractError):
                audit_run(p, out)
    def test_source_snapshot_change_detected(self):
        with experiment() as (_, _, p, _, out, _):
            f = out / "source_snapshot" / "runner.py"; f.write_text("# changed", encoding="utf-8")
            with self.assertRaises(ContractError):
                audit_run(p, out)
    def test_derived_score_not_trusted(self):
        with experiment("original_false") as (_, _, p, _, out, _):
            write_json(out / "summary.json", {"everything_passed": True})
            r = audit_run(p, out)
            self.assertEqual(r["arms"]["original"]["final_correct"], 3)
    def test_multiseed_not_pooled_as_independent_tasks(self):
        with experiment("original_false", cycles=1, seeds=[1729, 2718]) as (_, _, _, _, _, r):
            pair = r["paired_final_outcomes"]["pipeline-original"]
            self.assertEqual(len(pair["per_seed"]), 2); self.assertIsNone(pair["inferential_p_value"])
            self.assertEqual(r["inference_calls"], 32)
