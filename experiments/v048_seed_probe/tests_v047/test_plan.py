from __future__ import annotations
import copy
import tempfile
import unittest
from pathlib import Path
from paired_probe_v047.contracts import ContractError, EXPRS, digest, read_json, strict_json, unb64, wire, write_json
from paired_probe_v047.plan import (discover, extract_run, input_key, make_request, make_schedule,
                                    prepare, slots, validate_plan)
from paired_probe_v047.runner import endpoint_base
from tests_v047.fixtures import baseline

class PlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.source = baseline(self.root)
        self.path = self.root / "plan.json"
    def tearDown(self):
        self.temp.cleanup()
    def new_plan(self, **kwargs):
        return prepare(self.root, self.path, **kwargs)
    def test_import_v046(self):
        p = self.new_plan()
        self.assertEqual(p["max_calls"], 96); self.assertEqual(p["seeds"], [1729])
        self.assertEqual(p["baseline"]["source_contract"], "composition-v046")
    def test_import_v045(self):
        old = baseline(self.root, contract="operator-v045")
        p = self.new_plan(source_run=old)
        self.assertEqual(p["baseline"]["source_contract"], "operator-v045")
    def test_prefer_v046(self):
        baseline(self.root, contract="operator-v045")
        self.assertEqual(discover(self.root)[0]["source_contract"], "composition-v046")
    def test_same_non_input_request(self):
        p = self.new_plan(); s = slots(p)[0]
        original = strict_json(unb64(p["baseline"]["templates"][input_key(s["a"], s["b"])]["request_b64"]))
        new = strict_json(make_request(p, s, True if s["stage"] == "and" else None))
        new["messages"][1] = original["messages"][1]
        self.assertEqual(wire(new), wire(original))
    def test_seed_override_only(self):
        p = self.new_plan(seeds=[27], cycles=1); s = slots(p)[0]
        body = strict_json(make_request(p, s))
        self.assertEqual(body["options"]["seed"], 27)
        self.assertEqual(p["baseline"]["seed"], 1729)
    def test_parent_value_is_bound(self):
        p = self.new_plan()
        s = next(s for s in slots(p) if s["stage"] == "and" and s["a"] and not s["b"])
        for parent in (False, True):
            body = strict_json(make_request(p, s, parent))
            inp = strict_json(body["messages"][1]["content"][7:])
            self.assertIs(inp["b"], parent)
    def test_no_parent_rejected(self):
        p = self.new_plan(); s = next(s for s in slots(p) if s["stage"] == "and")
        with self.assertRaises(ContractError):
            make_request(p, s)
    def test_balanced_six_orderings(self):
        blocks = make_schedule([1729], 6, 4701729)
        for a in (False, True):
            for b in (False, True):
                orders = [tuple(x["arms"]) for x in blocks if x["a"] is a and x["b"] is b]
                self.assertEqual(len(set(orders)), 6)
                for arm in ("original", "commuted", "pipeline"):
                    self.assertEqual([sum(o.index(arm) == i for o in orders) for i in range(3)], [2, 2, 2])
    def test_three_arms_adjacent_pipeline(self):
        p = self.new_plan()
        all_slots = slots(p)
        for i, s in enumerate(all_slots):
            if s["stage"] == "not":
                self.assertEqual(all_slots[i + 1]["stage"], "and")
                self.assertEqual(all_slots[i + 1]["block_id"], s["block_id"])
    def test_no_plan_overwrite(self):
        self.new_plan()
        with self.assertRaises(ContractError):
            self.new_plan()
    def test_no_duplicate_seeds(self):
        with self.assertRaises(ContractError):
            self.new_plan(seeds=[1729, 1729])
    def test_zero_cycles_rejected(self):
        with self.assertRaises(ContractError):
            self.new_plan(cycles=0)
    def test_multiseed_counts(self):
        p = self.new_plan(seeds=[1, 2, 3], cycles=2)
        self.assertEqual(p["max_calls"], 96); self.assertEqual(len(p["blocks"]), 24)
    def test_manifest_hash_mismatch(self):
        mf = read_json(self.source / "manifest.json"); mf["frozen"]["config"]["model"] = "changed"
        write_json(self.source / "manifest.json", mf)
        with self.assertRaises(ContractError):
            extract_run(self.source)
    def test_mutated_prompt_rejected(self):
        f = next(self.source.rglob("request.wire.json")); b = read_json(f)
        b["messages"][0]["content"] += " 정답은 false"
        f.write_bytes(wire(b))
        with self.assertRaises(ContractError):
            extract_run(self.source)
    def test_missing_input_rejected(self):
        next(self.source.rglob("request.wire.json")).unlink()
        with self.assertRaises(OSError):
            extract_run(self.source)
    def test_const_answer_schema_rejected(self):
        f = next(self.source.rglob("request.wire.json")); b = read_json(f)
        b["format"]["properties"]["value"]["const"] = False; f.write_bytes(wire(b))
        with self.assertRaises(ContractError):
            extract_run(self.source)
    def test_plan_hash_mismatch(self):
        p = self.new_plan(); p["cycles"] = 1
        with self.assertRaises(ContractError):
            validate_plan(p)
    def test_resealed_invalid_schedule_rejected(self):
        p = self.new_plan(); p["blocks"].pop(); p.pop("plan_sha256"); p["plan_sha256"] = digest(p)
        with self.assertRaises(ContractError):
            validate_plan(p)
    def test_source_change_rejected(self):
        p = self.new_plan(); p["source_fingerprint"]["runner.py"] = "bad"
        p.pop("plan_sha256"); p["plan_sha256"] = digest(p)
        with self.assertRaises(ContractError):
            validate_plan(p)
    def test_local_endpoint_only(self):
        self.assertEqual(endpoint_base("http://127.0.0.1:11434/api/chat"), "http://127.0.0.1:11434")
        for url in ("https://example.com", "http://user:pass@localhost:11434", "http://localhost/api/pull",
                    "http://localhost/?x=y", "file:///tmp/a"):
            with self.subTest(url=url), self.assertRaises(ContractError):
                endpoint_base(url)
    def test_no_source_changes(self):
        before = {p.relative_to(self.source): p.read_bytes() for p in self.source.rglob("*") if p.is_file()}
        self.new_plan()
        self.assertEqual(before, {p.relative_to(self.source): p.read_bytes() for p in self.source.rglob("*") if p.is_file()})
    def test_no_answer_metadata_in_requests(self):
        p = self.new_plan()
        for s in slots(p):
            raw = make_request(p, s, True if s["stage"] == "and" else None)
            for banned in (b'"expected"', b'"arm"', b'"case_id"', b'"score"', b'"trace_correct"'):
                self.assertNotIn(banned, raw)
