import ast,base64,copy,json,unittest
from pathlib import Path
from fixtures import *
import route
class Logic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.plan=design.build_plan(baseline_path(),'v066_logic','synthetic')
    def test_36_calls_48_actions(self):self.assertEqual((len(self.plan['slots']),len(self.plan['actions'])),(36,48))
    def test_arms_budget_12_24(self):self.assertEqual([sum(s['arm']==a for s in self.plan['slots']) for a in ('direct','staged')],[12,24])
    def test_one_plan_one_parent_per_construct(self):
        for s in self.plan['slots']:
            if s['stage']=='construct':
                before=next(p for p in self.plan['slots'] if p['id']==s['parent_plan_id']);self.assertEqual(before['stage'],'plan');self.assertEqual(before['direction'],s['direction']);self.assertEqual(s['previous_call_id'],before['id'])
    def test_valid_route_does_not_report_actual_D(self):
        for p in common.spec()['problems']:
            for i in (0,1):
                m=route.assess_plan(p,{'rule_ids':ROUTES[p['id']][i]});self.assertTrue(m['plan_valid']);self.assertEqual(m['planned_D'],common.spec()['depth_ranges'][p['id']][i]);self.assertNotIn('actual_D',m)
    def test_bad_id_not_repaired(self):
        m=route.assess_plan(common.spec()['problems'][0],{'rule_ids':['r8_3']});self.assertFalse(m['plan_valid']);self.assertEqual(m['selected_rule_ids'],['r8_3'])
    def test_extra_route_rejected(self):
        p=common.spec()['problems'][1];self.assertFalse(route.assess_plan(p,{'rule_ids':['n64','n52']})['plan_valid'])
    def test_wrong_order_rejected(self):
        p=common.spec()['problems'][0];self.assertFalse(route.assess_plan(p,{'rule_ids':['r69','r04','r57','r21']})['plan_valid'])
    def test_duplicate_rule_rejected(self):self.assertFalse(route.assess_plan(common.spec()['problems'][0],{'rule_ids':['r83','r83']})['plan_valid'])
    def test_malformed_plan_not_logical_error(self):
        for v in (None,{},[],{'rule_ids':[]}):self.assertIsNone(route.assess_plan(common.spec()['problems'][0],v)['plan_valid'])
    def test_transfer_preserves_whitespace_and_wrong_content(self):
        s=next(s for s in self.plan['slots'] if s['stage']=='construct');text=' {"rule_ids": ["unknown_rule"]}\n  ';raw=common.wire({'message':{'content':text}});q=design.request_for(self.plan,s,raw);v=common.load(q['messages'][0]['content'].split('\nroute_plan_response: ')[1]);self.assertEqual(v['content'],text);self.assertEqual(v['response_sha256'],common.sha(raw))
    def test_unparsed_content_also_forwarded(self):
        raw=common.wire({'message':{'content':'{안됨'}});self.assertEqual(design.transfer(raw,'x')['content'],'{안됨')
    def test_missing_message_no_fabricated_plan(self):self.assertIsNone(design.transfer(b'{}','x')['content'])
    def test_request_does_not_import_scorer(self):
        node=next(n for n in ast.parse((ROOT/'design.py').read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='request_for');calls=[ast.unparse(n.func) for n in ast.walk(node) if isinstance(n,ast.Call)];self.assertFalse(any('assess' in c or 'depth' in c for c in calls))
    def test_no_rule_id_targets_or_enum_in_plan_request(self):
        s=next(s for s in self.plan['slots'] if s['stage']=='plan');q=design.request_for(self.plan,s);before=q['messages'][0]['content'].split('\n\nproblem: ')[0]
        for p in self.plan['protocol']['problems']:
            for r in p['rules']:self.assertNotIn(r['id'],before)
        self.assertNotIn('enum',str(q['format']));self.assertNotIn('const',str(q['format']))
    def test_same_seed_options_all_stages(self):
        for s in self.plan['slots']:
            q=design.request_for(self.plan,s,b'{}' if s['stage']=='construct' else None);a=copy.deepcopy(self.plan['baseline_request']['options']);a['seed']=s['seed'];self.assertEqual(q['options'],a)
    def test_schema_strict_json_duplicate_nonfinite(self):
        for raw in (b'{"x":1,"x":2}',b'{"x":NaN}'):
            with self.assertRaises(ValueError):common.load(raw)
    def test_graph_scorer_unchanged_semantics(self):
        for p in common.spec()['problems']:
            for d in (False,True):self.assertTrue(measure.assess(p,proof(p,d))['strict_valid'])
    def test_wrong_plan_cannot_match_correct_graph(self):
        p=common.spec()['problems'][0];self.assertFalse(route.follows_plan({'rule_ids':['unknown']},proof(p),True))
    def test_own_independent_plan_cases(self):
        for p in common.spec()['problems']:
            cases=[{'rule_ids':r} for r in [*ROUTES[p['id']],[],['unknown'],ROUTES[p['id']][1][::-1],ROUTES[p['id']][0]*2]]+[None,{}, {'rule_ids':True}]
            for c in cases:self.assertEqual(route.assess_plan(p,c),verify._plan_semantics(p,c))
if __name__=='__main__':unittest.main()
