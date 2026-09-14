"""경로 깊이, 방향/순서 교차, 무보정, 미측정, 독립 계산의 반례 시험."""
import unittest,ast,itertools,random
from fixtures import *
class Logic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.plan=design.build_plan(baseline_path(),'v070_logic','synthetic')
    def test_40_calls_60_actions_and20_pairs(self):
        self.assertEqual(len(self.plan['slots']),40);self.assertEqual(len(self.plan['actions']),60)
        self.assertEqual(len({s['pair_id'] for s in self.plan['slots']}),20)
    def test_full_factorial_and_independent_schedule(self):
        self.assertEqual(self.plan['slots'],verify._slot_schedule(self.plan['protocol']))
        for block in range(10):
            ss=[s for s in self.plan['slots'] if s['block']==block]
            self.assertEqual({(s['candidate_order_index'],s['condition']) for s in ss},set(itertools.product([0,1],['shallow','deep'])))
    def test_depth_not_rule_count(self):
        spec=self.plan['protocol']
        for pid,lens in [('E01_shared_fork',(1,3)),('C01_equal_count',(3,3)),('C02_count_reversal',(4,3))]:
            p=next(p for p in spec['problems'] if p['id']==pid);routes=spec['reference_plans'][pid]
            self.assertEqual(tuple(len(routes[c]) for c in spec['reference_conditions']),lens)
            self.assertEqual([reference.validate(p,routes[c]) for c in spec['reference_conditions']],spec['depth_ranges'][pid])
            self.assertEqual(measure.depth_ranges(p),spec['depth_ranges'][pid])
    def test_only_D_instruction_differs_in_pair(self):
        for sid in {s['pair_id'] for s in self.plan['slots']}:
            ss=[s for s in self.plan['slots'] if s['pair_id']==sid];b=[design.request_for(self.plan,s) for s in ss]
            for obj in b:
                prefix,txt=obj['messages'][0]['content'].split('\n\ninput: ');data=common.load(txt);data['requested_depth']='D_ONLY';obj['messages'][0]['content']=prefix+'\n\ninput: '+common.wire(data).decode()
            self.assertEqual(b[0],b[1])
    def test_requests_independently_reconstructed_and_no_answer_labels(self):
        for s in self.plan['slots']:
            q=design.request_for(self.plan,s)
            self.assertEqual(common.wire(q),verify._request_for(self.plan,s,{}))
            text=q['messages'][0]['content']
            for label in ('reference_short','reference_long','target_D','depth_ranges',s['problem_id']):self.assertNotIn(label,text)
            self.assertNotIn('enum',q['format']['properties']['rule_ids'])
    def test_selector_rejects_history(self):
        with self.assertRaises(ValueError):design.request_for(self.plan,self.plan['slots'][0],{'previous':b'wrong'})
    def test_perfect_selector_not_end_to_end(self):
        recs,_=records_for(self.plan);r=report.summarize(self.plan,recs,'complete')
        self.assertEqual(r['overall']['successes'],40);self.assertEqual(r['overall']['paired_successes'],20);self.assertTrue(r['overall']['selector_ready'])
        self.assertIsNone(r['overall']['end_to_end_graph_D_control']);self.assertFalse(r['limits']['constructor_executed'])
    def test_fixed_position_never_passes_pair(self):
        for mode in ('first','last','fixed_short'):
            r=report.summarize(self.plan,records_for(self.plan,mode)[0],'complete')
            self.assertEqual(r['overall']['successes'],20);self.assertEqual(r['overall']['paired_successes'],0)
    def test_length_heuristic_fails_controls(self):
        r=report.summarize(self.plan,records_for(self.plan,'by_count')[0],'complete')
        self.assertEqual(r['overall']['successes'],28);self.assertEqual(r['overall']['paired_successes'],12);self.assertFalse(r['overall']['selector_ready'])
        self.assertTrue(all(x['selection_success'] is False for x in r['rows'] if x['problem_id']=='C02_count_reversal'))
    def test_nonmember_valid_route_not_repaired(self):
        r=report.summarize(self.plan,records_for(self.plan,'nonmember_valid')[0],'complete')
        for x in r['rows']:
            if x['problem_id']=='E01_shared_fork' and x['condition']=='deep':
                self.assertTrue(x['route_valid']);self.assertFalse(x['candidate_member']);self.assertFalse(x['selection_success']);self.assertEqual(x['selected_rule_ids'],['n91','n08','n37'])
    def test_duplicate_ids_and_unused_nodes_fail(self):
        for mode in ('unknown','duplicate','mixed'):
            r=report.summarize(self.plan,records_for(self.plan,mode)[0],'complete');self.assertEqual(r['overall']['successes'],0)
    def test_unmeasured_not_zero_D(self):
        for mode in ('parse_error','duplicate_json','nonfinite','empty','extra_field','bool_payload','nested','incomplete','tool_calls'):
            r=report.summarize(self.plan,records_for(self.plan,mode)[0],'complete')
            self.assertEqual(r['overall']['unmeasured'],40,mode);self.assertIsNone(r['overall']['selector_ready'],mode);self.assertTrue(all(x['route_D'] is None for x in r['rows']))
    def test_missing_and_boolean_usage_not_zero(self):
        for mode in ('missing_usage','bool_usage'):
            r=report.summarize(self.plan,records_for(self.plan,mode)[0],'complete');self.assertIsNone(r['usage']['eval_count'])
    def test_partial_has_null_gate(self):
        recs,_=records_for(self.plan);r=report.summarize(self.plan,recs[:3],'crashed');self.assertEqual(r['overall']['successes'],3);self.assertIsNone(r['overall']['selector_ready'])
    def test_no_production_import_in_verifier(self):
        tree=ast.parse((ROOT/'verify.py').read_text());mods=[]
        for n in ast.walk(tree):
            if isinstance(n,ast.Import):mods += [a.name for a in n.names]
            if isinstance(n,ast.ImportFrom):mods.append(n.module)
        self.assertFalse(set(mods)&{'report','measure','reference','selection','design','run'})
    def test_24_modes_production_independent_summary_and_render(self):
        modes=['perfect','reversed','fixed_short','first','last','by_count','reverse_ids','unknown','duplicate','empty','mixed','nonmember_valid','extra_field','bool_payload','nested','parse_error','duplicate_json','nonfinite','wrong_model','over_budget','missing_usage','incomplete','tool_calls','bool_usage']
        for mode in modes:
            recs,_=records_for(self.plan,mode)
            for state in ['complete','crashed']:
                a=report.summarize(self.plan,recs,state);b=verify._summary(self.plan,recs,state)
                self.assertTrue(common.exact(a,b),mode);self.assertEqual(report.render(a),verify._render(b))
    def test_500_route_mutations_independent_depth(self):
        rng=random.Random(7001);n=0
        for p in self.plan['protocol']['problems']:
            rs=self.plan['protocol']['reference_plans'][p['id']];cs=[rs[c] for c in self.plan['protocol']['reference_conditions']]
            for i in range(100):
                ids=list(cs[i%2]);op=i%7
                if op==0:ids+=['bad']
                elif op==1:ids.reverse()
                elif op==2:ids.pop(rng.randrange(len(ids)))
                elif op==3:ids+=ids[-1:]
                elif op==4:rng.shuffle(ids)
                elif op==5:ids=cs[0]+cs[1]
                d=self.plan['protocol']['depth_ranges'][p['id']][i%2];obj={'rule_ids':ids}
                self.assertTrue(common.exact(selection.assess(p,obj,cs,d),verify._selection(p,obj,cs,d)));n+=1
        self.assertEqual(n,500)
    def test_all_source_imports_compile(self):
        for path in ROOT.rglob('*.py'):compile(path.read_bytes(),str(path),'exec')
if __name__=='__main__':unittest.main()
