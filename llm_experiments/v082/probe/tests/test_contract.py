"""v082 계약: 실제 대조군 요청 보존, 무보정 계산표 전달, 독립 재구성."""
import ast,unittest,zipfile
from collections import Counter
from copy import deepcopy
import core082 as core, design082 as design, audit082 as audit, report082 as report
from fixtures082 import plan,response_set,decode_request,BASELINE

class Contract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p=plan();cls.records,cls.raws,cls.requests=response_set(cls.p)
        cls.summary=report.summarize(cls.p,cls.records,cls.raws,'complete')
    def test_independent_schedule(self):
        self.assertEqual(design.schedule(self.p['protocol']),audit.reconstruct_schedule(self.p['protocol']))
        audit.validate_protocol(self.p['protocol'])
    def test_exact_counts(self):
        self.assertEqual((len(self.p['trials']),len(self.p['slots']),len(self.p['actions'])),(208,1484,1500))
        self.assertEqual(Counter(o['stage'] for o in self.p['slots']),{'profile':16,'select':192,'facts':208,'rule':860,'final':208})
        for v in ('candidate_id','profiled_id'):
            self.assertEqual(Counter(t['metric'] for t in self.p['trials'] if t['selector_variant']==v),{'D':64,'W':32})
    def test_balanced_order(self):
        units={}
        for t in self.p['trials']:
            if t['arm']=='model':units.setdefault(t['unit_id'],[]).append(t['selector_variant'])
        self.assertEqual(Counter(v[0] for v in units.values()),{'candidate_id':48,'profiled_id':48})
        perblock={}
        for o in self.p['slots']:
            if o['stage']=='profile':perblock.setdefault(o['id'][:3],[]).append(o['candidate_kind'])
        self.assertEqual(Counter(v[0] for v in perblock.values()),{0:4,1:4})
    def test_all_requests_independently_reconstructed(self):
        for op in self.p['slots']:
            skip,raw=audit.expected_request(self.p,op,self.raws)
            self.assertEqual(skip,design.disposition(self.p,op,self.raws),op['id'])
            if skip is None:self.assertEqual(raw,self.requests[op['id']],op['id'])
    def test_full_summary_independent(self):
        self.assertEqual(self.summary,audit.independent_summary(self.p,self.records,self.raws,'complete'))
    def test_perfect_synthetic_counts(self):
        self.assertEqual(len(self.requests),1420)
        self.assertEqual(self.summary['profile_analysis']['trace']['successes'],16)
        for v in ('candidate_id','profiled_id'):
            self.assertEqual(self.summary['groups'][v]['totals']['D']['metric_end_to_end']['successes'],64)
            self.assertEqual(self.summary['groups'][v]['totals']['D']['end_to_end_pairs']['successes'],32)
        self.assertEqual(self.summary['profile_analysis']['pipeline_pairs']['D']['successes'],32)
    def test_same_selector_output_schema_api_input_difference_explicit(self):
        for a in self.p['trials']:
            if a['selector_variant']!='candidate_id':continue
            b=next(t for t in self.p['trials'] if t['unit_id']==a['unit_id'] and t['selector_variant']=='profiled_id')
            ra,rb=[core.load(self.requests[t['selection_slot_id']]) for t in (a,b)]
            self.assertEqual({k:v for k,v in ra.items() if k!='messages'},{k:v for k,v in rb.items() if k!='messages'})
            da,db=map(decode_request,(ra,rb));db.pop('candidate_measurements')
            self.assertEqual(da,db)
    def test_direction_changes_only_demand(self):
        groups={}
        for t in self.p['trials']:
            if t['pair_id']:groups.setdefault(t['pair_id'],[]).append(t)
        for ts in groups.values():
            bodies=[]
            for t in ts:
                b=core.load(self.requests[t['selection_slot_id']]);d=decode_request(b)
                d.pop('requested_depth',None);d.pop('requested_rule_count',None)
                head=b['messages'][0]['content'].split('\n\ninput: ',1)[0]
                b['messages'][0]['content']=head+'\n\ninput: '+core.wire(d).decode();bodies.append(b)
            self.assertEqual(bodies[0],bodies[1])
    def test_profile_inputs_no_other_candidate_label_or_demand(self):
        seen=set()
        for o in self.p['slots']:
            if o['stage']!='profile':continue
            d=decode_request(core.load(self.requests[o['id']]))
            self.assertEqual(set(d),{'facts','goal','candidate_rules'})
            self.assertTrue(all(set(r)=={'id','premises','conclusion'} for r in d['candidate_rules']))
            t=design.trial_for(self.p,o);key=(t['problem_id'],t['seed'],o['candidate_kind'])
            self.assertNotIn(key,seen);seen.add(key)
        self.assertEqual(len(seen),16)
    def test_exact_profile_strings_shared_and_matched_to_cards(self):
        for t in self.p['trials']:
            if t['selector_variant']!='profiled_id':continue
            data=decode_request(core.load(self.requests[t['selection_slot_id']]))
            for i,x in enumerate(data['candidate_measurements']):
                kind=self.p['protocol']['candidate_orders'][t['candidate_order_index']][i]
                sid=f"b{t['block']:02d}_profile_{kind}"
                self.assertEqual(x,{'candidate_id':data['candidates'][i]['candidate_id'],'content':core.load(self.raws[sid])['message']['content']})
    def test_no_trace_enum_or_answer_values(self):
        text=core.wire(self.p['protocol']['profile_schema']).decode()
        self.assertNotIn('"enum"',text);self.assertNotIn('"const"',text)
        self.assertEqual(self.p['protocol']['profile_schema']['properties']['steps']['maxItems'],16)
        self.assertIs(self.p['protocol']['numeric_report_required'],False)
    def test_generation_never_gets_profiles(self):
        for o in self.p['slots']:
            if o['stage'] in ('profile','select') or o['id'] not in self.requests:continue
            d=decode_request(core.load(self.requests[o['id']]))
            self.assertNotIn('candidate_measurements',d)
            self.assertNotIn('profile',core.wire(d).decode())
            previous=[s for s in self.p['slots'][:self.p['slots'].index(o)] if s['trial_id']==o['trial_id'] and s['stage'] in ('facts','rule','final') and s['id'] in self.raws]
            self.assertEqual([h['content'] for h in d['history']],[core.load(self.raws[p['id']])['message']['content'] for p in previous])
    def test_equal_chosen_ID_equal_generation_requests_in_synthetic(self):
        for t in self.p['trials']:
            if t['selector_variant']!='candidate_id':continue
            b=next(x for x in self.p['trials'] if x['unit_id']==t['unit_id'] and x['selector_variant']=='profiled_id')
            aa=[o for o in self.p['slots'] if o['trial_id']==t['id'] and o['stage'] in ('facts','rule','final')]
            bb=[o for o in self.p['slots'] if o['trial_id']==b['id'] and o['stage'] in ('facts','rule','final')]
            for x,y in zip(aa,bb):self.assertEqual(self.requests.get(x['id']),self.requests.get(y['id']))
    def test_profile_usage_not_counted_as_generation_or_multiple_times(self):
        g=self.summary['groups']
        self.assertEqual(g['profiled_id']['usage_by_stage']['profile']['calls'],16)
        self.assertEqual(g['candidate_id']['usage_by_stage']['profile']['calls'],0)
        self.assertEqual(g['candidate_id']['usage_by_stage']['generation']['calls'],g['profiled_id']['usage_by_stage']['generation']['calls'])
        self.assertEqual(self.summary['reference']['assigned'],16)
    def test_mapping_never_uses_required_metric_or_profiles(self):
        for t in self.p['trials']:
            if t['arm']!='model':continue
            changed=deepcopy(t);changed['condition']='deep' if t['condition']=='shallow' else 'shallow';changed['metric']='W'
            self.assertEqual(design.selected_route(self.p,t,self.raws),design.selected_route(self.p,changed,self.raws))
            no_profile={k:v for k,v in self.raws.items() if '_profile_' not in k}
            self.assertEqual(design.selected_route(self.p,t,self.raws),design.selected_route(self.p,t,no_profile))
    def test_independent_modules_no_production_imports(self):
        forbidden={'design082','report082','profile082','measure','stages','design','report'}
        for name in ['audit082.py','audit_profile082.py','verify082.py','legacy/audit_model.py','legacy/audit_graph.py']:
            tree=ast.parse((core.ROOT/name).read_text());imports=[]
            for n in ast.walk(tree):
                if isinstance(n,ast.Import):imports.extend(x.name for x in n.names)
                elif isinstance(n,ast.ImportFrom):imports.append(n.module)
            self.assertFalse(set(imports)&forbidden,name)
    @unittest.skipUnless(BASELINE.is_file(),'baseline unavailable')
    def test_prior_739_control_and_reference_requests_preserved(self):
        with zipfile.ZipFile(BASELINE) as z:
            raws={n.split('/')[1]:z.read(n) for n in z.namelist() if n.startswith('wire/') and n.endswith('/response.raw.json')}
            n=0
            for op in self.p['slots']:
                t=design.trial_for(self.p,op)
                if t['selector_variant'] not in ('candidate_id','reference'):continue
                key='wire/'+op['id']+'/request.wire.json'
                if key in z.namelist():self.assertEqual(core.wire(design.request_for(self.p,op,raws)),z.read(key),op['id']);n+=1
            self.assertEqual(n,739)
    @unittest.skipUnless(BASELINE.is_file(),'baseline unavailable')
    def test_legacy_bytes_unchanged(self):
        with zipfile.ZipFile(BASELINE) as z:
            for p in (core.ROOT/'legacy').glob('*.py'):self.assertEqual(p.read_bytes(),z.read('source/legacy/'+p.name),p.name)

if __name__=='__main__':unittest.main()
