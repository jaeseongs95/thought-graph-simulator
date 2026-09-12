from __future__ import annotations
import copy
import itertools
import unittest
from paired_probe_v047.contracts import ContractError, EXPRS, decode_response, strict_json, usage, wire
from paired_probe_v047.oracle import TABLE, evaluate, score_pipeline
from tests_v047.fixtures import MODEL, envelope

class ContractTests(unittest.TestCase):
    def test_valid_bools(self):
        for value in (True, False):
            self.assertIs(decode_response(wire(envelope(value)), MODEL)["value"], value)
    def test_eight_bad_payloads(self):
        bad = ['{"value":1}', '{"value":"true"}', '{"value":null}',
               '{"value":true,"value":false}', '{"value":false,"extra":1}',
               '[false]', '{}', '```json\n{"value":false}\n```']
        for text in bad:
            with self.subTest(text=text), self.assertRaises(ContractError):
                decode_response(wire(envelope(content=text)), MODEL)
    def test_duplicate_envelope_key(self):
        with self.assertRaises(ContractError):
            strict_json('{"model":"a","model":"b"}')
    def test_non_finite(self):
        for text in ('NaN', 'Infinity', '-Infinity'):
            with self.subTest(text=text), self.assertRaises(ContractError):
                strict_json(text)
    def test_trailing_data(self):
        with self.assertRaises(ContractError):
            strict_json('{"value":false} x')
    def test_wrong_model(self):
        with self.assertRaises(ContractError):
            decode_response(wire(envelope(model="other")), MODEL)
    def test_incomplete_done(self):
        r = envelope(); r["done"] = False
        with self.assertRaises(ContractError):
            decode_response(wire(r), MODEL)
    def test_length_stop(self):
        r = envelope(); r["done_reason"] = "length"
        with self.assertRaises(ContractError):
            decode_response(wire(r), MODEL)
    def test_wrong_role(self):
        r = envelope(); r["message"]["role"] = "user"
        with self.assertRaises(ContractError):
            decode_response(wire(r), MODEL)
    def test_thinking_channel(self):
        r = envelope(); r["message"]["thinking"] = "hidden calculation"
        with self.assertRaises(ContractError):
            decode_response(wire(r), MODEL)
    def test_empty_thinking_allowed(self):
        r = envelope(); r["message"]["thinking"] = ""
        self.assertIs(decode_response(wire(r), MODEL)["value"], False)
    def test_tool_calls(self):
        r = envelope(); r["message"]["tool_calls"] = [{"function": "x"}]
        with self.assertRaises(ContractError):
            decode_response(wire(r), MODEL)
    def test_unknown_usage_stays_null(self):
        r = envelope(); del r["eval_count"]
        self.assertIsNone(usage(wire(r))["eval_count"])
    def test_usage_bool_not_int(self):
        r = envelope(); r["eval_count"] = True
        self.assertIsNone(usage(wire(r))["eval_count"])
    def test_wire_preserves_key_order(self):
        self.assertEqual(wire({"b": False, "a": True}), b'{"b":false,"a":true}')

class OracleTests(unittest.TestCase):
    def test_all_expressions_and_inputs(self):
        for (a, b), (final, parent) in TABLE.items():
            for expr in (EXPRS["original"], EXPRS["commuted"]):
                self.assertIs(evaluate(expr, a, b), final)
            self.assertIs(evaluate(EXPRS["not"], a, b), parent)
            self.assertIs(evaluate(EXPRS["and"], a, b), a and b)
    def test_short_circuit_does_not_skip_parsing(self):
        self.assertIs(evaluate('(a AND (NOT b))', False, False), False)
    def test_invalid_expressions(self):
        for expr in ('', 'a OR b', '(a AND b', 'a AND b)', 'a b', '__import__("os")', 'a AND'):
            with self.subTest(expr=expr), self.assertRaises(ContractError):
                evaluate(expr, True, False)
    def test_bool_not_int_input(self):
        with self.assertRaises(ContractError):
            evaluate('a', 1, False)
    def test_false_parent_and_coincidentally_correct_final_rejected(self):
        r = score_pipeline(False, False, False, False)
        self.assertTrue(r["final_correct"]); self.assertFalse(r["trace_correct"])
    def test_all_16_per_case_states(self):
        tested = 0
        for a, b in TABLE:
            for parent, final in itertools.product((False, True), repeat=2):
                r = score_pipeline(a, b, parent, final)
                self.assertEqual(r["trace_correct"], parent is TABLE[a, b][1] and final is TABLE[a, b][0])
                tested += 1
        self.assertEqual(tested, 16)
    def test_all_256_pipeline_bit_patterns(self):
        fully_correct = 0; final_all_correct_bad_trace = 0
        for bits in itertools.product((False, True), repeat=8):
            rows = [score_pipeline(a, b, bits[2 * i], bits[2 * i + 1]) for i, (a, b) in enumerate(TABLE)]
            strict = all(r["trace_correct"] for r in rows)
            final = all(r["final_correct"] for r in rows)
            fully_correct += strict; final_all_correct_bad_trace += final and not strict
        self.assertEqual(fully_correct, 1)
        self.assertEqual(final_all_correct_bad_trace, 15)
    def test_missing_parent_not_true(self):
        self.assertFalse(score_pipeline(True, False, None, True)["trace_correct"])
