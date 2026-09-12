"""실제 응답 재현 + 네 입력의 전수 부울 검사 + 모의 HTTP 실행. LLM을 호출하지 않는다."""
from __future__ import annotations
import contextlib, copy, hashlib, io, itertools, json, tempfile, unittest, zipfile
from pathlib import Path
from unittest.mock import Mock, patch
from local_llm.common import PACKAGE, ContractError, load_core, read_json, wire_json
from local_llm.client import Reply
from local_llm.decision_source import load_decision_source
from local_llm.decision_evidence import FIELDS
from local_llm import decision_table as dt, factor_probe as fp, model_integrity as mi
from local_llm.runner import request_body, assess_response, run
from local_llm.report import read_records

TABLE={(False,False):(False,False,False),(False,True):(False,False,False),
       (True,False):(True,False,True),(True,True):(True,True,False)}

class V044Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name)/'original'
        with zipfile.ZipFile(PACKAGE/'tests/fixtures/v043_decision_run.zip') as z:z.extractall(cls.root)
        cls.core,cls.info=load_core();cls.source=load_decision_source(cls.core,cls.info,cls.root)
        cls.plan=fp.build_plan(cls.source);cls.cfg=cls.source['manifest']['frozen']['config']
        cls.meta=cls.source['manifest']['ollama_metadata'];cls.ps={p['id']:p for p in cls.plan['problems']}
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def payload(self,c):
        p=self.ps[c['problem_id']];bits=TABLE[c['probe_atom']==p['goal'],c['probe_atom'] in p['facts']]
        return {'finding':{c['output_key_map'][k]:v for k,v in zip(FIELDS,bits)}}

    def test_8_original_decisions_replay(self):
        self.assertEqual(self.source['validation']['records_replayed'],8)
        self.assertEqual(sum(r['status']=='accepted' for r in self.source['records']),5)

    def test_stage_semantic_diagnostics_previously_missing_are_present(self):
        for x in self.source['selected']:
            d=x['record']['task_diagnostics']['decision_contract']
            self.assertTrue(d['assessable']);self.assertEqual(d['source_provenance'],'previous_response')

    def test_staged_3_of_4_is_exact_ignore_b_table(self):
        d=dt.summarize_records(self.source['manifest']['frozen']['plan'],self.source['records'])['staged']
        self.assertEqual(d['correct_full_rows'],3);self.assertTrue(d['all_four_rows_match_ignore_b_shortcut'])
        self.assertEqual(d['false_acceptance_count'],1);self.assertFalse(d['all_conditions_verified'])
        self.assertTrue(d['critical_b_pair']['outputs_identical'])

    def test_json_2_of_4_and_false_acceptance_retained(self):
        d=dt.summarize_records(self.source['manifest']['frozen']['plan'],self.source['records'])['format_json']
        self.assertEqual(d['correct_full_rows'],2);self.assertEqual(d['false_acceptance_count'],1)

    def test_missing_or_repeated_table_not_full_truth_function(self):
        rows=dt.summarize_records(self.source['manifest']['frozen']['plan'],self.source['records'])['staged']['rows']
        for x in (rows[:-1],rows+rows,[]):self.assertFalse(dt.table_summary(x)['complete_four_input_table'])

    def test_correct_values_cannot_override_protocol_failure(self):
        rows=copy.deepcopy(dt.summarize_records(self.source['manifest']['frozen']['plan'],self.source['records'])['staged']['rows'])
        for row in rows:
            row['actual']=row['expected'];row['source_prerequisites_correct']=True;row['status']='protocol_error'
        d=dt.table_summary(rows)
        self.assertFalse(d['all_conditions_verified']);self.assertEqual(d['correct_full_rows'],0)
        self.assertEqual(d['correct_value_rows'],4)

    def test_nonboolean_diagnostic_not_assessable(self):
        x=self.source['selected'][0]
        self.assertFalse(dt.row_evidence(x['problem'],x['case'],{'finding':{k:0 for k in FIELDS}})['assessable'])

    def test_plan_is_16_calls_four_per_arm(self):
        self.assertEqual(self.plan['assigned_calls'],16)
        for arm in fp.DEFAULT_ARMS:self.assertEqual(sum(c['arm']==arm for c in self.plan['cases']),4)
        self.assertEqual(fp.build_plan(self.source),self.plan)

    def test_all_four_boolean_inputs_retained_each_arm(self):
        for arm in fp.DEFAULT_ARMS:
            self.assertEqual({(c['source_projection']['primitives']['same_as_goal'],c['source_projection']['primitives']['in_facts'])
                              for c in self.plan['cases'] if c['arm']==arm},set(TABLE))

    def test_arm_selection_and_extra_temperature_zero(self):
        for arm in fp.ARMS:self.assertEqual(fp.build_plan(self.source,[arm])['assigned_calls'],4)
        for arms in ([],['replay','replay'],['invalid']):
            with self.assertRaises(ContractError):fp.build_plan(self.source,arms)

    def test_replay_is_byte_identical(self):
        for c in self.plan['cases']:
            if c['arm']=='replay':self.assertEqual(wire_json(fp.make_request(self.cfg,c,None)),wire_json(c['source_request']))

    def test_only_format_field_differs_json(self):
        for c in self.plan['cases']:
            if c['arm']=='json':
                b=fp.make_request(self.cfg,c,None);old=copy.deepcopy(c['source_request']);self.assertEqual(b.pop('format'),'json');old.pop('format');self.assertEqual(wire_json(b),wire_json(old))

    def test_b_last_changes_only_key_order_not_value(self):
        for c in self.plan['cases']:
            if c['arm']=='b_last':
                b=fp.make_request(self.cfg,c,None);a=json.loads(b['messages'][1]['content'].split(': ',1)[1])
                self.assertEqual(a,c['source_projection']);self.assertEqual(list(a['primitives']),['same_as_goal','in_facts']);self.assertTrue(fp.check_delta(c,b)['allowed_delta_verified'])

    def test_neutral_keys_is_reversible_names_only(self):
        for c in self.plan['cases']:
            if c['arm']=='neutral_keys':
                b=fp.make_request(self.cfg,c,None);self.assertTrue(fp.check_delta(c,b)['allowed_delta_verified'])
                self.assertEqual(b['messages'][1],c['source_request']['messages'][1])
                self.assertEqual(list(b['format']['properties']['finding']['properties']),['r0','r1','r2'])

    def test_temperature_control_is_exactly_one_option(self):
        for c in fp.build_plan(self.source,['temperature_zero'])['cases']:
            b=fp.make_request(self.cfg,c,None);self.assertEqual(b['options']['temperature'],0);self.assertTrue(fp.check_delta(c,b)['allowed_delta_verified'])

    def test_unallowed_changes_rejected(self):
        for c in self.plan['cases']:
            b=fp.make_request(self.cfg,c,None);b['options']['top_k']=999
            with self.assertRaises(ContractError):fp.check_delta(c,b)

    def test_source_not_mutated(self):
        before=copy.deepcopy(self.source)
        for c in self.plan['cases']:fp.make_request(self.cfg,c,None)
        self.assertEqual(before,self.source)

    def test_all_128_outputs_match_independent_truth_table(self):
        for c in self.plan['cases']:
            p=self.ps[c['problem_id']];expect=TABLE[c['probe_atom']==p['goal'],c['probe_atom'] in p['facts']]
            for bits in itertools.product((False,True),repeat=3):
                payload={'finding':{c['output_key_map'][k]:v for k,v in zip(FIELDS,bits)}}
                self.assertEqual(fp.assess_payload(self.core,p,c,payload)['valid_completion'],bits==expect)

    def test_shortcut_not_upgraded_in_any_arm(self):
        for c in self.plan['cases']:
            p=self.ps[c['problem_id']];a=c['probe_atom']==p['goal'];b=c['probe_atom'] in p['facts'];payload={'finding':{c['output_key_map'][k]:v for k,v in zip(FIELDS,(a,a,False))}}
            result=fp.assess_payload(self.core,p,c,payload);self.assertEqual(result['valid_completion'],not(a and not b))

    def test_wrong_prior_state_still_fails_correct_final(self):
        c=copy.deepcopy(self.plan['cases'][0]);c['source_case']['source_projection']['primitives']['in_facts']=not c['source_case']['source_projection']['primitives']['in_facts']
        self.assertFalse(fp.assess_payload(self.core,self.ps[c['problem_id']],c,self.payload(c))['valid_completion'])

    def test_evaluator_does_not_mutate_values(self):
        for c in self.plan['cases']:
            x=self.payload(c);old=copy.deepcopy(x);fp.assess_payload(self.core,self.ps[c['problem_id']],c,x);self.assertEqual(x,old)

    def test_no_solution_generator_in_request_path(self):
        with patch.object(self.core,'simulate',side_effect=AssertionError('answer leak')):
            for c in fp.build_plan(self.source)['cases']:fp.make_request(self.cfg,c,None)

    def test_runtime_changes_rejected(self):
        m=copy.deepcopy(self.meta);m['tag']['digest']='wrong'
        with self.assertRaises(ContractError):fp.validate_runtime(self.plan,self.info,self.cfg,m)

    def test_source_artifact_tamper_rejected(self):
        path=self.root/'cases'/self.source['selected'][0]['case']['case_id']/'response.raw.json';old=path.read_bytes()
        try:
            path.write_bytes(old+b' ')
            with self.assertRaises(ContractError):load_decision_source(self.core,self.info,self.root)
        finally:path.write_bytes(old)

    def test_plan_only_no_network(self):
        with patch('local_llm.client.OllamaClient',side_effect=AssertionError('network')),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(fp.main(['--input',str(self.root),'--plan-only']),0)

    def test_mock_16_calls_report_and_resume(self):
        client=Mock();client.inspect.return_value=self.meta;client.tag.return_value=self.meta['tag'];client.running_model.return_value=self.meta['tag']
        replies=[]
        for c in self.plan['cases']:
            response={'model':self.cfg['model'],'done':True,'done_reason':'stop','message':{'role':'assistant','content':wire_json(self.payload(c))},'eval_count':24}
            replies.append(Reply(response,wire_json(response),0.01))
        client.chat.side_effect=replies
        out=Path(self.tmp.name)/'mock_run'
        with patch('local_llm.runner.OllamaClient',return_value=client),patch('local_llm.runner.environment',return_value={'nvidia_smi':None}),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(run(self.core,self.info,self.plan,copy.deepcopy(self.cfg),out),0)
            self.assertEqual(client.chat.call_count,16)
            self.assertEqual(run(self.core,self.info,self.plan,copy.deepcopy(self.cfg),out,resume=True),0)
            self.assertEqual(client.chat.call_count,16)
        tables=read_json(out/'decision_tables.json')
        for arm in fp.DEFAULT_ARMS:self.assertTrue(tables[arm]['all_conditions_verified'])

    def test_recorded_blob_distinct_from_manifest_digest(self):
        path,h=mi.recorded_blob(self.source['manifest']);self.assertIn('sha256-'+h,path);self.assertNotEqual(h,self.source['manifest']['frozen']['model']['digest'])

    def test_synthetic_gguf_checksum_pass_and_fail(self):
        f=Path(self.tmp.name)/'tiny.gguf';data=b'GGUF\x03\x00\x00\x00'+b'fake_test_payload';f.write_bytes(data)
        good=mi.inspect_file(f,hashlib.sha256(data).hexdigest());self.assertTrue(good['passed']);self.assertFalse(good['network_called'])
        self.assertFalse(mi.inspect_file(f,'0'*64)['passed'])

    def test_non_gguf_and_missing_file_rejected(self):
        f=Path(self.tmp.name)/'notgguf';f.write_bytes(b'abc');self.assertFalse(mi.inspect_file(f,hashlib.sha256(b'abc').hexdigest())['passed'])
        with self.assertRaises(ContractError):mi.inspect_file(Path(self.tmp.name)/'missing','0'*64)

    def test_tag_is_not_accepted_as_blob_digest(self):
        m=copy.deepcopy(self.source['manifest']);m['ollama_metadata']['show']['modelfile']='FROM qwen3:4b-instruct\n'
        with self.assertRaises(ContractError):mi.recorded_blob(m)

    def test_checksum_plan_reads_no_weight_file(self):
        with patch.object(Path,'open',side_effect=AssertionError('weights must not be opened')):
            # 경로 해석 함수는 파일 바이트에 접근하지 않는다.
            mi.recorded_blob(self.source['manifest'])

if __name__=='__main__':unittest.main()
