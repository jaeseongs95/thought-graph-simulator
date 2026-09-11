"""v0.4.2 실제 보존 응답·반례·모의 API 회귀시험. 모델 추론 없음."""
from __future__ import annotations
import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from local_llm import micro_probe, task_evidence, component_report, calibration_v4, compare_runs
from local_llm.client import Reply
from local_llm.common import PACKAGE, ContractError, load_core, read_json, wire_json
from local_llm.model_policy import resolve_config
from local_llm.runner import request_body, assess_response, run
from local_llm.report import build_summary
from local_llm.tests import test_v04 as prior
config, metadata = prior.config, prior.metadata


class V042Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core, cls.info = load_core()
        cls.obs = read_json(PACKAGE/'tests/fixtures/v041_probe_observations.json')
        cls.plan = micro_probe.build_plan(cls.core)
        cls.ps = {p['id']:p for p in cls.plan['problems']}
        cls.cfg = resolve_config(config(), metadata())
        cls.helper = prior.V04Tests(); cls.helper.core, cls.helper.info = cls.core, cls.info

    def row(self, role):
        return next(x for x in self.obs['observations'] if x['case']['role_id']==role)

    def observed_evidence(self, role):
        r=self.row(role);p=next(p for p in self.obs['plan']['problems'] if p['id']==r['case']['problem_id'])
        return task_evidence.task_diagnostics(p,r['case'],r['response']['message']['content'],micro_probe.output_schema(r['case']))

    def payload(self, p, c):
        if c['task']=='input_echo': return copy.deepcopy(c['echo'])
        if c['task']=='literal_equality': return {'equal':c['operands']['left']==c['operands']['right']}
        if c['task']=='criterion_witness':
            ev=task_evidence.criterion_evidence(p,c['probe_atom'],{})
            return {'observed':{'probe_atom':c['probe_atom'],'goal_atom':p['goal'],'facts':copy.deepcopy(p['facts'])},
                    'primitives':ev['expected_primitives'],'finding':ev['expected']}
        if c['task']=='edge_map':
            proof=calibration_v4.fixtures()[2][1]
            return {'links':[{k:copy.deepcopy(v) for k,v in n.items() if k in {'node_id','parent_node_ids'}} for n in proof['nodes']]}
        return self.helper.payload(p,c)

    def execute_mock(self, plan, out, alter=None):
        ps={p['id']:p for p in plan['problems']}; meta=metadata();client=Mock()
        client.inspect.return_value=meta;client.tag.return_value=meta['tag'];client.running_model.return_value=meta['tag']
        rs=[]
        for c in plan['cases']:
            payload=self.payload(ps[c['problem_id']],c)
            if alter: alter(c,payload)
            r={'model':self.cfg['model'],'done':True,'done_reason':'stop',
               'message':{'role':'assistant','content':wire_json(payload)},'eval_count':50,'prompt_eval_count':100}
            rs.append(Reply(r,wire_json(r),0.01))
        client.chat.side_effect=rs
        with patch('local_llm.runner.OllamaClient',return_value=client),patch('local_llm.runner.environment',return_value={'nvidia_smi':None}),contextlib.redirect_stdout(io.StringIO()):
            code=run(self.core,self.info,plan,config(),out)
        return code,client

    def test_actual_twelve_decisions_exactly_preserved(self):
        ps={p['id']:p for p in self.obs['plan']['problems']}
        for r in self.obs['observations']:
            c=r['case'];p=ps[c['problem_id']]
            out,_=assess_response(self.core,p,c,self.obs['plan']['reference_depths'][p['id']],r['request'],r['response'],self.obs['config']['mode_policy'])
            for key in ('status','error','audit','usage','done_reason','response_channels'):
                self.assertEqual(out.get(key),r['record'].get(key),(c['role_id'],key))

    def test_actual_twelve_http_requests_unchanged(self):
        ps={p['id']:p for p in self.obs['plan']['problems']}
        for r in self.obs['observations']:
            self.assertEqual(wire_json(request_body(self.obs['config'],r['case'],ps[r['case']['problem_id']])),wire_json(r['request']))

    def test_actual_schema_missing_only_fact(self):
        for variant in ('union','schema_only','json'):
            ev=self.observed_evidence('schema_K03_'+variant)['schema']['views'][0]
            self.assertEqual(ev['missing_clauses'],[{'if':[],'then':'Ea'}])
            self.assertEqual(ev['extra_clauses'],[])
            self.assertTrue(ev['conclusion_grounding_valid'])

    def test_actual_schema_all_false_counterexample(self):
        ev=self.observed_evidence('schema_K03_union')['schema']['views'][0]
        self.assertFalse(ev['supplied_clauses_entail_conclusion'])
        self.assertTrue(all(v is False for v in ev['counterexample_valuation'].values()))

    def test_bindings_object_is_observed_not_repaired(self):
        r=self.row('schema_K03_json');before=copy.deepcopy(r)
        ev=self.observed_evidence('schema_K03_json')
        self.assertTrue(ev['schema']['views'][0]['noncanonical_mapping_observation_only'])
        self.assertEqual(r,before)
        self.assertTrue(any('.bindings' in str(e) for e in ev['shape_errors']))

    def test_anyof_branch_reports_bindings_path(self):
        ev=self.observed_evidence('schema_K03_json')
        self.assertIn('$.node_views[0].view.bindings',str(ev['shape_errors']))

    def test_fact_only_synthetic_addition_passes_without_changing_score(self):
        r=copy.deepcopy(self.row('schema_K03_union'));p=next(p for p in self.obs['plan']['problems'] if p['id']=='K03')
        v=json.loads(r['response']['message']['content']);view=v['node_views'][0]['view']
        symbol=next(x['variable'] for x in view['bindings'] if x['atom']=='Ea')
        view['clauses'].insert(0,{'if':[],'then':symbol})
        self.assertTrue(calibration_v4.assess_payload(self.core,p,r['case'],v)['valid_completion'])
        self.assertEqual(self.row('schema_K03_union')['record']['status'],'invalid_task')

    def test_actual_proof_detects_two_wrong_links(self):
        ev=self.observed_evidence('proof_K03_baseline')['support']
        bad=[x for x in ev['nodes'] if not x['locally_valid']]
        self.assertEqual(len(bad),2)
        self.assertEqual(bad[0]['expected_parent_atoms'],['Eb'])
        self.assertEqual(bad[0]['actual_parent_atoms'],['Ec'])

    def test_actual_criterion_three_outputs_are_constant_but_not_three_successes(self):
        evs=[self.observed_evidence('criterion_0'+str(i)+'_compact')['criterion'] for i in (1,2,3)]
        self.assertEqual(len({wire_json(x['actual']) for x in evs}),1)
        self.assertEqual(sum(all(x['matches'].values()) for x in evs),1)
        self.assertFalse(evs[1]['expected_primitives']['same_as_goal'])
        self.assertTrue(evs[1]['actual']['answer_only_accepts'])

    def test_three_schema_variants_all_survive_component_summary(self):
        records=[r['record'] for r in self.obs['observations']]
        c=component_report.component_summary(self.obs['plan'],records)
        self.assertEqual(len(c['schema_scope_conditions']),3)
        pair=c['schema_scope_pairs'][0]
        self.assertTrue(pair['ambiguous_scope_comparison'])
        self.assertEqual(len(pair['final_node_only']['conditions']),3)
        self.assertEqual({x['status'] for x in pair['final_node_only']['conditions']},{'invalid_task','protocol_error'})

    def test_all_twelve_micro_tasks_are_declared(self):
        self.assertEqual(len(self.plan['cases']),12)
        for group,n in [('control',4),('criterion',4),('graph',2),('schema',2)]:
            self.assertEqual(sum(c['diagnostic_group']==group for c in self.plan['cases']),n)

    def test_selected_groups_make_only_eight_calls(self):
        p=micro_probe.build_plan(self.core,groups=['control','criterion'])
        self.assertEqual(p['assigned_calls'],8)
        self.assertEqual({c['task'] for c in p['cases']},{'input_echo','literal_equality','criterion_witness'})

    def test_all_four_primitive_truth_pairs_are_present(self):
        pairs={(c['probe_atom']==self.ps[c['problem_id']]['goal'],c['probe_atom'] in self.ps[c['problem_id']]['facts']) for c in self.plan['cases'] if c['task']=='criterion_witness'}
        self.assertEqual(pairs,{(True,True),(True,False),(False,True),(False,False)})

    def test_format_changes_only_format_not_messages_or_semantics(self):
        plans=[micro_probe.build_plan(self.core,format_mode=f) for f in ('schema','json','none')]
        byname=[{c['role_id']:c for c in p['cases']} for p in plans]
        for name in byname[0]:
            bodies=[request_body(self.cfg,b[name],self.ps[b[name]['problem_id']]) for b in byname]
            values=[x.pop('format','omitted') for x in bodies]
            self.assertEqual(bodies[0],bodies[1]);self.assertEqual(bodies[1],bodies[2])
            self.assertEqual(values[1: ],['json','omitted'])

    def test_message_contains_full_same_schema(self):
        for c in self.plan['cases']:
            self.assertIn(wire_json(micro_probe.output_schema(c)),micro_probe.messages(self.ps[c['problem_id']],c)[0]['content'])

    def test_schema_hint_is_only_additional_instruction(self):
        cs=[c for c in self.plan['cases'] if c['task']=='schema']; cs.sort(key=lambda c:c['fact_first'])
        a,b=[request_body(self.cfg,c,self.ps[c['problem_id']]) for c in cs]
        ma,mb=a.pop('messages'),b.pop('messages')
        self.assertEqual(a,b);self.assertEqual(ma[1],mb[1]);self.assertNotEqual(ma[0],mb[0])

    def test_no_generator_called_for_micro_plan_or_messages(self):
        with patch.object(self.core,'simulate',side_effect=AssertionError('정답 생성 금지')):
            p=micro_probe.build_plan(self.core)
            for c in p['cases']: micro_probe.messages(self.ps[c['problem_id']],c)

    def test_edge_skeleton_contains_no_parent_answers(self):
        c=next(c for c in self.plan['cases'] if c['task']=='edge_map')
        self.assertTrue(all('parent_node_ids' not in n for n in c['skeleton']['nodes']))
        self.assertIn('D 성과로 세지 않음',c['host_supplied'])

    def test_valid_mock_payloads_all_accepted(self):
        for c in self.plan['cases']:
            p=self.ps[c['problem_id']];self.assertTrue(micro_probe.assess_payload(self.core,p,c,self.payload(p,c))['valid_completion'],c['role_id'])

    def test_false_equality_is_not_truthy_string(self):
        c=next(c for c in self.plan['cases'] if c['role_id']=='control_not_equal')
        with self.assertRaises(ContractError):micro_probe.assess_payload(self.core,self.ps[c['problem_id']],c,{'equal':'false'})
        self.assertFalse(micro_probe.assess_payload(self.core,self.ps[c['problem_id']],c,{'equal':True})['valid_completion'])

    def test_criterion_witness_localizes_observed_input_error(self):
        c=next(c for c in self.plan['cases'] if c['task']=='criterion_witness');p=self.ps[c['problem_id']]
        v=self.payload(p,c);v['observed']['probe_atom']='wrong'
        a=micro_probe.assess_payload(self.core,p,c,v)
        self.assertEqual(a['details']['first_failed_observable_stage'],'observed')
        self.assertFalse(a['valid_completion'])

    def test_criterion_witness_localizes_primitive_error(self):
        c=next(c for c in self.plan['cases'] if c['task']=='criterion_witness');p=self.ps[c['problem_id']]
        v=self.payload(p,c);v['primitives']['same_as_goal']=not v['primitives']['same_as_goal']
        a=micro_probe.assess_payload(self.core,p,c,v)
        self.assertEqual(a['details']['first_failed_observable_stage'],'primitives')

    def test_criterion_witness_localizes_finding_error(self):
        c=next(c for c in self.plan['cases'] if c['task']=='criterion_witness');p=self.ps[c['problem_id']]
        v=self.payload(p,c);v['finding']['gap_detected']=not v['finding']['gap_detected']
        self.assertEqual(micro_probe.assess_payload(self.core,p,c,v)['details']['first_failed_observable_stage'],'finding')

    def test_edge_missing_entry_not_completed(self):
        c=next(c for c in self.plan['cases'] if c['task']=='edge_map');p=self.ps[c['problem_id']]
        v=self.payload(p,c);v['links'].pop(0)
        a=micro_probe.assess_payload(self.core,p,c,v)
        self.assertFalse(a['valid_completion']);self.assertTrue(a['details']['missing_or_duplicate_links_not_reconstructed'])
        self.assertNotIn('core_audit',a['details'])

    def test_edge_duplicate_entry_rejected(self):
        c=next(c for c in self.plan['cases'] if c['task']=='edge_map');p=self.ps[c['problem_id']]
        v=self.payload(p,c);v['links'].append(copy.deepcopy(v['links'][0]))
        self.assertFalse(micro_probe.assess_payload(self.core,p,c,v)['valid_completion'])

    def test_malformed_diagnostic_does_not_crash(self):
        c=next(c for c in self.plan['cases'] if c['task']=='schema')
        for raw in ['null','[]','{"node_views":[null]}','not json']:
            ev=task_evidence.task_diagnostics(self.ps[c['problem_id']],c,raw,micro_probe.output_schema(c))
            self.assertTrue(ev['shape_errors'] or ev.get('diagnostic_error'))

    def test_control_failure_not_hidden_by_other_votes(self):
        records=[{'case':c,'status':'accepted'} for c in self.plan['cases']]
        next(r for r in records if r['case']['diagnostic_group']=='control')['status']='invalid_task'
        self.assertEqual(micro_probe.summarize_probe(self.plan,records)['next_evidence_action'],'stop_scaling_up_check_input_or_runtime_pair')

    def test_no_records_not_reported_as_control_success(self):
        self.assertEqual(micro_probe.summarize_probe(self.plan,[])['next_evidence_action'],'control_not_fully_measured')

    def test_mock_end_to_end_twelve_requests_reports_evidence(self):
        with tempfile.TemporaryDirectory() as t:
            out=Path(t)/'run';code,client=self.execute_mock(self.plan,out)
            self.assertEqual(code,0);self.assertEqual(client.chat.call_count,12)
            summary=read_json(out/'micro_probe.json');self.assertEqual(len(summary['cases']),12)
            self.assertTrue(summary['not_an_ADM_success_rate']);self.assertEqual(len(read_json(out/'task_evidence.json')),12)
            self.assertFalse((out/'causal_probe.json').exists())

    def test_micro_plan_only_does_not_construct_client(self):
        with patch('local_llm.runner.OllamaClient') as c,contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(micro_probe.main(['--plan-only','--group','control']),0)
        c.assert_not_called()

    def test_format_pair_compare_checks_wire_fields(self):
        with tempfile.TemporaryDirectory() as t:
            a,b=Path(t)/'a',Path(t)/'b'
            self.execute_mock(micro_probe.build_plan(self.core,groups=['control']),a)
            self.execute_mock(micro_probe.build_plan(self.core,groups=['control'],format_mode='json'),b)
            r=compare_runs.compare(a,b,'format')
            self.assertEqual(r['paired_cases'],4);self.assertTrue(r['request_control_verified'])
            with self.assertRaises(ContractError): compare_runs.compare(a,b,'temperature')

    def test_same_run_not_comparison(self):
        with self.assertRaises(ContractError):compare_runs.compare(Path('/tmp/same'),Path('/tmp/same'),'format')

    def test_unrequested_factor_difference_survives_normalization(self):
        c=self.plan['cases'][0];a=request_body(self.cfg,c,self.ps[c['problem_id']]);b=copy.deepcopy(a)
        b['format']='json';b['options']['temperature']=0.0
        self.assertNotEqual(compare_runs.normalized_request(a,'format')[0],compare_runs.normalized_request(b,'format')[0])

if __name__=='__main__':unittest.main()
