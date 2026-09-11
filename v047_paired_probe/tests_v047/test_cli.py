from __future__ import annotations
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from paired_probe_v047.__main__ import main
from paired_probe_v047.contracts import ContractError, digest, read_json, write_json
from paired_probe_v047.plan import prepare, validate_plan
from tests_v047.fixtures import baseline, fake_server

class CliTests(unittest.TestCase):
    def test_actual_subprocess_prepare_show_run_audit(self):
        with tempfile.TemporaryDirectory() as temp, fake_server("original_false") as (state, endpoint):
            root = Path(temp); baseline(root, endpoint)
            p = root / "plan.json"; out = root / "run"
            workdir = Path(__file__).resolve().parent.parent
            commands = [
                ["prepare", "--source-root", str(root), "--out", str(p), "--cycles", "1"],
                ["show", "--plan", str(p)],
                ["run", "--plan", str(p), "--out", str(out)],
                ["audit", "--plan", str(p), "--run", str(out)],
            ]
            for args in commands:
                result = subprocess.run([sys.executable, "-m", "paired_probe_v047", *args],
                    cwd=workdir, capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(state.requests), 16)
            r = read_json(out / "summary.json")
            self.assertEqual(r["arms"]["original"]["final_correct"], 3)
            self.assertFalse(r["new_model_inference"])
    def test_missing_input_exit_two(self):
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["show", "--plan", str(Path(temp) / "absent.json")]), 2)
    def test_resealed_zero_cycle_plan_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); baseline(root)
            p = prepare(root, root / "plan.json")
            p.update(cycles=0, blocks=[], max_calls=0)
            p.pop("plan_sha256"); p["plan_sha256"] = digest(p)
            with self.assertRaises(ContractError):
                validate_plan(p)
    def test_resealed_fixture_label_change_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); baseline(root)
            p = prepare(root, root / "plan.json")
            p["baseline"]["evidence_kind"] = "live_source_artifacts"
            p.pop("plan_sha256"); p["plan_sha256"] = digest(p)
            with self.assertRaises(ContractError):
                validate_plan(p)
    def test_empty_source_is_not_success(self):
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["prepare", "--source-root", temp, "--out", str(Path(temp) / "p.json")]), 2)
