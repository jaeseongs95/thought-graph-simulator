from __future__ import annotations
import copy
import itertools
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from paired_probe_v048.contracts import ContractError, digest, read_json, strict_json, wire, write_json, source_fingerprint
from paired_probe_v048.plan import (prepare, default_seeds, validate_plan, make_schedule, make_request, slots,
                                    ARMS, SEED_DOMAIN)
from tests_v048.fixtures import build_v047, fake_server


class PlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        with fake_server() as (_, endpoint):
            cls.old_plan, cls.old_run = build_v047(cls.root, endpoint)
        cls.plan = prepare(cls.old_run, cls.root / "initial.plan.json", baseline_plan=cls.old_plan)
    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()
    def changed(self, fn):
        plan = copy.deepcopy(self.plan); fn(plan); plan.pop("plan_sha256"); plan["plan_sha256"] = digest(plan)
        return plan
    def test_default_calls_960(self):
        self.assertEqual(self.plan["max_calls"], 960); self.assertEqual(len(slots(self.plan)), 960)
    def test_default_seeds_are_frozen(self):
        self.assertEqual(default_seeds([1729]), [580410664,661935755,209422594,1790124989,267101868,752235971,1292559482,223674688,860724506,68285180])
    def test_discovery_seed_excluded(self):
        self.assertNotIn(1729, self.plan["seeds"])
    def test_ten_distinct_seeds(self):
        self.assertEqual(len(set(self.plan["seeds"])), 10)
    def test_seed_lists_do_not_use_model_scores(self):
        self.assertEqual(default_seeds([1729]), default_seeds([1729]))
    def test_every_seed_input_has_six_permutations(self):
        for seed in self.plan["seeds"]:
            for a, b in itertools.product((False, True), repeat=2):
                found = [tuple(x["arms"]) for x in self.plan["blocks"] if (x["seed"],x["a"],x["b"]) == (seed,a,b)]
                self.assertCountEqual(found, itertools.permutations(ARMS))
    def test_rounds_interleave_all_seeds(self):
        for cycle in range(6):
            wave = [b for b in self.plan["blocks"] if b["cycle"] == cycle]
            self.assertEqual(len(wave), 40)
            self.assertEqual({b["seed"] for b in wave}, set(self.plan["seeds"]))
    def test_schedule_reproducible(self):
        self.assertEqual(self.plan["blocks"], make_schedule(self.plan["seeds"],6,self.plan["order_seed"]))
    def test_unique_slot_ids(self):
        ids = [x["id"] for x in slots(self.plan)]; self.assertEqual(len(ids),len(set(ids)))
    def test_seed_change_preserves_sampling_options(self):
        for slot in slots(self.plan):
            if slot["stage"] == "and": continue
            request = strict_json(make_request(self.plan,slot))
            self.assertEqual(request["options"], dict(self.plan["baseline"]["config"]["options"],seed=slot["seed"]))
    def test_expressions_only_difference_in_direct_pair(self):
        s = slots(self.plan)[0].copy();s["stage"]="original"
        a = strict_json(make_request(self.plan,s));s["stage"]="commuted"
        b = strict_json(make_request(self.plan,s))
        va = strict_json(a["messages"][1]["content"][7:]);vb = strict_json(b["messages"][1]["content"][7:])
        va["expression"] = vb["expression"]
        a["messages"][1]["content"]="input: "+wire(va).decode()
        self.assertEqual(a,b)
    def test_and_requires_actual_bool(self):
        slot = next(s for s in slots(self.plan) if s["stage"]=="and")
        for value in (None, 0, 1, "true", []):
            with self.subTest(value=value), self.assertRaises(ContractError): make_request(self.plan,slot,value)
    def test_wrong_parent_is_not_corrected(self):
        slot = next(s for s in slots(self.plan) if s["stage"]=="and")
        for value in (True,False):
            body = strict_json(make_request(self.plan,slot,value))
            self.assertIs(strict_json(body["messages"][1]["content"][7:])["b"],value)
    def test_policy_reseal_cannot_allow_retry(self):
        p = self.changed(lambda x:x["analysis_policy"].update(no_retry=False))
        with self.assertRaises(ContractError): validate_plan(p)
    def test_schedule_reseal_cannot_omit_cell(self):
        p = self.changed(lambda x:x["blocks"].pop())
        with self.assertRaises(ContractError): validate_plan(p)
    def test_bool_input_cannot_be_integer_even_if_resealed(self):
        p = self.changed(lambda x:x["blocks"][0].update(a=int(x["blocks"][0]["a"])))
        with self.assertRaises(ContractError): validate_plan(p)
    def test_config_reseal_cannot_change_temperature(self):
        p = self.changed(lambda x:x["baseline"]["config"]["options"].update(temperature=1.1))
        with self.assertRaises(ContractError): validate_plan(p)
    def test_default_seed_reseal_cannot_change_seed(self):
        p = self.changed(lambda x:x["seeds"].__setitem__(0,1))
        with self.assertRaises(ContractError): validate_plan(p)
    def test_source_change_detected(self):
        p = self.changed(lambda x:x["source_fingerprint"].update({"paired_probe_v048/runner.py":"0"*64}))
        with self.assertRaises(ContractError): validate_plan(p)
    def test_source_fingerprint_contains_legacy_and_new(self):
        self.assertIn("paired_probe_v047/audit.py",source_fingerprint())
        self.assertIn("paired_probe_v048/runner.py",source_fingerprint())
    def test_unknown_plan_fields_rejected(self):
        p=self.changed(lambda x:x.update(extra=True))
        with self.assertRaises(ContractError): validate_plan(p)
    def test_prepare_offline(self):
        with patch("paired_probe_v048.runner.OllamaHTTP.request",side_effect=AssertionError("network")):
            prepare(self.old_run,self.root/"offline.plan.json",baseline_plan=self.old_plan)
    def test_prepare_does_not_overwrite(self):
        with self.assertRaises(ContractError): prepare(self.old_run,self.root/"initial.plan.json",baseline_plan=self.old_plan)
    def test_snapshot_requires_explicit_flag(self):
        with self.assertRaises(ContractError): prepare(self.old_run,self.root/"noanchor.json")
    def test_snapshot_not_external_by_same_path(self):
        with self.assertRaises(ContractError): prepare(self.old_run,self.root/"badanchor.json",baseline_plan=self.old_run/"plan.snapshot.json")
    def test_snapshot_fallback_labelled(self):
        p=prepare(self.old_run,self.root/"snapshot.plan.json",accept_snapshot=True)
        self.assertEqual(p["reference"]["anchor"],"snapshot_only")
    def test_external_anchor_labelled(self):
        self.assertEqual(self.plan["reference"]["anchor"],"external_plan")
    def test_discovery_custom_seed_rejected(self):
        with self.assertRaises(ContractError): prepare(self.old_run,self.root/"oldseed.json",baseline_plan=self.old_plan,seeds=[1729])
    def test_duplicate_custom_seed_rejected(self):
        with self.assertRaises(ContractError): prepare(self.old_run,self.root/"duplicate.json",baseline_plan=self.old_plan,seeds=[101,101])
    def test_unbalanced_cycle_rejected(self):
        for cycles in (0,1,5,7,True):
            with self.subTest(cycles=cycles),self.assertRaises(ContractError):
                prepare(self.old_run,self.root/"badcycles.json",baseline_plan=self.old_plan,cycles=cycles)
    def test_invalid_seed_type_range_rejected(self):
        for seeds in ([True],[-1],[2147483648],[]):
            with self.subTest(seeds=seeds),self.assertRaises(ContractError):
                prepare(self.old_run,self.root/"badseed.json",baseline_plan=self.old_plan,seeds=seeds)
    def test_reference_is_separate_from_new_sample(self):
        self.assertEqual(self.plan["reference"]["recorded_inference_calls"],16)
        self.assertEqual(self.plan["max_calls"],960)
    def test_import_source_evidence_inventory(self):
        hashes=self.plan["reference"]["artifact_hashes"]
        self.assertIn("events.jsonl",hashes)
        self.assertNotIn("summary.json",hashes)
    def test_legacy_summary_not_trusted(self):
        target=self.old_run/"summary.json";old=target.read_bytes()
        try:
            write_json(target,{"all_pass":True})
            p=prepare(self.old_run,self.root/"ignore_summary.json",baseline_plan=self.old_plan,seeds=[202])
            self.assertEqual(p["reference"]["reference_only_scores"]["original"]["assigned"],4)
        finally: target.write_bytes(old)
