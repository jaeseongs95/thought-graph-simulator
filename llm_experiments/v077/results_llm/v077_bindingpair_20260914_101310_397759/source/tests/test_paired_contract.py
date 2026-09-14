"""v077 대응표 계약·내용 투영·무보정·전버전 의미 회귀 시험."""
import ast, copy, collections, json, random, unittest
from fixtures import plan, memory_run, input_of, baseline_path, ROOT
import common, design, report, audit_model, bindings, audit_bindings

class PairedContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p=plan();cls.records,cls.raw,cls.synth=memory_run(cls.p)
        cls.summary=report.summarize(cls.p,cls.records,cls.raw,'complete')
        cls.baseline=common.unzip(baseline_path().read_bytes())
    def twins(self):
        for uid in sorted({t['unit_id'] for t in self.p['trials']}):
            yield [next(t for t in self.p['trials'] if t['unit_id']==uid and t['variant']==v) for v in ('base','premise_binding')]
    def slots(self,t):return [s for s in self.p['slots'] if s['trial_id']==t['id'] and s['stage']!='select']
    def test_initial_requests_identical(self):
        for a,b in self.twins():
            self.assertEqual(design.request_for(self.p,self.slots(a)[0],self.raw),design.request_for(self.p,self.slots(b)[0],self.raw))
    def test_node_schema_is_not_parent_count_restriction(self):
        for t in self.p['trials']:
            for s in self.slots(t):
                if s['stage']!='rule' or design.disposition(self.p,s,self.raw):continue
                req=design.request_for(self.p,s,self.raw)
                self.assertEqual(req['format']['properties']['node'],self.p['protocol']['generation_schema']['properties']['nodes']['items'])
                if t['variant']=='premise_binding':
                    bs=req['format']['properties']['bindings']
                    self.assertEqual(bs,self.p['protocol']['binding_schema'])
                    self.assertEqual((bs['minItems'],bs['maxItems']),(0,16))
                    self.assertNotIn('enum',str(bs));self.assertNotIn('const',str(bs))
    def test_shared_prefix_only_binding_contract_differs(self):
        # 양 군에 똑같은 이전 content를 넣은 가상 대조. 실제 원문을 수정하지 않는다.
        for a,b in self.twins():
            mapped=dict(self.raw)
            for sa,sb in zip(self.slots(a),self.slots(b)):
                if sa['id'] in self.raw:mapped[sb['id']]=self.raw[sa['id']]
            for sa,sb in zip(self.slots(a),self.slots(b)):
                if design.disposition(self.p,sa,mapped):continue
                left=design.request_for(self.p,sa,mapped);right=design.request_for(self.p,sb,mapped)
                self.assertEqual(input_of(left),input_of(right))
                if sa['stage']=='rule':
                    expected=copy.deepcopy(left['format'])
                    expected['properties']={'bindings':copy.deepcopy(self.p['protocol']['binding_schema']),**expected['properties']}
                    expected['required']=['bindings','node']
                    self.assertEqual(right['format'],expected)
                    right['messages'][0]['content']=right['messages'][0]['content'].replace('\n\n'+self.p['protocol']['headers']['binding_rule'],'',1).replace(common.wire(expected).decode(),common.wire(left['format']).decode(),1)
                    right['format']=left['format']
                self.assertEqual(left,right)
    def test_content_preserved_and_hashes_outside_prompt(self):
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
    def test_bad_binding_is_forwarded_not_replaced(self):
        r,w,_=memory_run(self.p,'binding_lie')
        seen=0
        for t in self.p['trials']:
            if t['variant']!='premise_binding':continue
            for s in self.slots(t):
                if design.disposition(self.p,s,w):continue
                d=input_of(design.request_for(self.p,s,w))
                for h in d['history']:
                    if 'invented_premise' in h['content']:seen+=1
        self.assertGreater(seen,0)
    def test_envelope_changes_do_not_change_request(self):
        changed={}
        for i,(sid,raw) in enumerate(self.raw.items()):
            outer=common.load(raw);outer.update(created_at=str(i),eval_duration=999+i,total_duration=99999+i)
            changed[sid]=common.wire(outer)
        for s in self.p['slots']:
            if design.disposition(self.p,s,self.raw):continue
            self.assertEqual(design.request_for(self.p,s,self.raw),design.request_for(self.p,s,changed))
    def test_content_whitespace_is_not_normalized(self):
        s=next(s for s in self.p['slots'] if s['stage']=='facts')
        nxt=next(x for x in self.p['slots'] if x['trial_id']==s['trial_id'] and x['stage']=='rule')
        w=dict(self.raw);obj=common.load(w[s['id']]);obj['message']['content']='\n '+obj['message']['content']+' \n';w[s['id']]=common.wire(obj)
        d=input_of(design.request_for(self.p,nxt,w));self.assertEqual(d['history'][0]['content'],obj['message']['content'])
    def test_balanced_arm_order(self):
        groups=collections.defaultdict(list)
        for t in self.p['trials']:groups[t['unit_id']].append(t)
        for arm,n in [('model',12),('reference',6)]:
            self.assertEqual(collections.Counter(v[0]['variant'] for v in groups.values() if v[0]['arm']==arm),{'base':n,'premise_binding':n})
    def test_gain_and_harm_patterns_both_preserved(self):
        for mode,winner in [('binding_sensitive','premise_binding'),('binding_harms','base')]:
            r,w,_=memory_run(self.p,mode);s=report.summarize(self.p,r,w,'complete')
            self.assertEqual(s['paired_effects']['model_trace'][winner+'_only'],24)
    def test_graph_valid_but_binding_wrong_is_not_contract_success(self):
        r,w,_=memory_run(self.p,'binding_lie');s=report.summarize(self.p,r,w,'complete');a=s['arms']['premise_binding']
        self.assertEqual(a['model_target_structure']['successes'],24)
        self.assertEqual(a['model_graph_only_trace']['successes'],24)
        self.assertEqual(a['model_trace']['failures'],24)
        self.assertEqual(a['graph_valid_binding_failed'],36)
        self.assertEqual(s['arms']['base']['model_trace']['successes'],24)
    def test_correct_table_does_not_repair_wrong_node(self):
        r,w,_=memory_run(self.p,'bad_parent');s=report.summarize(self.p,r,w,'complete')
        for row in s['trials']:
            if row['variant']=='premise_binding' and row['arm']=='model':
                self.assertFalse(row['generator_success']);self.assertIn('absent',str(row['graph']))
                self.assertTrue(any('binding_node_parents_disagree' in (x['error_codes'] or []) for x in row['binding_checks']))
    def test_self_consistent_wrong_parent_is_rejected(self):
        r,w,_=memory_run(self.p,'binding_self_consistent_wrong');s=report.summarize(self.p,r,w,'complete')
        a=s['arms']['premise_binding'];self.assertGreater(a['binding_steps']['failures'],0);self.assertLess(a['model_trace']['successes'],24)
    def test_missing_duplicate_or_future_binding_not_success(self):
        for mode in ['binding_missing','binding_duplicate','binding_wrong_existing','binding_forward_parent']:
            r,w,_=memory_run(self.p,mode);s=report.summarize(self.p,r,w,'complete')
            self.assertGreater(s['arms']['premise_binding']['binding_steps']['failures'],0,mode)
    def test_binding_schema_failure_not_zero_depth(self):
        for mode in ['binding_malformed','binding_absent']:
            r,w,_=memory_run(self.p,mode);s=report.summarize(self.p,r,w,'complete')
            self.assertIsNone(s['end_to_end_baseline_ready'])
            self.assertEqual(s['arms']['premise_binding']['model_trace']['unmeasured'],24)
            self.assertTrue(all(x['graph_metric']['strict_valid'] is True for x in s['trials'] if x['variant']=='premise_binding'))
            self.assertEqual(s['arms']['premise_binding']['model_graph_only_trace']['successes'],24)
    def test_selection_ceiling_unchanged(self):
        r,w,_=memory_run(self.p,'always_short');s=report.summarize(self.p,r,w,'complete')
        self.assertEqual(s['selection_trace_ceiling']['successful_trials'],12)
        for a in s['arms'].values():
            self.assertEqual(a['model_generator_fidelity']['successes'],24);self.assertEqual(a['model_trace']['successes'],12)
    def test_v076_selector_requests_identical(self):
        for s in self.p['slots']:
            if s['stage']=='select':self.assertEqual(common.wire(design.request_for(self.p,s,{})),self.baseline['wire/'+s['id']+'/request.wire.json'])
    def test_v076_base_request_bytes_identical_for_same_history(self):
        w={n.split('/')[1]:raw for n,raw in self.baseline.items() if n.startswith('wire/') and n.endswith('/response.raw.json')}
        for t in self.p['trials']:
            if t['variant']!='base':continue
            for s in self.slots(t):
                if design.disposition(self.p,s,w):continue
                self.assertEqual(common.wire(design.request_for(self.p,s,w)),self.baseline['wire/'+s['id']+'/request.wire.json'])
    def test_v076_base_semantics_replayed_without_binding_invention(self):
        records={};w={}
        for s in self.p['slots']:
            old=s['id'].replace('_premise_binding_','_base_')
            r=common.load(self.baseline['records/'+old+'.json']);r['id']=s['id'];records[s['id']]=r
            if r['kind']=='call':w[s['id']]=self.baseline['wire/'+old+'/response.raw.json']
        a=report.summarize(self.p,records,w,'complete');b=audit_model.independent_summary(self.p,records,w,'complete')
        self.assertTrue(common.exact(a,b));x=a['arms']['base']
        self.assertEqual((x['model_trace']['successes'],x['model_pairs']['successes'],x['reference_construction']['successes']),(14,2,10))
        self.assertEqual(a['arms']['premise_binding']['model_trace']['unmeasured'],24)
    def test_frozen_v076_scores_match_source_bundle(self):
        prior=common.load(self.baseline['summary.json']);frozen=self.p['protocol']['v076_frozen']
        for variant in ('base','parent_count'):
            row=prior['arms'][variant];f=frozen[variant]
            self.assertEqual(f['model_trace'],row['model_trace']['successes'])
            self.assertEqual(f['reference'],row['reference_construction']['successes'])
            self.assertEqual(f['model_pairs'],row['model_pairs']['successes'])
            self.assertEqual(f['valid_rule_steps'],row['rule_semantic_steps']['successes'])
        self.assertNotIn('parent_count_schema_contract',self.p['protocol'])
    def test_previous_bad_table_does_not_hide_later_measurable_binding(self):
        # 앞 표만 형식 오류이고 node는 정상이면 뒤 표의 직접 대응은 측정 가능하다.
        row=next(r for r in self.summary['trials'] if r['variant']=='premise_binding' and len(r['selected_rule_ids'])>2)
        t=next(t for t in self.p['trials'] if t['id']==row['trial_id']);p=design.problem_for(self.p,t)
        seq=[dict(s,requested_rule_id=row['selected_rule_ids'][s['rule_position']] if s['stage']=='rule' else None) for s in self.slots(t) if not design.disposition(self.p,s,self.raw)]
        objs={s['id']:common.load(design.raw_content(self.raw[s['id']])) for s in seq};stat={s['id']:'ok' for s in seq};table=dict(stat)
        first=seq[1]['id'];objs[first]['bindings']='bad';table[first]='invalid_schema'
        a=bindings.audit(p,seq,objs,set(stat),{k for k,v in table.items() if v=='ok'});b=audit_bindings.inspect(p,seq,objs,stat,table)
        self.assertEqual(a,b);self.assertIsNone(a[0]['valid']);self.assertTrue(all(c['valid'] is True for c in a[1:]))
    def test_projection_keeps_node_unchanged(self):
        for sid,raw in self.raw.items():
            obj=common.load(design.raw_content(raw))
            if 'bindings' in obj:
                node=copy.deepcopy(obj['node']);bs=copy.deepcopy(obj['bindings']);p=bindings.node_payload(obj)
                self.assertEqual(p,{'node':node});self.assertEqual(obj['bindings'],bs)
    def test_partial_not_filled_with_zero(self):
        r,w,_=memory_run(self.p,limit=7);s=report.summarize(self.p,r,w,'crashed')
        self.assertIsNone(s['end_to_end_baseline_ready']);self.assertTrue(any(x['valid'] is None for row in s['trials'] for x in row['binding_checks']))
    def test_all_new_patterns_independently_recomputed(self):
        modes=['binding_sensitive','binding_harms','binding_lie','binding_missing','binding_duplicate','binding_wrong_existing','binding_self_consistent_wrong','binding_forward_parent','binding_malformed','binding_absent','correct_count_wrong_identity','duplicate_parent_for_Ab']
        for mode in modes:
            r,w,_=memory_run(self.p,mode)
            for state in ('complete','crashed'):
                a=report.summarize(self.p,r,w,state);b=audit_model.independent_summary(self.p,r,w,state)
                self.assertTrue(common.exact(a,b),mode);self.assertEqual(report.render(a),audit_model.independent_report(b),mode)
    def test_independent_binding_module_has_no_production_imports(self):
        bad={'bindings','stages','report','design','measure','run','common'}
        for fn in ('audit_bindings.py','audit_model.py','verify.py'):
            for n in ast.walk(ast.parse((ROOT/fn).read_text())):
                if isinstance(n,ast.Import):self.assertFalse({a.name.split('.')[0] for a in n.names}&bad)
                elif isinstance(n,ast.ImportFrom):self.assertNotIn((n.module or '').split('.')[0],bad)
    def test_binding_differential_240_cases(self):
        rows=[r for r in self.summary['trials'] if r['variant']=='premise_binding']
        rng=random.Random(77001)
        for i in range(240):
            row=rng.choice(rows);t=next(t for t in self.p['trials'] if t['id']==row['trial_id']);p=design.problem_for(self.p,t)
            seq=[dict(s,requested_rule_id=row['selected_rule_ids'][s['rule_position']] if s['stage']=='rule' else None) for s in self.slots(t) if not design.disposition(self.p,s,self.raw)]
            objs={s['id']:common.load(design.raw_content(self.raw[s['id']])) for s in seq};status={s['id']:'ok' for s in seq}
            action=rng.choice([s for s in seq if s['stage']=='rule']);x=objs[action['id']];k=i%8
            if k==1:x['bindings'][0]['premise']='wrong'
            elif k==2:x['bindings'][0]['parent_id']='absent'
            elif k==3:x['node']['parents']=[]
            elif k==4:x['bindings']=[]
            elif k==5:x['bindings'].append(copy.deepcopy(x['bindings'][0]))
            elif k==6:status[seq[0]['id']]='invalid_schema'
            elif k==7:x['bindings'].reverse()
            ready={s for s,v in status.items() if v=='ok'}
            self.assertEqual(bindings.audit(p,seq,objs,ready),audit_bindings.inspect(p,seq,objs,status),i)

if __name__=='__main__':unittest.main()
