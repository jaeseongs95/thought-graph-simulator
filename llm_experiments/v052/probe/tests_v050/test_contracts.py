from __future__ import annotations
import copy,unittest
from criterion_probe_v050.contracts import *
from criterion_probe_v050.dataset import cases
from criterion_probe_v050.scoring import expected
from tests_v048.fixtures import envelope,MODEL

class Contracts(unittest.TestCase):
    def test_witness_valid(self):
        p=expected(cases()[0]);self.assertEqual(decode_response(wire(envelope(content=wire(p).decode())),MODEL,'oneshot_original'),p)
    def test_extract_valid(self):
        p=expected(cases()[0]);p.pop('finding');self.assertEqual(decode_response(wire(envelope(content=wire(p).decode())),MODEL,'extract'),p)
    def test_duplicate_keys(self):
        with self.assertRaises(ContractError):strict_json('{"value":true,"value":false}')
    def test_nonfinite(self):
        for s in ('NaN','Infinity','1e999'):
            with self.subTest(s=s),self.assertRaises(ContractError):strict_json(s)
    def test_value_wrong_types(self):
        for v in (0,1,'true',None,[],{}):
            with self.subTest(v=v),self.assertRaises(ContractError):decode_response(wire(envelope(content=wire({'value':v}).decode())),MODEL,'not')
    def test_extra_payload_key(self):
        with self.assertRaises(ContractError):decode_response(wire(envelope(content='{"value":true,"extra":1}')),MODEL,'not')
    def test_trailing_prose(self):
        with self.assertRaises(ContractError):decode_response(wire(envelope(content='{"value":true} done')),MODEL,'not')
    def test_truncation(self):
        e=envelope();e['done_reason']='length'
        with self.assertRaises(ContractError):decode_response(wire(e),MODEL,'not')
    def test_wrong_model(self):
        with self.assertRaises(ContractError):decode_response(wire(envelope(model='other')),MODEL,'not')
    def test_thinking_channel(self):
        e=envelope();e['message']['thinking']='something'
        with self.assertRaises(ContractError):decode_response(wire(e),MODEL,'not')
    def test_tool_calls(self):
        e=envelope();e['message']['tool_calls']=[{}]
        with self.assertRaises(ContractError):decode_response(wire(e),MODEL,'not')
    def test_observed_string_not_coerced(self):
        p=expected(cases()[0]);p['observed']['goal_atom']=1
        with self.assertRaises(ContractError):validate_payload(p,WITNESS_SCHEMA)
    def test_empty_facts_not_filled(self):
        p=expected(cases()[0]);p['observed']['facts']=[]
        with self.assertRaises(ContractError):validate_payload(p,WITNESS_SCHEMA)
    def test_semantically_wrong_payload_is_retained(self):
        p=expected(cases()[0]);p['primitives']['same_as_goal']=not p['primitives']['same_as_goal']
        validate_payload(p,WITNESS_SCHEMA)
    def test_schema_does_not_contain_answer_const_or_enum(self):
        self.assertNotIn('"const"',wire(WITNESS_SCHEMA).decode());self.assertNotIn('"enum"',wire(WITNESS_SCHEMA).decode())
    def test_missing_usage_stays_null(self):self.assertIsNone(usage(b'{}')['prompt_eval_count'])
