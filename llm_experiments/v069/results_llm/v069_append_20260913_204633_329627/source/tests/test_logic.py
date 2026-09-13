"""무추론 시험. 과제·전달·채점·사전 gate와 검산 구현을 대조한다."""
import unittest,copy,ast,subprocess
from fixtures import *
class Logic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.plan=design.build_plan(baseline_path(),'v069_logic','synthetic')
    def test_frozen_54_calls(self):
        self.assertEqual(len(self.plan['slots']),54);self.assertEqual(len(self.plan['actions']),66)
        self.assertEqual(design._slots(common.spec()),verify._slot_schedule(common.spec()))
        self.assertEqual([sum(s['stage']==k for s in self.plan['slots']) for k in ('facts','rule','final')],[12,30,12])
    def test_reference_depths(self):
        for p in self.plan['protocol']['problems']:
            for i,ids in enumerate(ROUTES[p['id']]):
                self.assertEqual(reference.validate(p,ids),self.plan['protocol']['depth_ranges'][p['id']][i])
                self.assertEqual(verify._reference_depth(p,ids),reference.validate(p,ids))
    def test_same_model_options_and_fixed_problems(self):
        old=common.load(common.unzip(baseline_path().read_bytes())['plan.json'])
        records,files=records_for(self.plan)
        self.assertEqual(self.plan['identity'],old['identity'])
        self.assertEqual(self.plan['protocol']['problems'],old['protocol']['problems'])
        for slot in self.plan['slots']:
            q=common.load(files['wire/'+slot['id']+'/request.wire.json']);expected=deepcopy(old['baseline_request']['options']);expected['seed']=slot['seed'];self.assertEqual(q['options'],expected)
    def test_schemas_no_answer_enum(self):
        records,files=records_for(self.plan)
        for s in self.plan['slots']:
            q=common.load(files['wire/'+s['id']+'/request.wire.json']);fields=q['format']['properties']
            self.assertEqual(set(fields),{dict(facts='nodes',rule='node',final='final_node_id')[s['stage']]});self.assertNotIn('enum',str(fields))
    def test_invalid_raw_transferred_exactly(self):
        slot=next(s for s in self.plan['slots'] if s['stage']=='final');text=' {"nodes": [incorrect!] } \n  '
        raw=common.wire({'message':{'content':text}});history={sid:raw for sid in slot['history_ids']}
        q=design.request_for(self.plan,slot,history);actual=common.load(q['messages'][0]['content'].split('\n\nhistory: ')[1])
        self.assertEqual(len(actual),2)
        for item in actual:self.assertEqual(item['content'],text);self.assertEqual(item['response_sha256'],common.sha(raw))
    def test_all_history_preserved_not_only_last(self):
        slot=next(s for s in self.plan['slots'] if s['stage']=='final' and s['condition']=='reference_long');history={sid:common.wire({'message':{'content':sid+'\n'}}) for sid in slot['history_ids']}
        items=common.load(design.request_for(self.plan,slot,history)['messages'][0]['content'].split('\n\nhistory: ')[1])
        self.assertEqual([x['content'] for x in items],[sid+'\n' for sid in slot['history_ids']])
    def test_no_cross_trial_history(self):
        for s in self.plan['slots']:
            self.assertTrue(all(sid.startswith(s['trial_id']+'_') for sid in s['history_ids']))
            self.assertEqual(len(s['history_ids']),s['operation_index'])
    def test_missing_history_not_fabricated(self):
        slot=next(s for s in self.plan['slots'] if s['stage']=='rule')
        with self.assertRaises(ValueError):design.request_for(self.plan,slot,{})
    def test_raw_bad_outer_retained_as_null_content(self):
        slot=next(s for s in self.plan['slots'] if s['stage']=='rule');raw=b'not JSON';q=design.request_for(self.plan,slot,{sid:raw for sid in slot['history_ids']})
        item=common.load(q['messages'][0]['content'].split('\n\nhistory: ')[1])[0];self.assertIsNone(item['content']);self.assertEqual(item['response_sha256'],common.sha(raw))
    def test_full_synthetic_summaries_independent(self):
        modes=('perfect','fixed_short','reversed','extra_fact','missing_fact','all_in_facts','facts_extra_field','wrong_fact','duplicate_fact_id','bad_parent','bad_early_rule','wrong_atom','wrong_rule','duplicate_rule_id','rule_extra_field','self_cycle','stage_swap','cross_stage_smuggling','wrong_final','invalid_schema','parse_error','facts_parse_error','rule_parse_error','missing_usage','incomplete','over_budget')
        for mode in modes:
            with self.subTest(mode=mode):
                records,_=records_for(self.plan,mode);a=report.summarize(self.plan,records,'complete');b=verify._summary(self.plan,records,'complete')
                self.assertEqual(a,b);self.assertEqual(report.render(a),verify._render(b));self.assertIsNone(a['overall']['D_instruction_control'])
    def test_valid_graph_cannot_rescue_wrong_earlier_contract(self):
        records,_=records_for(self.plan,'cross_stage_smuggling');r=report.summarize(self.plan,records,'complete')
        ts=[t for t in r['trials'] if t['problem_id']=='E01_shared_fork' and t['condition']=='reference_long']
        self.assertEqual(len(ts),2)
        for t in ts:self.assertTrue(t['strict_valid']);self.assertTrue(t['reference_order_followed']);self.assertFalse(t['stage_contract_valid']);self.assertFalse(t['reconstruction_success'])
    def test_no_repair_of_bad_early_rule(self):
        records,_=records_for(self.plan,'bad_early_rule');r=report.summarize(self.plan,records,'complete');self.assertEqual(r['overall']['successes'],0)
        for t in r['trials']:self.assertFalse(t['stage_contract_valid'])
    def test_graph_assembly_preserves_object_values(self):
        slots=[s for s in self.plan['slots'] if s['trial_id']==self.plan['slots'][0]['trial_id']]
        payloads={s['id']:common.load(synthetic_value(self.plan,s)['message']['content']) for s in slots};before=deepcopy(payloads)
        graph=stages.assemble(slots,payloads)
        self.assertEqual(payloads,before);self.assertIs(graph['nodes'][-1],payloads[slots[1]['id']]['node'])
    def test_missing_results_null_not_zero(self):
        r=report.summarize(self.plan,[],'crashed');self.assertIsNone(r['overall']['positive_control_ready'])
        for t in r['trials']:self.assertIsNone(t['actual_D']);self.assertIsNone(t['reconstruction_success'])
    def test_gates_full_partial_zero_and_unmeasured(self):
        for mode,success,gate in [('perfect',12,True),('fixed_short',6,False),('wrong_final',0,False),('facts_parse_error',0,None)]:
            records,_=records_for(self.plan,mode);r=report.summarize(self.plan,records,'complete');self.assertEqual(r['overall']['successes'],success);self.assertIs(r['overall']['positive_control_ready'],gate)
    def test_prior_results_not_rewritten(self):
        records,_=records_for(self.plan);r=report.summarize(self.plan,records,'complete')
        self.assertEqual((r['overall']['v068_direct_successes_unchanged'],r['overall']['v068_staged_successes_unchanged']),(4,8))
    def test_long_short_order_balanced(self):
        for pi in range(3):
            first=[next(s['condition'] for s in self.plan['slots'] if s['block']==pi*2+si) for si in range(2)]
            self.assertEqual(set(first),{'reference_short','reference_long'})
    def test_semantics_independent_perturbations(self):
        count=0
        for p in self.plan['protocol']['problems']:
            for long in (False,True):
                g=proof(p,long);variants=[g]
                for idx in range(len(g['nodes'])):
                    for change in ('wrong_atom','missing_parent','self_cycle','extra_parent','wrong_rule','duplicate'):
                        q=deepcopy(g);n=q['nodes'][idx]
                        if change=='wrong_atom':n['atom']='invalid'
                        if change=='missing_parent':n['parents']=['absent']
                        if change=='self_cycle':n['parents']=[n['id']]
                        if change=='extra_parent':n['parents']+=n['parents'] or ['absent']
                        if change=='wrong_rule':n['rule']='not_a_rule'
                        if change=='duplicate':q['nodes'].append(deepcopy(n))
                        variants.append(q)
                for q in variants:self.assertEqual(measure.assess(p,q),verify._semantic(p,q));count+=1
        self.assertGreaterEqual(count,150)
    def test_independent_import_boundary(self):
        tree=ast.parse((ROOT/'verify.py').read_text(encoding='utf-8'));names=[]
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):names += [x.name for x in node.names]
            elif isinstance(node,ast.ImportFrom):names.append(node.module)
        self.assertFalse(set(names)&{'measure','report','design','run','stages'})
    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(ValueError):common.load('{"a":1,"a":2}')
    def test_nan_rejected(self):
        for s in ('{"a":NaN}','{"a":1e999}'):
            with self.assertRaises(ValueError):common.load(s)
    def test_unsafe_archive_path_rejected(self):
        for name in ('../x','/x','a\\b','CON.txt','x:y','foo/../bar'):
            with self.assertRaises(ValueError):common.safe_name(name)
    def test_endpoint_loopback_only(self):
        for endpoint in ('https://127.0.0.1:11434','http://example.com','http://user@127.0.0.1','http://127.0.0.1/?x'):
            with self.assertRaises(ValueError):run.endpoint_ok(endpoint)
    def test_request_budget_not_silently_truncated(self):
        slot=next(s for s in self.plan['slots'] if s['stage']=='rule');raw=common.wire({'message':{'content':'x'*40000}})
        with self.assertRaisesRegex(ValueError,'request byte limit'):design.request_for(self.plan,slot,{sid:raw for sid in slot['history_ids']})
    def test_combined_schema_overflow_is_unmeasured(self):
        records,_=records_for(self.plan)
        for r in records:
            slot=next(s for s in self.plan['slots'] if s['id']==r['id'])
            if slot['stage']!='facts':continue
            env=common.load(base64.b64decode(r['response_b64']));nodes=[{'id':'x'+str(i),'atom':self.plan['protocol']['problems'][0]['facts'][0],'rule':None,'parents':[]} for i in range(16)]
            env['message']['content']=common.wire({'nodes':nodes}).decode();raw=common.wire(env);r['response_sha256']=common.sha(raw);r['response_b64']=base64.b64encode(raw).decode()
        a=report.summarize(self.plan,records,'complete');self.assertEqual(a,verify._summary(self.plan,records,'complete'))
        self.assertEqual(a['overall']['unmeasured'],12);self.assertIsNone(a['overall']['positive_control_ready'])
    def test_prepare_reports_actual_fiftyfour_calls(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'plan.json';proc=subprocess.run([sys.executable,'-X','utf8','-B',str(ROOT/'run.py'),'prepare','--baseline',str(baseline_path()),'--run-name','v069_prepare_test','--out',str(p),'--synthetic'],cwd=ROOT,capture_output=True,timeout=60)
            self.assertEqual(proc.returncode,0,proc.stderr.decode('utf-8',errors='replace'))
            value=common.load(proc.stdout);self.assertEqual(value['max_inference_calls_when_executed'],54);self.assertFalse(value['new_model_inference'])
