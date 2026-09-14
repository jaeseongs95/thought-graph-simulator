"""v076: 부모 개수 대조·content-only 경계·원문 무보정·v075 의미 회귀."""
import copy,collections,json,unittest
from fixtures import plan,memory_run,input_of,baseline_path
import common,design,report,audit_model

class PairedContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p=plan();cls.records,cls.raw,cls.synth=memory_run(cls.p)
        cls.summary=report.summarize(cls.p,cls.records,cls.raw,'complete')
        cls.baseline=common.unzip(baseline_path().read_bytes())
    def twins(self):
        for uid in sorted(set(t['unit_id'] for t in self.p['trials'])):
            yield [next(t for t in self.p['trials'] if t['unit_id']==uid and t['variant']==v) for v in ('base','parent_count')]
    def slots(self,t):return [s for s in self.p['slots'] if s['trial_id']==t['id'] and s['stage']!='select']
    def initial(self,t):return next(s for s in self.slots(t) if s['stage']=='facts')
    def test_only_24_shared_selector_calls(self):
        self.assertEqual(sum(s['stage']=='select' for s in self.p['slots']),24)
        self.assertEqual(self.summary['shared_model_selection']['assigned'],24)
        self.assertEqual(self.summary['shared_selection_pairs']['assigned'],12)
    def test_exact_shared_selection_no_hash(self):
        for a,b in self.twins():
            src=design.source_for(self.p,a,self.raw)
            self.assertEqual(src,design.source_for(self.p,b,self.raw))
            self.assertEqual(set(src),{'source_type','source_id','content'})
            self.assertEqual(design.selected_route(self.p,a,self.raw),design.selected_route(self.p,b,self.raw))
    def test_both_initial_requests_byte_identical(self):
        for a,b in self.twins():
            x=design.request_for(self.p,self.initial(a),self.raw);y=design.request_for(self.p,self.initial(b),self.raw)
            self.assertEqual(common.wire(x),common.wire(y))
    def test_fact_only_constraints_retained_in_both_arms(self):
        for t in self.p['trials']:
            schema=design.request_for(self.p,self.initial(t),self.raw)['format']['properties']['nodes']
            props=schema['items']['properties'];p=design.problem_for(self.p,t)
            self.assertEqual((schema['minItems'],schema['maxItems']),(len(p['facts']),len(p['facts'])))
            self.assertEqual(props['rule'],{'type':'null'});self.assertEqual(props['parents']['maxItems'],0)
            for key in ('id','atom'):
                self.assertEqual(props[key],self.p['protocol']['generation_schema']['properties']['nodes']['items']['properties'][key])
    def test_rules_only_two_cardinality_fields_differ(self):
        for a,b in self.twins():
            for u,v in zip(self.slots(a),self.slots(b)):
                if design.disposition(self.p,u,self.raw):continue
                left=design.request_for(self.p,u,self.raw);right=design.request_for(self.p,v,self.raw)
                if u['stage']=='rule':
                    x=left['format'];y=right['format'];delta=copy.deepcopy(y)
                    delta['properties']['node']['properties']['parents'].update(minItems=0,maxItems=16)
                    self.assertEqual(x,delta)
                    old=common.wire(x).decode();new=common.wire(y).decode()
                    right['messages'][0]['content']=right['messages'][0]['content'].replace(new,old,1)
                    right['format']=x
                self.assertEqual(left,right)
    def test_parent_count_from_requested_rule_without_node_lookup(self):
        for t in self.p['trials']:
            if t['variant']!='parent_count':continue
            p=design.problem_for(self.p,t)
            for s in self.slots(t):
                if s['stage']!='rule' or design.disposition(self.p,s,self.raw):continue
                body=design.request_for(self.p,s,self.raw);data=input_of(body)
                n=len(next(r for r in p['rules'] if r['id']==data['operation']['requested_rule_id'])['premises'])
                ps=body['format']['properties']['node']['properties']['parents']
                self.assertEqual((ps['minItems'],ps['maxItems']),(n,n))
                self.assertEqual(ps['items'],self.p['protocol']['generation_schema']['properties']['nodes']['items']['properties']['parents']['items'])
                for k in ('id','atom','rule'):
                    self.assertEqual(body['format']['properties']['node']['properties'][k],self.p['protocol']['generation_schema']['properties']['nodes']['items']['properties'][k])
    def test_content_preserved_hashes_outside_prompt(self):
        for t in self.p['trials']:
            for s in self.slots(t):
                if design.disposition(self.p,s,self.raw):continue
                d=input_of(design.request_for(self.p,s,self.raw))
                self.assertNotIn('response_sha256',d['selection_original'])
                for h in d['history']:
                    self.assertEqual(set(h),{'source_slot_id','content'})
                    old=next(z for z in self.p['slots'] if z['trial_id']==t['id'] and z['logical_id']==h['source_slot_id'])
                    self.assertEqual(h['content'],design.raw_content(self.raw[old['id']]))
                    self.assertEqual(self.records[old['id']]['response_sha256'],common.sha(self.raw[old['id']]))
    def test_all_envelope_only_changes_leave_requests_identical(self):
        changed={}
        for i,(sid,raw) in enumerate(self.raw.items()):
            outer=common.load(raw);outer.update(created_at='different-time-'+str(i),eval_duration=i+999,total_duration=i+999999)
            changed[sid]=common.wire(outer)
        for s in self.p['slots']:
            if design.disposition(self.p,s,self.raw):continue
            self.assertEqual(design.request_for(self.p,s,self.raw),design.request_for(self.p,s,changed))
            self.assertEqual(audit_model.expected_request(self.p,s,self.raw),audit_model.expected_request(self.p,s,changed))
    def test_content_whitespace_is_not_normalized(self):
        first=next(s for s in self.p['slots'] if s['stage']=='facts');t=next(t for t in self.p['trials'] if t['id']==first['trial_id'])
        rule=next(s for s in self.slots(t) if s['stage']=='rule')
        raw=dict(self.raw);o=common.load(raw[first['id']]);o['message']['content']='\n '+o['message']['content']+' \n';raw[first['id']]=common.wire(o)
        d=input_of(design.request_for(self.p,rule,raw));self.assertEqual(d['history'][0]['content'],o['message']['content'])
        self.assertNotEqual(design.request_for(self.p,rule,raw),design.request_for(self.p,rule,self.raw))
    def test_variant_order_balanced(self):
        groups=collections.defaultdict(list)
        for t in self.p['trials']:groups[t['unit_id']].append(t)
        for arm,n in [('model',12),('reference',6)]:
            self.assertEqual(collections.Counter(ts[0]['variant'] for ts in groups.values() if ts[0]['arm']==arm),{'base':n,'parent_count':n})
    def test_gain_pattern_counted_without_cherry_pick(self):
        r,w,_=memory_run(self.p,'arity_sensitive');s=report.summarize(self.p,r,w,'complete')
        self.assertEqual(s['shared_model_selection']['successes'],24)
        self.assertEqual(s['arms']['base']['model_trace']['successes'],0)
        self.assertEqual(s['arms']['parent_count']['model_trace']['successes'],24)
        self.assertEqual(s['paired_effects']['model_trace']['parent_count_only'],24)
    def test_harm_pattern_preserved(self):
        r,w,_=memory_run(self.p,'arity_harms');s=report.summarize(self.p,r,w,'complete')
        self.assertEqual(s['arms']['parent_count']['model_trace']['successes'],0)
        self.assertEqual(s['paired_effects']['model_trace']['base_only'],24)
    def test_right_number_wrong_parent_remains_failure(self):
        r,w,_=memory_run(self.p,'correct_count_wrong_identity');s=report.summarize(self.p,r,w,'complete')
        for a in s['arms'].values():
            self.assertEqual(a['rule_parent_counts']['failures'],0)
            self.assertGreater(a['count_correct_but_step_wrong'],0)
            self.assertEqual(a['model_trace']['successes'],0)
    def test_duplicate_parent_does_not_replace_missing_Ab(self):
        r,w,_=memory_run(self.p,'duplicate_parent_for_Ab');s=report.summarize(self.p,r,w,'complete')
        rows=[r for r in s['trials'] if r['problem_id']=='E01_shared_fork' and r['condition']=='deep']
        for row in rows:
            last=next(c for c in row['parent_count_checks'] if c['requested_rule_id']=='n37')
            self.assertTrue(last['count_valid']);self.assertFalse(last['step_valid'])
            self.assertIn('premise_counter_mismatch',last['error_codes'])
            self.assertFalse(row['generator_success'])
    def test_wrong_parent_count_not_padded(self):
        r,w,_=memory_run(self.p,'arity_missing_all');s=report.summarize(self.p,r,w,'complete')
        for arm in s['arms'].values():self.assertGreater(arm['rule_parent_counts']['failures'],0)
        for row in s['trials']:
            if row['graph'] is None:continue
            for c in row['parent_count_checks']:
                if c['count_valid'] is False:self.assertLess(c['observed_count'],c['expected_count'])
    def test_wrong_atoms_and_duplicate_ids_not_fixed(self):
        for mode in ('wrong_atom_parent_count','duplicate_fact_ids','fact_overflow'):
            r,w,_=memory_run(self.p,mode);s=report.summarize(self.p,r,w,'complete')
            for v in ('base','parent_count'):
                self.assertEqual(s['arms'][v]['initial_fact_stage']['failures'],36)
                self.assertEqual(s['arms'][v]['model_trace']['successes'],0)
    def test_selection_ceiling_not_changed_by_generation(self):
        r,w,_=memory_run(self.p,'always_short');s=report.summarize(self.p,r,w,'complete')
        self.assertEqual(s['selection_trace_ceiling']['successful_trials'],12)
        self.assertEqual(s['selection_trace_ceiling']['successful_pairs'],0)
        for a in s['arms'].values():
            self.assertEqual(a['model_generator_fidelity']['successes'],24);self.assertEqual(a['model_trace']['successes'],12)
    def test_selector_requests_identical_to_v075(self):
        for s in self.p['slots']:
            if s['stage']=='select':self.assertEqual(common.wire(design.request_for(self.p,s,{})),self.baseline['wire/'+s['id']+'/request.wire.json'])
    def test_base_equals_v075_fact_only_when_audit_hash_removed(self):
        raw={n.split('/')[1]:b for n,b in self.baseline.items() if n.startswith('wire/') and n.endswith('/response.raw.json')}
        mapped={}
        for s in self.p['slots']:
            old=s['id'] if s['stage']=='select' else s['logical_id'].replace('_facts','_fact_only_facts').replace('_rule_','_fact_only_rule_').replace('_final','_fact_only_final')
            if old in raw:mapped[s['id']]=raw[old]
        for t in self.p['trials']:
            if t['variant']!='base':continue
            for s in self.slots(t):
                if design.disposition(self.p,s,mapped):continue
                oldid=s['id'].replace('_base_','_fact_only_');old=common.load(self.baseline['wire/'+oldid+'/request.wire.json'])
                d=input_of(old);d['selection_original'].pop('response_sha256')
                for h in d['history']:h.pop('response_sha256')
                prefix=old['messages'][0]['content'].split('\n\ninput: ',1)[0]
                old['messages'][0]['content']=prefix+'\n\ninput: '+common.wire(d).decode()
                self.assertEqual(old,design.request_for(self.p,s,mapped))
    def test_v075_fact_only_replay_does_not_repair_old_errors(self):
        records={};raw={}
        for s in self.p['slots']:
            oldid=s['id'] if s['stage']=='select' else s['id'].replace('_base_','_fact_only_').replace('_parent_count_','_fact_only_')
            r=common.load(self.baseline['records/'+oldid+'.json']);r['id']=s['id'];records[s['id']]=r
            if r['kind']=='call':raw[s['id']]=self.baseline['wire/'+oldid+'/response.raw.json']
        a=report.summarize(self.p,records,raw,'complete');b=audit_model.independent_summary(self.p,records,raw,'complete')
        self.assertTrue(common.exact(a,b));self.assertEqual(a['shared_model_selection']['successes'],20)
        self.assertEqual(a['observed_inference_calls'],332)
        for v in ('base','parent_count'):
            x=a['arms'][v];self.assertEqual(x['model_trace']['successes'],17);self.assertEqual(x['model_pairs']['successes'],5)
            self.assertEqual(x['reference_construction']['successes'],9);self.assertEqual(x['initial_fact_stage']['successes'],36)
    def test_new_patterns_independent(self):
        modes=['arity_sensitive','arity_harms','arity_missing_all','correct_count_wrong_identity','duplicate_parent_for_Ab','wrong_atom_parent_count','duplicate_fact_ids','fact_overflow']
        for mode in modes:
            r,w,_=memory_run(self.p,mode)
            for state in ('complete','crashed'):
                a=report.summarize(self.p,r,w,state);b=audit_model.independent_summary(self.p,r,w,state)
                self.assertTrue(common.exact(a,b),mode);self.assertEqual(report.render(a),audit_model.independent_report(b),mode)
    def test_partial_diagnostics_not_filled_with_zero(self):
        r,w,_=memory_run(self.p,limit=7);s=report.summarize(self.p,r,w,'crashed')
        self.assertIsNone(s['end_to_end_baseline_ready'])
        self.assertTrue(any(c['observed_count'] is None for t in s['trials'] for c in t['parent_count_checks']))
    def test_hashes_do_not_disappear_from_evidence(self):
        for sid,r in self.records.items():
            if r['kind']=='call':self.assertEqual(r['response_sha256'],common.sha(self.raw[sid]))

if __name__=='__main__':unittest.main()
