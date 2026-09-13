"""모델 이름 이외 요청 변경, 표본 제외, identity 우회, seed 선택을 거부한다."""
import ast,collections,copy,contextlib,io,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from model_probe_v055.contracts import ContractError,read_json,write_json,digest,unb64,canonical
from model_probe_v055.plan import validate_plan,prepare
from model_probe_v055.metadata import capture,validate_pair
from model_probe_v055.requests import request_bytes
from model_probe_v055.design import schedule
from .fixtures import shared

class Design(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.base=shared();cls.plan=cls.base['plan']
    def test_240_crossed_slots(self):self.assertEqual(len(self.plan['slots']),240)
    def test_model_120_each(self):self.assertEqual(collections.Counter(s['model_key'] for s in self.plan['slots']),{'reference':120,'candidate':120})
    def test_all_seeds_preserved(self):self.assertEqual(len(self.plan['seeds']),10)
    def test_same_12_order_per_seed(self):
        for seed in self.plan['seeds']:
            cells=[[s['reference_slot_id'] for s in self.plan['slots'] if s['seed']==seed and s['model_key']==key] for key in self.plan['model_keys']]
            self.assertEqual(*cells)
    def test_model_first_balanced(self):
        keys=[next(s for s in self.plan['slots'] if s['seed']==seed)['model_key'] for seed in self.plan['seeds']]
        self.assertEqual(collections.Counter(keys),{'reference':5,'candidate':5})
    def test_280_actions_40_metadata(self):
        self.assertEqual(len(self.plan['actions']),280);self.assertEqual(sum(a['kind']=='metadata' for a in self.plan['actions']),40)
    def test_capture_zero_inference(self):self.assertEqual(self.plan['capture']['inference_calls'],0)
    def test_prepare_offline(self):
        with tempfile.TemporaryDirectory() as td,patch('model_probe_v055.metadata.OllamaHTTP',side_effect=AssertionError('network forbidden')):
            p=prepare(self.base['bundle'],self.base['root']/'capture/capture.json',Path(td)/'p.json');self.assertEqual(p['max_calls'],240)
    def test_reference_requests_byte_exact(self):
        for s in self.plan['slots']:
            if s['model_key']=='reference':self.assertEqual(request_bytes(self.plan,s),unb64(self.plan['reference']['request_bank'][s['reference_slot_id']]))
    def test_candidate_only_model_field(self):
        import json
        for s in self.plan['slots']:
            if s['model_key']=='candidate':
                a=json.loads(request_bytes(self.plan,s));b=json.loads(unb64(self.plan['reference']['request_bank'][s['reference_slot_id']]))
                self.assertNotEqual(a.pop('model'),b.pop('model'));self.assertEqual(a,b)
    def test_models_same_schema_messages_options(self):
        import json
        for s in self.plan['slots']:
            if s['model_key']=='candidate':
                q={**s,'model_key':'reference'};a=json.loads(request_bytes(self.plan,s));b=json.loads(request_bytes(self.plan,q))
                for key in ('messages','options','format','keep_alive'):self.assertEqual(a[key],b[key])
    def test_no_solver_import_in_runner_requests(self):
        root=Path(__file__).resolve().parent.parent/'model_probe_v055'
        for name in ('runner.py','requests.py'):
            text=(root/name).read_text();self.assertNotIn('tests_v',text);self.assertNotIn('generic_trace',text);self.assertNotIn('depth_bounds',text)
    def test_plan_resealed_budget_rejected(self):
        p=copy.deepcopy(self.plan);p['max_calls']=1;p['plan_sha256']=digest({k:v for k,v in p.items() if k!='plan_sha256'})
        with self.assertRaises(ContractError):validate_plan(p)
    def test_plan_resealed_schedule_rejected(self):
        p=copy.deepcopy(self.plan);p['slots'].reverse();p['plan_sha256']=digest({k:v for k,v in p.items() if k!='plan_sha256'})
        with self.assertRaises(ContractError):validate_plan(p)
    def test_forged_live_label_rejected(self):
        p=copy.deepcopy(self.plan);p['reference']['evidence_kind']='live_source_artifacts';p['reference']['receipt_sha256']=digest({k:v for k,v in p['reference'].items() if k!='receipt_sha256'});p['plan_sha256']=digest({k:v for k,v in p.items() if k!='plan_sha256'})
        with self.assertRaises(ContractError):validate_plan(p)
    def test_resealed_wrong_request_rejected(self):
        from model_probe_v055.contracts import b64
        p=copy.deepcopy(self.plan);key=next(iter(p['reference']['request_bank']));p['reference']['request_bank'][key]=b64(b'{}')
        p['reference']['request_bank_sha256']=digest(p['reference']['request_bank']);p['reference']['receipt_sha256']=digest({k:v for k,v in p['reference'].items() if k!='receipt_sha256'});p['plan_sha256']=digest({k:v for k,v in p.items() if k!='plan_sha256'})
        with self.assertRaises(ContractError):validate_plan(p)
    def test_zero_call_plan_is_rejected(self):
        p=copy.deepcopy(self.plan);p['slots']=[];p['actions']=[];p['max_calls']=0;p['plan_sha256']=digest({k:v for k,v in p.items() if k!='plan_sha256'})
        with self.assertRaises(ContractError):validate_plan(p)
    def test_missing_candidate_fails_before_calls(self):
        state=self.base['state'];state.mode='missing_candidate';state.requests.clear()
        try:
            with tempfile.TemporaryDirectory() as td:
                target=Path(td)/'capture'
                with self.assertRaises(ContractError):capture(self.base['bundle'],target)
                r=read_json(target/'capture.json');self.assertEqual(r['inference_calls'],0);self.assertEqual(len(state.requests),0);self.assertIn('candidate',r['metadata'])
        finally:state.mode='perfect'
    def test_unmatched_family_size_quant_digest_rejected(self):
        state=self.base['state']
        for mode in ('same_digest','bad_family','bad_quant','bad_size'):
            with self.subTest(mode=mode):
                state.mode=mode
                try:
                    with tempfile.TemporaryDirectory() as td:
                        with self.assertRaises(ContractError):capture(self.base['bundle'],Path(td)/'capture')
                finally:state.mode='perfect'
