"""실제 16건 오프라인 회귀, 값 연결·실패 보존·모의 API 검사. 모델 추론은 하지 않음."""
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
from unittest.mock import patch

from local_llm import composition_probe as cp
from local_llm import operator_probe as op
from local_llm.operator_audit import load_operator_source
from local_llm.common import (PACKAGE, ContractError, digest, load_core, read_json, source_text_identity, wire_json)
from local_llm.client import Reply
from local_llm.runner import request_body, assess_response

TRUTH = {(False,False):(False,False,True,False), (False,True):(False,False,False,False),
         (True,False):(True,False,True,True), (True,True):(True,True,False,False)}

class V046Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name)
        with zipfile.ZipFile(PACKAGE/'tests/fixtures/v045_operator_run.zip') as z:z.extractall(cls.root)
        cls.src=cls.root/'v045_operator_01';cls.core,cls.info=load_core()
        cls.source=load_operator_source(cls.core,cls.info,cls.src)
        cls.cfg=cls.source['manifest']['frozen']['config'];cls.meta=cls.source['manifest']['ollama_metadata']
        cls.plan=cp.build_phase_one(cls.source);cls.problems={p['id']:p for p in cls.plan['problems']}
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def raw(self,value):
        return {'model':self.cfg['model'],'done':True,'done_reason':'stop',
                'message':{'role':'assistant','content':wire_json({'value':value})}}
    def evaluate(self,c,value):
        p=self.problems[c['problem_id']];b=request_body(self.cfg,c,p)
        return assess_response(self.core,p,c,self.plan['reference_depths'][p['id']],b,self.raw(value),self.cfg['mode_policy'])[0]
    def first(self,wrong=None,invalid=None):
        entries=[]
        for c in self.plan['cases']:
            a,b=c['original_input']['a'],c['original_input']['b'];v=not b if c['arm']=='not' else a and not b
            if c['arm']=='not' and (a,b)==wrong:v=not v
            r=self.evaluate(c,v);raw=self.raw(v)
            if c['arm']=='not' and (a,b)==invalid:
                raw['message']['content']='not JSON';r['status']='protocol_error'
            entries.append({'case':c,'record':dict(r,case=c),'response':raw,
                            'response_sha256':digest(raw),'request_sha256':'b'*64})
        return {'manifest':{'run_sha256':'a'*64},'entries':entries,'records':[e['record'] for e in entries]}
    def test_16_original_decisions_replayed(self):
        self.assertEqual(self.source['validation']['records_replayed'],16)
        self.assertEqual(sum(r['status']=='accepted' for r in self.source['records']),15)
    def test_39_snapshots_checked_without_execution(self):
        self.assertEqual(self.source['validation']['source_files_checked'],39)
        self.assertFalse(self.source['validation']['snapshot_code_executed'])
    def test_composite_failure_not_primitive_failure(self):
        s=self.source['summary'];self.assertTrue(s['classification']['primitive_groups_all_passed'])
        self.assertEqual(s['diagnostic'],'composite_formula_failure_with_primitives_passed')
    def test_partial_results_not_labelled_failure(self):
        s=op.summary(self.source['manifest']['frozen']['plan'],[])
        self.assertEqual(s['diagnostic'],'not_completed')
    def test_crlf_lf_core_equivalent(self):
        blob=Path(self.core.__file__).read_bytes().decode('utf-8-sig').replace('\r\n','\n')
        for raw in (blob.encode(),blob.replace('\n','\r\n').encode(),b'\xef\xbb\xbf'+blob.encode()):
            info=dict(self.info,**source_text_identity(raw));self.assertTrue(load_operator_source(self.core,info,self.src)['core_compatibility']['same_source'])
    def test_real_edit_rejected(self):
        info=dict(self.info,**source_text_identity(Path(self.core.__file__).read_bytes()+b'\n# edit\n'))
        with self.assertRaises(ContractError):load_operator_source(self.core,info,self.src)
    def tamper(self,p):
        data=p.read_bytes()
        try:
            p.write_bytes(data+b' ')
            with self.assertRaises((ContractError,ValueError)):load_operator_source(self.core,self.info,self.src)
        finally:p.write_bytes(data)
    def test_raw_response_tamper(self):self.tamper(next((self.src/'cases').glob('*/response.raw.json')))
    def test_wire_tamper(self):self.tamper(next((self.src/'cases').glob('*/request.wire.json')))
    def test_snapshot_tamper(self):self.tamper(self.src/'source_snapshot/operator_probe.py')
    def test_missing_record(self):
        p=next((self.src/'cases').glob('*/record.json'));data=p.read_bytes()
        try:
            p.unlink()
            with self.assertRaises(ContractError):load_operator_source(self.core,self.info,self.src)
        finally:p.write_bytes(data)
    def test_gate_truth_32_combinations(self):
        for e in self.source['entries']:
            c=e['case'];opindex=list(op.OPERATIONS).index(c['operation']);a,b=c['input_literals'].values()
            for value in (False,True):
                outcome,_=assess_response(self.core,e['problem'],c,
                    self.source['manifest']['frozen']['plan']['reference_depths'][e['problem']['id']],
                    e['request'],self.raw(value),self.cfg['mode_policy'])
                self.assertEqual(outcome['status']=='accepted',value==TRUTH[a,b][opindex])
    def test_plan_includes_all_rows(self):
        self.assertEqual(len(self.plan['cases']),8)
        for arm in ('not','commuted'):
            self.assertEqual({tuple(c['original_input'].values()) for c in self.plan['cases'] if c['arm']==arm},set(TRUTH))
    def test_chain_only_count(self):self.assertEqual(len(cp.build_phase_one(self.source,True)['cases']),4)
    def test_first_plan_deterministic(self):self.assertEqual(cp.build_phase_one(self.source),self.plan)
    def test_not_request_exact_bytes(self):
        for c in self.plan['cases']:
            if c['arm']=='not':self.assertEqual(wire_json(cp.make_request(self.cfg,c,{})),wire_json(c['source_request']))
    def test_commuted_only_expression_changed(self):
        for c in self.plan['cases']:
            if c['arm']!='commuted':continue
            body=cp.make_request(self.cfg,c,{});data=json.loads(body['messages'][1]['content'][7:])
            self.assertEqual(data['expression'],'((NOT b) AND a)');data['expression']='(a AND (NOT b))'
            body['messages'][1]['content']='input: '+wire_json(data)
            self.assertEqual(wire_json(body),wire_json(c['source_request']))
    def test_second_uses_fresh_parent_value(self):
        plan=cp.build_phase_two(self.source,self.first())
        self.assertEqual(len(plan['cases']),4)
        for c in plan['cases']:
            body=cp.make_request(self.cfg,c,{});data=json.loads(body['messages'][1]['content'][7:])
            self.assertEqual(data['b'],json.loads(c['parent']['response']['message']['content'])['value'])
            self.assertEqual(data['expression'],'(a AND b)')
    def test_wrong_parent_not_repaired(self):
        plan=cp.build_phase_two(self.source,self.first(wrong=(True,False)))
        c=next(c for c in plan['cases'] if c['original_input']=={'a':True,'b':False})
        data=json.loads(cp.make_request(self.cfg,c,{})['messages'][1]['content'][7:])
        self.assertFalse(data['b']);self.assertEqual(self.evaluate(c,False)['status'],'invalid_task')
    def test_compensating_wrong_parent_stays_failure(self):
        plan=cp.build_phase_two(self.source,self.first(wrong=(False,False)))
        c=next(c for c in plan['cases'] if c['original_input']=={'a':False,'b':False})
        r=self.evaluate(c,False);self.assertEqual(r['status'],'invalid_task')
        self.assertTrue(r['audit']['details']['final_formula_correct'])
    def test_invalid_parent_blocks_only_child(self):
        p=cp.build_phase_two(self.source,self.first(invalid=(True,False)))
        self.assertEqual(len(p['cases']),3);self.assertEqual(len(p['blocked_inputs']),1)
    def test_followup_all_truth_pairs(self):
        for c in cp.build_phase_two(self.source,self.first())['cases']:
            a,b=c['original_input'].values()
            for value in (False,True):self.assertEqual(self.evaluate(c,value)['status']=='accepted',value==TRUTH[a,b][3])
    def test_schema_does_not_accept_integer(self):
        with self.assertRaises(ContractError):cp.assess_payload(self.core,self.problems['K01'],self.plan['cases'][0],{'value':1})
    def test_prompt_contains_no_expected_answer_fields(self):
        for c in self.plan['cases']+cp.build_phase_two(self.source,self.first())['cases']:
            body=cp.make_request(self.cfg,c,{})
            self.assertNotIn('expected',wire_json(body));self.assertNotIn('parent.status',wire_json(body))
    def test_model_config_change_rejected(self):
        cfg=copy.deepcopy(self.cfg);cfg['options']['temperature']=0
        with self.assertRaises(ContractError):cp.make_request(cfg,self.plan['cases'][0],{})
    def test_plan_only_no_network(self):
        with patch('local_llm.runner.OllamaClient',side_effect=AssertionError('no network')),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cp.main(['--input',str(self.src),'--plan-only']),0)
    def integration(self,invalid_not=False):
        class Fake:
            bodies=[]
            def __init__(inner,*a):pass
            def inspect(inner,*a):return copy.deepcopy(self.meta)
            def tag(inner,*a):return copy.deepcopy(self.meta["tag"])
            def running_model(inner,*a):return {}
            def gpu_snapshot(inner,*a):return {}
            def request(inner,path,body=None):
                if path!='/api/chat':raise AssertionError(path)
                Fake.bodies.append(copy.deepcopy(body));v=json.loads(body['messages'][1]['content'][7:]);a,b=v['a'],v['b']
                expr=v['expression'];answer=not b if expr=='(NOT b)' else a and b if expr=='(a AND b)' else (not b) and a
                raw=self.raw(answer)
                if invalid_not and expr=='(NOT b)' and a and not b:raw['message']['content']='not JSON'
                return Reply(raw,wire_json(raw),.001)
            def chat(inner,body):return inner.request('/api/chat',body)
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'result'
            with patch('local_llm.runner.OllamaClient',Fake),patch('local_llm.runner.environment',return_value=self.source['manifest']['environment']),contextlib.redirect_stdout(io.StringIO()):
                code=cp.main(['--input',str(self.src),'--out',str(out)])
                self.assertEqual(code,0)
                report=read_json(out/'composition_probe.json')
                self.assertEqual(report['pipeline_assigned'],4)
                self.assertEqual(report['pipeline_passed'],3 if invalid_not else 4)
                self.assertEqual(len(Fake.bodies),11 if invalid_not else 12)
                n=len(Fake.bodies)
                self.assertEqual(cp.main(['--input',str(self.src),'--out',str(out),'--resume']),0)
                self.assertEqual(len(Fake.bodies),n)
                return report
    def test_mock_12_call_pipeline_and_resume(self):self.integration()
    def test_mock_invalid_parent_not_dropped_from_denominator(self):self.integration(True)
    def test_summary_preserves_original_failure(self):
        first=self.first();p=cp.build_phase_two(self.source,first);entries=[]
        for c in p['cases']:
            a,b=c['original_input'].values();r=self.evaluate(c,a and not b)
            entries.append({'case':c,'record':dict(r,case=c),'response_sha256':'a'*64})
        s=cp.summarize(self.source,first,{'entries':entries},p)
        self.assertEqual(s['pipeline_passed'],4)
        self.assertEqual(sum(r['baseline_direct']['status']=='accepted' for r in s['rows']),3)
        self.assertFalse(s['ADM_success'])

if __name__=='__main__':unittest.main()
