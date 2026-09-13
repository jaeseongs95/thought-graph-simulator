import ast,copy,collections,itertools,unittest
from fixtures import *
class Logic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.p=design.build_plan(baseline_path(),'v067_logic','synthetic')
    def test_12_calls_and_24_actions(self):self.assertEqual((len(self.p['slots']),len(self.p['actions'])),(12,24))
    def test_reference_list_valid_and_depth_not_model_measurement(self):
        for p in common.spec()['problems']:
            for c,d in zip(common.spec()['conditions'],common.spec()['depth_ranges'][p['id']]):self.assertEqual(reference.validate(p,common.spec()['reference_plans'][p['id']][c]),d)
    def test_reference_input_declares_experimenter_origin(self):
        for s in self.p['slots']:
            q=design.request_for(self.p,s);t=q['messages'][0]['content'];self.assertIn('앞선 모델의 응답이 아니다',t);r=common.load(t.split('\nprovided_route_plan: ',1)[1]);self.assertEqual(r,{'origin':'experimenter_verified_reference','rule_ids':s['reference_rule_ids']})
    def test_no_free_shallow_deep_instruction(self):
        for s in self.p['slots']:
            t=design.request_for(self.p,s)['messages'][0]['content'];self.assertNotIn('가장 작은 경로',t);self.assertNotIn('가장 큰 경로',t)
    def test_model_options_schema_unchanged(self):
        for s in self.p['slots']:
            q=design.request_for(self.p,s);old=copy.deepcopy(self.p['baseline_request']);old['options']['seed']=s['seed'];self.assertEqual({k:v for k,v in q.items() if k!='messages'},{k:v for k,v in old.items() if k!='messages'})
    def test_exact_request_independent_reconstruction(self):
        for s in self.p['slots']:self.assertEqual(common.wire(design.request_for(self.p,s)),verify._request_for(self.p,s))
    def test_all_six_canonical_proofs(self):
        for p in common.spec()['problems']:
            for b in (False,True):self.assertTrue(measure.assess(p,proof(p,b))['strict_valid']);self.assertEqual(measure.assess(p,proof(p,b)),verify._semantic(p,proof(p,b)))
    def test_requests_do_not_score_or_construct_graphs(self):
        f=next(n for n in ast.parse((ROOT/'design.py').read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='request_for');code=ast.unparse(f);self.assertNotIn('measure.',code);self.assertNotIn('reference.validate',code);self.assertNotIn('depth_ranges',code);self.assertNotIn('proof(',code)
    def test_reference_never_selected_from_user_successes(self):
        self.assertEqual(common.spec()['reference_plans'],{p['id']:{'reference_short':ROUTES[p['id']][0],'reference_long':ROUTES[p['id']][1]} for p in common.spec()['problems']})
    def test_positions_balanced_per_problem(self):
        for p in common.spec()['problems']:
            rows=[s for s in self.p['slots'] if s['problem_id']==p['id']];self.assertEqual(collections.Counter((r['condition'],r['period']) for r in rows),{('reference_short',0):1,('reference_short',1):1,('reference_long',0):1,('reference_long',1):1})
    def test_unknown_reference_rule_rejected(self):
        with self.assertRaises(ValueError):reference.validate(common.spec()['problems'][0],['r8_3'])
    def test_missing_reference_premise_rejected(self):
        with self.assertRaises(ValueError):reference.validate(common.spec()['problems'][0],['r83','r69'])
    def test_unused_reference_rules_rejected(self):
        with self.assertRaises(ValueError):reference.validate(common.spec()['problems'][1],['n08','n91','n52'])
    def test_unfinished_reference_rejected(self):
        with self.assertRaises(ValueError):reference.validate(common.spec()['problems'][2],['m18','m33','m05','m84'])
    def test_duplicate_and_nonfinite_json_rejected(self):
        for raw in (b'{"a":1,"a":2}',b'{"x":NaN}',b'{"x":1e999}'):
            with self.assertRaises(ValueError):common.load(raw)
    def test_graph_extra_nodes_not_deleted(self):
        p=common.spec()['problems'][0];x=proof(p);x['nodes'].append({'id':'unused','atom':p['facts'][0],'rule':None,'parents':[]});old=copy.deepcopy(x);m=measure.assess(p,x);self.assertTrue(m['proof_valid']);self.assertFalse(m['strict_valid']);self.assertEqual(x,old)
    def test_reference_foreground_no_correct_dag(self):
        for s in self.p['slots']:
            v=common.load(design.request_for(self.p,s)['messages'][0]['content'].split('\nprovided_route_plan: ',1)[1]);self.assertEqual(set(v),{'origin','rule_ids'});self.assertNotIn('nodes',v)
    def test_independent_verifier_does_not_import_production(self):
        t=ast.parse((ROOT/'verify.py').read_text());mods=[x.module for x in ast.walk(t) if isinstance(x,ast.ImportFrom)]+[a.name for x in ast.walk(t) if isinstance(x,ast.Import) for a in x.names];self.assertFalse(set(mods)&{'design','report','measure','run','reference'})
    def test_empty_records_not_declared_semantic_failure(self):
        r=report.summarize(self.p,[],'crashed');self.assertIsNone(r['overall']['positive_control_ready']);self.assertEqual(r['overall']['next_decision'],'measurement_incomplete');self.assertEqual(r['failure_layers']['proof_failures'],0)
