from __future__ import annotations
import ast,collections,copy,inspect,unittest
from pathlib import Path
from adm_pilot_v051.design import ROLES,PROBLEM,schedule
from adm_pilot_v051.contracts import ContractError,strict_json,canonical,digest,OUTPUT_SCHEMA
from adm_pilot_v051.plan import validate_plan
from adm_pilot_v051.requests import request_bytes
from .fixtures import shared

class Design(unittest.TestCase):
    def test_twelve_conditions_and_240_slots(self):
        p=shared()['plan'];self.assertEqual(len(ROLES),12);self.assertEqual(len(p['slots']),240)
    def test_all_ten_seeds_preserved(self):
        p=shared()['plan'];self.assertEqual(len(p['seeds']),10);self.assertEqual({len([s for s in p['slots'] if s['seed']==x]) for x in p['seeds']},{24})
    def test_each_role_20_calls(self):
        self.assertEqual(set(collections.Counter(s['role_id'] for s in shared()['plan']['slots']).values()),{20})
    def test_problem_bytes_identical_for_every_role(self):
        p=shared()['plan'];texts={strict_json(request_bytes(p,s))['messages'][1]['content'] for s in p['slots']};self.assertEqual(len(texts),1)
    def test_all_roles_same_schema(self):
        p=shared()['plan'];self.assertEqual({canonical(strict_json(request_bytes(p,s))['format']) for s in p['slots']},{canonical(OUTPUT_SCHEMA)})
    def test_same_seed_requested_unchanged_sampling(self):
        p=shared()['plan']
        for s in p['slots']:
            q=strict_json(request_bytes(p,s));self.assertEqual(q['options'],dict(p['baseline']['config']['options'],seed=s['seed']))
    def test_one_axis_changes_one_instruction_line(self):
        p=shared()['plan'];seed=p['seeds'][0]
        slots=[s for s in p['slots'] if s['seed']==seed and s['cycle']==0]
        for a in slots:
            ra=next(r for r in ROLES if r['id']==a['role_id'])
            for b in slots:
                rb=next(r for r in ROLES if r['id']==b['role_id'])
                if sum(ra[k]!=rb[k] for k in ('A','D','M'))==1:
                    ta=strict_json(request_bytes(p,a))['messages'][0]['content'].splitlines();tb=strict_json(request_bytes(p,b))['messages'][0]['content'].splitlines()
                    self.assertEqual(len(ta),len(tb));self.assertEqual(sum(x!=y for x,y in zip(ta,tb)),1)
    def test_second_cycle_reverses_each_seed_order(self):
        p=shared()['plan']
        for seed in p['seeds']:
            a=[s['role_id'] for s in p['slots'] if s['seed']==seed and s['cycle']==0]
            b=[s['role_id'] for s in p['slots'] if s['seed']==seed and s['cycle']==1];self.assertEqual(a,list(reversed(b)))
    def test_measurement_function_has_no_role_parameter(self):
        from adm_pilot_v051.measure import measure
        self.assertEqual(tuple(inspect.signature(measure).parameters),('problem','payload'))
    def test_generation_does_not_import_measurement_or_fixtures(self):
        root=Path(__file__).resolve().parents[1]/'adm_pilot_v051'
        tree=ast.parse((root/'requests.py').read_text())
        imports=[n.module or '' for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
        self.assertFalse(any(any(k in s for k in ('measure','fixtures','oracle','simulate')) for s in imports))
        # runner의 audit 호출은 수집 try/finally 이후 한 번이다.
        text=(root/'runner.py').read_text();self.assertLess(text.index("status['finished_at']"),text.index('from .audit import'))
    def test_reforged_goal_plan_rejected(self):
        p=copy.deepcopy(shared()['plan']);p['problem']['goal']='Ca';p['problem_sha256']=digest(p['problem']);p['plan_sha256']=digest({k:v for k,v in p.items() if k!='plan_sha256'})
        with self.assertRaises(ContractError):validate_plan(p)
    def test_reforged_role_schedule_rejected(self):
        p=copy.deepcopy(shared()['plan']);p['slots'][0]['role_id']='schema_deep_M2';p['plan_sha256']=digest({k:v for k,v in p.items() if k!='plan_sha256'})
        with self.assertRaises(ContractError):validate_plan(p)
    def test_hash_binding_cannot_be_reforged_to_different_code(self):
        p=copy.deepcopy(shared()['plan']);p['source_fingerprint']['adm_pilot_v051/measure.py']='0'*64;p['plan_sha256']=digest({k:v for k,v in p.items() if k!='plan_sha256'})
        with self.assertRaises(ContractError):validate_plan(p)
