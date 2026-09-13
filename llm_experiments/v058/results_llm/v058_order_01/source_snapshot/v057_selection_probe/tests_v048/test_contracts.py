from __future__ import annotations
import ast
import itertools
import unittest
from pathlib import Path
from paired_probe_v048.contracts import ContractError, strict_json, wire, decode_response, usage
from paired_probe_v048.oracle import evaluate, score_pipeline
from paired_probe_v048.runner import endpoint_base
from tests_v048.fixtures import envelope, MODEL


class ContractTests(unittest.TestCase):
    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(ContractError): strict_json('{"value":true,"value":false}')
    def test_nan_and_infinity_rejected(self):
        for source in ('NaN','Infinity','-Infinity','1e999','-1e999'):
            with self.subTest(source=source),self.assertRaises(ContractError): strict_json(source)
    def test_finite_float_remains_valid(self):
        self.assertEqual(strict_json('0.7'),0.7)
    def test_schema_invalid_payloads_rejected(self):
        for source in ('{"value":1}','{"value":0}','{"value":"true"}','{"value":null}',
                       '{"value":true,"extra":false}','true','[]','{"value":true,"value":false}'):
            with self.subTest(source=source),self.assertRaises(ContractError):
                decode_response(wire(envelope(content=source)),MODEL)
    def test_nonfinite_usage_is_missing_not_zero(self):
        values=usage(b'{"prompt_eval_count":1e999}')
        self.assertIsNone(values["prompt_eval_count"])
    def test_usage_negative_and_bool_not_integer_counts(self):
        values=usage(b'{"eval_count":true,"prompt_eval_count":-1}')
        self.assertIsNone(values["eval_count"]);self.assertIsNone(values["prompt_eval_count"])
    def test_256_output_bit_patterns(self):
        inputs=list(itertools.product((False,True),repeat=2))
        trace_all=0; final_all_wrong_trace=0
        for bits in itertools.product((False,True),repeat=8):
            scores=[score_pipeline(a,b,bits[2*i],bits[2*i+1]) for i,(a,b) in enumerate(inputs)]
            all_final=all(s["final_correct"] for s in scores)
            all_trace=all(s["trace_correct"] for s in scores)
            trace_all+=all_trace
            final_all_wrong_trace+=all_final and not all_trace
        self.assertEqual(trace_all,1);self.assertEqual(final_all_wrong_trace,15)
    def test_parser_matches_manual_truth_table(self):
        expected={(False,False):False,(False,True):False,(True,False):True,(True,True):False}
        for pair,result in expected.items():
            for expression in ('(a AND (NOT b))','((NOT b) AND a)'):
                self.assertIs(evaluate(expression,*pair),result)
    def test_parser_rejects_unknown_operator(self):
        with self.assertRaises(ContractError): evaluate('a OR b',True,False)
    def test_loopback_only_no_external_endpoint(self):
        for url in ('https://example.com','http://192.168.0.1:11434','http://127.0.0.1@evil.test',
                    'http://127.0.0.1:11434/api/chat?x=1','file:///tmp/server','http://localhost/api/pull'):
            with self.subTest(url=url),self.assertRaises(ContractError): endpoint_base(url)
    def test_loopback_localhost_ipv4_ipv6(self):
        for url in ('http://127.0.0.1:11434','http://localhost:11434/api/chat','http://[::1]:11434/api/chat'):
            self.assertTrue(endpoint_base(url).startswith('http://'))
    def test_runner_never_imports_oracle(self):
        root=Path(__file__).resolve().parent.parent/'paired_probe_v048'
        tree=ast.parse((root/'runner.py').read_text(encoding='utf-8'))
        imports=[n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
        self.assertNotIn('oracle',imports)
    def test_plan_never_uses_truth_evaluation_to_build_requests(self):
        root=Path(__file__).resolve().parent.parent/'paired_probe_v048'
        tree=ast.parse((root/'plan.py').read_text(encoding='utf-8'))
        target=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='make_request')
        names={n.id for n in ast.walk(target) if isinstance(n,ast.Name)}
        self.assertFalse(names.intersection({'evaluate','TABLE','AND_TABLE','score_pipeline'}))
