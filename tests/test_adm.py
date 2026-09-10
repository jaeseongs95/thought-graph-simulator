"""명세 검사·변조 거부·재현성 시험. 모델 능력의 통계적 검증이 아니다."""
import ast
import copy
import itertools
import json
import os
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from adm_minimal import Invalid, canonical, check_problem, digest, load_problems, negative_controls, run_suite, simulate, verify


class ADMTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.problems = load_problems(ROOT / "examples" / "problems.json")
        cls.p = cls.problems[1]

    def good(self):
        return simulate(self.p, "schema", "deep", 2)

    def rejected(self, t, code=None):
        result = verify(self.p, t)
        self.assertFalse(result["valid"], result)
        if code:
            self.assertIn(code, result["error"])
        return result

    def test_all_36_conditions(self):
        for p, a, d, m in itertools.product(self.problems, ("instance", "schema"), ("shallow", "deep"), range(3)):
            with self.subTest(problem=p["id"], a=a, d=d, m=m):
                audit = verify(p, simulate(p, a, d, m))
                self.assertTrue(audit["valid"], audit)
                self.assertEqual(audit["metrics"]["A"], a)
                self.assertEqual(audit["metrics"]["M"], m)

    def test_a_change_preserves_proof(self):
        x, y = simulate(self.p), simulate(self.p, "schema")
        self.assertEqual(x["nodes"], y["nodes"])
        self.assertEqual(verify(self.p, x)["metrics"]["D"], verify(self.p, y)["metrics"]["D"])
        self.assertNotEqual(x["views"], y["views"])

    def test_d_is_actual_path_depth(self):
        self.assertEqual(verify(self.p, simulate(self.p))["metrics"]["D"], 1)
        self.assertEqual(verify(self.p, simulate(self.p, d="deep"))["metrics"]["D"], 3)

    def test_m_change_preserves_proof_and_views(self):
        traces = [simulate(self.p, m=m) for m in range(3)]
        self.assertEqual(traces[0]["nodes"], traces[2]["nodes"])
        self.assertEqual(traces[0]["views"], traces[2]["views"])
        self.assertEqual([len(t["reviews"]) for t in traces], [0, 1, 2])

    def test_depth_is_not_node_count(self):
        p = self.problems[2]
        audit = verify(p, simulate(p, d="deep"))
        self.assertTrue(audit["valid"])
        self.assertEqual(audit["metrics"]["D"], 4)
        self.assertEqual(audit["node_count"], 6)

    def test_all_negative_controls(self):
        for p in self.problems:
            for name, bad in negative_controls(p, simulate(p, "schema", "deep", 2)):
                with self.subTest(problem=p["id"], mutation=name):
                    self.assertFalse(verify(p, bad)["valid"])

    def test_fixed_goal_cannot_be_forged(self):
        t = self.good()
        t["nodes"][-1].update(rule=None, parents=[])
        self.assertEqual(t["nodes"][-1]["atom"], self.p["goal"])
        self.rejected(t, "PROOF")

    def test_dangling_parent(self):
        t = self.good()
        t["nodes"][-1]["parents"] = ["missing"]
        self.rejected(t, "GRAPH")

    def test_unused_valid_fact_cannot_inflate_graph(self):
        t = self.good()
        t["nodes"].append({"id": "extra", "atom": "p", "rule": None, "parents": []})
        t["views"]["extra"] = {"kind": "instance", "atom": "p"}
        self.rejected(t, "무관")

    def test_invalid_final_node(self):
        t = self.good()
        t["final"] = "n0"
        self.rejected(t, "GOAL")

    def test_duplicate_parent(self):
        t = self.good()
        t["nodes"][-1]["parents"] *= 2
        self.rejected(t, "중복")

    def test_unknown_top_level_fields(self):
        t = self.good()
        t["claimed_D"] = 999
        self.rejected(t, "SCHEMA")

    def test_version_bool_not_int(self):
        t = self.good()
        t["version"] = True
        self.rejected(t, "VERSION")

    def test_missing_problem_binding(self):
        t = self.good()
        t["problem_sha256"] = ""
        self.rejected(t, "BINDING")

    def test_empty_trace(self):
        t = self.good()
        t["nodes"] = []
        self.rejected(t, "GRAPH")

    def test_wrong_instance_representation(self):
        t = simulate(self.p)
        t["views"][t["final"]]["atom"] = "q"
        self.rejected(t, "VIEW")

    def test_extra_schema_assumption_not_allowed(self):
        t = self.good()
        view = t["views"][t["final"]]
        view["assumptions"].append({"if": [], "then": view["conclusion"]})
        self.rejected(t, "VIEW")

    def test_bad_schema_binding(self):
        t = self.good()
        view = t["views"][t["final"]]
        view["binding"][view["conclusion"]] = "foreign_atom"
        self.rejected(t, "VIEW")

    def test_non_bijective_schema_binding(self):
        t = self.good()
        view = t["views"][t["final"]]
        keys = list(view["binding"])
        view["binding"][keys[0]] = view["binding"][keys[1]]
        self.rejected(t, "VIEW")

    def test_alpha_renaming_schema_is_invariant(self):
        t = self.good()
        for view in t["views"].values():
            rename = {v: "Renamed_" + v for v in view["binding"]}
            view["binding"] = {rename[k]: v for k, v in view["binding"].items()}
            view["conclusion"] = rename[view["conclusion"]]
            for c in view["assumptions"]:
                c["if"] = [rename[v] for v in c["if"]]
                c["then"] = rename[c["then"]]
        self.assertTrue(verify(self.p, t)["valid"])

    def test_schema_clause_order_is_invariant(self):
        t = self.good()
        for view in t["views"].values():
            view["assumptions"].reverse()
        self.assertTrue(verify(self.p, t)["valid"])

    def test_node_id_renaming_is_invariant(self):
        t = self.good()
        rename = {n["id"]: "node_" + n["id"] for n in t["nodes"]}
        for n in t["nodes"]:
            n["id"] = rename[n["id"]]
            n["parents"] = [rename[x] for x in n["parents"]]
        t["final"] = rename[t["final"]]
        t["views"] = {rename[k]: v for k, v in t["views"].items()}
        t["reviews"][0]["target"] = rename[t["reviews"][0]["target"]]
        t["reviews"][0]["evidence"] = [rename[x] for x in t["reviews"][0]["evidence"]]
        self.assertTrue(verify(self.p, t)["valid"])
        # 원자명도 일괄 치환하고 원문 문제 바인딩을 갱신하면 측정값은 보존된다.
        p = copy.deepcopy(self.p)
        rename_atom = lambda atom: "renamed_" + atom
        p["facts"] = [rename_atom(x) for x in p["facts"]]
        p["goal"] = rename_atom(p["goal"])
        for rule in p["rules"]:
            rule["premises"] = [rename_atom(x) for x in rule["premises"]]
            rule["conclusion"] = rename_atom(rule["conclusion"])
        t["problem_sha256"] = digest(p)
        for node in t["nodes"]:
            node["atom"] = rename_atom(node["atom"])
        for view in t["views"].values():
            view["binding"] = {k: rename_atom(v) for k, v in view["binding"].items()}
        t["reviews"][0]["finding"]["conclusion"] = rename_atom(t["reviews"][0]["finding"]["conclusion"])
        t["reviews"][1]["probe"]["atom"] = rename_atom(t["reviews"][1]["probe"]["atom"])
        audit = verify(p, t)
        self.assertTrue(audit["valid"], audit)
        self.assertEqual(audit["metrics"], {"A": "schema", "D": 3, "M": 2})

    def test_m_level_is_separate_from_review_correctness(self):
        t = self.good()
        t["reviews"][1]["finding"]["proof_and_goal_accepts"] = True
        audit = self.rejected(t, "META")
        self.assertEqual(audit["metrics"]["M"], 2)

    def test_meta_two_need_not_contain_meta_one(self):
        t = self.good()
        t["reviews"] = t["reviews"][1:]
        audit = verify(self.p, t)
        self.assertTrue(audit["valid"])
        self.assertEqual(audit["metrics"]["M"], 2)

    def test_empty_meta_evidence(self):
        t = self.good()
        t["reviews"][0]["evidence"] = []
        self.rejected(t)

    def test_meta_boolean_is_not_numeric_label(self):
        t = self.good()
        t["reviews"][0]["finding"]["grounded"] = 1
        self.rejected(t, "META")

    def test_unknown_meta_target(self):
        t = self.good()
        t["reviews"][1]["target"] = "unregistered_criterion"
        self.rejected(t, "META")

    def test_duplicate_review(self):
        t = self.good()
        duplicate = copy.deepcopy(t["reviews"][0])
        duplicate["id"] = "other_review"
        t["reviews"] = [t["reviews"][0], duplicate]
        self.rejected(t, "META")

    def test_criterion_really_distinguishes_fixed_answer_from_proof(self):
        finding = self.good()["reviews"][1]["finding"]
        self.assertEqual(finding, {"answer_only_accepts": True,
                                  "proof_and_goal_accepts": False, "gap_detected": True})

    def test_fact_goal_is_supported(self):
        p = {"id": "already_given", "facts": ["p"], "rules": [], "goal": "p"}
        t = simulate(p, "schema", "deep", 2)
        audit = verify(p, t)
        self.assertTrue(audit["valid"], audit)
        self.assertEqual(audit["metrics"]["D"], 0)
        self.assertFalse(t["reviews"][1]["finding"]["gap_detected"])

    def test_unreachable_goal_raises_instead_of_appending_answer(self):
        p = {"id": "unreachable", "facts": ["p"], "rules": [], "goal": "g"}
        with self.assertRaisesRegex(Invalid, "UNREACHABLE"):
            simulate(p)

    def test_cyclic_rules_cannot_manufacture_proof(self):
        p = {"id": "cycle", "facts": ["p"], "goal": "g", "rules": [
            {"id": "r1", "premises": ["g"], "conclusion": "q"},
            {"id": "r2", "premises": ["q"], "conclusion": "g"}]}
        with self.assertRaisesRegex(Invalid, "UNREACHABLE"):
            simulate(p)

    def test_invalid_problem_rejected(self):
        p = copy.deepcopy(self.p)
        p["rules"][0]["premises"] = []
        with self.assertRaises(Invalid):
            check_problem(p)

    def test_fixed_seed_generated_problem_checks(self):
        rng = random.Random(20260910)
        for i in range(40):
            length = rng.randint(2, 5)
            atoms = [f"p{k}" for k in range(length + 1)]
            rules = [{"id": f"r{k}", "premises": [atoms[k]], "conclusion": atoms[k + 1]}
                     for k in range(length)]
            rules.append({"id": "direct", "premises": [atoms[0]], "conclusion": atoms[-1]})
            rng.shuffle(rules)
            p = {"id": f"seeded_{i}", "facts": [atoms[0]], "rules": rules, "goal": atoms[-1]}
            for a, d, m in itertools.product(("instance", "schema"), ("shallow", "deep"), range(3)):
                audit = verify(p, simulate(p, a, d, m))
                self.assertTrue(audit["valid"], audit)
                self.assertEqual(audit["metrics"]["D"], 1 if d == "shallow" else length)

    def test_deterministic_replay(self):
        self.assertEqual(canonical(self.good()), canonical(self.good()))

    def test_summary_and_artifacts(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            summary = run_suite(self.problems, out)
            self.assertTrue(summary["pass"])
            self.assertEqual(summary["conditions"], 36)
            self.assertEqual(summary["contrasts"], 60)
            self.assertEqual(summary["negative_controls_rejected"], 42)
            self.assertTrue((out / "runs.json").exists())
            self.assertTrue((out / "metrics.csv").read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_cli_verify_exit_codes(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "trace.json"
            t = self.good()
            for valid in (True, False):
                if not valid:
                    t["problem_sha256"] = "wrong"
                path.write_text(json.dumps(t), encoding="utf-8")
                run = subprocess.run([sys.executable, str(ROOT / "adm_minimal.py"), "verify", "--trace", str(path)],
                                     capture_output=True, text=True, encoding="utf-8", timeout=15,
                                     env={**os.environ, "PYTHONUTF8": "1"})
                self.assertEqual(run.returncode, 0 if valid else 1, run.stderr)
            run = subprocess.run([sys.executable, str(ROOT / "adm_minimal.py"), "verify"],
                                 capture_output=True, text=True, encoding="utf-8", timeout=15,
                                     env={**os.environ, "PYTHONUTF8": "1"})
            self.assertEqual(run.returncode, 2)

    def test_no_network_or_llm_dependencies(self):
        tree = ast.parse((ROOT / "adm_minimal.py").read_text(encoding="utf-8"))
        allowed = {"__future__", "argparse", "copy", "csv", "hashlib", "itertools", "json", "re", "sys", "pathlib", "typing"}
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module.split(".")[0])
        self.assertLessEqual(imported, allowed)
        funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
        generator_calls = {n.func.id for name in ("simulate", "_plans", "_make_view", "_generator_ancestors")
                           for n in ast.walk(funcs[name]) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        verifier_calls = {n.func.id for n in ast.walk(funcs["verify"])
                          if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        self.assertNotIn("verify", generator_calls)
        self.assertTrue({"simulate", "_plans", "_make_view", "_generator_ancestors"}.isdisjoint(verifier_calls))

    def test_bad_shapes_fail_closed(self):
        mutations = [("nodes", None), ("nodes", [None]), ("views", []), ("reviews", [None]),
                     ("final", []), ("reviews", "M2")]
        for key, value in mutations:
            with self.subTest(key=key, value=value):
                t = self.good()
                t[key] = value
                self.rejected(t)


if __name__ == "__main__":
    unittest.main(verbosity=2)
