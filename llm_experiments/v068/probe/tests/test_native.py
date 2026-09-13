"""Windows native stderr/exit code and Unicode/space arguments, without Ollama."""
import base64
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


@unittest.skipUnless(os.name == 'nt', 'Windows PowerShell native boundary')
class NativeBoundaryTests(unittest.TestCase):
    def test_stderr_is_preserved_and_exit_code_controls_outcome(self):
        with tempfile.TemporaryDirectory(prefix='v068 한글 공백 ') as temp:
            for code in (0, 7):
                log = Path(temp) / ('native_' + str(code) + '.log')
                script = "import sys; print('한글 공백 stdout'); print('native stderr', file=sys.stderr); sys.exit(" + str(code) + ")"
                ps = "$ErrorActionPreference = 'Stop'; $ProgressPreference = 'SilentlyContinue'; [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false); . " + literal(ROOT / 'windows/native.ps1')
                ps += '; $code = Invoke-PythonCapture -Executable ' + literal(sys.executable)
                ps += " -ToolArgs @('-X','utf8','-B','-c'," + literal(script) + ')'
                ps += ' -WorkDir ' + literal(temp) + ' -Log ' + literal(log) + '; exit $code'
                encoded = base64.b64encode(ps.encode('utf-16-le')).decode()
                result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-OutputFormat', 'Text', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', encoded], capture_output=True)
                self.assertEqual(result.returncode, code, result.stderr.decode('utf-8', errors='replace'))
                self.assertIn('한글 공백 stdout', result.stdout.decode('utf-8'))
                self.assertIn('native stderr', result.stderr.decode('utf-8'))
                saved = log.read_bytes()
                self.assertFalse(saved.startswith(b'\xef\xbb\xbf'))
                self.assertNotIn(b'\r\n', saved)
                self.assertIn('한글 공백 stdout', saved.decode('utf-8'))


if __name__ == '__main__': unittest.main()
