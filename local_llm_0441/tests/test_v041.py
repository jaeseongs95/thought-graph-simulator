"""실제 실패 분석에서 도출한 회귀/원인 분리 계약 시험. 모의 응답 외 모델 호출 없음."""
from __future__ import annotations
import copy
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_llm import calibration_v4, causal_probe, evidence
from local_llm.common import load_core, read_json, wire_json
from local_llm.design import reference_depths
from local_llm.model_policy import resolve_config
from local_llm.runner import request_body, assess_response
from local_llm.tests import test_v04 as prior


class V041Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core, cls.info = load_core()
        cls.plan = causal_probe.build_probe_plan(cls.core)
        cls.ps = {p['id']:p for p in cls.plan['problems']}
        cls.cfg = resolve_config(prior.config(), prior.metadata())
        cls.helper = prior.V04Tests()
        cls.helper.core, cls.helper.info = cls.core, cls.info

    def schema_case(self, scope='all_nodes'):
        p, proof = calibration_v4.fixtures()[0]
        c = {'task':'schema','provided_proof':proof,'calibration_version':4,'view_scope':scope}
        return p,c,self.helper.payload(p,c)

    def test_mixed_schema_false_positive_now_rejected(self):
        p,c,v=self.schema_case()
        v['node_views'][0]['view']={'kind':'instance','atom':p['facts'][0]}
        a=calibration_v4.assess_payload(self.core,p,c,v)
        self.assertTrue(a['task_checks']['valid_schema_views'])
        self.assertFalse(a['task_checks']['all_schema'])
        self.assertFalse(a['valid_completion'])

    def test_all_schema_valid_positive(self):
        p,c,v=self.schema_case()
        self.assertTrue(calibration_v4.assess_payload(self.core,p,c,v)['valid_completion'])

    def test_final_only_schema_still_positive(self):
        p,c,v=self.schema_case('final_node_only')
        self.assertTrue(calibration_v4.assess_payload(self.core,p,c,v)['valid_completion'])

    def test_actual_final_A_and_all_node_kinds_not_conflated(self):
        p,c,v=self.schema_case()
        v['node_views'][0]['view']={'kind':'instance','atom':p['facts'][0]}
        a=calibration_v4.assess_payload(self.core,p,c,v)
        comparison={x['field']:x for x in a['task_comparisons']}
        self.assertTrue(comparison['A_on_valid_representation']['matches'])
        self.assertFalse(comparison['all_node_view_kinds']['matches'])

    def test_invalid_unrelated_nodes_do_not_hide_valid_selected_support(self):
        p=calibration_v4.fixtures()[0][0]
        t=self.core.simulate(p,'instance','shallow',0)
        t['nodes'].append({'id':'bad','atom':'wrong','rule':'missing','parents':[]})
        before=copy.deepcopy(t)
        a=evidence.support(p,t,core_format=True)
        self.assertTrue(a['selected_support_valid'])
        self.assertFalse(a['full_support_valid'])
        self.assertEqual(a['unrelated_node_ids'],['bad'])
        self.assertFalse(self.core.verify(p,t)['valid'])
        self.assertEqual(t,before)

    def test_duplicate_ids_do_not_receive_selected_support_credit(self):
        p=calibration_v4.fixtures()[0][0]
        t=self.core.simulate(p,'instance','deep',0)
        t['nodes'].append(copy.deepcopy(t['nodes'][0]))
        self.assertFalse(evidence.support(p,t,core_format=True)['selected_support_valid'])

    def test_wrong_parent_atoms_reported_not_repaired(self):
        p=calibration_v4.fixtures()[0][0]
        t=self.core.simulate(p,'instance','deep',0)
        t['nodes'][-1]['parents']=[t['nodes'][0]['id']]
        a=evidence.support(p,t,core_format=True)
        f=a['first_failure']
        self.assertIn('wrong_premises',f['faults'])
        self.assertNotEqual(f['actual_parent_atoms'],f['expected_parent_atoms'])
        self.assertFalse(a['selected_support_valid'])

    def test_independent_depth_reference_fixtures(self):
        for p in self.ps.values():
            with self.subTest(p=p['id']):
                self.assertEqual(evidence.depth_set_forward(p),reference_depths(p)['depths'])

    def test_exactly_twelve_probes(self):
        self.assertEqual(len(self.plan['cases']),12)
        self.assertEqual(self.plan['assigned_calls'],12)
        self.assertEqual(len({c['case_id'] for c in self.plan['cases']}),12)

    def test_old_baseline_request_unchanged(self):
        for c in self.plan['cases']:
            if c['probe_variant']=='baseline':
                old=copy.deepcopy(c);old.pop('probe_contract')
                self.assertEqual(wire_json(request_body(self.cfg,c,self.ps[c['problem_id']])),
                                 wire_json(request_body(self.cfg,old,self.ps[c['problem_id']])))

    def test_prompt_pairs_change_only_messages(self):
        for pid in ('K01','K02','K03'):
            cases=[c for c in self.plan['cases'] if c['task']=='proof' and c['problem_id']==pid]
            a,b=[request_body(self.cfg,c,self.ps[pid]) for c in cases]
            self.assertNotEqual(a.pop('messages'),b.pop('messages'))
            self.assertEqual(a,b)

    def test_schema_variants_change_only_format(self):
        cases=[c for c in self.plan['cases'] if c['task']=='schema']
        bodies=[request_body(self.cfg,c,self.ps[c['problem_id']]) for c in cases]
        formats=[b.pop('format') for b in bodies]
        self.assertTrue(all(b==bodies[0] for b in bodies))
        self.assertEqual(len({wire_json(v) for v in formats}),3)

    def test_schema_only_is_not_ordinary_A_trial(self):
        c=next(c for c in self.plan['cases'] if c['probe_variant']=='schema_only')
        body=request_body(self.cfg,c,self.ps[c['problem_id']])
        v=body['format']['properties']['node_views']['items']['properties']['view']
        self.assertEqual(v['properties']['kind']['const'],'universal_schema')
        self.assertEqual(c['role']['kind'],'neutral')

    def test_no_simulator_used_to_build_prompts(self):
        with patch.object(self.core,'simulate',side_effect=AssertionError('정답 생성 금지')):
            plan=causal_probe.build_probe_plan(self.core)
            for c in plan['cases']:
                body=request_body(self.cfg,c,self.ps[c['problem_id']])
                self.assertNotIn('reference_depths',body['messages'][1]['content'])

    def test_json_format_response_is_validated_semantically(self):
        c=next(c for c in self.plan['cases'] if c['probe_variant']=='json')
        p=self.ps[c['problem_id']];body=request_body(self.cfg,c,p)
        resp=self.helper.reply(p,c,self.cfg)
        good,_=assess_response(self.core,p,c,reference_depths(p),body,resp,self.cfg['mode_policy'])
        self.assertEqual(good['status'],'accepted')
        bad=json.loads(resp['message']['content']);bad['node_views'][0]['view']={'kind':'instance','atom':p['goal']}
        resp['message']['content']=wire_json(bad)
        invalid,_=assess_response(self.core,p,c,reference_depths(p),body,resp,self.cfg['mode_policy'])
        self.assertNotEqual(invalid['status'],'accepted')

    def test_criterion_has_three_distinct_ground_truth_patterns(self):
        values=[evidence.criterion(self.ps[c['problem_id']],c['probe_atom'])
                for c in self.plan['cases'] if c['task']=='criterion']
        self.assertEqual(len({wire_json(v) for v in values}),3)

    def test_mock_complete_probe_and_report(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'probe'
            result,client=self.helper.run_mock(self.plan,out)
            self.assertEqual(result,0)
            self.assertEqual(client.chat.call_count,12)
            summary=read_json(out/'causal_probe.json')
            self.assertEqual(len(summary['proof_pairs']),3)
            self.assertTrue(summary['not_an_ADM_success_rate'])
            self.assertEqual(sum(x['accepted'] for x in summary['cases']),12)

    def test_plan_only_never_constructs_client(self):
        with patch('local_llm.runner.OllamaClient') as client, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(causal_probe.main(['--plan-only']),0)
        client.assert_not_called()

if __name__=='__main__':
    unittest.main()
