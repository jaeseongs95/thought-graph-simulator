"""분해 계약, 중간값 무보정, 측정 경계와 독립 계산의 반례 시험."""
import unittest,ast,itertools,random
from fixtures import *

class Logic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.plan=design.build_plan(baseline_path(),'v071_logic','synthetic')
    def result(self,mode='perfect'):
        return report.summarize(self.plan,records_for(self.plan,mode)[0],'complete')
    def test_100_calls_140_actions_20_estimates(self):
        self.assertEqual(len(self.plan['slots']),100);self.assertEqual(len(self.plan['actions']),140)
        self.assertEqual(sum(s['stage']=='estimate' for s in self.plan['slots']),20)
        self.assertEqual(self.plan['slots'],verify._slot_schedule(self.plan['protocol']))
    def test_full_factorial_arms_orders_directions(self):
        for p in self.plan['protocol']['problems']:
            ss=[s for s in self.plan['slots'] if s['problem_id']==p['id'] and s['stage']=='select']
            self.assertEqual({(s['seed_index'],s['candidate_order_index'],s['arm'],s['condition']) for s in ss},set(itertools.product([0,1],[0,1],['oracle_depth','model_depth'],['shallow','deep'])))
    def test_model_estimate_precedes_both_shared_choices(self):
        for s in self.plan['slots']:
            if s['arm']=='model_depth':
                prev=next(x for x in self.plan['slots'] if x['id']==s['history_ids'][0]);self.assertLess(prev['period'],s['period']);self.assertEqual(prev['unit_id'],s['unit_id'])
    def test_only_D_instruction_differs_within_choice_pair(self):
        _,files=records_for(self.plan,'whitespace')
        for pid in {s['pair_id'] for s in self.plan['slots'] if s['pair_id']}:
            qs=[common.load(files['wire/'+s['id']+'/request.wire.json']) for s in self.plan['slots'] if s['pair_id']==pid]
            for q in qs:
                prefix,tail=q['messages'][0]['content'].split('\n\ninput: ');data=common.load(tail);data['requested_depth']='D_ONLY';q['messages'][0]['content']=prefix+'\n\ninput: '+common.wire(data).decode()
            self.assertEqual(qs[0],qs[1])
    def test_estimator_has_no_answer_or_D_direction(self):
        for s in self.plan['slots']:
            if s['stage']!='estimate':continue
            q=design.request_for(self.plan,s);txt=q['messages'][0]['content']
            for bad in ('reference_short','reference_long','depth_ranges','requested_depth',s['problem_id']):self.assertNotIn(bad,txt)
            self.assertNotIn('enum',q['format']['properties']['depths']['items'])
    def test_compare_has_no_problem_route_or_host_selected_index(self):
        _,files=records_for(self.plan)
        for s in self.plan['slots']:
            if s['stage']!='select':continue
            q=common.load(files['wire/'+s['id']+'/request.wire.json']);data=common.load(q['messages'][0]['content'].split('\n\ninput: ')[1])
            self.assertEqual(set(data),{'depth_report','requested_depth'})
    def test_model_raw_string_is_not_normalized_or_repaired(self):
        for mode in ('whitespace','reverse_depths','estimate_parse_error','estimate_incomplete'):
            _,files=records_for(self.plan,mode)
            for s in self.plan['slots']:
                if s['arm']!='model_depth':continue
                original=common.load(files['wire/'+s['history_ids'][0]+'/response.raw.json'])['message']['content']
                request=common.load(files['wire/'+s['id']+'/request.wire.json']);data=common.load(request['messages'][0]['content'].split('\n\ninput: ')[1])
                self.assertEqual(data['depth_report'],original)
    def test_absent_content_forwarded_as_null_not_zero(self):
        _,files=records_for(self.plan,'missing_content')
        for s in self.plan['slots']:
            if s['arm']=='model_depth':
                q=common.load(files['wire/'+s['id']+'/request.wire.json']);self.assertIsNone(common.load(q['messages'][0]['content'].split('\n\ninput: ')[1])['depth_report'])
        r=self.result('missing_content');self.assertEqual(r['overall']['depth_reports']['measured'],0);self.assertIsNone(r['overall']['pipeline_ready'])
    def test_wrong_intermediate_cannot_be_rescued_by_correct_selection(self):
        r=self.result('wrong_depth_correct_choice')['overall']
        self.assertEqual(r['depth_reports']['successes'],0);self.assertEqual(r['model_selection']['successes'],40);self.assertEqual(r['model_pipeline']['successes'],0);self.assertFalse(r['pipeline_ready'])
    def test_offset_depth_preserves_order_but_not_numeric_success(self):
        r=self.result('offset_depths')['overall'];self.assertEqual(r['model_selection']['successes'],40);self.assertEqual(r['depth_reports']['successes'],0);self.assertEqual(r['model_pipeline']['successes'],0)
    def test_count_heuristic_fails_depth_controls(self):
        r=self.result('by_count')['overall'];self.assertEqual(r['depth_reports']['successes'],8);self.assertEqual(r['model_selection']['successes'],28);self.assertEqual(r['model_pipeline']['successes'],16)
    def test_tie_not_fabricated_numeric_success(self):
        r=self.result('tie_depths');self.assertTrue(all(x['numeric_choice_success'] is None for x in r['rows'] if x['arm']=='model_depth'));self.assertEqual(r['overall']['model_selection']['successes'],20)
    def test_fixed_position_has_no_selective_pairs(self):
        for mode in ('first','last'):
            r=self.result(mode)['overall'];self.assertEqual(r['model_selection']['successes'],20);self.assertEqual(r['model_selection_pair_successes'],0);self.assertEqual(r['oracle_pair_successes'],0)
    def test_perfect_not_graph_control_or_100_depth_measurements(self):
        r=self.result();self.assertTrue(r['overall']['pipeline_ready']);self.assertEqual(r['overall']['depth_reports']['assigned'],20);self.assertEqual(r['overall']['model_pipeline']['successes'],40);self.assertIsNone(r['overall']['end_to_end_graph_D_control']);self.assertFalse(r['limits']['constructor_executed'])
    def test_unobserved_null_not_false_or_zero_D(self):
        r=report.summarize(self.plan,[],'crashed');self.assertIsNone(r['overall']['pipeline_ready']);self.assertEqual(r['overall']['unmeasured_calls'],100);self.assertTrue(all(x['selected_D'] is None for x in r['rows']))
    def test_bad_json_and_types_are_not_logical_failures(self):
        for mode in ('parse_error','duplicate_json','nonfinite','bool_choice','bool_depth','float_depth','float_choice','out_of_range'):
            r=self.result(mode);self.assertIsNone(r['overall']['pipeline_ready']);self.assertGreater(r['overall']['unmeasured_calls'],0)
    def test_independent_summaries_and_renderers_many_patterns(self):
        modes=('perfect','reverse_depths','offset_depths','tie_depths','by_count','wrong_depth_correct_choice','first','last','reverse_choice','oracle_wrong','model_wrong','bool_depth','float_depth','negative_depth','too_large_depth','extra_depth','bool_choice','float_choice','out_of_range','extra_field','parse_error','estimate_parse_error','duplicate_json','nonfinite','whitespace','missing_content','wrong_model','over_budget','incomplete','estimate_incomplete','missing_usage','bool_usage','tool_calls')
        for mode in modes:
            calls,_=records_for(self.plan,mode)
            for state in ('complete','crashed'):
                a=report.summarize(self.plan,calls,state);b=verify._summary(self.plan,calls,state)
                self.assertTrue(common.exact(a,b),(mode,state));self.assertEqual(report.render(a),verify._render(b))
    def test_global_and_reference_depths_agree_for_all_candidates(self):
        spec=self.plan['protocol']
        for p in spec['problems']:
            self.assertEqual(measure.depth_ranges(p),spec['depth_ranges'][p['id']])
            for i,c in enumerate(spec['reference_conditions']):
                ids=spec['reference_plans'][p['id']][c];self.assertEqual(reference.validate(p,ids),verify._reference_depth(p,ids))
    def test_500_route_counterexamples_independent(self):
        spec=self.plan['protocol'];rng=random.Random(7119)
        for p in spec['problems']:
            good=spec['reference_plans'][p['id']]['reference_long'];pool=[r['id'] for r in p['rules']]+['unknown']
            for i in range(100):
                ids=good[:] if i==0 else rng.choices(pool,k=rng.randrange(0,8))
                results=[]
                for fn in (reference.validate,verify._reference_depth):
                    try:results.append(('ok',fn(p,ids)))
                    except ValueError:results.append(('invalid',None))
                self.assertEqual(*results)
    def test_extra_or_missing_history_rejected(self):
        s=next(x for x in self.plan['slots'] if x['arm']=='model_depth')
        with self.assertRaises(ValueError):design.request_for(self.plan,s,{})
        s=next(x for x in self.plan['slots'] if x['stage']=='estimate')
        with self.assertRaises(ValueError):design.request_for(self.plan,s,{'extra':b'{}'})
    def test_verifier_does_not_import_production_semantics(self):
        tree=ast.parse((ROOT/'verify.py').read_text())
        imports=[]
        for n in ast.walk(tree):
            if isinstance(n,ast.Import):imports.extend(a.name for a in n.names)
            elif isinstance(n,ast.ImportFrom):imports.append(n.module)
        self.assertFalse(set(imports)&{'design','depths','measure','report','run','reference'})
    def test_unchanged_options_and_token_upper_bound(self):
        p=self.plan;self.assertEqual(p['protocol']['generation_token_upper_bound'],100*p['protocol']['num_predict'])
        for s in p['slots']:
            if s['stage']!='estimate':continue
            q=design.request_for(p,s);want=deepcopy(p['baseline_request']['options']);want['seed']=s['seed'];self.assertEqual(q['options'],want)
