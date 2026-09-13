"""입력 순서만 변경했는지와 계획/정답 주입 우회를 검증한다."""
import ast, collections, copy, json, unittest
from pathlib import Path
from unittest.mock import patch
from depth_probe_v053.requests import request_bytes as old_request
from order_probe_v054.contracts import ContractError, strict_json, unb64, digest
from order_probe_v054.design import PROBLEMS, ARMS, DIRECTIONS, RULE_ORDERS, schedule, problem_for
from order_probe_v054.plan import validate_plan, prepare
from order_probe_v054.requests import request_bytes
from order_probe_v054.measure import depth_bounds
from .fixtures import shared, copied

class Design(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.base=shared(); cls.plan=cls.base['plan']
    def test_total_and_cell_balance(self):
        slots=self.plan['slots']; self.assertEqual(len(slots),120)
        c=collections.Counter((s['problem_id'],s['arm'],s['direction']) for s in slots)
        self.assertEqual(len(c),12);self.assertEqual(set(c.values()),{10})
    def test_original_sixty_wire_requests_identical(self):
        previous=strict_json(unb64(self.plan['reference']['plan_b64']));count=0
        for slot in self.plan['slots']:
            if slot['arm']=='original':self.assertEqual(request_bytes(self.plan,slot),old_request(previous,slot));count+=1
        self.assertEqual(count,60)
    def test_only_rules_array_order_changes(self):
        for slot in self.plan['slots']:
            if slot['arm']!='original':continue
            a=strict_json(request_bytes(self.plan,slot));b=strict_json(request_bytes(self.plan,{**slot,'arm':'swapped'}))
            pa=json.loads(a['messages'][1]['content'][9:]);pb=json.loads(b['messages'][1]['content'][9:])
            self.assertNotEqual(pa['rules'],pb['rules']);self.assertEqual(sorted(pa['rules'],key=lambda x:x['id']),sorted(pb['rules'],key=lambda x:x['id']))
            pb['rules']=pa['rules'];self.assertEqual(pa,pb)
            b['messages'][1]=a['messages'][1];self.assertEqual(a,b)
    def test_chain_internal_order_preserved(self):
        for pid, chain in [('K01',['k10','k17']),('T02',['r21','r57','r04','r69'])]:
            for arm in ARMS:self.assertEqual([x for x in RULE_ORDERS[pid][arm] if x in chain],chain)
    def test_order_does_not_depend_on_direction(self):
        for pid in PROBLEMS:
            for arm in ARMS:
                values=[problem_for({'problem_id':pid,'arm':arm,'direction':d}) for d in DIRECTIONS]
                self.assertTrue(all(p==values[0] for p in values))
    def test_problem_semantics_and_bounds_preserved(self):
        for pid in PROBLEMS:
            for arm in ARMS:
                p=problem_for({'problem_id':pid,'arm':arm});self.assertEqual(depth_bounds(p),depth_bounds(PROBLEMS[pid]))
                self.assertEqual(p['facts'],PROBLEMS[pid]['facts']);self.assertEqual(p['goal'],PROBLEMS[pid]['goal'])
    def test_seed_and_model_configuration_preserved(self):
        old=strict_json(unb64(self.plan['reference']['plan_b64']))
        self.assertEqual(old['seeds'],self.plan['seeds']);self.assertEqual(old['baseline'],self.plan['baseline'])
    def test_neutral_has_no_direction_instruction(self):
        for slot in self.plan['slots']:
            if slot['direction']=='neutral':
                text=strict_json(request_bytes(self.plan,slot))['messages'][0]['content']
                self.assertNotIn('경로 지시:',text);self.assertNotIn('가장 작은 경로',text);self.assertNotIn('가장 큰 경로',text)
    def test_definition_not_mixed_into_order_intervention(self):
        for slot in self.plan['slots']:
            self.assertNotIn('깊이의 계산 정의:',strict_json(request_bytes(self.plan,slot))['messages'][0]['content'])
    def test_schema_and_messages_do_not_supply_answers(self):
        for slot in self.plan['slots']:
            req=strict_json(request_bytes(self.plan,slot));self.assertEqual([m['role'] for m in req['messages']],['system','user'])
            self.assertEqual(set(req['format']['properties']),{'nodes','final_node_id'});self.assertNotIn('reference_record',json.dumps(req))
    def test_generator_does_not_import_answer_oracle(self):
        path=Path(__file__).resolve().parents[1]/'order_probe_v054/requests.py'
        imports=[n.module or '' for n in ast.walk(ast.parse(path.read_text())) if isinstance(n,ast.ImportFrom)]
        self.assertFalse(any(any(word in name for word in ('measure','oracle','fixture','calibration')) for name in imports))
    def test_schedule_is_fixed(self):self.assertEqual(schedule(self.plan['seeds']),self.plan['slots'])
    def rejects(self, mutator):
        p=copy.deepcopy(self.plan);mutator(p);p['plan_sha256']=digest({k:v for k,v in p.items() if k!='plan_sha256'})
        with self.assertRaises(ContractError):validate_plan(p)
    def test_resealed_rule_order_change_rejected(self):self.rejects(lambda p:p['rule_orders']['K01']['swapped'].reverse())
    def test_resealed_rule_content_change_rejected(self):self.rejects(lambda p:p['problems']['K01']['rules'][0].update(conclusion='Cc'))
    def test_resealed_seed_change_rejected(self):self.rejects(lambda p:p['seeds'].__setitem__(0,99))
    def test_resealed_source_change_rejected(self):self.rejects(lambda p:p['source_fingerprint'].update({'extra.py':'0'*64}))
    def test_resealed_policy_change_rejected(self):self.rejects(lambda p:p['policy'].update(retry=True))
    def test_prepare_is_offline(self):
        with copied() as (root,plan,run,base),patch('paired_probe_v049.runner.OllamaHTTP',side_effect=AssertionError('network forbidden')):
            result=prepare(base['bundle'],root/'new.plan');self.assertEqual(result['max_calls'],120)
    def test_existing_plan_preserved(self):
        with copied() as (root,plan,run,base):
            before=plan.read_bytes()
            with self.assertRaises(ContractError):prepare(base['bundle'],plan)
            self.assertEqual(before,plan.read_bytes())
