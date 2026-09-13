"""무추론 빠른 검증: 의미·역방향·정답 보정 금지·과제 범위."""
import ast,copy,unittest
from pathlib import Path
from fixtures import common,design,report,verify,proof,envelope
import measure

class Semantics(unittest.TestCase):
    def test_six_specified_paths(self):
        for p in common.spec()['problems']:
            for d,long in zip(common.spec()['depth_ranges'][p['id']],(False,True)):
                with self.subTest(problem=p['id'],long=long):
                    m=measure.assess(p,proof(p,long));self.assertTrue(m['strict_valid']);self.assertEqual(m['actual_D'],d);self.assertEqual(m,verify._semantic(p,proof(p,long)))
    def test_extra_is_not_logical_error(self):
        for p in common.spec()['problems']:
            x=proof(p,True);x['nodes'].append({'id':'unused','atom':p['facts'][0],'rule':None,'parents':[]});before=copy.deepcopy(x)
            m=measure.assess(p,x);self.assertTrue(m['proof_valid']);self.assertFalse(m['strict_valid']);self.assertIsNone(m['actual_D']);self.assertEqual(m['error_codes'],['extra_unused_node']);self.assertEqual(x,before)
    def test_node_order_is_not_logical_error(self):
        p=common.spec()['problems'][0];x=proof(p,True);x['nodes'].reverse();m=measure.assess(p,x);self.assertTrue(m['proof_valid']);self.assertFalse(m['strict_valid']);self.assertIsNone(m['actual_D'])
    def test_wrong_parents_stay_wrong(self):
        p=common.spec()['problems'][0];x=proof(p,True);x['nodes'][-1]['parents']=[];self.assertFalse(measure.assess(p,x)['proof_valid'])
    def test_unknown_rule_not_repaired(self):
        p=common.spec()['problems'][0];x=proof(p,True);x['nodes'][-1]['rule']='r6_9';self.assertFalse(measure.assess(p,x)['strict_valid'])
    def test_missing_final_not_repaired(self):
        p=common.spec()['problems'][0];x=proof(p,True);x['final_node_id']='missing';self.assertFalse(measure.assess(p,x)['strict_valid'])
    def test_duplicate_node_not_last_wins(self):
        p=common.spec()['problems'][0];x=proof(p,True);x['nodes'].append(copy.deepcopy(x['nodes'][0]));self.assertIn('duplicate_id',measure.assess(p,x)['error_codes'])
    def test_input_false_fact(self):
        p=common.spec()['problems'][0];x=proof(p,True);x['nodes'][0]['atom']='invented';self.assertFalse(measure.assess(p,x)['proof_valid'])
    def test_duplicate_key_rejected(self):
        with self.assertRaises(ValueError):common.load(b'{"nodes":[],"nodes":[]}')
    def test_nonfinite_rejected(self):
        for v in (b'NaN',b'Infinity',b'1e999'):
            with self.assertRaises(ValueError):common.load(b'{"a":'+v+b'}')
    def test_response_limit(self):
        with self.assertRaises(ValueError):common.load(b' '*(8*1024**2+1))
    def test_48_independent_semantic_cases(self):
        count=0
        for p in common.spec()['problems']:
            for long in (False,True):
                base=proof(p,long);cases=[base,None,{},copy.deepcopy(base),copy.deepcopy(base),copy.deepcopy(base),copy.deepcopy(base),copy.deepcopy(base)]
                cases[3]['nodes'].reverse();cases[4]['nodes'][-1]['rule']='wrong';cases[5]['nodes'][-1]['parents']=[];cases[6]['final_node_id']='missing';cases[7]['nodes'].append({'id':'unused','atom':p['facts'][0],'rule':None,'parents':[]})
                for c in cases:self.assertEqual(measure.assess(p,c),verify._semantic(p,c));count+=1
        self.assertEqual(count,48)
    def test_request_generator_does_not_call_depth_calculator(self):
        tree=ast.parse((common.ROOT/'design.py').read_text());f=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='request_for')
        s=ast.unparse(f);self.assertNotIn('measure.',s);self.assertNotIn('depth_ranges',s);self.assertNotIn('proof(',s)
    def test_verifier_no_producer_import(self):
        tree=ast.parse((common.ROOT/'verify.py').read_text());imports=[]
        for n in ast.walk(tree):
            if isinstance(n,ast.Import):imports.extend(a.name for a in n.names)
            elif isinstance(n,ast.ImportFrom):imports.append(n.module or '')
        self.assertFalse(set(imports)&{'design','measure','report','run'})
    def test_schedule_balanced_twelve(self):
        slots=design._slots(common.spec());self.assertEqual(len(slots),12);self.assertEqual(len(design._actions(slots,6)),24)
        for p in common.spec()['problems']:
            rs=[s for s in slots if s['problem_id']==p['id']];self.assertEqual([s['condition'] for s in rs],['prescribed_short','prescribed_long','prescribed_long','prescribed_short'])
    def test_bound_12_and_49152(self):self.assertEqual(common.spec()['max_inference_calls'],12);self.assertEqual(common.spec()['generation_token_upper_bound'],12*4096)
