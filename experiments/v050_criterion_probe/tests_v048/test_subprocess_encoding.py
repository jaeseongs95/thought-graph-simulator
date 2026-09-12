from __future__ import annotations

import sys
import unittest

from test_support.subprocess_text import (
    SubprocessDecodeError,
    decode_process_bytes,
    run_text_process,
)


class SubprocessEncodingTests(unittest.TestCase):
    def test_ascii_is_stable(self):
        text, encoding = decode_process_bytes(b"PASS\n")
        self.assertEqual(text, "PASS\n")
        self.assertTrue(encoding)

    def test_cp949_korean_bytes_are_losslessly_decoded(self):
        raw = "검증 완료".encode("cp949")
        text, encoding = decode_process_bytes(raw)
        self.assertEqual(text, "검증 완료")
        self.assertEqual(encoding.lower().replace("_", "-"), "cp949")

    def test_python_child_stdout_stderr_are_forced_to_utf8(self):
        code = "import sys; print('표준출력 한글'); print('표준오류 한글', file=sys.stderr)"
        result = run_text_process([sys.executable, "-c", code], timeout=10)
        self.assertEqual(result.returncode, 0)
        self.assertIn("표준출력 한글", result.stdout)
        self.assertIn("표준오류 한글", result.stderr)
        self.assertEqual(result.stdout_encoding.lower().replace("_", "-"), "utf-8")
        self.assertEqual(result.stderr_encoding.lower().replace("_", "-"), "utf-8")

    def test_raw_cp949_child_output_does_not_raise_readerthread_unicode_error(self):
        code = (
            "import sys; "
            "sys.stdout.buffer.write('가나다'.encode('cp949')); "
            "sys.stderr.buffer.write('라마바'.encode('cp949'))"
        )
        result = run_text_process([sys.executable, "-c", code], timeout=10)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "가나다")
        self.assertEqual(result.stderr, "라마바")
        self.assertEqual(result.stdout_encoding.lower().replace("_", "-"), "cp949")
        self.assertEqual(result.stderr_encoding.lower().replace("_", "-"), "cp949")

    def test_undecodable_truncated_byte_raises_explicit_error(self):
        with self.assertRaises(SubprocessDecodeError):
            decode_process_bytes(b"\x81")


if __name__ == "__main__":
    unittest.main()
