"""동결 계약·배정·신규 구조·실제 v083 요청 바이트 회귀. 모델 호출 없음."""
from copy import deepcopy
from collections import Counter
from pathlib import Path
import sys,unittest,zipfile,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core084 as c,design084 as d,audit084 as a,cases084
from fixtures084 import plan,response_set,BASELINE,decode_request

class Contract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p=plan();cls.recs,cls.raws,cls.requests=response_set(cls.p)
    def test_independent_schedule(self):
        a.validate_protocol(self.p['protocol']);self.assertTrue(c.exact(d.schedule(self.p['protocol']),a.reconstruct_schedule(self.p['protocol'])))
    def test_count_scopes(self):
        p=self.p;self.assertEqual((len(p['trials']),len(p['slots']),len(p['actions'])),(416,2284,2316))
        self.assertEqual(sum(t['generate'] for t in p['trials']),288)
        self.assertEqual(Counter(t['selector_variant'] for t in p['trials']),{'candidate_id':192,'correct_values':192,'reference':32})
        self.assertEqual(len(self.raws),2220)
    def test_no_profile_model_calls(self):self.assertFalse(any(o['stage']=='profile' for o in self.p['slots']))
    def test_W_has_no_generation_slots(self):
        for t in self.p['trials']:
            if not t['generate']:
                self.assertEqual(t['metric'],'W');self.assertEqual([o['stage'] for o in self.p['slots'] if o['trial_id']==t['id']],['select'])
    def test_counterbalanced_arm_order(self):
        for metric in ('D','W'):
            sets={}
            for t in self.p['trials']:
                if t['arm']=='model' and t['metric']==metric:sets.setdefault(t['unit_id'],[]).append(t['selector_variant'])
            for pos in range(2):self.assertEqual(len(set(Counter(v[pos] for v in sets.values()).values())),1)
    def test_every_request_independently_reconstructed(self):
        for op in self.p['slots']:
            skip,raw=a.expected_request(self.p,op,self.raws)
            self.assertEqual(skip,d.disposition(self.p,op,self.raws))
            if skip is None:self.assertEqual(raw,self.requests[op['id']])
    def test_control_origin_and_truth(self):
        s=self.p['protocol']
        for p in s['problems']:
            for i in (0,1):self.assertEqual(s['frozen_profiles'][p['id']][i],a.reference_profile(s,p,i))
    def test_control_mutations_rejected(self):
        for key,val in [('goal_depth',True),('goal_depth',9),('rule_count',0)]:
            s=deepcopy(self.p['protocol']);s['frozen_profiles']['T01'][0][key]=val
            with self.assertRaises(ValueError):a.validate_protocol(s)
    def test_support_contains_only_D_W_not_answer_label(self):
        for t in self.p['trials']:
            if t['selector_variant']!='correct_values':continue
            items=d.measurements_for(self.p,t)
            for item in items:
                value=c.load(item['content']);self.assertEqual(set(value),{'goal_depth','rule_count'})
                self.assertTrue(all(type(v) is int for v in value.values()))
    def test_no_oracle_tag_in_selector_prompt(self):
        for t in self.p['trials']:
            if t['arm']!='model':continue
            text=c.load(self.requests[t['selection_slot_id']])['messages'][0]['content']
            for tag in ['correct_values','experimenter_constructed','oracle','equal_rule_count','structural_case']:
                self.assertNotIn(tag,text)
    def test_support_not_sent_to_generator(self):
        for op in self.p['slots']:
            if op['stage']=='select' or op['id'] not in self.requests:continue
            data=decode_request(c.load(self.requests[op['id']]))
            self.assertEqual(set(data),{'problem','selection_original','provided_route_plan','operation','history'})
    def test_same_selection_history_same_generator_bytes(self):
        by={}
        for op in self.p['slots']:
            t=d.trial_for(self.p,op)
            if t['arm']!='model' or op['stage']=='select' or op['id'] not in self.requests:continue
            key=(t['unit_id'],op['stage'],op['rule_position']);by.setdefault(key,[]).append(self.requests[op['id']])
        for arr in by.values():self.assertEqual(len(set(arr)),1)
    def test_wrong_selection_not_repaired(self):
        t=next(t for t in self.p['trials'] if t['selector_variant']=='correct_values' and t['condition']=='deep')
        cs=d.cards(self.p,t);p=d.problem_for(self.p,t)
        vals=[a.prior.route_depth(p,[r['id'] for r in x['rules']]) for x in cs]
        wrong=cs[vals.index(min(vals))]['candidate_id']
        raw=c.wire({'message':{'content':c.wire({'candidate_id':wrong}).decode()}})
        self.assertEqual(d.selected_route(self.p,t,{t['selection_slot_id']:raw})['candidate_id'],wrong)
    def test_invalid_selection_not_filled(self):
        t=next(t for t in self.p['trials'] if t['arm']=='model')
        for value in [{'candidate_id':'absent'},{'candidate_id':True},{'candidate_id':'route_0','x':1},{}]:
            raw=c.wire({'message':{'content':c.wire(value).decode()}});self.assertIsNone(d.selected_route(self.p,t,{t['selection_slot_id']:raw}))
    def test_reference_only_once(self):
        refs=[t for t in self.p['trials'] if t['arm']=='reference'];self.assertEqual(len(refs),32)
        self.assertTrue(all(t['selection_slot_id'] is None for t in refs))
    def test_rebuild_frozen_cases(self):self.assertTrue(c.exact(cases084.build_protocol(),self.p['protocol']))
    def test_all_preserved_request_keys(self):
        old=c.load((c.ROOT/'data/v083_protocol.json').read_bytes())
        for key in cases084.FROZEN_REQUEST_KEYS:self.assertTrue(c.exact(old[key],self.p['protocol'][key]),key)
    def test_topology_rename_invariance_and_independent_isomorphism(self):
        s=self.p['protocol']
        for p in s['problems']:
            paths=[s['reference_plans'][p['id']][k] for k in s['reference_conditions']]
            q=deepcopy(p)
            q['facts']=['renamed_'+x for x in q['facts']][::-1];q['goal']='renamed_'+q['goal']
            for r in q['rules']:
                r['id']='r_'+r['id'];r['conclusion']='renamed_'+r['conclusion'];r['premises']=['renamed_'+x for x in r['premises']][::-1]
            q['rules'].reverse();routes=[['r_'+x for x in path] for path in paths]
            self.assertEqual(cases084.topology_signature(p,paths),cases084.topology_signature(q,routes))
            self.assertTrue(a.isomorphic_pair(p,paths,q,routes))
    def test_topology_is_not_layer_histogram(self):
        s=self.p['protocol'];p=s['problems'][2];q=s['problems'][3]
        ps=[s['reference_plans'][p['id']][k] for k in s['reference_conditions']];qs=[s['reference_plans'][q['id']][k] for k in s['reference_conditions']]
        self.assertFalse(a.isomorphic_pair(p,ps,q,qs));self.assertNotEqual(cases084.topology_signature(p,ps),cases084.topology_signature(q,qs))
    @unittest.skipUnless(BASELINE.is_file(),'v083 evidence required')
    def test_previous_actual_request_compatibility(self):
        with zipfile.ZipFile(BASELINE) as z:
            old=c.load(z.read('plan.json'))
            raws={name.split('/')[1]:z.read(name) for name in z.namelist() if name.startswith('wire/') and name.endswith('/response.raw.json')}
            count=choices=0
            for op in old['slots']:
                t=d.trial_for(old,op)
                if t['selector_variant'] not in ('candidate_id','reference','correct_values'):continue
                path='wire/'+op['id']+'/request.wire.json'
                if path not in z.namelist():continue
                self.assertEqual(c.wire(d.request_for(old,op,raws)),z.read(path));count+=1;choices+=op['stage']=='select'
            self.assertEqual(choices,192);self.assertEqual(count,1020)
    @unittest.skipUnless(BASELINE.is_file(),'v083 evidence required')
    def test_previous_independent_verifier(self):
        from previous084 import audit
        rec=audit(BASELINE.read_bytes());self.assertTrue(rec['verified']);self.assertEqual(rec['observed_calls'],1576)
    def test_legacy_hashes_unchanged(self):
        h=c.load((c.ROOT/'data/legacy_hashes.json').read_bytes())
        for name,digest in h.items():self.assertEqual(c.sha((c.ROOT/'legacy'/name).read_bytes()),digest)
