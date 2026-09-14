"""v079 개입 경계·짝비교·원요청 호환성 시험. 실제 LLM 호출 없음."""
import copy, json, unittest, zipfile
from collections import Counter
from fixtures import ROOT, plan, baseline_path, memory_run, input_of
import common, design, report, audit_model

class ExplicitRule(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p=plan();cls.recs,cls.raw,cls.synth=memory_run(cls.p)
        cls.summary=report.summarize(cls.p,cls.recs,cls.raw,'complete')
    def test_only_rule_input_field_changes_for_equal_histories(self):
        paired=0
        for slot in self.p['slots']:
            t=next(t for t in self.p['trials'] if t['id']==slot['trial_id'])
            if t['variant']!='base' or slot['stage']=='select' or design.disposition(self.p,slot,self.raw):continue
            other=next(s for s in self.p['slots'] if s['logical_id']==slot['logical_id'] and s['id']!=slot['id'])
            a=design.request_for(self.p,slot,self.raw);b=design.request_for(self.p,other,self.raw)
            data=input_of(b)
            if slot['stage']=='rule':
                current=data['operation'].pop('requested_rule')
                self.assertEqual(current,next(r for r in data['problem']['rules'] if r['id']==data['operation']['requested_rule_id']))
                self.assertEqual(set(current),{'id','premises','conclusion'})
            else:self.assertNotIn('requested_rule',data['operation'])
            b['messages'][0]['content']=b['messages'][0]['content'].split('\n\ninput: ',1)[0]+'\n\ninput: '+common.wire(data).decode()
            self.assertEqual(common.wire(a),common.wire(b));paired+=1
        self.assertEqual(paired,276)
    def test_original_v078_base_requests_replayed_byte_for_byte(self):
        with zipfile.ZipFile(baseline_path()) as z:
            raw={n.split('/')[1]:z.read(n) for n in z.namelist() if n.startswith('wire/') and n.endswith('/response.raw.json')}
            count=0
            for slot in self.p['slots']:
                name='wire/'+slot['id']+'/request.wire.json'
                if name in z.namelist():
                    self.assertEqual(common.wire(design.request_for(self.p,slot,raw)),z.read(name),slot['id']);count+=1
        self.assertEqual(count,306)
    def test_one_shared_selection_per_unit(self):
        selects=[s for s in self.p['slots'] if s['stage']=='select']
        self.assertEqual(len(selects),32)
        for s in selects:
            ts=[t for t in self.p['trials'] if t['selection_slot_id']==s['id']]
            self.assertEqual({t['variant'] for t in ts},{'base','explicit_rule'})
            values=[design.source_for(self.p,t,self.raw) for t in ts]
            self.assertEqual(values[0],values[1])
    def test_counterbalanced_generator_execution_order(self):
        first={}
        for t in self.p['trials']:first.setdefault(t['unit_id'],t['variant'])
        self.assertEqual(Counter(first.values()),{'base':24,'explicit_rule':24})
    def test_scores_use_same_graph_contract(self):
        for t in self.summary['trials']:
            self.assertIs(t['generator_success'],t['graph_only_generator_success'])
            self.assertIs(t['trace_success'],t['graph_only_trace_success'])
    def test_ideal_counts_are_not_doubled_selections(self):
        self.assertEqual(self.summary['shared_model_selection']['successes'],32)
        self.assertEqual(self.summary['shared_selection_pairs']['successes'],16)
        for a in self.summary['arms'].values():
            self.assertEqual(a['model_trace']['successes'],32)
            self.assertEqual(a['model_pairs']['successes'],16)
            self.assertEqual(a['reference_construction']['successes'],16)
    def test_treatment_improvement_and_regression_are_not_hidden(self):
        for mode,winner,loser,sign in [('explicit_rule_better','explicit_rule','base',1),('explicit_rule_worse','base','explicit_rule',-1)]:
            r,raw,_=memory_run(self.p,mode);s=report.summarize(self.p,r,raw,'complete')
            self.assertEqual(s['arms'][winner]['model_trace']['successes'],32)
            self.assertEqual(s['arms'][loser]['model_trace']['successes'],0)
            for name,n in [('model_generator_fidelity',32),('model_trace',32),('reference_construction',16),('model_pairs',16)]:
                c=s['paired_comparisons'][name];self.assertEqual(c['net_success_change'],sign*n)
                self.assertEqual(c['unmeasured'],0)
            self.assertTrue(common.exact(s,audit_model.independent_summary(self.p,r,raw,'complete')))
    def test_unmeasured_counterpart_is_not_treatment_win(self):
        rows=copy.deepcopy(self.summary['trials'])
        r=next(r for r in rows if r['variant']=='base' and r['arm']=='model')
        r['generator_success']=None;r['trace_success']=None
        s=report.aggregate(rows,'crashed',self.p['protocol'])
        for name in ['model_generator_fidelity','model_trace','model_pairs']:
            self.assertEqual(s['paired_comparisons'][name]['unmeasured'],1)
            self.assertEqual(s['paired_comparisons'][name]['explicit_rule_only'],0)
        self.assertTrue(common.exact(s,audit_model.independent_aggregate(rows,'crashed',self.p['protocol'])))
    def test_reverse_valid_graph_pair_not_promoted(self):
        r,raw,_=memory_run(self.p,'reverse_direction');s=report.summarize(self.p,r,raw,'complete')
        self.assertEqual(s['shared_selection_patterns'],{'reversed':16})
        for a in s['arms'].values():
            self.assertEqual(a['model_generator_fidelity']['successes'],32)
            self.assertEqual(a['model_trace']['successes'],0)
            self.assertEqual(a['model_pairs']['successes'],0)
            self.assertEqual(a['valid_graph_pair_directions'],{'reversed':16})
    def test_treatment_cannot_correct_wrong_selection(self):
        r,raw,_=memory_run(self.p,'always_first');s=report.summarize(self.p,r,raw,'complete')
        for a in s['arms'].values():
            self.assertEqual(a['model_generator_fidelity']['successes'],32)
            self.assertEqual(a['model_trace']['successes'],16)
            self.assertEqual(a['model_pairs']['successes'],0)
    def test_usage_grouping_no_double_count(self):
        groups=self.summary['usage_by_group']
        self.assertEqual({k:v['observed_calls'] for k,v in groups.items()},{'shared_selection':32,'base':276,'explicit_rule':276})
        for key,metric in self.summary['usage'].items():
            for field in ('observed_sum','missing_records'):
                self.assertEqual(metric[field],sum(g['fields'][key][field] for g in groups.values()))
    def test_missing_usage_retains_missing_counts_by_arm(self):
        r,raw,_=memory_run(self.p,'missing_usage');s=report.summarize(self.p,r,raw,'complete')
        for group in s['usage_by_group'].values():
            self.assertEqual(group['fields']['eval_count']['missing_records'],group['observed_calls'])
    def test_request_builder_never_calls_graph_solver(self):
        from unittest.mock import patch
        import measure,preflight
        with patch.object(measure,'assess',side_effect=AssertionError('solver used')),patch.object(measure,'depth_ranges',side_effect=AssertionError('D answer used')),patch.object(preflight,'candidate_graph',side_effect=AssertionError('oracle used')):
            for slot in self.p['slots']:
                if not design.disposition(self.p,slot,self.raw):design.request_for(self.p,slot,self.raw)
    def test_wrong_history_in_explicit_arm_not_repaired(self):
        r,raw,_=memory_run(self.p,'wrong_existing_parent')
        for slot in self.p['slots']:
            if slot['stage']!='final' or design.disposition(self.p,slot,raw):continue
            t=next(t for t in self.p['trials'] if t['id']==slot['trial_id'])
            if t['variant']!='explicit_rule':continue
            d=input_of(design.request_for(self.p,slot,raw))
            for prev in d['history']:
                sid=next(s['id'] for s in self.p['slots'] if s['trial_id']==t['id'] and s['logical_id']==prev['source_slot_id'])
                self.assertEqual(prev['content'],design.raw_content(raw[sid]))
    def test_bad_shared_selection_disagreement_rejected(self):
        rows=copy.deepcopy(self.summary['trials'])
        r=next(r for r in rows if r['variant']=='explicit_rule' and r['arm']=='model')
        r['selected_candidate_id']='tampered'
        for fn in (report.aggregate,audit_model.independent_aggregate):
            with self.assertRaises(ValueError):fn(rows,'complete',self.p['protocol'])
    def test_no_automatic_followup_decision(self):
        for mode in ('correct','explicit_rule_worse','always_first'):
            r,raw,_=memory_run(self.p,mode);s=report.summarize(self.p,r,raw,'complete')
            self.assertEqual(s['decision'],'close_frozen_generator_diagnostic')

    def test_synthetic_cli_never_invokes_server(self):
        import tempfile,contextlib,io
        from pathlib import Path
        from unittest.mock import patch
        import run
        with tempfile.TemporaryDirectory() as td:
            planfile=Path(td)/'plan.json';common.save(planfile,self.p)
            with patch.object(run,'exchange',side_effect=AssertionError('network forbidden')),contextlib.redirect_stderr(io.StringIO()):
                code=run.main(['execute','--plan',str(planfile),'--baseline',str(baseline_path()),'--out',str(Path(td)/'result')])
            self.assertEqual(code,2);self.assertFalse((Path(td)/'result').exists())

if __name__=='__main__':unittest.main()
