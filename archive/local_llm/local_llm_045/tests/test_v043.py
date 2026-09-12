"""실제 v042 원문 회귀와 v043 대조·단계형 실행의 오프라인 시험. 모델 호출 없음."""
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
from local_llm import decision_probe as dp, decision_evidence as de, component_report, diagnostics, micro_probe
from local_llm.client import Reply
from local_llm.common import PACKAGE, ContractError, load_core, read_json, wire_json, bytes_hash, digest
from local_llm.report import read_records, build_summary
from local_llm.runner import request_body, assess_response, run

# 구현 함수를 호출해 정답을 만드는 대신, 네 입력의 진리표를 별도 상수로 고정한다.
TRUTH = {(False, False): (False, False, False), (False, True): (False, False, False),
         (True, False): (True, False, True), (True, True): (True, True, False)}


class V043Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.parent = Path(cls.temp.name)
        with zipfile.ZipFile(PACKAGE/'tests/fixtures/v042_micro_run.zip') as z:
            z.extractall(cls.parent)  # 패키지에 고정된 검사 대상 fixture만 사용
        cls.path = cls.parent/'v042_micro_01'
        cls.core, cls.info = load_core()
        cls.source = dp.load_source(cls.core, cls.info, cls.path)
        cls.plan = dp.build_plan(cls.source)
        cls.cfg = cls.source['manifest']['frozen']['config']
        cls.meta = cls.source['manifest']['ollama_metadata']
        cls.ps = {p['id']: p for p in cls.plan['problems']}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def actual_records(self):
        mf = self.source['manifest'];records = read_records(self.path,mf);out=[]
        for r in records:
            c=r['case'];p=self.ps[c['problem_id']];folder=self.path/'cases'/c['case_id']
            body=read_json(folder/'request.json')['body'];response=read_json(folder/'response.raw.json')
            a,_=assess_response(self.core,p,c,self.plan['reference_depths'][p['id']],body,response,self.cfg['mode_policy'])
            out.append(dict(r,**a))
        return out

    def answer(self, case):
        p=self.ps[case['problem_id']];a=case['probe_atom']==p['goal'];b=case['probe_atom'] in p['facts']
        finding=dict(zip(de.FIELDS,TRUTH[a,b]))
        if case['arm']=='staged':return {'finding':finding}
        return {'observed':{'probe_atom':case['probe_atom'],'goal_atom':p['goal'],'facts':copy.deepcopy(p['facts'])},
                'primitives':{'same_as_goal':a,'in_facts':b},'finding':finding}

    def mock_client(self, alter=None):
        client=Mock();client.inspect.return_value=self.meta;client.tag.return_value=self.meta['tag']
        client.running_model.return_value=self.meta['tag'];replies=[]
        for c in self.plan['cases']:
            payload=self.answer(c)
            if alter:payload=alter(c,payload)
            response={'model':self.cfg['model'],'done':True,'done_reason':'stop',
                      'message':{'role':'assistant','content':wire_json(payload)},
                      'prompt_eval_count':100,'eval_count':20}
            replies.append(Reply(response,wire_json(response),0.01))
        client.chat.side_effect=replies;return client

    def mock_run(self, out, client, **kwargs):
        with patch('local_llm.runner.OllamaClient',return_value=client), \
             patch('local_llm.runner.environment',return_value={'nvidia_smi':None}), \
             contextlib.redirect_stdout(io.StringIO()):
            return run(self.core,self.info,self.plan,copy.deepcopy(self.cfg),out,**kwargs)

    def test_actual_source_8_records_27_sources_replayed(self):
        self.assertEqual(self.source['validation'],{'all_source_records_replayed':8,'criterion_cases':4,
                                                   'snapshot_files_verified':27,'network_called':False})

    def test_all_four_truth_conditions_retained_including_failures(self):
        self.assertEqual(len(self.source['selected']),4)
        self.assertEqual(sum(x['original_status']=='invalid_task' for x in self.source['selected']),2)
        self.assertEqual({(x['source_evidence']['primitives']['same_as_goal'],x['source_evidence']['primitives']['in_facts'])
                          for x in self.source['selected']},set(TRUTH))

    def test_actual_grade_and_audit_not_changed(self):
        new=self.actual_records();old=read_records(self.path,self.source['manifest'])
        for a,b in zip(new,old):
            for k in ('status','error','audit','usage','done_reason','response_channels'):
                self.assertEqual(a.get(k),b.get(k),(a['case']['role_id'],k))

    def test_actual_wire_keeps_requested_insertion_order(self):
        for r in self.actual_records():
            c=r['case'];actual=(self.path/'cases'/c['case_id']/'request.wire.json').read_text()
            self.assertEqual(wire_json(request_body(self.cfg,c,self.ps[c['problem_id']])),actual)
        for s in self.source['selected']:
            self.assertEqual(list(s['request']['format']['properties']),['observed','primitives','finding'])

    def test_observed_order_is_not_instruction_order(self):
        for x in self.source['selected']:
            ev=x['source_evidence'];self.assertEqual(ev['raw_object_key_order'],['finding','observed','primitives'])
            self.assertFalse(ev['internal_process_observed']);self.assertTrue(ev['serialization_is_not_internal_reasoning_order'])

    def test_witness_summary_reports_constant_false_and_correct_primitives(self):
        d=de.aggregate_witnesses(self.actual_records())
        self.assertEqual(d['assessable_cases'],4);self.assertEqual(d['observed_correct_cases'],4)
        self.assertEqual(d['primitives_correct_cases'],4);self.assertEqual(d['finding_correct_cases'],2)
        self.assertEqual(d['own_primitive_inconsistency_cases'],2)
        self.assertEqual(d['actual_patterns'],{'false,false,false':4})
        for x in d['per_field_counts'].values():self.assertEqual(x['balanced_accuracy'],0.5)

    def test_component_report_no_longer_omits_witness_patterns(self):
        d=component_report.component_summary(self.source['manifest']['frozen']['plan'],self.actual_records())
        self.assertEqual(d['criterion_actual_patterns'],{'false,false,false':4})
        self.assertEqual(sum(x['assigned'] for x in d['criterion_expected_patterns'].values()),4)

    def test_micro_next_branch_is_final_inconsistency_not_input_failure(self):
        d=micro_probe.summarize_probe(self.source['manifest']['frozen']['plan'],self.actual_records())
        self.assertEqual(d['next_evidence_action'],'input_and_primitives_correct_final_finding_inconsistent')

    def test_input_errors_not_relabeled_as_final_only(self):
        x=self.source['selected'][0];payload=copy.deepcopy(x['projection']);payload['finding']=dict(zip(de.FIELDS,TRUTH[True,True]))
        payload['observed']['goal_atom']='wrong';d=de.witness_evidence(x['problem'],x['case'],payload)
        self.assertEqual(d['failed_observable_component'],'observed')

    def test_malformed_witness_is_not_falsely_counted(self):
        x=self.source['selected'][0]
        for v in (None,{},[],{'observed':{},'primitives':{'in_facts':'false'},'finding':{} }):
            self.assertFalse(de.witness_evidence(x['problem'],x['case'],v)['assessable'])

    def test_eight_calls_and_distinct_ids_are_stable(self):
        self.assertEqual(self.plan,dp.build_plan(self.source));self.assertEqual(self.plan['assigned_calls'],8)
        self.assertEqual(len({c['case_id'] for c in self.plan['cases']}),8)
        for arm in dp.ARMS:self.assertEqual(sum(c['arm']==arm for c in self.plan['cases']),4)

    def test_each_arm_can_be_requested_alone(self):
        for arm in dp.ARMS:self.assertEqual(dp.build_plan(self.source,[arm])['assigned_calls'],4)
        for arms in ([],['staged','staged'],['other']):
            with self.assertRaises(ContractError):dp.build_plan(self.source,arms)

    def test_format_arm_changes_only_format_in_actual_wire(self):
        for c in self.plan['cases']:
            if c['arm']!='format_json':continue
            b=dp.make_request(self.cfg,c,self.ps[c['problem_id']]);old=copy.deepcopy(c['source_request'])
            self.assertEqual(b.pop('format'),'json');old.pop('format')
            self.assertEqual(wire_json(b),wire_json(old))

    def test_staged_projection_is_actual_model_output_not_answer_feedback(self):
        for c in self.plan['cases']:
            if c['arm']!='staged':continue
            original=next(s for s in self.source['selected'] if s['case']['case_id']==c['source_case']['case_id'])
            b=dp.make_request(self.cfg,c,self.ps[c['problem_id']]);text=b['messages'][1]['content']
            projected=json.loads(text.split(': ',1)[1]);self.assertEqual(projected,original['projection'])
            self.assertEqual(set(projected),{'observed','primitives'})
            self.assertNotIn('finding',projected);self.assertNotIn('source_evidence',text)

    def test_staged_schema_permits_each_boolean_value(self):
        c=next(c for c in self.plan['cases'] if c['arm']=='staged')
        for vals in itertools.product((False,True),repeat=3):
            dp.validate_schema({'finding':dict(zip(de.FIELDS,vals))},dp.output_schema(c))

    def test_runtime_prompt_does_not_call_solution_generator(self):
        with patch.object(self.core,'simulate',side_effect=AssertionError('runtime answer leak')):
            plan=dp.build_plan(self.source)
            for c in plan['cases']:dp.make_request(self.cfg,c,self.ps[c['problem_id']])

    def test_staged_all_32_outputs_match_independent_truth_table(self):
        for c in self.plan['cases']:
            if c['arm']!='staged':continue
            p=self.ps[c['problem_id']];wanted=TRUTH[c['probe_atom']==p['goal'],c['probe_atom'] in p['facts']]
            for vals in itertools.product((False,True),repeat=3):
                self.assertEqual(dp.assess_payload(self.core,p,c,{'finding':dict(zip(de.FIELDS,vals))})['valid_completion'],vals==wanted)

    def test_wrong_source_primitives_cannot_be_upgraded_to_pipeline_success(self):
        c=copy.deepcopy(next(c for c in self.plan['cases'] if c['arm']=='staged'));p=self.ps[c['problem_id']]
        c['source_projection']['primitives']['same_as_goal']=not c['source_projection']['primitives']['same_as_goal']
        bits=c['source_projection']['primitives'];finding=dict(zip(de.FIELDS,TRUTH[bits['same_as_goal'],bits['in_facts']]))
        a=dp.assess_payload(self.core,p,c,{'finding':finding})
        self.assertTrue(a['details']['conditional_consistency']);self.assertFalse(a['valid_completion'])
        self.assertFalse(a['details']['source_prerequisites_correct'])

    def test_wrong_source_observation_prevents_success_even_correct_final(self):
        c=copy.deepcopy(next(c for c in self.plan['cases'] if c['arm']=='staged'));p=self.ps[c['problem_id']]
        c['source_projection']['observed']['facts']=[]
        a=dp.assess_payload(self.core,p,c,self.answer(c));self.assertFalse(a['valid_completion'])

    def test_strings_and_missing_findings_are_not_coerced(self):
        c=next(c for c in self.plan['cases'] if c['arm']=='staged');p=self.ps[c['problem_id']]
        for payload in ({},{'finding':{k:'false' for k in de.FIELDS}},{'finding':{},'extra':True}):
            with self.assertRaises(ContractError):dp.assess_payload(self.core,p,c,payload)

    def test_requests_do_not_modify_source(self):
        a=copy.deepcopy(self.source);p=copy.deepcopy(self.plan)
        for c in self.plan['cases']:dp.make_request(self.cfg,c,self.ps[c['problem_id']])
        self.assertEqual(self.source,a);self.assertEqual(self.plan,p)

    def test_model_server_and_config_changes_rejected(self):
        for key in ('tag','server','show'):
            m=copy.deepcopy(self.meta)
            if key=='tag':m['tag']['digest']='wrong'
            elif key=='server':m['server']['version']='wrong'
            else:m['show']['template']='wrong'
            with self.assertRaises(ContractError):dp.validate_runtime(self.plan,self.info,self.cfg,m)
        cfg=copy.deepcopy(self.cfg);cfg['options']['temperature']=0
        with self.assertRaises(ContractError):dp.validate_runtime(self.plan,self.info,cfg,self.meta)

    def test_changed_original_artifact_or_snapshot_rejected(self):
        for target in ('source_snapshot/micro_probe.py','manifest.json','cases/'+self.source['selected'][0]['case']['case_id']+'/response.raw.json'):
            with tempfile.TemporaryDirectory() as t:
                with zipfile.ZipFile(PACKAGE/'tests/fixtures/v042_micro_run.zip') as z:z.extractall(t)
                root=Path(t)/'v042_micro_01';f=root/target;f.write_bytes(f.read_bytes()+b' ')
                # manifest 공백만으로는 의미가 바뀌지 않으므로 값도 변경한다.
                if target=='manifest.json':
                    m=read_json(f);m['frozen']['config']['options']['temperature']=0;f.write_text(wire_json(m))
                with self.assertRaises((ContractError,ValueError)):dp.load_source(self.core,self.info,root)

    def test_missing_failed_record_rejected_not_silently_excluded(self):
        with tempfile.TemporaryDirectory() as t:
            with zipfile.ZipFile(PACKAGE/'tests/fixtures/v042_micro_run.zip') as z:z.extractall(t)
            root=Path(t)/'v042_micro_01';failed=next(s for s in self.source['selected'] if s['original_status']=='invalid_task')
            (root/'cases'/failed['case']['case_id']/'record.json').unlink()
            with self.assertRaises(ContractError):dp.load_source(self.core,self.info,root)

    def test_plan_only_makes_no_network_call(self):
        with patch('local_llm.runner.OllamaClient',side_effect=AssertionError('network')),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(dp.main(['--input',str(self.path),'--plan-only']),0)

    def test_source_output_overlap_rejected_before_inference(self):
        with patch('local_llm.runner.OllamaClient',side_effect=AssertionError('network')),contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(dp.main(['--input',str(self.path),'--out',str(self.path)]),2)

    def test_mock_eight_calls_report_separate_arms_and_original_failures(self):
        with tempfile.TemporaryDirectory() as t:
            out=Path(t)/'run';client=self.mock_client();self.assertEqual(self.mock_run(out,client),0)
            d=read_json(out/'decision_probe.json');self.assertEqual(client.chat.call_count,8)
            self.assertEqual(d['arms'],{a:{'assigned':4,'recorded':4,'accepted':4} for a in dp.ARMS})
            self.assertEqual(sum(x['source_status']=='invalid_task' for x in d['cases']),4)
            self.assertEqual(read_json(out/'summary.json')['experiment_kind'],'calibration')
            self.assertTrue(all(x['only_format_field_changed'] for x in d['cases'] if x['arm']=='format_json'))

    def test_mock_failures_recorded_and_resume_does_not_resample(self):
        def alter(c,p):
            if c['arm']=='staged':p['finding']={k:False for k in de.FIELDS}
            return p
        with tempfile.TemporaryDirectory() as t:
            out=Path(t)/'run';client=self.mock_client(alter);self.assertEqual(self.mock_run(out,client),0)
            summary=read_json(out/'summary.json');self.assertEqual(summary['valid_completions'],6)
            nxt=self.mock_client();self.assertEqual(self.mock_run(out,nxt,resume=True),0)
            self.assertEqual(nxt.chat.call_count,0);self.assertEqual(read_json(out/'summary.json')['valid_completions'],6)

    def test_mock_malformed_json_format_result_is_not_repaired(self):
        def alter(c,p):
            if c['arm']=='format_json':p['finding']['answer_only_accepts']='false'
            return p
        with tempfile.TemporaryDirectory() as t:
            out=Path(t)/'run';client=self.mock_client(alter);self.assertEqual(self.mock_run(out,client),0)
            self.assertEqual(read_json(out/'decision_probe.json')['arms']['format_json']['accepted'],0)
            self.assertEqual(client.chat.call_count,8)

    def test_reanalysis_supports_new_contract_and_keeps_source_untouched(self):
        with tempfile.TemporaryDirectory() as t:
            out=Path(t)/'run';self.mock_run(out,self.mock_client())
            before={p.relative_to(out).as_posix():bytes_hash(p.read_bytes()) for p in out.rglob('*') if p.is_file()}
            d=diagnostics.reanalyze(self.core,out,Path(t)/'audit')
            self.assertEqual(d['counts']['original_decision_reproduced'],8)
            self.assertTrue(all(r['full_audit_object_reproduced'] for r in d['cases']))
            after={p.relative_to(out).as_posix():bytes_hash(p.read_bytes()) for p in out.rglob('*') if p.is_file()}
            self.assertEqual(before,after)

    def test_reanalysis_of_actual_source_reports_four_correct_primitives(self):
        with tempfile.TemporaryDirectory() as t:
            d=diagnostics.reanalyze(self.core,self.path,Path(t)/'audit')
            self.assertEqual(d['counts']['original_decision_reproduced'],8)
            self.assertEqual(d['criterion_witness_stages']['primitives_correct_cases'],4)
            self.assertEqual(d['criterion_witness_stages']['finding_correct_cases'],2)
            self.assertTrue(all(r['full_audit_object_reproduced'] for r in d['cases']))

    def test_not_started_conditions_stay_in_denominator(self):
        d=dp.summarize(self.plan,[])
        self.assertEqual(d['arms'],{a:{'assigned':4,'recorded':0,'accepted':0} for a in dp.ARMS})

if __name__=='__main__':unittest.main()
