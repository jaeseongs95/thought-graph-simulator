"""공유 선택/짝비교/초기 사실 스키마 경계와 실제 v074 원문 회귀."""
import base64,copy,json,unittest,collections
from pathlib import Path
from fixtures import plan,memory_run,input_of,baseline_path,ROOT
import common,design,report,audit_model

class PairedContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p=plan();cls.records,cls.raw,cls.synth=memory_run(cls.p);cls.summary=report.summarize(cls.p,cls.records,cls.raw,'complete')
        cls.baseline=common.unzip(baseline_path().read_bytes())
    def twins(self):
        for uid in sorted(set(t['unit_id'] for t in self.p['trials'])):
            yield [next(t for t in self.p['trials'] if t['unit_id']==uid and t['variant']==v) for v in ('legacy','fact_only')]
    def slot(self,t,stage):return next(s for s in self.p['slots'] if s['trial_id']==t['id'] and s['stage']==stage)
    def test_only_24_selector_calls(self):
        self.assertEqual(sum(s['stage']=='select' for s in self.p['slots']),24)
        self.assertEqual(self.summary['shared_model_selection']['assigned'],24)
        self.assertEqual(self.summary['shared_selection_pairs']['assigned'],12)
    def test_both_arms_share_the_exact_selection_object(self):
        for a,b in self.twins():
            self.assertEqual(design.source_for(self.p,a,self.raw),design.source_for(self.p,b,self.raw))
            self.assertEqual(design.selected_route(self.p,a,self.raw),design.selected_route(self.p,b,self.raw))
    def test_first_call_only_schema_changes(self):
        for a,b in self.twins():
            x=design.request_for(self.p,self.slot(a,'facts'),self.raw);y=design.request_for(self.p,self.slot(b,'facts'),self.raw)
            old=common.wire(x['format']).decode();new=common.wire(y['format']).decode()
            self.assertNotEqual(old,new)
            y['messages'][0]['content']=y['messages'][0]['content'].replace(new,old,1);y['format']=x['format']
            self.assertEqual(x,y)
    def test_initial_schema_supplies_no_atom_or_id_answers(self):
        for t in self.p['trials']:
            if t['variant']!='fact_only':continue
            schema=design.request_for(self.p,self.slot(t,'facts'),self.raw)['format']['properties']['nodes'];base=self.p['protocol']['generation_schema']['properties']['nodes'];p=design.problem_for(self.p,t)
            self.assertEqual((schema['minItems'],schema['maxItems']),(len(p['facts']),len(p['facts'])))
            props=schema['items']['properties']
            self.assertEqual(props['rule'],{'type':'null'});self.assertEqual(props['parents']['maxItems'],0)
            for k in ('atom','id'):self.assertEqual(props[k],base['items']['properties'][k]);self.assertNotIn('enum',props[k]);self.assertNotIn('const',props[k])
    def test_rule_final_requests_identical_if_histories_equal(self):
        for a,b in self.twins():
            aa=[s for s in self.p['slots'] if s['trial_id']==a['id'] and s['stage'] in ('rule','final')]
            bb=[s for s in self.p['slots'] if s['trial_id']==b['id'] and s['stage'] in ('rule','final')]
            for x,y in zip(aa,bb):
                if design.disposition(self.p,x,self.raw):continue
                self.assertEqual(design.request_for(self.p,x,self.raw),design.request_for(self.p,y,self.raw))
    def test_logical_history_maps_to_same_arm_actual_records(self):
        for t in self.p['trials']:
            for s in [x for x in self.p['slots'] if x['trial_id']==t['id'] and x['stage']=='final']:
                if design.disposition(self.p,s,self.raw):continue
                d=input_of(design.request_for(self.p,s,self.raw))
                for h in d['history']:
                    old=next(z for z in self.p['slots'] if z['trial_id']==t['id'] and z['logical_id']==h['source_slot_id'])
                    self.assertEqual(h['response_sha256'],common.sha(self.raw[old['id']]))
                    self.assertEqual(h['content'],design.raw_content(self.raw[old['id']]))
    def test_variant_order_balanced(self):
        groups=collections.defaultdict(list)
        for t in self.p['trials']:groups[t['unit_id']].append(t)
        for arm,n in [('model',12),('reference',6)]:
            c=collections.Counter(ts[0]['variant'] for ts in groups.values() if ts[0]['arm']==arm)
            self.assertEqual(c,{'legacy':n,'fact_only':n})
    def test_schema_effect_measured_within_same_selection(self):
        r,w,_=memory_run(self.p,'schema_sensitive');s=report.summarize(self.p,r,w,'complete')
        self.assertEqual(s['shared_model_selection']['successes'],24)
        self.assertEqual(s['arms']['legacy']['model_trace']['successes'],0)
        self.assertEqual(s['arms']['fact_only']['model_trace']['successes'],24)
        self.assertEqual(s['paired_effects']['model_trace']['fact_only_only'],24)
        self.assertEqual(s['preferred_generator_for_future_contract'],'fact_only')
    def test_new_contract_can_harm_without_cherry_pick(self):
        r,w,_=memory_run(self.p,'schema_harms');s=report.summarize(self.p,r,w,'complete')
        self.assertEqual(s['arms']['fact_only']['model_trace']['successes'],0)
        self.assertEqual(s['paired_effects']['model_trace']['legacy_only'],24)
        self.assertEqual(s['preferred_generator_for_future_contract'],'legacy')
    def test_no_posthoc_fact_filter_in_either_arm(self):
        r,w,_=memory_run(self.p,'fact_overflow');s=report.summarize(self.p,r,w,'complete')
        for v in ('legacy','fact_only'):
            self.assertEqual(s['arms'][v]['initial_fact_stage']['failures'],36)
            self.assertEqual(s['arms'][v]['model_trace']['successes'],0)
        for row in s['trials']:self.assertTrue(any(n['id']=='premature' for n in row['graph']['nodes']))
    def test_shape_limit_does_not_guarantee_fact_correctness(self):
        r,w,_=memory_run(self.p,'wrong_atom_fact_only');s=report.summarize(self.p,r,w,'complete')
        self.assertEqual(s['arms']['fact_only']['initial_fact_stage']['failures'],36)
        self.assertEqual(s['arms']['fact_only']['model_trace']['successes'],0)
    def test_duplicate_ids_still_fail(self):
        r,w,_=memory_run(self.p,'duplicate_fact_ids');s=report.summarize(self.p,r,w,'complete')
        for v in ('legacy','fact_only'):self.assertEqual(s['arms'][v]['initial_fact_stage']['failures'],36)
    def test_selection_ceiling_not_hidden_by_generator_success(self):
        r,w,_=memory_run(self.p,'always_short');s=report.summarize(self.p,r,w,'complete')
        self.assertEqual(s['selection_trace_ceiling']['successful_trials'],12)
        self.assertEqual(s['selection_trace_ceiling']['successful_pairs'],0)
        for v in ('legacy','fact_only'):
            self.assertEqual(s['arms'][v]['model_generator_fidelity']['successes'],24)
            self.assertEqual(s['arms'][v]['model_trace']['successes'],12)
            self.assertFalse(s['arms'][v]['end_to_end_baseline_ready'])
    def test_selector_wire_bytes_equal_v074_all24(self):
        for slot in self.p['slots']:
            if slot['stage']=='select':self.assertEqual(common.wire(design.request_for(self.p,slot,{})),self.baseline['wire/'+slot['id']+'/request.wire.json'])
    def test_legacy_initial_request_bytes_equal_v074_all36(self):
        source={n.split('/')[1]:b for n,b in self.baseline.items() if n.startswith('wire/') and n.endswith('/response.raw.json')}
        for t in self.p['trials']:
            if t['variant']=='legacy':
                self.assertEqual(common.wire(design.request_for(self.p,self.slot(t,'facts'),source)),self.baseline['wire/'+t['unit_id']+'_facts/request.wire.json'])
    def test_v074_semantic_replay_both_arms_keeps_old_failures(self):
        # 출력 계약을 바꿨다는 이유로 옛 원응답에서 사실만 추출하지 않는다.
        r={};w={}
        for slot in self.p['slots']:
            sid=slot['id'];oldid=slot['logical_id'];record=common.load(self.baseline['records/'+oldid+'.json']);record['id']=sid;r[sid]=record
            if record['kind']=='call':w[sid]=self.baseline['wire/'+oldid+'/response.raw.json']
        s=report.summarize(self.p,r,w,'complete');a=audit_model.independent_summary(self.p,r,w,'complete')
        self.assertTrue(common.exact(s,a));self.assertEqual(s['shared_model_selection']['successes'],20)
        self.assertEqual(s['observed_inference_calls'],332)
        for v in ('legacy','fact_only'):
            self.assertEqual(s['arms'][v]['model_trace']['successes'],8)
            self.assertEqual(s['arms'][v]['model_pairs']['successes'],3)
            self.assertEqual(s['arms'][v]['reference_construction']['successes'],3)
            self.assertEqual(s['arms'][v]['initial_fact_stage']['failures'],22)
    def test_new_pattern_summaries_and_reports_independent(self):
        for mode in ['fact_overflow','schema_sensitive','schema_harms','wrong_atom_fact_only','duplicate_fact_ids']:
            r,w,_=memory_run(self.p,mode)
            for state in ('complete','crashed'):
                a=report.summarize(self.p,r,w,state);b=audit_model.independent_summary(self.p,r,w,state)
                self.assertTrue(common.exact(a,b),mode);self.assertEqual(report.render(a),audit_model.independent_report(b))
    def test_half_pair_interruption_cannot_pass(self):
        r,w,_=memory_run(self.p,limit=7);s=report.summarize(self.p,r,w,'crashed')
        self.assertIsNone(s['end_to_end_baseline_ready'])
        self.assertGreater(s['paired_effects']['initial_fact_all']['unmeasured'],0)

if __name__=='__main__':unittest.main()
