from __future__ import annotations
import copy
import itertools
import unittest
from collections import Counter
from paired_probe_v049.contracts import ContractError, EXPRS, digest, strict_json
from paired_probe_v049.plan import ARMS,DIRECT,ORDER_SEED,CYCLES,make_schedule,slots,validate_plan,make_request,order_rows
from paired_probe_v049.oracle import evaluate,score_pipeline
from .fixtures import shared

class DesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.plan=shared()['plan']
    def test_eighty_blocks_480_requests(self):
        self.assertEqual(len(self.plan['blocks']),80);self.assertEqual(len(slots(self.plan)),480)
    def test_all_ten_baseline_seeds_retained(self):
        from paired_probe_v048.plan import default_seeds
        self.assertEqual(self.plan['seeds'],default_seeds([1729]))
    def test_all_four_inputs_two_times_per_seed(self):
        c=Counter((b['seed'],b['a'],b['b']) for b in self.plan['blocks'])
        self.assertEqual(len(c),40);self.assertEqual(set(c.values()),{2})
    def test_every_arm_position_balanced(self):
        for cycle in range(2):
            for a,b in itertools.product((False,True),repeat=2):
                blocks=[x for x in self.plan['blocks'] if x['cycle']==cycle and x['a'] is a and x['b'] is b]
                c=Counter((arm,pos) for x in blocks for pos,arm in enumerate(x['arms']))
                self.assertEqual(len(c),25);self.assertEqual(set(c.values()),{2})
    def test_every_ordered_predecessor_balanced(self):
        for cycle in range(2):
            for a,b in itertools.product((False,True),repeat=2):
                blocks=[x for x in self.plan['blocks'] if x['cycle']==cycle and x['a'] is a and x['b'] is b]
                c=Counter(pair for x in blocks for pair in zip(x['arms'],x['arms'][1:]))
                self.assertEqual(len(c),20);self.assertEqual(set(c.values()),{2})
    def test_within_seed_second_order_reverses_first(self):
        d={(x['seed'],x['a'],x['b'],x['cycle']):x['arms'] for x in self.plan['blocks']}
        for seed in self.plan['seeds']:
            for a,b in itertools.product((False,True),repeat=2):self.assertEqual(d[seed,a,b,1],d[seed,a,b,0][::-1])
    def test_order_has_every_seed_in_each_cycle(self):
        for c in range(2):self.assertEqual({b['seed'] for b in self.plan['blocks'] if b['cycle']==c},set(self.plan['seeds']))
    def test_no_goal_or_answer_in_request(self):
        for s in slots(self.plan):
            r=strict_json(make_request(self.plan,s,False if s['stage']=='and' else None))
            self.assertEqual(set(strict_json(r['messages'][1]['content'][7:])),{'a','b','expression'})
            self.assertEqual(set(r['format']['properties']),{'value'})
    def test_all_direct_forms_same_manual_truth_table(self):
        truth={(False,False):False,(False,True):False,(True,False):True,(True,True):False}
        for a,b in truth:
            for arm in DIRECT:self.assertIs(evaluate(EXPRS[arm],a,b),truth[a,b])
    def test_only_outer_parentheses_are_removed(self):
        for wrapped,opened in [('original','original_open'),('commuted','commuted_open')]:
            self.assertEqual(EXPRS[wrapped][1:-1],EXPRS[opened]);self.assertIn('(NOT b)',EXPRS[opened])
    def test_all_anchor_request_bytes_match_v048(self):
        from paired_probe_v048.plan import make_request as legacy
        for s in slots(self.plan):
            if s['stage'] in ('original','commuted','not','and'):
                for parent in ((False,True) if s['stage']=='and' else (None,)):
                    self.assertEqual(make_request(self.plan,s,parent),legacy(self.plan,s,parent))
    def test_direct_request_differences_only_expression(self):
        by={}
        for s in slots(self.plan):
            if s['stage'] not in DIRECT:continue
            body=strict_json(make_request(self.plan,s));values=strict_json(body['messages'][1]['content'][7:]);values.pop('expression');body['messages'][1]['content']=values
            if s['block_id'] in by:self.assertEqual(body,by[s['block_id']])
            by[s['block_id']]=body
    def test_invalid_parent_never_silently_coerced(self):
        s=next(s for s in slots(self.plan) if s['stage']=='and')
        for value in (None,0,1,'true',[],{}):
            with self.subTest(value=value),self.assertRaises(ContractError):make_request(self.plan,s,value)
    def test_wrong_parent_is_not_corrected(self):
        s=next(s for s in slots(self.plan) if s['stage']=='and' and s['a'] and not s['b'])
        self.assertFalse(strict_json(strict_json(make_request(self.plan,s,False))['messages'][1]['content'][7:])['b'])
    def test_256_trace_patterns_accept_exactly_one(self):
        truth=list(itertools.product((False,True),repeat=2));accepted=0;masked=0
        for bits in itertools.product((False,True),repeat=8):
            scores=[score_pipeline(a,b,*bits[i*2:i*2+2]) for i,(a,b) in enumerate(truth)]
            accepted+=all(s['trace_correct'] for s in scores)
            masked+=all(s['final_correct'] for s in scores) and not all(s['trace_correct'] for s in scores)
        self.assertEqual(accepted,1);self.assertEqual(masked,15)
    def _reject(self,change):
        p=copy.deepcopy(self.plan);change(p);p['plan_sha256']=digest({k:v for k,v in p.items() if k!='plan_sha256'})
        with self.assertRaises((ValueError,KeyError,TypeError)):validate_plan(p)
    def test_seed_selection_rejected_even_with_rehash(self):self._reject(lambda p:p['seeds'].__setitem__(0,1729))
    def test_seed_boolean_rejected(self):self._reject(lambda p:p['seeds'].__setitem__(0,True))
    def test_cycle_change_rejected(self):self._reject(lambda p:p.__setitem__('cycles',6))
    def test_arm_schedule_change_rejected(self):self._reject(lambda p:p['blocks'][0]['arms'].reverse())
    def test_expression_policy_change_rejected(self):self._reject(lambda p:p['analysis_policy']['expressions'].__setitem__('original','a'))
    def test_instruction_change_rejected(self):self._reject(lambda p:p['baseline']['config']['options'].__setitem__('temperature',0))
    def test_source_digest_change_rejected(self):self._reject(lambda p:p['source_fingerprint'].__setitem__('forged.py','0'*64))
    def test_extra_top_level_field_rejected(self):self._reject(lambda p:p.__setitem__('unexpected',True))
    def test_schedule_is_deterministic(self):self.assertEqual(make_schedule(self.plan['seeds'],CYCLES,ORDER_SEED),self.plan['blocks'])
