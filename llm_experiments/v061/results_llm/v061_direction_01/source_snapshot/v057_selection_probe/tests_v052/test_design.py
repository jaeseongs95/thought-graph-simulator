import ast,collections,copy,json,unittest
from pathlib import Path
from adm_diagnostic_v052.design import schedule,TASK_COUNTS,PROBLEMS,ROLES,role_for
from adm_diagnostic_v052.requests import request_bytes
from adm_diagnostic_v052.contracts import read_json,unb64,strict_json,wire,digest,ContractError
from adm_diagnostic_v052.plan import validate_plan
from adm_diagnostic_v052.schema import schema_for
from .fixtures import shared

class Design(unittest.TestCase):
    def test_schedule_440(self):
        s=schedule(list(range(10)));self.assertEqual(len(s),440);self.assertEqual(collections.Counter(x['task'] for x in s),TASK_COUNTS);self.assertEqual(len({x['id'] for x in s}),440)
    def test_schedule_seed_all_roles(self):
        s=schedule(list(range(10)))
        for seed in range(10):
            for pid in PROBLEMS:self.assertEqual(len([x for x in s if x['seed']==seed and x['problem_id']==pid and x['task']=='factorial']),12)
    def test_schedule_deterministic(self):self.assertEqual(schedule(list(range(10))),schedule(list(range(10))))
    def test_same_schema_all_primary_roles(self):
        ss=[s for s in schedule(list(range(10))) if s['task']=='factorial'];self.assertEqual(len({wire(schema_for(s)) for s in ss}),1)
    def test_schema_not_answer_enumeration(self):
        s=next(x for x in schedule(list(range(10))) if x['task']=='factorial');text=wire(schema_for(s)).decode();self.assertNotIn('"enum"',text);self.assertNotIn('k03',text);self.assertNotIn('Cc',text)
    def test_primary_request_no_reference(self):
        p=shared()['plan']
        for s in p['slots']:
            req=strict_json(request_bytes(p,s));texts='\n'.join(m['content'] for m in req['messages'])
            if s['task']!='copy_control':self.assertNotIn('reference_record:',texts)
            else:self.assertIn('reference_record:',texts)
    def test_actual_original_request_bytes_120_match(self):
        from adm_pilot_v051.requests import request_bytes as oldrequest
        p=shared()['plan'];old=strict_json(unb64(p['reference']['plan_b64']))
        for s in p['slots']:
            if s['task']=='legacy':self.assertEqual(request_bytes(p,s),oldrequest(old,s))
    def test_neutral_omits_role_instructions(self):
        p=shared()['plan'];s=next(x for x in p['slots'] if x['task']=='neutral');system=strict_json(request_bytes(p,s))['messages'][0]['content'];self.assertNotIn('이번 역할 지시',system);self.assertNotIn('최종 지지 깊이가 가장',system)
    def test_axis_pairs_differ_only_one_instruction_line(self):
        p=shared()['plan'];base=next(x for x in p['slots'] if x['task']=='factorial' and x['problem_id']=='K01' and x['role_id']=='instance_shallow_M0')
        a=strict_json(request_bytes(p,base))
        for role in ('schema_shallow_M0','instance_deep_M0','instance_shallow_M2'):
            s=dict(base,role_id=role);b=strict_json(request_bytes(p,s));al=a['messages'][0]['content'].splitlines();bl=b['messages'][0]['content'].splitlines();self.assertEqual(sum(x!=y for x,y in zip(al,bl)),1);self.assertEqual(a['messages'][1],b['messages'][1]);self.assertEqual(a['format'],b['format'])
    def test_full_and_graph_problem_equal(self):
        p=shared()['plan']
        for pid in PROBLEMS:
            vals=[strict_json(request_bytes(p,s))['messages'][1]['content'] for s in p['slots'] if s['problem_id']==pid and s['task'] in ('factorial','neutral','graph_only')];self.assertEqual(len(set(vals)),1)
    def test_model_settings_inherit(self):
        p=shared()['plan'];original=strict_json(unb64(p['baseline']['templates']['00']['request_b64']))
        for s in p['slots']:
            r=strict_json(request_bytes(p,s));self.assertEqual(r['options'],dict(original['options'],seed=s['seed']));self.assertEqual(r['model'],original['model'])
    def test_bad_plan_rehashed_rejected(self):
        p=copy.deepcopy(shared()['plan']);p['max_calls']=1;p['plan_sha256']=digest({k:v for k,v in p.items() if k!='plan_sha256'})
        with self.assertRaises(ContractError):validate_plan(p)
    def test_legacy_not_on_transfer(self):self.assertTrue(all(s['problem_id']=='K01' for s in schedule(list(range(10))) if s['task']=='legacy'))
    def test_runner_request_do_not_import_test_or_solver(self):
        root=Path(__file__).resolve().parent.parent/'adm_diagnostic_v052'
        for name in ('requests.py','runner.py'):
            tree=ast.parse((root/name).read_text())
            for n in ast.walk(tree):
                if isinstance(n,ast.ImportFrom):self.assertNotIn('tests',n.module or '');self.assertNotIn('calibration',n.module or '');self.assertNotIn('measure',n.module or '')
    def test_schema_nodes_before_final(self):
        s=next(x for x in schedule(list(range(10))) if x['task']=='factorial');self.assertEqual(list(schema_for(s)['properties'])[:2],['nodes','final_node_id'])
    def test_no_copy_id_reused_as_primary(self):
        s=schedule(list(range(10)));self.assertFalse({x['id'] for x in s if x['task']=='factorial'}&{x['id'] for x in s if x['task']=='copy_control'})
