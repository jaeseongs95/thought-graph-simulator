from __future__ import annotations
import contextlib
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from paired_probe_v048.__main__ import bundle
from paired_probe_v048.contracts import ContractError, read_json, sha
from tests_v048.fixtures import build_v047, fake_server, experiment
from test_support.subprocess_text import run_text_process

ROOT=Path(__file__).resolve().parent.parent

def command(*args):
    return run_text_process([sys.executable,'-m','paired_probe_v048',*map(str,args)], cwd=ROOT, timeout=45)


class CliTests(unittest.TestCase):
    def test_help_does_not_require_ollama(self):
        result=command('--help');self.assertEqual(result.returncode,0);self.assertIn('prepare',result.stdout)
    def test_missing_anchor_is_cli_error(self):
        result=command('prepare','--baseline-run','unused','--out','unused.json')
        self.assertEqual(result.returncode,2)
    def test_prepare_show_run_audit_bundle_subprocess(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            with fake_server() as (state,endpoint):
                oldplan,oldrun=build_v047(root,endpoint);state.requests.clear();state.mode='original_false'
                plan=root/'new.plan.json';out=root/'run';archive=root/'evidence.zip'
                result=command('prepare','--baseline-run',oldrun,'--baseline-plan',oldplan,'--seeds','101','--out',plan)
                self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(len(state.requests),0)
                result=command('show','--plan',plan);self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(len(state.requests),0)
                result=command('run','--plan',plan,'--out',out);self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(len(state.requests),96)
            result=command('audit','--plan',plan,'--run',out)
            self.assertEqual(result.returncode,0,result.stderr)
            result=command('bundle','--plan',plan,'--run',out,'--out',archive)
            self.assertEqual(result.returncode,0,result.stderr)
            with zipfile.ZipFile(archive) as z:
                manifest=json.loads(z.read('BUNDLE_MANIFEST.json'))
                for name,digest in manifest['file_hashes'].items(): self.assertEqual(sha(z.read(name)),digest)
    def test_bundle_refuses_overwrite(self):
        with experiment() as (root,_,plan,_,out,_):
            path=root/'evidence.zip';bundle(plan,out,path)
            with self.assertRaises(ContractError):bundle(plan,out,path)
    def test_bundle_refuses_inside_run_path(self):
        with experiment() as (_,_,plan,_,out,_):
            with self.assertRaises(ContractError):bundle(plan,out,out/'evidence.zip')
    def test_cli_returns_three_for_incomplete(self):
        with experiment('http_error') as (_,_,plan,_,out,_):
            result=command('audit','--plan',plan,'--run',out)
            self.assertEqual(result.returncode,3,result.stderr)
    def test_cli_returns_two_for_integrity_failure(self):
        with experiment() as (_,_,plan,_,out,_):
            next((out/'calls').rglob('response.raw.json')).write_bytes(b'{}')
            result=command('audit','--plan',plan,'--run',out)
            self.assertEqual(result.returncode,2)
            self.assertFalse(read_json(out/'audit.json')['data_integrity'])
