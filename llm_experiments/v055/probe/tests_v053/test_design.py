"""동일 입력·무보정·전체 seed·요청 바이트 대비를 검사한다."""
import ast
import collections
import copy
import json
import unittest
from pathlib import Path
from adm_diagnostic_v052.requests import request_bytes as previous_request
from depth_probe_v053.contracts import ContractError,strict_json,unb64,digest,write_json
from depth_probe_v053.design import PROBLEMS,ARMS,DIRECTIONS,schedule
from depth_probe_v053.plan import validate_plan,prepare
from depth_probe_v053.requests import request_bytes,DEPTH_DEFINITION
from depth_probe_v053.schema import schema_for
from adm_pilot_v051.requests import D
from .fixtures import shared,copied

class Design(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=shared();cls.plan=cls.base['plan']
    def test_full_120_with_80_directed(self):
        self.assertEqual(len(self.plan['slots']),120);self.assertEqual(sum(s['direction']!='neutral' for s in self.plan['slots']),80)
    def test_balanced_cells(self):
        cells=collections.Counter((s['problem_id'],s['arm'],s['direction']) for s in self.plan['slots'])
        self.assertEqual(len(cells),12);self.assertEqual(set(cells.values()),{10})
    def test_all_original_seeds_preserved(self):
        old=strict_json(unb64(self.plan['reference']['plan_b64']));self.assertEqual(self.plan['seeds'],old['seeds'])
    def test_original_40_request_bytes_identical(self):
        old=strict_json(unb64(self.plan['reference']['plan_b64']))
        oldmap={(s['seed'],s['problem_id'],s['role_id']):s for s in old['slots'] if s['task']=='graph_only'}
        count=0
        for s in self.plan['slots']:
            if s['arm']=='original' and s['direction']!='neutral':
                previous=oldmap[s['seed'],s['problem_id'],'instance_'+s['direction']+'_M0']
                self.assertEqual(request_bytes(self.plan,s),previous_request(old,previous));count+=1
        self.assertEqual(count,40)
    def test_only_definition_paragraph_changes(self):
        for s in self.plan['slots']:
            if s['arm']!='original':continue
            changed={**s,'arm':'defined'}
            a=strict_json(request_bytes(self.plan,s));b=strict_json(request_bytes(self.plan,changed))
            self.assertEqual(b['messages'][0]['content'].count(DEPTH_DEFINITION),1)
            b['messages'][0]['content']=b['messages'][0]['content'].replace(DEPTH_DEFINITION,'',1)
            self.assertEqual(a,b)
    def test_neutral_has_no_direction_instruction(self):
        for s in self.plan['slots']:
            if s['direction']=='neutral':
                text=strict_json(request_bytes(self.plan,s))['messages'][0]['content']
                self.assertNotIn(D['shallow'],text);self.assertNotIn(D['deep'],text)
    def test_user_input_problem_unchanged(self):
        for s in self.plan['slots']:
            request=strict_json(request_bytes(self.plan,s));self.assertEqual(json.loads(request['messages'][1]['content'][9:]),PROBLEMS[s['problem_id']])
    def test_schema_same_all_conditions(self):
        schemas=[schema_for(s) for s in self.plan['slots']];self.assertTrue(all(x==schemas[0] for x in schemas))
    def test_no_response_context_or_host_answers(self):
        for s in self.plan['slots']:
            request=strict_json(request_bytes(self.plan,s));self.assertEqual([m['role'] for m in request['messages']],['system','user'])
            self.assertEqual(set(request['format']['properties']),{'nodes','final_node_id'})
            self.assertNotIn('reference_record',json.dumps(request))
    def test_request_does_not_import_measurement_or_fixture(self):
        source=Path(__file__).resolve().parent.parent/'depth_probe_v053/requests.py'
        tree=ast.parse(source.read_text())
        modules=[n.module or '' for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
        self.assertFalse(any(any(word in m for word in ('measure','oracle','fixture','calibration')) for m in modules))
    def test_fixed_order(self):
        self.assertEqual(schedule(self.plan['seeds']),self.plan['slots'])
    def test_tampered_seed_resealed_is_rejected(self):
        p=copy.deepcopy(self.plan);p['seeds'][0]+=1;p['plan_sha256']=digest({k:v for k,v in p.items() if k!='plan_sha256'})
        with self.assertRaises(ContractError):validate_plan(p)
    def test_tampered_problem_resealed_is_rejected(self):
        p=copy.deepcopy(self.plan);p['problems']['K01']['goal']='Ca';p['plan_sha256']=digest({k:v for k,v in p.items() if k!='plan_sha256'})
        with self.assertRaises(ContractError):validate_plan(p)
    def test_tampered_policy_resealed_is_rejected(self):
        p=copy.deepcopy(self.plan);p['policy']['retry']=True;p['plan_sha256']=digest({k:v for k,v in p.items() if k!='plan_sha256'})
        with self.assertRaises(ContractError):validate_plan(p)
    def test_source_fingerprint_change_rejected(self):
        p=copy.deepcopy(self.plan);p['source_fingerprint'][next(iter(p['source_fingerprint']))]='0'*64;p['plan_sha256']=digest({k:v for k,v in p.items() if k!='plan_sha256'})
        with self.assertRaises(ContractError):validate_plan(p)
    def test_existing_plan_not_overwritten(self):
        with copied() as (root,plan,run,base):
            with self.assertRaises(ContractError):prepare(base['bundle'],plan)
