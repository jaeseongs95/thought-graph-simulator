"""배정·출처·요청 처치·기존 요청 회귀. 실제 네트워크 호출 없음."""
from copy import deepcopy
from collections import Counter
from pathlib import Path
import sys,unittest,zipfile,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core083 as c,design083 as d,audit083 as a
from fixtures083 import plan,response_set,BASELINE,decode_request

class Contract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p=plan();cls.recs,cls.raws,cls.requests=response_set(cls.p)
    def test_independent_schedule(self):
        a.validate_protocol(self.p['protocol']);self.assertTrue(c.exact(d.schedule(self.p['protocol']),a.reconstruct_schedule(self.p['protocol'])))
    def test_count_scopes(self):
        p=self.p;self.assertEqual((len(p['trials']),len(p['slots']),len(p['actions'])),(400,1628,1644))
        self.assertEqual(sum(t['generate'] for t in p['trials']),208)
        self.assertEqual(Counter(t['selector_variant'] for t in p['trials']),{'candidate_id':96,'correct_full':96,'correct_values':96,'swapped_values':96,'reference':16})
    def test_no_profile_model_calls(self):self.assertFalse(any(o['stage']=='profile' for o in self.p['slots']))
    def test_selection_only_has_no_generation_slots(self):
        for t in self.p['trials']:
            if not t['generate']:self.assertEqual([o['stage'] for o in self.p['slots'] if o['trial_id']==t['id']],['select'])
    def test_counterbalanced_arm_order(self):
        for metric in ('D','W'):
            sets={}
            for t in self.p['trials']:
                if t['arm']=='model' and t['metric']==metric:sets.setdefault(t['unit_id'],[]).append(t['selector_variant'])
            for pos in range(4):self.assertEqual(len(set(Counter(v[pos] for v in sets.values()).values())),1)
    def test_every_request_independently_reconstructed(self):
        for op in self.p['slots']:
            skip,raw=a.expected_request(self.p,op,self.raws)
            self.assertEqual(skip,d.disposition(self.p,op,self.raws))
            if skip is None:self.assertEqual(raw,self.requests[op['id']])
    def test_control_origin_and_truth(self):
        s=self.p['protocol'];self.assertEqual(s['support_origin'],'experimenter_constructed_before_inference_not_model_computation')
        for p in s['problems']:
            for i in (0,1):self.assertEqual(s['frozen_profiles'][p['id']][i],a.reference_profile(s,p,i))
    def test_control_mutations_rejected(self):
        mutations=[('goal_depth',True),('goal_depth',9),('rule_count',0)]
        for key,val in mutations:
            s=deepcopy(self.p['protocol']);s['frozen_profiles']['H01'][0][key]=val
            with self.assertRaises(ValueError):a.validate_protocol(s)
    def test_swap_only_two_requested_values(self):
        for uid in sorted({t['unit_id'] for t in self.p['trials'] if t['arm']=='model'}):
            ts={t['selector_variant']:t for t in self.p['trials'] if t['unit_id']==uid}
            t,u=ts['correct_values'],ts['swapped_values'];q=c.load(self.requests[t['selection_slot_id']]);r=c.load(self.requests[u['selection_slot_id']])
            x=decode_request(q);y=decode_request(r);key='goal_depth' if t['metric']=='D' else 'rule_count'
            values=[c.load(z['content']) for z in x['candidate_measurements']]
            swapped=deepcopy(values);swapped[0][key],swapped[1][key]=values[1][key],values[0][key]
            y0=deepcopy(x)
            for card,val in zip(y0['candidate_measurements'],swapped):card['content']=c.wire(val).decode()
            self.assertEqual(y,y0)
            old=q['messages'][0]['content'];new=r['messages'][0]['content']
            self.assertEqual(old.split('\n\ninput: ')[0],new.split('\n\ninput: ')[0]);self.assertEqual(len(c.wire(q)),len(c.wire(r)))
            q['messages']=r['messages'];self.assertEqual(q,r)
    def test_full_summary_agree_on_numbers(self):
        for t in self.p['trials']:
            if t['selector_variant']!='correct_full':continue
            full=d.measurements_for(self.p,t);other=deepcopy(t);other['selector_variant']='correct_values';brief=d.measurements_for(self.p,other)
            for x,y in zip(full,brief):
                p,q=c.load(x['content']),c.load(y['content']);self.assertEqual({k:p[k] for k in q},q)
                self.assertEqual(set(q),{'goal_depth','rule_count'})
    def test_no_oracle_tag_in_selector_prompt(self):
        for t in self.p['trials']:
            if t['arm']!='model':continue
            text=c.load(self.requests[t['selection_slot_id']])['messages'][0]['content']
            for tag in ['correct_full','correct_values','swapped_values','experimenter_constructed','oracle']:
                self.assertNotIn(tag,text)
    def test_support_not_sent_to_generator(self):
        for op in self.p['slots']:
            if op['stage']=='select' or op['id'] not in self.requests:continue
            data=decode_request(c.load(self.requests[op['id']]))
            self.assertEqual(set(data),{'problem','selection_original','provided_route_plan','operation','history'})
            self.assertNotIn('candidate_measurements',data)
    def test_same_selection_history_same_generator_bytes(self):
        by={}
        for op in self.p['slots']:
            t=d.trial_for(self.p,op)
            if t['arm']!='model' or op['stage']=='select' or op['id'] not in self.requests:continue
            key=(t['unit_id'],op['stage'],op['rule_position']);by.setdefault(key,[]).append(self.requests[op['id']])
        self.assertTrue(by)
        for arr in by.values():self.assertEqual(len(set(arr)),1)
    def test_wrong_selection_not_repaired(self):
        t=next(t for t in self.p['trials'] if t['selector_variant']=='correct_values' and t['condition']=='deep')
        cs=d.cards(self.p,t);wrong=cs[0]['candidate_id'];raw=c.wire({'message':{'content':c.wire({'candidate_id':wrong}).decode()}})
        route=d.selected_route(self.p,t,{t['selection_slot_id']:raw});self.assertEqual(route['candidate_id'],wrong)
    def test_invalid_selection_not_filled(self):
        t=next(t for t in self.p['trials'] if t['arm']=='model')
        for value in [{'candidate_id':'absent'},{'candidate_id':True},{'candidate_id':'route_0','x':1},{}]:
            raw=c.wire({'message':{'content':c.wire(value).decode()}});self.assertIsNone(d.selected_route(self.p,t,{t['selection_slot_id']:raw}))
    def test_reference_only_once(self):
        refs=[t for t in self.p['trials'] if t['arm']=='reference'];self.assertEqual(len(refs),16)
        self.assertTrue(all(t['selection_slot_id'] is None for t in refs))
    def test_no_id_or_direction_inside_control_content(self):
        for p in self.p['protocol']['frozen_profiles'].values():
            raw=c.wire(p).decode()
            for bad in ['route_0','route_1','shallow','deep','candidate_id']:self.assertNotIn(bad,raw)
    @unittest.skipUnless(BASELINE.is_file(),'v082 evidence required')
    def test_previous_actual_request_compatibility(self):
        with zipfile.ZipFile(BASELINE) as z:
            raws={name.split('/')[1]:z.read(name) for name in z.namelist() if name.startswith('wire/') and name.endswith('/response.raw.json')}
            count=0;choices=0
            for op in self.p['slots']:
                t=d.trial_for(self.p,op)
                if t['selector_variant'] not in ('candidate_id','reference'):continue
                path='wire/'+op['id']+'/request.wire.json'
                if path not in z.namelist():continue
                self.assertEqual(c.wire(d.request_for(self.p,op,raws)),z.read(path));count+=1;choices+=op['stage']=='select'
            self.assertEqual(choices,96);self.assertGreater(count,500)
    @unittest.skipUnless(BASELINE.is_file(),'v082 evidence required')
    def test_previous_independent_verifier(self):
        from previous083 import audit
        rec=audit(BASELINE.read_bytes());self.assertTrue(rec['verified']);self.assertEqual(rec['observed_calls'],1407)
    def test_legacy_hashes_unchanged(self):
        h=c.load((c.ROOT/'data/legacy_hashes.json').read_bytes())
        for name,digest in h.items():self.assertEqual(c.sha((c.ROOT/'legacy'/name).read_bytes()),digest)
