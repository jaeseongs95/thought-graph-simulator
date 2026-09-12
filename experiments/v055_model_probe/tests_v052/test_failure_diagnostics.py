import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from adm_diagnostic_v052.__main__ import main
from adm_diagnostic_v052.contracts import ContractError
from adm_diagnostic_v052.runner import _failure_kind


class FailureDiagnostics(unittest.TestCase):
    def test_failure_kind_preflight_metadata(self):
        self.assertEqual(_failure_kind('preflight_metadata', ContractError('x'), {}), 'runtime_metadata_error')

    def test_failure_kind_preflight_identity(self):
        self.assertEqual(_failure_kind('preflight_identity', ContractError('x'), {}), 'runtime_identity_error')

    def test_failure_kind_inference_transport(self):
        self.assertEqual(_failure_kind('inference', ContractError('통신 오류. 원문 보존, 자동 재시도 없음: x'), {}), 'transport_error')

    def test_cli_exit3_surfaces_run_error(self):
        report={
            'data_integrity':True,'data_complete':False,'comparative_analysis_ready':False,
            'evidence_kind':'live_source_artifacts','inference_calls':0,'max_inference_calls':440,
            'run_state':'incomplete','failure_stage':'preflight_metadata',
            'failure_kind':'runtime_metadata_error','failure_slot_id':None,
            'run_error':'ContractError: synthetic connection refused',
        }
        with tempfile.TemporaryDirectory() as td, patch('adm_diagnostic_v052.runner.execute',return_value=report):
            out=io.StringIO();err=io.StringIO()
            with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
                code=main(['run','--plan',str(Path(td)/'plan.json'),'--out',str(Path(td)/'run')])
        self.assertEqual(code,3)
        self.assertIn('preflight_metadata',out.getvalue())
        self.assertIn('runtime_metadata_error',out.getvalue())
        self.assertIn('synthetic connection refused',out.getvalue())
        self.assertIn('실행 중단 원인:',err.getvalue())


if __name__=='__main__':
    unittest.main()
