"""v0.4.5 원문 회귀·진리표·변조·모의 API 시험. 실제 LLM/네트워크 없음."""
from __future__ import annotations
import contextlib
import copy
import io
import itertools
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

from local_llm import operator_probe as op
from local_llm.client import Reply
from local_llm.common import (PACKAGE, ContractError, core_identity_compatibility, digest, load_core,
                              read_json, source_text_identity, wire_json)
from local_llm.decision_table import summary_markdown
from local_llm.factor_audit import load_factor_source
from local_llm.runner import assess_response, request_body, run

# 검사 대상 함수/표를 호출해 정답을 생성하지 않는 독립 시험표.
ORACLE = {
    (False, False): {'copy_a': False, 'and_ab': False, 'not_b': True, 'and_not_b': False},
    (False, True): {'copy_a': False, 'and_ab': False, 'not_b': False, 'and_not_b': False},
    (True, False): {'copy_a': True, 'and_ab': False, 'not_b': True, 'and_not_b': True},
    (True, True): {'copy_a': True, 'and_ab': True, 'not_b': False, 'and_not_b': False}}


class V045Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        with zipfile.ZipFile(PACKAGE / 'tests/fixtures/v044_factor_run.zip') as z:
            z.extractall(cls.root / 'source')
        cls.path = cls.root / 'source/v044_factor_01'
        cls.core, cls.info = load_core()
        cls.source = load_factor_source(cls.core, cls.info, cls.path)
        cls.cfg = cls.source['manifest']['frozen']['config']
        cls.meta = cls.source['manifest']['ollama_metadata']
        cls.plan = op.build_plan(cls.source)
        cls.problems = {p['id']: p for p in cls.plan['problems']}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def response(self, case, value):
        return {'model': self.cfg['model'], 'done': True, 'done_reason': 'stop',
                'message': {'role': 'assistant', 'content': wire_json({'value': value})},
                'eval_count': 8, 'prompt_eval_count': 60}

    def evaluate(self, case, value):
        body = request_body(self.cfg, case, self.problems[case['problem_id']])
        return assess_response(self.core, self.problems[case['problem_id']], case,
                               self.plan['reference_depths'][case['problem_id']], body,
                               self.response(case, value), self.cfg['mode_policy'])[0]

    def oracle(self, c):
        return ORACLE[c['input_literals']['a'], c['input_literals']['b']][c['operation']]

    def test_original_16_decisions_unchanged(self):
        self.assertEqual(self.source['validation']['records_replayed'], 16)
        self.assertEqual(sum(r['status'] == 'accepted' for r in self.source['records']), 12)

    def test_36_sources_and_raw_requests_checked(self):
        self.assertEqual(self.source['validation']['source_files_checked'], 36)
        self.assertEqual(self.source['validation']['request_wires_reproduced'], 16)
        self.assertFalse(self.source['validation']['snapshot_code_executed'])

    def test_crlf_core_remains_compatible(self):
        data = Path(self.core.__file__).read_bytes().decode('utf-8-sig').replace('\r\n', '\n')
        info = dict(self.info, **source_text_identity(data.replace('\n', '\r\n').encode('utf-8')))
        d = load_factor_source(self.core, info, self.path)
        self.assertTrue(d['core_compatibility']['same_source'])

    def test_actual_core_edit_rejected(self):
        info = dict(self.info, **source_text_identity(Path(self.core.__file__).read_bytes() + b'\n# changed\n'))
        with self.assertRaises(ContractError):
            load_factor_source(self.core, info, self.path)

    def test_missing_hash_does_not_authorize_identity(self):
        for left, right in (({}, {}), ({'sha256': None}, {'sha256': None}),
                            ({'sha256': ''}, {'sha256': ''}),
                            ({'git_blob_sha1': 'bad'}, {'git_blob_sha1': 'bad'})):
            self.assertFalse(core_identity_compatibility(left, right)['same_source'])

    def test_valid_legacy_sha256_fallback(self):
        self.assertTrue(core_identity_compatibility({'sha256': 'a'*64}, {'sha256': 'a'*64})['same_source'])
        self.assertFalse(core_identity_compatibility({'sha256': 'a'*64}, {'sha256': 'b'*64})['same_source'])

    def changed_file_rejected(self, path):
        data = path.read_bytes()
        try:
            path.write_bytes(data + b' ')
            with self.assertRaises(ContractError):
                load_factor_source(self.core, self.info, self.path)
        finally:
            path.write_bytes(data)

    def test_response_tamper_rejected(self):
        self.changed_file_rejected(next((self.path/'cases').glob('*/response.raw.json')))

    def test_request_wire_tamper_rejected(self):
        self.changed_file_rejected(next((self.path/'cases').glob('*/request.wire.json')))

    def test_snapshot_tamper_rejected(self):
        self.changed_file_rejected(self.path/'source_snapshot/factor_probe.py')

    def test_core_snapshot_tamper_rejected(self):
        self.changed_file_rejected(self.path/'source_snapshot/adm_minimal.py')

    def test_manifest_tamper_rejected(self):
        p = self.path/'manifest.json'; data = p.read_bytes()
        try:
            m = json.loads(data);m['frozen']['config']['options']['temperature'] = 0
            p.write_text(json.dumps(m), encoding='utf-8')
            with self.assertRaises(ContractError):load_factor_source(self.core, self.info, self.path)
        finally:p.write_bytes(data)

    def test_missing_record_rejected(self):
        p = next((self.path/'cases').glob('*/record.json'));data = p.read_bytes()
        try:
            p.unlink()
            with self.assertRaises(ContractError):load_factor_source(self.core, self.info, self.path)
        finally:p.write_bytes(data)

    def test_b_last_partial_change_not_lost_in_total(self):
        d = self.source['tables']['b_last']
        self.assertEqual(d['correct_full_rows'], 3)
        self.assertEqual(d['correct_bits'], 11)
        self.assertEqual(d['false_acceptance_count'], 0)
        self.assertEqual(d['per_field']['proof_and_goal_accepts']['correct'], 4)
        self.assertEqual(d['per_field']['gap_detected']['positive_detected'], 0)
        self.assertEqual(d['final_field_inconsistency_count'], 1)

    def test_other_arms_ten_bits_and_one_false_acceptance(self):
        for name in ('replay', 'json', 'neutral_keys'):
            d = self.source['tables'][name]
            self.assertEqual(d['correct_bits'], 10)
            self.assertEqual(d['false_acceptance_count'], 1)
            self.assertTrue(d['all_four_rows_match_ignore_b_shortcut'])

    def test_summary_table_has_four_contiguous_rows(self):
        text = summary_markdown(self.source['tables'])
        lines = text.splitlines(); start = next(i for i, x in enumerate(lines) if x.startswith('| ---'))
        self.assertTrue(all(x.startswith('| ') for x in lines[start+1:start+5]))
        self.assertIn('gap 양성', text)

    def test_plan_16_fixed_inputs_no_success_selection(self):
        self.assertEqual(self.plan['assigned_calls'], 16)
        for name in op.OPERATIONS:
            cc = [c for c in self.plan['cases'] if c['operation'] == name]
            self.assertEqual(len(cc), 4)
            self.assertEqual({tuple(c['input_literals'].values()) for c in cc}, set(ORACLE))
            self.assertEqual(sum(c['source_status'] != 'accepted' for c in cc), 1)

    def test_plan_deterministic_case_ids(self):
        self.assertEqual(self.plan, op.build_plan(self.source))
        for c in self.plan['cases']:
            self.assertEqual(digest({k:v for k,v in c.items() if k!='case_id'})[:24], c['case_id'])

    def test_schema_allows_both_values_and_no_oracle(self):
        from local_llm.protocol import validate_schema
        for value in (False, True):validate_schema({'value': value}, op.SCHEMA)
        text = wire_json(op.SCHEMA)
        self.assertNotIn('const', text);self.assertNotIn('enum', text)
        for c in self.plan['cases']:
            b = op.make_request(self.cfg, c, None)
            self.assertNotIn('expected', wire_json(b))
            self.assertEqual(b['format'], {'type':'object', 'properties':{'value':{'type':'boolean'}},
                                          'required':['value'], 'additionalProperties':False})

    def test_source_values_projected_not_replaced(self):
        for c in self.plan['cases']:
            self.assertEqual(c['input_literals'], {'a':c['source_projection']['primitives']['same_as_goal'],
                                                  'b':c['source_projection']['primitives']['in_facts']})

    def test_changed_projection_rejected(self):
        c = copy.deepcopy(self.plan['cases'][0]);c['input_literals']['a'] = not c['input_literals']['a']
        with self.assertRaises(ContractError):op.make_request(self.cfg, c, None)

    def test_incorrect_previous_model_values_not_rescued(self):
        c = copy.deepcopy(self.plan['cases'][0])
        c['source_projection']['primitives']['in_facts'] = not c['source_projection']['primitives']['in_facts']
        c['input_literals']['b'] = c['source_projection']['primitives']['in_facts']
        result = self.evaluate(c, self.oracle(c))
        self.assertEqual(result['status'], 'invalid_task')
        self.assertFalse(result['audit']['task_checks']['source.primitives'])

    def test_each_operator_two_outputs_32_cases(self):
        for c in self.plan['cases']:
            for v in (False, True):
                out = self.evaluate(c, v)
                self.assertEqual(out['status']=='accepted', v==self.oracle(c))

    def test_string_number_null_not_booleans(self):
        for v in ('true', 'false', 0, 1, None, []):
            self.assertEqual(self.evaluate(self.plan['cases'][0], v)['status'], 'protocol_error')

    def test_schema_json_none_differ_only_format(self):
        for original in self.plan['cases']:
            bodies = []
            for mode in ('schema','json','none'):
                c = dict(original, format_mode=mode)
                body = op.make_request(self.cfg,c,None);body.pop('format',None);bodies.append(wire_json(body))
            self.assertEqual(len(set(bodies)),1)

    def test_operator_prompts_same_except_expression(self):
        cc = [c for c in self.plan['cases'] if c['input_literals']=={'a':True,'b':False}]
        bodies = []
        for c in cc:
            b = op.make_request(self.cfg,c,None)
            inp = json.loads(b['messages'][1]['content'].split(': ',1)[1]);inp['expression']='OP'
            b['messages'][1]['content']='input: '+wire_json(inp);bodies.append(wire_json(b))
        self.assertEqual(len(set(bodies)),1)

    def test_truncation_not_accepted_even_correct_json(self):
        c=self.plan['cases'][0];raw=self.response(c,self.oracle(c));raw['done_reason']='length'
        body=request_body(self.cfg,c,self.problems[c['problem_id']])
        out,_=assess_response(self.core,self.problems[c['problem_id']],c,{},body,raw,self.cfg['mode_policy'])
        self.assertEqual(out['status'],'truncated')

    def test_runtime_checks_same_model_and_source(self):
        op.validate_runtime(self.plan,self.info,self.cfg,self.meta)
        bad=copy.deepcopy(self.meta);bad['tag']['digest']='x'
        with self.assertRaises(ContractError):op.validate_runtime(self.plan,self.info,self.cfg,bad)

    def test_explicit_comparison_model_separate_checkpoint(self):
        plan=op.build_plan(self.source,comparison_model='installed-other-instruct')
        config=copy.deepcopy(self.cfg);config['model']='installed-other-instruct'
        op.validate_runtime(plan,self.info,config,self.meta)
        config['options']['temperature']=0
        with self.assertRaises(ContractError):op.validate_runtime(plan,self.info,config,self.meta)

    def test_comparison_model_no_thinking_switch(self):
        plan=op.build_plan(self.source,comparison_model='other');config=copy.deepcopy(self.cfg)
        config['model']='other';config['mode_policy']['resolved_mode']='thinking'
        with self.assertRaises(ContractError):op.validate_runtime(plan,self.info,config,self.meta)

    def test_plan_only_calls_no_network(self):
        with patch('local_llm.client.OllamaClient', side_effect=AssertionError('network')), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(op.main(['--input',str(self.path),'--plan-only']),0)

    def mock_run(self, out, flip_gap=False):
        client=Mock();client.inspect.return_value=self.meta;client.tag.return_value=self.meta['tag']
        client.running_model.return_value=self.meta['tag'];replies=[]
        for c in self.plan['cases']:
            value=self.oracle(c)
            if flip_gap and c['operation']=='and_not_b' and c['input_literals']=={'a':True,'b':False}:
                value=False
            raw=self.response(c,value);replies.append(Reply(raw,wire_json(raw),0.01))
        client.chat.side_effect=replies
        with patch('local_llm.runner.OllamaClient',return_value=client), \
             patch('local_llm.runner.environment',return_value={'nvidia_smi':None}), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(run(self.core,self.info,self.plan,copy.deepcopy(self.cfg),out),0)
            self.assertEqual(client.chat.call_count,16)
            self.assertEqual(run(self.core,self.info,self.plan,copy.deepcopy(self.cfg),out,resume=True),0)
            self.assertEqual(client.chat.call_count,16)
        return read_json(out/'operator_probe.json')

    def test_mock_all_16_success_and_resume_no_calls(self):
        d=self.mock_run(self.root/'all_success')
        self.assertTrue(d['all_atomic_correct']);self.assertEqual(d['conditional_assembly_successes'],4)

    def test_mock_failed_gap_preserved_no_not_auto_repair(self):
        d=self.mock_run(self.root/'failed_gap',flip_gap=True)
        self.assertEqual(d['groups']['not_b']['accepted'],4)
        self.assertEqual(d['groups']['and_not_b']['accepted'],3)
        self.assertEqual(d['conditional_assembly_successes'],3)
        row=next(r for r in d['conditional_assemblies'] if r['input_ab']==[True,False])
        self.assertEqual(row['model_output_assembly'],[True,False,False]);self.assertFalse(row['accepted'])

    def test_empty_records_dont_create_answers(self):
        d=op.summary(self.plan,[])
        self.assertFalse(d['all_atomic_correct'])
        self.assertEqual(d['conditional_assembly_successes'],0)
        self.assertTrue(all(x['model_output_assembly'] is None for x in d['conditional_assemblies']))

    def test_invalid_format_and_model_rejected(self):
        with self.assertRaises(ContractError):op.build_plan(self.source,format_mode='invalid')
        with self.assertRaises(ContractError):op.build_plan(self.source,comparison_model='')

    def test_original_rows_not_edited_by_summary(self):
        before=copy.deepcopy(self.source['records'])
        from local_llm.decision_table import summarize_records
        summarize_records(self.source['manifest']['frozen']['plan'],self.source['records'])
        self.assertEqual(self.source['records'],before)


if __name__=='__main__':
    unittest.main()
