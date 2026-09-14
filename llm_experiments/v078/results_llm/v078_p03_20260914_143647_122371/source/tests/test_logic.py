import ast,base64,copy,json,random,unittest
from pathlib import Path
from fixtures import plan,memory_run,input_of,ROOT,Synth
import common,design,report,measure,stages,audit_graph,audit_model,audit_io

class Logic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p=plan();cls.rec,cls.raw,cls.synth=memory_run(cls.p)
        cls.summary=report.summarize(cls.p,cls.rec,cls.raw,'complete')
    def test_schedule_counts(self):
        p=self.p;self.assertEqual((len(p['trials']),len(p['slots']),len(p['actions'])),(48,316,332))
        self.assertEqual(sum(t['arm']=='model' for t in p['trials']),32)
    def test_factor_crossing(self):
        keys={(t['problem_id'],t['seed'],t['candidate_order_index'],t['condition']) for t in self.p['trials'] if t['arm']=='model'}
        self.assertEqual(len(keys),32)
    def test_control_balance(self):
        refs=[t for t in self.p['trials'] if t['arm']=='reference']
        self.assertEqual(len(refs),16)
        self.assertEqual(sum(t['candidate_order_index']==0 for t in refs),8)
    def test_independent_schedule(self):
        self.assertEqual(audit_model.reconstruct_schedule(self.p['protocol']),(self.p['trials'],self.p['slots'],self.p['actions']))
    def test_all_correct_is_308_not_316(self):
        self.assertEqual(self.synth.calls,308);self.assertEqual(self.summary['arms']['base']['model_trace']['successes'],32)
        self.assertEqual(self.summary['arms']['base']['reference_construction']['successes'],16)
        self.assertEqual(self.summary['arms']['base']['model_pairs']['successes'],16)
        self.assertIs(self.summary['end_to_end_baseline_ready'],True)
    def test_all_request_bytes_independent(self):
        for slot in self.p['slots']:
            skip,want=audit_model.expected_request(self.p,slot,self.raw)
            self.assertEqual(skip,design.disposition(self.p,slot,self.raw))
            if skip is None:self.assertEqual(want,common.wire(design.request_for(self.p,slot,self.raw)))
    def test_candidates_are_unchanged_rule_records(self):
        for t in self.p['trials']:
            p=design.problem_for(self.p,t)
            for c in design.cards(self.p,t):
                self.assertEqual(set(c),{'candidate_id','rules'})
                for r in c['rules']:self.assertIn(r,p['rules'])
    def test_no_numeric_stage(self):
        self.assertEqual({s['stage'] for s in self.p['slots']},{'select','facts','rule','final'})
        for s in self.p['slots']:
            if s['stage']=='select':
                d=input_of(design.request_for(self.p,s,{}))
                self.assertEqual(set(d),{'problem','candidates','requested_depth'})
                self.assertNotIn('target_D',str(d));self.assertNotIn('depth_report',str(d))
    def test_only_D_requirement_changes_in_selector_pair(self):
        for pair in self.summary['pairs']:
            ts=[next(t for t in self.p['trials'] if t['id']==i) for i in pair['trial_ids']]
            bs=[design.request_for(self.p,next(s for s in self.p['slots'] if s['id']==t['selection_slot_id']),{}) for t in ts]
            ds=[input_of(b) for b in bs]
            for d in ds:d.pop('requested_depth')
            self.assertEqual(ds[0],ds[1])
            for b in bs:b['messages'][0]['content']=''
            self.assertEqual(bs[0],bs[1])
    def test_generator_blind_to_requested_D(self):
        for slot in self.p['slots']:
            t=next(t for t in self.p['trials'] if t['id']==slot['trial_id'])
            if t['arm']!='model' or slot['stage']=='select' or design.disposition(self.p,slot,self.raw):continue
            changed=copy.deepcopy(self.p);ct=next(t for t in changed['trials'] if t['id']==slot['trial_id']);ct['condition']='deep' if ct['condition']=='shallow' else 'shallow'
            self.assertEqual(design.request_for(self.p,slot,self.raw),design.request_for(changed,slot,self.raw))
    def test_selector_whitespace_preserved(self):
        r,raw,_=memory_run(self.p,'selector_whitespace')
        for s in self.p['slots']:
            if s['stage']=='facts':
                t=next(t for t in self.p['trials'] if t['id']==s['trial_id'])
                if t['arm']=='model':self.assertEqual(input_of(design.request_for(self.p,s,raw))['selection_original']['content'],design.raw_content(raw[t['selection_slot_id']]))
    def test_bad_parent_not_repaired(self):
        r,raw,_=memory_run(self.p,'bad_parent');x=report.summarize(self.p,r,raw,'complete')
        self.assertEqual(x['arms']['base']['model_trace']['successes'],0)
        self.assertEqual(x['arms']['base']['reference_construction']['successes'],16)
        self.assertTrue(any('missing_parent' in rr['graph_metric']['error_codes'] for rr in x['trials'] if rr['arm']=='model'))
    def test_correct_graph_cannot_erase_wrong_stage(self):
        r,raw,_=memory_run(self.p,'swap_valid_branches');x=report.summarize(self.p,r,raw,'complete')
        matched=[t for t in x['trials'] if t['arm']=='model' and t['problem_id']=='H01' and t['condition']=='shallow']
        self.assertEqual(len(matched),4)
        for t in matched:self.assertTrue(t['target_structure_success']);self.assertFalse(t['trace_success']);self.assertFalse(t['route_fidelity'])
    def test_wrong_selection_still_runs_selected_route(self):
        r,raw,_=memory_run(self.p,'always_first');x=report.summarize(self.p,r,raw,'complete')
        self.assertEqual(x['arms']['base']['model_generator_fidelity']['successes'],32);self.assertEqual(x['arms']['base']['model_trace']['successes'],16);self.assertEqual(x['arms']['base']['model_pairs']['successes'],0)
    def test_dynamic_budget_extremes(self):
        for mode,n in [('always_short',316),('always_long',300),('invalid_selector',124),('max_rules',316),('min_rules',300)]:
            r,raw,s=memory_run(self.p,mode);self.assertEqual(s.calls,n)
    def test_invalid_selection_blocks_without_zero_depth(self):
        r,raw,_=memory_run(self.p,'invalid_selector');x=report.summarize(self.p,r,raw,'complete')
        self.assertEqual(x['arms']['base']['model_trace']['unmeasured'],32);self.assertIsNone(x['end_to_end_baseline_ready'])
        for t in x['trials']:
            if t['arm']=='model':self.assertIsNone(t['selected_route_D']);self.assertIsNone(t['graph'])
    def test_invalid_fact_content_transferred_unchanged(self):
        r,raw,_=memory_run(self.p,'malformed_facts')
        for s in self.p['slots']:
            if s['stage']=='rule' and not design.disposition(self.p,s,raw):
                t=next(t for t in self.p['trials'] if t['id']==s['trial_id'])
                if t['arm']=='model':self.assertEqual(input_of(design.request_for(self.p,s,raw))['history'][0]['content'],'not json')
    def test_length_selector_not_promoted_by_successful_graph(self):
        r,raw,_=memory_run(self.p,'length_selector');x=report.summarize(self.p,r,raw,'complete')
        self.assertEqual(x['arms']['base']['model_generator_fidelity']['successes'],32);self.assertEqual(x['arms']['base']['model_trace']['unmeasured'],32);self.assertIsNone(x['end_to_end_baseline_ready'])
    def test_reference_not_counted_as_model(self):
        self.assertEqual(self.summary['shared_model_selection']['assigned'],32)
        for t in self.summary['trials']:
            if t['arm']=='reference':self.assertIsNone(t['selection_success']);self.assertIsNone(t['trace_success'])
    def test_control_failure_keeps_actual_model_success(self):
        r,raw,_=memory_run(self.p,'control_fails');x=report.summarize(self.p,r,raw,'complete')
        self.assertEqual(x['arms']['base']['model_trace']['successes'],32);self.assertFalse(x['end_to_end_baseline_ready']);self.assertEqual(x['arms']['base']['reference_construction']['successes'],0)
    def test_absent_usage_not_fabricated(self):
        r,raw,s=memory_run(self.p,'missing_usage');x=report.summarize(self.p,r,raw,'complete')
        self.assertEqual(x['usage']['eval_count']['missing_records'],s.calls)
        self.assertEqual(x['usage']['eval_count']['observed_sum'],0)
    def test_partial_gate_null(self):
        r,raw,_=memory_run(self.p,limit=20);x=report.summarize(self.p,r,raw,'crashed')
        self.assertIsNone(x['end_to_end_baseline_ready']);self.assertGreater(x['arms']['base']['model_trace']['unmeasured'],0)
    def test_summary_and_report_differential_patterns(self):
        modes=['correct','always_first','always_short','always_long','bad_fact','bad_parent','bad_final','control_fails','swap_valid_branches','malformed_facts','invalid_selector','selector_whitespace','length_selector','missing_usage','wrong_existing_parent','missing_parent','duplicate_parent','malformed_rule','length_rule','extra_bindings','fact_overflow','duplicate_fact_ids','rule_count_heuristic']
        for mode in modes:
            r,raw,_=memory_run(self.p,mode)
            for state in ('complete','crashed'):
                a=report.summarize(self.p,r,raw,state);b=audit_model.independent_summary(self.p,r,raw,state)
                self.assertTrue(common.exact(a,b),mode);self.assertEqual(report.render(a),audit_model.independent_report(b),mode)
    def test_graph_differential_180_cases(self):
        rng=random.Random(74001);base=[r for r in self.summary['trials'] if r['graph'] is not None]
        for i in range(180):
            row=rng.choice(base);g=copy.deepcopy(row['graph']);p=next(p for p in self.p['protocol']['problems'] if p['id']==row['problem_id']);k=i%10
            if k==1:g['final_node_id']='absent'
            elif k==2:g['nodes'][-1]['parents']=['absent']
            elif k==3:g['nodes'].append(copy.deepcopy(g['nodes'][0]))
            elif k==4:g['nodes'][-1]['atom']='bad_atom'
            elif k==5:g['nodes'][-1]['rule']='bad_rule'
            elif k==6:g['nodes'].reverse()
            elif k==7:g['nodes'][-1]['parents']=[g['nodes'][-1]['id']]
            elif k==8:g['nodes'].append({'id':'unused','atom':p['facts'][0],'rule':None,'parents':[]})
            elif k==9:g['nodes'][0]['parents']=[False]
            self.assertTrue(common.exact(measure.assess(p,g),audit_graph._semantic(p,g)),str(i))
    def test_depth_is_dependency_not_count(self):
        row=next(r for r in self.summary['trials'] if r['problem_id']=='H01' and r['condition']=='shallow')
        self.assertEqual(row['graph_metric']['actual_D'],2)
        self.assertEqual(len(row['selected_rule_ids']),3)
    def test_original_measure_and_stage_bytes_preserved(self):
        p=common.load((ROOT/'data/source_provenance.json').read_bytes())
        for f in ('measure.py','stages.py'):self.assertEqual(common.sha((ROOT/f).read_bytes()),p['reused_unchanged'][f])
    def test_duplicate_json_keys_and_nonfinite_rejected(self):
        for raw in (b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":1e999}'):
            for loader in (common.load,audit_io.load):
                with self.assertRaises(ValueError):loader(raw)
    def test_independent_modules_do_not_import_production(self):
        bad={'design','report','measure','stages','run','common','previous'}
        for f in ('verify.py','audit_model.py','audit_graph.py','audit_io.py','audit_design.py'):
            for n in ast.walk(ast.parse((ROOT/f).read_text())):
                if isinstance(n,ast.Import):self.assertFalse({a.name.split('.')[0] for a in n.names}&bad)
                if isinstance(n,ast.ImportFrom):self.assertNotIn((n.module or '').split('.')[0],bad)

if __name__=='__main__':unittest.main()
