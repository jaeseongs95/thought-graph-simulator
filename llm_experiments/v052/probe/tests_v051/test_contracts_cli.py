from __future__ import annotations
import copy,tempfile,unittest,sys
from pathlib import Path
from adm_pilot_v051.contracts import ContractError,wire,strict_json,decode_response,validate_payload
from test_support.subprocess_text import run_text_process
from .fixtures import sample_trace,envelope,MODEL,shared

class Contracts(unittest.TestCase):
    def test_duplicate_keys_rejected(self):
        with self.assertRaises(ContractError):strict_json('{"x":1,"x":2}')
    def test_nonfinite_rejected(self):
        for raw in ('{"x":NaN}','{"x":Infinity}','{"x":1e999}'):
            with self.assertRaises(ContractError):strict_json(raw)
    def test_valid_envelope(self):
        p=sample_trace();env=envelope(content=wire(p).decode());self.assertEqual(decode_response(wire(env),MODEL),p)
    def test_valid_json_with_schema_error_is_preserved_for_partial_measurement(self):
        p=sample_trace(m=2);p['reviews'][0]['finding']['gap_detected']='bad';env=envelope(content=wire(p).decode());self.assertEqual(decode_response(wire(env),MODEL),p)
        with self.assertRaises(ContractError):validate_payload(p)
    def test_wrong_model_rejected(self):
        env=envelope(content=wire(sample_trace()).decode());env['model']='other'
        with self.assertRaises(ContractError):decode_response(wire(env),MODEL)
    def test_length_truncation_rejected(self):
        env=envelope(content=wire(sample_trace()).decode());env['done_reason']='length'
        with self.assertRaises(ContractError):decode_response(wire(env),MODEL)
    def test_thinking_rejected(self):
        env=envelope(content=wire(sample_trace()).decode());env['message']['thinking']='hidden text'
        with self.assertRaises(ContractError):decode_response(wire(env),MODEL)
    def test_nonobject_rejected(self):
        env=envelope(content='[]')
        with self.assertRaises(ContractError):decode_response(wire(env),MODEL)
    def test_output_tag_not_hidden_in_content(self):
        env=envelope(content='<think>foo</think>{}')
        with self.assertRaises(ContractError):decode_response(wire(env),MODEL)

class CLI(unittest.TestCase):
    def command(self,*args):
        root=Path(__file__).resolve().parents[1]
        return run_text_process([sys.executable,'-m','adm_pilot_v051',*map(str,args)],cwd=root,timeout=90)
    def test_help(self):
        r=self.command('--help');self.assertEqual(r.returncode,0);self.assertIn('prepare',r.stdout)
    def test_prepare_and_show_in_korean_path(self):
        with tempfile.TemporaryDirectory(prefix='한글_계획_') as td:
            p=Path(td)/'외부계획.json';r=self.command('prepare','--baseline-bundle',shared()['bundle'],'--out',p)
            self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(self.command('show','--plan',p).returncode,0)
    def test_existing_plan_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'plan';p.write_bytes(b'keep');r=self.command('prepare','--baseline-bundle',shared()['bundle'],'--out',p)
            self.assertNotEqual(r.returncode,0);self.assertEqual(p.read_bytes(),b'keep')
    def test_missing_plan_fails(self):
        with tempfile.TemporaryDirectory() as td:
            r=self.command('run','--plan',Path(td)/'missing','--out',Path(td)/'run');self.assertNotEqual(r.returncode,0)
    def test_audit_cli(self):
        f=shared();r=self.command('audit','--plan',f['root']/'v51.plan','--run',f['root']/'v51.run');self.assertEqual(r.returncode,0,r.stderr)
    def test_run_audit_bundle_cli(self):
        with tempfile.TemporaryDirectory(prefix='실행_') as td:
            root=Path(td);p=root/'plan';run=root/'run';bundle=root/'evidence.zip'
            f=shared()
            for args in [('prepare','--baseline-bundle',f['bundle'],'--out',p),('run','--plan',p,'--out',run),('audit','--plan',p,'--run',run),('bundle','--plan',p,'--run',run,'--out',bundle)]:
                r=self.command(*args);self.assertEqual(r.returncode,0,r.stderr)
            self.assertTrue(bundle.is_file())
