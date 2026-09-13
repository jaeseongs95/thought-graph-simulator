import copy,unittest,collections,ast
from pathlib import Path
from .quick_fixture import plan
from selection_probe_v057.plan import validate_plan
from selection_probe_v057.contracts import ContractError,unb64,strict_json,digest
from selection_probe_v057.requests import request_bytes,CHOICE_SCHEMA
from order_probe_v054.design import problem_for

class Design(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.p=plan()
    def test_480_slots_520_actions(self):self.assertEqual((len(self.p['slots']),len(self.p['actions'])),(480,520))
    def test_full_factorial_no_duplicate(self):
        c=collections.Counter((s['mode'],s['model_key'],s['problem_id'],s['arm'],s['direction'],s['seed']) for s in self.p['slots']);self.assertEqual(len(c),480);self.assertEqual(set(c.values()),{1})
    def test_graph_240_bytes_preserved(self):
        for s in self.p['slots']:
            if s['mode']=='graph':self.assertEqual(request_bytes(self.p,s),unb64(self.p['reference']['request_bank'][s['reference_slot_id']]))
    def test_choice_nontext_fields_preserved(self):
        for s in self.p['slots']:
            if s['mode']=='choice':
                old=strict_json(unb64(self.p['reference']['request_bank'][s['reference_slot_id']]));new=strict_json(request_bytes(self.p,s))
                self.assertEqual({k:v for k,v in old.items() if k not in ('messages','format')},{k:v for k,v in new.items() if k not in ('messages','format')})
    def test_problem_bytes_preserved(self):
        for s in self.p['slots']:
            old=strict_json(unb64(self.p['reference']['request_bank'][s['reference_slot_id']]))
            new=strict_json(request_bytes(self.p,s));self.assertEqual(old['messages'][0]['content'].rsplit('\n\nproblem: ',1)[1],new['messages'][0]['content'].rsplit('\n\nproblem: ',1)[1])
    def test_direction_text_preserved(self):
        for s in self.p['slots']:
            old=strict_json(unb64(self.p['reference']['request_bank'][s['reference_slot_id']]))['messages'][0]['content']
            new=strict_json(request_bytes(self.p,s))['messages'][0]['content']
            if s['direction']!='neutral':self.assertEqual(old.split('\n경로 지시:\n')[1].split('\nJSON')[0],new.split('\n경로 지시:\n')[1].split('\nJSON')[0])
            else:self.assertNotIn('\n경로 지시:\n',new)
    def test_schema_no_answer_enum(self):
        self.assertNotIn('enum',str(CHOICE_SCHEMA));self.assertNotIn('const',str(CHOICE_SCHEMA));self.assertEqual(set(CHOICE_SCHEMA['properties']),{'final_rule_id'})
    def test_no_answer_ids_in_choice_instruction(self):
        from selection_probe_v057.requests import CHOICE_INSTRUCTION
        for p in self.p['problems'].values():
            for rule in p['rules']:self.assertNotIn(rule['id'],CHOICE_INSTRUCTION)
    def test_request_module_no_oracle_import(self):
        text=(Path(__file__).parents[1]/'selection_probe_v057/requests.py').read_text();tree=ast.parse(text)
        names=[n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
        self.assertFalse(any('measure' in str(n) or 'oracle' in str(n) for n in names))
    def test_models_lead_five_each(self):
        c=collections.Counter(self.p['slots'][48*i]['model_key'] for i in range(10));self.assertEqual(c,{'reference':5,'candidate':5})
    def test_mode_lead_six_each_per_block(self):
        for block in range(20):
            ss=[s for s in self.p['slots'] if s['block']==block];self.assertEqual(collections.Counter(s['mode'] for s in ss[::2]),{'graph':6,'choice':6})
    def test_rehashed_policy_tamper_rejected(self):
        p=copy.deepcopy(self.p);p['policy']['retry']=True;p['plan_sha256']=digest({k:v for k,v in p.items() if k!='plan_sha256'})
        with self.assertRaises(ContractError):validate_plan(p)
    def test_rehashed_slot_drop_rejected(self):
        p=copy.deepcopy(self.p);p['slots'].pop();p['plan_sha256']=digest({k:v for k,v in p.items() if k!='plan_sha256'})
        with self.assertRaises(ContractError):validate_plan(p)
    def test_wrong_mode_rejected(self):
        s=copy.deepcopy(self.p['slots'][0]);s['mode']='force'
        with self.assertRaises(ContractError):request_bytes(self.p,s)
    def test_wrong_seed_rejected(self):
        s=copy.deepcopy(self.p['slots'][0]);s['seed']+=1
        with self.assertRaises(ContractError):request_bytes(self.p,s)
    def test_two_layouts_not_picked_per_model(self):self.assertEqual({s['layout'] for s in self.p['slots']},{'merged'})
