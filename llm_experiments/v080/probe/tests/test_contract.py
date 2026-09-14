"""설계·무보정·측정 분리·기존 요청 회귀 검사."""
import unittest,json,zipfile,sys,ast
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import core080 as core
import design080,audit080,report080,calibrate080
from fixtures080 import plan,response_set,decode_request,BASELINE


class Design(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.p=plan()
    def test_schedule_independent(self):
        self.assertEqual(design080.schedule(self.p['protocol']),audit080.reconstruct_schedule(self.p['protocol']))
    def test_exact_denominators(self):
        ts=self.p['trials'];self.assertEqual((len(ts),len(self.p['slots']),len(self.p['actions'])),(112,780,796))
        self.assertEqual(sum(t['arm']=='model' and t['metric']=='D' for t in ts),64)
        self.assertEqual(sum(t['arm']=='model' and t['metric']=='W' for t in ts),32)
        self.assertEqual(sum(t['arm']=='reference' for t in ts),16)
    def test_request_independent(self):
        for op in self.p['slots']:
            if op['stage']=='select':
                self.assertEqual(core.wire(design080.request_for(self.p,op,{})),audit080.expected_request(self.p,op,{})[1])
    def test_candidate_id_not_position(self):
        for t in self.p['trials']:
            if t['arm']=='model':
                cs=design080.cards(self.p,t)
                self.assertEqual(cs[0]['candidate_id'],'route_0' if t['id_assignment_index']==0 else 'route_1')
    def test_schema_enum_order_unchanged(self):
        for op in self.p['slots']:
            if op['stage']=='select':
                req=design080.request_for(self.p,op,{})
                self.assertEqual(req['format']['properties']['candidate_id']['enum'],['route_0','route_1'])
    def test_no_candidate_depth_or_work_leak(self):
        for op in self.p['slots']:
            if op['stage']=='select':
                data=decode_request(design080.request_for(self.p,op,{}))
                self.assertEqual(set(data['problem']),{'facts','rules','goal'})
                self.assertTrue(all(set(c)=={'candidate_id','rules'} for c in data['candidates']))
                self.assertEqual(set(data),{'problem','candidates','requested_rule_count' if 'requested_rule_count' in data else 'requested_depth'})
    def test_no_ties_in_W(self):
        for t in self.p['trials']:
            if t['metric']=='W':
                lengths=[len(c['rules']) for c in design080.cards(self.p,t)]
                self.assertNotEqual(*lengths)
    def test_direction_pair_only_request_diff(self):
        groups={}
        for t in self.p['trials']:
            if t['arm']=='model':groups.setdefault(t['pair_id'],[]).append(t)
        for ts in groups.values():
            bodies=[]
            for t in ts:
                op=next(s for s in self.p['slots'] if s['id']==t['selection_slot_id'])
                b=design080.request_for(self.p,op,{})
                head,tail=b['messages'][0]['content'].split('\n\ninput: ',1);data=core.load(tail)
                data.pop('requested_depth',None);data.pop('requested_rule_count',None)
                b['messages'][0]['content']=head+'\n\ninput: '+core.wire(data).decode();bodies.append(b)
            self.assertEqual(*bodies)
    def test_same_candidates_D_W(self):
        ts=self.p['trials']
        for w in ts:
            if w['arm']=='model' and w['metric']=='W':
                d=next(t for t in ts if t['arm']=='model' and t['metric']=='D' and all(t[k]==w[k] for k in ['problem_id','seed','candidate_order_index','id_assignment_index','condition']))
                self.assertEqual(design080.cards(self.p,w),design080.cards(self.p,d))
    def test_raw_content_preserved_even_length(self):
        t=next(t for t in self.p['trials'] if t['arm']=='model');sid=t['selection_slot_id']
        raw=core.wire({'model':'qwen3:4b-instruct','done':True,'done_reason':'length','message':{'role':'assistant','content':'{ "candidate_id" : "route_1" }'}})
        op=next(s for s in self.p['slots'] if s['trial_id']==t['id'] and s['stage']=='facts')
        data=decode_request(design080.request_for(self.p,op,{sid:raw}))
        self.assertEqual(data['selection_original']['content'],'{ "candidate_id" : "route_1" }')
    def test_no_new_numeric_reporting(self):
        self.assertEqual(self.p['protocol']['selector_schema']['required'],['candidate_id'])
    def test_no_runtime_scorer_import(self):
        tree=ast.parse((core.ROOT/'design080.py').read_text())
        imported=[]
        for n in ast.walk(tree):
            if isinstance(n,ast.Import):imported += [a.name for a in n.names]
        self.assertFalse({'measure','report080','calibrate080'}&set(imported))
    def test_independent_does_not_import_production(self):
        tree=ast.parse((core.ROOT/'audit080.py').read_text())
        names=[]
        for n in ast.walk(tree):
            if isinstance(n,ast.Import):names += [a.name for a in n.names]
            if isinstance(n,ast.ImportFrom):names.append(n.module)
        self.assertFalse({'design080','report080','measure','stages'}&set(names))
    def test_legacy_modules_unchanged(self):
        hashes=core.load((core.ROOT/'data/legacy_hashes.json').read_bytes())
        for n,h in hashes.items():self.assertEqual(core.sha((core.ROOT/'legacy'/n).read_bytes()),h)
    @unittest.skipUnless(BASELINE.is_file(),'v079 evidence가 없어서 읽기 전용 회귀 검사 건너뜀')
    def test_32_v079_D_requests_exact(self):
        with zipfile.ZipFile(BASELINE) as z:
            old=core.load(z.read('plan.json'));compared=0
            for t in self.p['trials']:
                if t['arm']!='model' or t['metric']!='D' or t['id_assignment_index']!=0:continue
                ot=next(x for x in old['trials'] if x['arm']=='model' and x['variant']=='explicit_rule' and all(x[k]==t[k] for k in ['problem_id','seed','candidate_order_index','condition']))
                slot=next(s for s in self.p['slots'] if s['id']==t['selection_slot_id'])
                self.assertEqual(core.wire(design080.request_for(self.p,slot,{})),z.read('wire/'+ot['selection_slot_id']+'/request.wire.json'));compared+=1
            self.assertEqual(compared,32)
    def test_schema_drift_rejected(self):
        s=deepcopy(self.p['protocol']);s['candidate_orders']=[[0,1],[0,1]]
        with self.assertRaises(ValueError):audit080.validate_protocol(s)


class Metrics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p=plan();cls.records,cls.raws,cls.requests=response_set(cls.p)
        cls.summary=report080.summarize(cls.p,cls.records,cls.raws,'complete')
    def test_full_normal_748(self):self.assertEqual(len(self.raws),748)
    def test_all_normal_scores(self):
        for m,n in [('D',64),('W',32)]:self.assertEqual(self.summary['totals'][m]['metric_end_to_end']['successes'],n)
        self.assertEqual(self.summary['reference']['successes'],16)
    def test_independent_full(self):
        self.assertEqual(self.summary,audit080.independent_summary(self.p,self.records,self.raws,'complete'))
    def test_all_followup_requests_independent(self):
        for op in self.p['slots']:
            if op['id'] in self.requests:
                self.assertEqual(self.requests[op['id']],audit080.expected_request(self.p,op,self.raws)[1])
    def test_robust_groups(self):
        self.assertEqual(self.summary['totals']['D']['presentation_robust_end_to_end']['successes'],8)
        self.assertEqual(self.summary['totals']['W']['presentation_robust_end_to_end']['successes'],4)
    def test_metric_discrimination(self):
        self.assertEqual(len(self.summary['metric_discrimination']),16)
        self.assertTrue(all(c['all_four_end_to_end_correct'] for c in self.summary['metric_discrimination']))
    def test_empty_is_unmeasured_not_zero(self):
        a=report080.summarize(self.p,{}, {},'crashed');b=audit080.independent_summary(self.p,{}, {},'crashed')
        self.assertEqual(a,b);self.assertEqual(a['totals']['D']['metric_end_to_end']['unmeasured'],64)
        self.assertTrue(all(r['actual_D'] is None for r in a['trials']))
    def test_half_pair_is_not_win(self):
        rows=deepcopy(self.summary['trials']);r=next(r for r in rows if r['arm']=='model')
        r['metric_end_to_end']=None;r['selection_success']=None;r['selector_status']='not_executed';r['generator_success']=None
        a=report080.aggregate(self.p,rows,{},[],'crashed');b=audit080.independent_aggregate(self.p,rows,{},[],'crashed')
        self.assertEqual(a,b);p=next(p for p in a['pairs'] if p['pair_id']==r['pair_id']);self.assertIsNone(p['end_to_end_success'])
    def test_wrong_intermediate_not_repaired(self):
        sid=next(op['id'] for op in self.p['slots'] if op['stage']=='rule')
        raws=deepcopy(self.raws);obj=core.load(raws[sid]);inner=core.load(obj['message']['content']);inner['node']['parents']=[]
        obj['message']['content']=core.wire(inner).decode();raws[sid]=core.wire(obj)
        a=report080.summarize(self.p,self.records,raws,'complete');b=audit080.independent_summary(self.p,self.records,raws,'complete')
        self.assertEqual(a,b);tid=next(s['trial_id'] for s in self.p['slots'] if s['id']==sid)
        row=next(r for r in a['trials'] if r['trial_id']==tid);self.assertFalse(row['generator_success']);self.assertIsNone(row['actual_D'])
    def test_usage_missing_not_zero(self):
        raws=deepcopy(self.raws);sid=next(iter(raws));obj=core.load(raws[sid]);obj.pop('eval_count');raws[sid]=core.wire(obj)
        s=report080.summarize(self.p,self.records,raws,'complete')
        self.assertEqual(s['usage']['eval_count']['missing'],1);self.assertEqual(s['usage']['eval_count']['sum_observed'],747)
    def test_length_and_schema_and_transport_separate(self):
        cases=[('length_termination',lambda o:o.update(done_reason='length')),('invalid_json',lambda o:o['message'].update(content='not json')),('identity_error',lambda o:o.update(model='other'))]
        sid=next(t['selection_slot_id'] for t in self.p['trials'] if t['arm']=='model')
        for status,fn in cases:
            with self.subTest(status=status):
                raws=dict(self.raws);o=core.load(raws[sid]);fn(o);raws[sid]=core.wire(o)
                a=report080.summarize(self.p,self.records,raws,'complete');b=audit080.independent_summary(self.p,self.records,raws,'complete')
                self.assertEqual(a,b);self.assertEqual(a['call_statuses'][status],1)


class Calibration(unittest.TestCase):
    def test_all_measurement_calibrations(self):
        r=calibrate080.calibration();self.assertEqual(r['failed'],0);self.assertGreaterEqual(r['passed'],87)
    def test_macro_raw_depth_not_invariant(self):
        m=calibrate080.calibration()['macro_example']
        self.assertEqual((m['raw_primitive_D'],m['raw_macro_D'],m['expanded_in_fixed_primitive_system_D']),(2,1,2))
    def test_wrong_macro_interface_rejected(self):
        p={'facts':['A'],'rules':[{'id':'r','premises':['A'],'conclusion':'G'}],'goal':'G'}
        with self.assertRaises(ValueError):calibrate080.expand_declared_macro({'premises':['B'],'conclusion':'G'},p,['r'])
        with self.assertRaises(ValueError):calibrate080.expand_declared_macro({'premises':['A'],'conclusion':'X'},p,['r'])
    def test_same_rule_count_not_same_D(self):
        xs=[x for x in calibrate080.calibration()['structures'] if x['problem']=='H01']
        self.assertEqual([x['W'] for x in xs],[3,3]);self.assertEqual([x['D'] for x in xs],[2,3])
    def test_D_not_serial_request_count(self):
        xs=[x for x in calibrate080.calibration()['structures'] if x['problem']=='H01']
        self.assertEqual([x['serial_generator_calls'] for x in xs],[5,5])

if __name__=='__main__':unittest.main()
