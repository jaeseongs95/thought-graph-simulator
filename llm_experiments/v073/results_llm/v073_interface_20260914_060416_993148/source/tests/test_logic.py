"""첫 실행 전 오프라인 사전 검사. 네트워크/실제 모델 호출 없음."""
import ast,random,unittest
from collections import Counter
from fixtures import *

class Logic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.plan=design.build_plan(baseline_path(),'v073_logic','synthetic')
    def test_64_calls_96_actions_no_history(self):
        self.assertEqual(len(self.plan['slots']),64);self.assertEqual(len(self.plan['actions']),96)
        self.assertTrue(all(not s['history_ids'] for s in self.plan['slots']))
        self.assertEqual(design._slots(common.spec()),verify._slot_schedule(common.spec()))
    def test_full_factorial_and_no_duplicate_numeric_pairs(self):
        s=self.plan['slots'];self.assertEqual(len({(x['numeric_pair_id'],x['seed'],x['candidate_order_index'],x['format'],x['condition']) for x in s}),64)
        self.assertEqual(len({tuple(p['values']) for p in common.spec()['numeric_pairs']}),4)
    def test_period_counterbalance(self):
        counts=Counter((s['period'],s['format'],s['condition']) for s in self.plan['slots'])
        self.assertEqual(set(counts.values()),{4})
        for pi in range(4):
            for oi in range(2):
                seq=[[s['format']+'/'+s['condition'] for s in self.plan['slots'] if s['block']==pi*4+si*2+oi] for si in (0,1)]
                self.assertEqual(seq[0],seq[1][::-1])
    def test_only_one_space_differs_in_32_request_pairs(self):
        for b in range(16):
            for cond in ['shallow','deep']:
                ss=[s for s in self.plan['slots'] if s['block']==b and s['condition']==cond]
                qs={s['format']:design.request_for(self.plan,s) for s in ss}
                c,s=qs['compact'],qs['comma_space']
                ct,st=c['messages'][0]['content'],s['messages'][0]['content']
                pre,tail=st.split('\n\ninput: ');data=common.load(tail)
                self.assertIn(', ',data['depth_report']);data['depth_report']=data['depth_report'].replace(', ', ',')
                s['messages'][0]['content']=pre+'\n\ninput: '+common.wire(data).decode()
                self.assertEqual(c,s);self.assertEqual(len(st.encode())-len(ct.encode()),1)
    def test_32_compact_requests_match_archived_numeric_control(self):
        files,old,_,_=previous.inspect_prior(baseline_path().read_bytes());count=0
        archived=[common.load(data) for n,data in files.items() if n.startswith('wire/') and '_oracle_depth_' in n and n.endswith('/request.wire.json')]
        for slot in self.plan['slots']:
            if slot['format']=='compact':
                self.assertIn(design.request_for(self.plan,slot),archived);count+=1
        self.assertEqual(count,32)
    def test_schema_and_nonmessage_options_unchanged(self):
        for s in self.plan['slots']:
            q=design.request_for(self.plan,s);q['messages']=self.plan['baseline_request']['messages'];q['options']['seed']=self.plan['baseline_request']['options']['seed']
            self.assertEqual(q,self.plan['baseline_request'])
    def test_unknown_history_refused(self):
        with self.assertRaises(ValueError):design.request_for(self.plan,self.plan['slots'][0],{'fake':b'{}'})
    def compare(self,mode,state='complete',n=None):
        records,_=records_for(self.plan,mode)
        if n is not None:records=records[:n]
        a=report.summarize(self.plan,records,state);b=verify._summary(self.plan,records,state)
        self.assertEqual(a,b,mode);self.assertEqual(report.render(a),verify._render(b));return a
    def test_synthetic_patterns_independent_50_comparisons(self):
        modes=['perfect','first','last','wrong','only_space','only_compact','ascending_only','bool_choice','float_choice','out_of_range','negative','extra_field','parse_error','duplicate_json','nonfinite','array','whitespace','missing_content','wrong_model','over_budget','length','not_done','missing_usage','bool_usage','tool_calls']
        self.assertEqual(len(modes),25)
        for mode in modes:
            for state in ('complete','crashed'):
                with self.subTest(mode=mode,state=state):self.compare(mode,state)
    def test_randomized_256_response_patterns(self):
        rng=random.Random(7337);base,_=records_for(self.plan)
        for case in range(256):
            records=deepcopy(base)
            for rec in records:
                env=common.load(base64.b64decode(rec['response_b64']));env['message']['content']=common.wire({'candidate_index':rng.randrange(2)}).decode()
                raw=common.wire(env);rec.update(response_b64=base64.b64encode(raw).decode(),response_sha256=common.sha(raw))
            if case%8==0:records=records[:case%65]
            a=report.summarize(self.plan,records,'complete' if len(records)==64 else 'crashed')
            b=verify._summary(self.plan,records,'complete' if len(records)==64 else 'crashed')
            self.assertEqual(a,b);self.assertEqual(report.render(a),verify._render(b))
    def test_both_formats_qualified_priority_is_prespecified(self):
        r=self.compare('perfect');self.assertTrue(r['overall']['interface_ready']);self.assertEqual(r['overall']['preferred_format_for_new_contract'],'compact')
        self.assertEqual(r['overall']['pairs']['successes'],32);self.assertIsNone(r['overall']['end_to_end_graph_D_control'])
    def test_space_only_is_not_global_robustness(self):
        r=self.compare('only_space');self.assertEqual(r['overall']['qualified_formats'],['comma_space']);self.assertFalse(r['overall']['robust_across_two_tested_formats'])
        self.assertEqual(r['contrast_counts']['spaced_only'],16)
    def test_both_fail_closes_contract(self):
        r=self.compare('first');self.assertEqual(r['overall']['selection']['successes'],32);self.assertEqual(r['overall']['pairs']['successes'],0)
        self.assertFalse(r['overall']['interface_ready']);self.assertEqual(r['overall']['next_decision'],'no_interface_qualified_close_diagnostic_branch')
    def test_malformed_is_unmeasured_not_wrong(self):
        r=self.compare('parse_error');self.assertIsNone(r['overall']['interface_ready']);self.assertEqual(r['overall']['unmeasured_calls'],64)
    def test_partial_does_not_qualify(self):
        r=self.compare('perfect','crashed',7);self.assertIsNone(r['overall']['interface_ready']);self.assertEqual(r['overall']['selection']['measured'],7)
    def test_missing_usage_is_null(self):
        r=self.compare('missing_usage');self.assertIsNone(r['usage']['eval_count']);self.assertTrue(r['overall']['interface_ready'])
    def test_input_values_not_model_depth_estimation(self):
        r=self.compare('perfect');self.assertFalse(r['limits']['depth_estimation_executed']);self.assertFalse(r['limits']['constructor_executed']);self.assertEqual(r['v072_frozen_result']['model_pipeline_correct'],4)
    def test_invalid_json_bytes_and_duplicate_keys(self):
        for raw in [b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":1e999}',b'\xff']:
            with self.subTest(raw=raw),self.assertRaises((ValueError,UnicodeError)):common.load(raw)
    def test_unsafe_paths(self):
        for path in ['../escape','/absolute','a\\b','CON','NUL.txt','a:bad','a/../b','a//b']:
            with self.subTest(path=path),self.assertRaises(ValueError):common.safe_name(path)
    def test_no_production_imports_in_verifier(self):
        tree=ast.parse((ROOT/'verify.py').read_text())
        names=[]
        for n in ast.walk(tree):
            if isinstance(n,ast.Import):names.extend(a.name for a in n.names)
            elif isinstance(n,ast.ImportFrom):names.append(n.module)
        self.assertFalse({'report','run','design','measure'}&set(names))
    def test_source_snapshot_includes_ledger_and_frozen_results(self):
        self.assertIn('docs/PLAN_LEDGER.ko.md',common.sources());self.assertIn('docs/V072_FROZEN.ko.md',common.sources())
    def test_endpoint_loopback_only(self):
        for url in ['https://localhost:11434','http://example.com','http://user@localhost:11434','http://127.0.0.1:11434/path']:
            with self.assertRaises(ValueError):run.endpoint_ok(url)
