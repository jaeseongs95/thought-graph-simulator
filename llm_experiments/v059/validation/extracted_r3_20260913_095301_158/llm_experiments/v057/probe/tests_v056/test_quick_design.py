import collections,copy,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from layout_probe_v056.contracts import ContractError,canonical,digest,read_plan_json,read_json,write_json,unb64
from layout_probe_v056.plan import validate_plan
from layout_probe_v056.requests import request_bytes
from layout_probe_v056.__main__ import main
from .quick_fixture import plan

class Design(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.p=plan()
    def test_complete_factorial_480(self):self.assertEqual(len(self.p['slots']),480)
    def test_all_cells_ten_seeds(self):self.assertEqual(set(collections.Counter((s['model_key'],s['layout'],s['problem_id'],s['arm'],s['direction']) for s in self.p['slots']).values()),{10})
    def test_directed_neutral_320_160(self):self.assertEqual(sum(s['direction']=='neutral' for s in self.p['slots']),160)
    def test_actions_520_metadata_40(self):self.assertEqual((len(self.p['actions']),sum(a['kind']=='metadata' for a in self.p['actions'])),(520,40))
    def test_models_first_five_each(self):self.assertEqual(collections.Counter(next(s['model_key'] for s in self.p['slots'] if s['seed']==seed) for seed in self.p['seeds']),{'reference':5,'candidate':5})
    def test_layout_first_six_each_block(self):
        for block in range(20):
            cells=[s for s in self.p['slots'] if s['block']==block];self.assertEqual(collections.Counter(s['layout'] for s in cells[::2]),{'split':6,'merged':6})
    def test_split_wire_byte_identical(self):
        for s in self.p['slots']:
            if s['layout']=='split':self.assertEqual(request_bytes(self.p,s),unb64(self.p['reference']['request_bank'][s['reference_slot_id']]))
    def test_merged_preserves_all_text_and_other_fields(self):
        for s in self.p['slots']:
            if s['layout']!='merged':continue
            a=json.loads(request_bytes(self.p,s));b=json.loads(unb64(self.p['reference']['request_bank'][s['reference_slot_id']]))
            ms=b.pop('messages');new=a.pop('messages');self.assertEqual(a,b)
            self.assertEqual(new,[{'role':'user','content':ms[0]['content']+'\n\n'+ms[1]['content']}])
    def test_no_solver_import_in_runner_requests(self):
        base=Path(__file__).resolve().parents[1]/'layout_probe_v056'
        for fn in ['runner.py','requests.py']:
            text=(base/fn).read_text();self.assertNotIn('tests_v',text);self.assertNotIn('depth_bounds',text);self.assertNotIn('generic_trace',text)
    def test_compact_plan_under_eight_mib(self):self.assertLess(len(canonical(self.p)),8*1024**2)
    def test_no_recursive_plan_base64(self):self.assertNotIn('plan_b64',self.p['reference']);self.assertNotIn('capture',self.p)
    def test_resealed_budget_change_rejected(self):
        p=copy.deepcopy(self.p);p['max_calls']=1;p['plan_sha256']=digest({k:v for k,v in p.items() if k!='plan_sha256'})
        with self.assertRaises(ContractError):validate_plan(p)
    def test_resealed_schedule_change_rejected(self):
        p=copy.deepcopy(self.p);p['actions'].reverse();p['plan_sha256']=digest({k:v for k,v in p.items() if k!='plan_sha256'})
        with self.assertRaises(ContractError):validate_plan(p)
    def test_source_change_rejected(self):
        p=copy.deepcopy(self.p);p['source_fingerprint']['layout_probe_v056/requests.py']='0'*64;p['plan_sha256']=digest({k:v for k,v in p.items() if k!='plan_sha256'})
        with self.assertRaises(ContractError):validate_plan(p)
    def test_unknown_layout_rejected(self):
        s=self.p['slots'][0]|{'layout':'other'}
        with self.assertRaises(ContractError):request_bytes(self.p,s)
    def test_missing_request_rejected(self):
        p=copy.deepcopy(self.p);p['reference']['request_bank'].pop(next(iter(p['reference']['request_bank'])));p['reference']['receipt_sha256']=digest({k:v for k,v in p['reference'].items() if k!='receipt_sha256'});p['plan_sha256']=digest({k:v for k,v in p.items() if k!='plan_sha256'})
        with self.assertRaises(ContractError):validate_plan(p)
    def test_show_real_dispatch_without_network(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'plan.json';write_json(p,self.p)
            with patch('sys.stdout',new=io.StringIO()),patch('layout_probe_v056.runner.OllamaHTTP',side_effect=AssertionError('no network')):self.assertEqual(main(['show','--plan',str(p)]),0)
    def test_large_local_plan_not_generic_response(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'large.json';p.write_bytes(b'{"x":"'+b'x'*(8*1024**2+100)+b'"}')
            self.assertEqual(len(read_plan_json(p)['x']),8*1024**2+100)
            with self.assertRaises(ContractError):read_json(p)
    def test_plan_duplicate_key_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'p';p.write_bytes(b'{"x":1,"x":2}')
            with self.assertRaises(ContractError):read_plan_json(p)
    def test_plan_nonfinite_numbers_rejected(self):
        for v in [b'NaN',b'Infinity',b'1e999']:
            with tempfile.TemporaryDirectory() as td:
                p=Path(td)/'p';p.write_bytes(b'{"x":'+v+b'}')
                with self.assertRaises(ContractError):read_plan_json(p)
    def test_plan_limit_before_parse(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'p'
            with p.open('wb') as f:f.truncate(32*1024**2+1)
            with self.assertRaises(ContractError):read_plan_json(p)
