"""v0.4.4.1: Windows CRLF/LF provenance compatibility regression tests. LLM/network 없음."""
from __future__ import annotations

import copy
import tempfile
import unittest
import zipfile
from pathlib import Path

from local_llm.common import (
    PACKAGE,
    ContractError,
    core_identity_compatibility,
    load_core,
    source_text_identity,
)
from local_llm.decision_source import load_decision_source
from local_llm import factor_probe as fp
from local_llm.decision_probe import validate_runtime


class V0441CoreIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name) / "original"
        with zipfile.ZipFile(PACKAGE / "tests/fixtures/v043_decision_run.zip") as z:
            z.extractall(cls.root)
        cls.core, cls.info = load_core()
        cls.core_bytes = Path(cls.core.__file__).read_bytes()
        text = cls.core_bytes.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
        cls.lf = text.encode("utf-8")
        cls.crlf = text.replace("\n", "\r\n").encode("utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_lf_and_crlf_are_same_source_identity(self):
        a = source_text_identity(self.lf)
        b = source_text_identity(self.crlf)
        result = core_identity_compatibility(a, b)
        self.assertTrue(result["same_source"])
        self.assertTrue(result["representation_diff_only"])
        self.assertNotEqual(a["sha256"], b["sha256"])
        self.assertEqual(a["normalized_git_blob_sha1"], b["normalized_git_blob_sha1"])

    def test_utf8_bom_and_lf_are_same_source_identity(self):
        a = source_text_identity(self.lf)
        b = source_text_identity(b"\xef\xbb\xbf" + self.lf)
        result = core_identity_compatibility(a, b)
        self.assertTrue(result["same_source"])
        self.assertTrue(result["representation_diff_only"])

    def test_real_source_edit_is_rejected(self):
        a = source_text_identity(self.lf)
        b = source_text_identity(self.lf + b"\n# actual semantic source edit\n")
        self.assertFalse(core_identity_compatibility(a, b)["same_source"])

    def test_decision_source_accepts_crlf_current_identity(self):
        # v043 snapshot is the original LF source. Simulate the user's Windows
        # working tree identity without executing a modified core module.
        current = copy.deepcopy(self.info)
        current.update(source_text_identity(self.crlf))
        data = load_decision_source(self.core, current, self.root)
        compat = data["core_compatibility"]
        self.assertTrue(compat["same_source"])
        self.assertTrue(compat["representation_diff_only"])
        self.assertEqual(data["validation"]["records_replayed"], 8)

    def test_decision_source_rejects_real_core_edit(self):
        current = copy.deepcopy(self.info)
        current.update(source_text_identity(self.lf + b"\n# real source edit\n"))
        with self.assertRaises(ContractError):
            load_decision_source(self.core, current, self.root)

    def test_factor_runtime_accepts_crlf_current_identity(self):
        current = copy.deepcopy(self.info)
        current.update(source_text_identity(self.crlf))
        source = load_decision_source(self.core, current, self.root)
        plan = fp.build_plan(source)
        frozen = source["manifest"]["frozen"]
        validate_runtime(plan, current, frozen["config"], source["manifest"]["ollama_metadata"])


if __name__ == "__main__":
    unittest.main()
