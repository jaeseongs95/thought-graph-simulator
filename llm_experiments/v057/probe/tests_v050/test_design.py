from __future__ import annotations
import copy,unittest
from unittest.mock import patch
from criterion_probe_v050.contracts import *
from criterion_probe_v050.plan import *
from criterion_probe_v050.requests import *
from criterion_probe_v050.scoring import expected
from .fixtures import shared

class Design(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.p=shared()['plan']
    def test_slot_count(self):self.assertEqual(len(slots(self.p)),560)
    def test_80_blocks(self):self.assertEqual(len(self.p['blocks']),80)
    def test_seeds_all_and_cycles(self):
        from collections import Counter
        c=Counter((b['seed'],b['case_id']) for b in self.p['blocks']);self.assertEqual(len(c),40);self.assertEqual(set(c.values()),{2})
    def test_dependencies_are_prior_slots(self):
        seen=set()
        for s in slots(self.p):
            self.assertTrue(set(dependency_ids(s))<=seen);self.assertNotIn(s['id'],seen);seen.add(s['id'])
    def test_cyclic_order_reversed(self):
        lookup={(b['seed'],b['case_id'],b['cycle']):b for b in self.p['blocks']}
        for b in self.p['blocks']:
            if b['cycle']==0:
                nxt=lookup[b['seed'],b['case_id'],1];self.assertEqual(nxt['groups'],b['groups'][::-1]);self.assertEqual(nxt['branches'],b['branches'][::-1])
    def test_all_truth_cases_present(self):
        self.assertEqual({tuple(expected(c)['primitives'].values()) for c in self.p['cases']},{(False,False),(False,True),(True,False),(True,True)})
    def test_oneshot_only_gap_order_differs(self):
        b=self.p['blocks'][0];ls={s['stage']:s for s in slots(self.p) if s['block_id']==b['id']}
        left=request_bytes(self.p,ls['oneshot_original'],{});right=request_bytes(self.p,ls['oneshot_commuted'],{})
        self.assertEqual(left.replace(GAP_ORIGINAL.encode(),GAP_COMMUTED.encode()),right)
    def test_request_never_contains_gold_answer_fields(self):
        s=next(s for s in slots(self.p) if s['stage']=='extract');q=strict_json(request_bytes(self.p,s,{}))
        self.assertNotIn('expected',q['messages'][1]['content']);self.assertNotIn('case_id',q['messages'][1]['content'])
    def test_bad_primitive_is_forwarded_verbatim(self):
        s=next(s for s in slots(self.p) if s['stage']=='gap_direct');c=next(c for c in self.p['cases'] if c['id']==s['case_id']);p=expected(c);p.pop('finding');p['primitives']={'same_as_goal':False,'in_facts':True}
        q=strict_json(request_bytes(self.p,s,{s['block_id']+'__extract':p}));i=strict_json(q['messages'][1]['content'][7:])
        self.assertIs(i['a'],False);self.assertIs(i['b'],True)
    def test_not_result_not_recomputed(self):
        s=next(s for s in slots(self.p) if s['stage']=='gap_and');p=expected(self.p['cases'][0]);p.pop('finding');p['primitives']={'same_as_goal':True,'in_facts':False}
        q=strict_json(request_bytes(self.p,s,{s['block_id']+'__extract':p,s['block_id']+'__not':{'value':False}}))
        self.assertIs(strict_json(q['messages'][1]['content'][7:])['b'],False)
    def test_missing_parent_rejected(self):
        s=next(s for s in slots(self.p) if s['stage']=='proof')
        with self.assertRaises(ContractError):request_bytes(self.p,s,{})
    def test_semantic_requests_keep_runtime_options(self):
        s=next(s for s in slots(self.p) if s['stage']=='extract');q=strict_json(request_bytes(self.p,s,{}))
        self.assertEqual(q['options'],dict(self.p['baseline']['config']['options'],seed=s['seed']))
    def test_plan_cannot_filter_seed(self):
        p=copy.deepcopy(self.p);p['seeds']=p['seeds'][1:];p['plan_sha256']=digest({k:v for k,v in p.items() if k!='plan_sha256'})
        with self.assertRaises(ContractError):validate_plan(p)
    def test_plan_cannot_change_case(self):
        p=copy.deepcopy(self.p);p['cases'][0]['probe']['atom']='Cc';p['plan_sha256']=digest({k:v for k,v in p.items() if k!='plan_sha256'})
        with self.assertRaises(ContractError):validate_plan(p)
    def test_plan_cannot_reorder_after_hash(self):
        p=copy.deepcopy(self.p);p['blocks'].reverse();p['plan_sha256']=digest({k:v for k,v in p.items() if k!='plan_sha256'})
        with self.assertRaises(ContractError):validate_plan(p)
    def test_no_oracle_in_generation_dependencies(self):
        import ast
        for n in ('requests.py','runner.py','plan.py'):
            src=(Path(__file__).parents[1]/'criterion_probe_v050'/n).read_text()
            self.assertNotIn('from .scoring',src);self.assertNotIn('from .oracle',src)
