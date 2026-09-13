import unittest,copy,ast
from fixtures import *
class Logic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.plan=design.build_plan(baseline_path(),'v068_logic','synthetic')
    def test_frozen_36_calls(self):
        self.assertEqual(len(self.plan['slots']),36);self.assertEqual(len(self.plan['actions']),48)
        self.assertEqual(design._slots(common.spec()),verify._slot_schedule(common.spec()))
    def test_reference_depths(self):
        for p in self.plan['protocol']['problems']:
            for i,ids in enumerate(ROUTES[p['id']]):
                self.assertEqual(reference.validate(p,ids),self.plan['protocol']['depth_ranges'][p['id']][i])
                self.assertEqual(verify._reference_depth(p,ids),reference.validate(p,ids))
    def test_direct_byte_identical_to_actual_v067_requests(self):
        f=common.unzip(baseline_path().read_bytes())
        for s in self.plan['slots']:
            if s['stage']=='direct':self.assertEqual(common.wire(design.request_for(self.plan,s)),f['wire/'+s['id'].removesuffix('_direct')+'/request.wire.json'])
    def test_nodes_and_final_schemas(self):
        records,files=records_for(self.plan)
        for s in self.plan['slots']:
            req=common.load(verify._request_for(self.plan,s,files));fields=req['format']['properties']
            self.assertEqual(set(fields),{'nodes'} if s['stage']=='nodes' else {'final_node_id'} if s['stage']=='final' else {'nodes','final_node_id'})
            self.assertNotIn('enum',str(fields))
    def test_invalid_raw_transferred_exactly(self):
        slot=next(s for s in self.plan['slots'] if s['stage']=='final');text=' {"nodes": [incorrect!] } \n  '
        raw=common.wire({'message':{'content':text}});q=design.request_for(self.plan,slot,raw)
        transfer=common.load(q['messages'][0]['content'].split('\n\nnodes_response: ')[1])
        self.assertEqual(transfer['content'],text);self.assertEqual(transfer['response_sha256'],common.sha(raw))
    def test_bad_nodes_not_repaired_by_valid_final(self):
        p=self.plan['protocol']['problems'][0];g=proof(p,True);g['nodes'][-1]['parents']=[]
        joined=stages.assemble({'nodes':g['nodes']},{'final_node_id':g['final_node_id']})
        self.assertIs(joined['nodes'],g['nodes']);self.assertFalse(measure.assess(p,joined)['strict_valid'])
    def test_extra_nodes_not_pruned(self):
        p=self.plan['protocol']['problems'][0];g=proof(p);g['nodes'].append({'id':'extra','atom':'Lp','rule':None,'parents':[]})
        self.assertEqual(measure.assess(p,stages.assemble({'nodes':g['nodes']},{'final_node_id':g['final_node_id']}))['error_codes'],['extra_unused_node'])
    def test_upstream_extra_field_rejected(self):
        g=proof(self.plan['protocol']['problems'][0]);self.assertIsNone(stages.assemble(g,{'final_node_id':g['final_node_id']}))
    def test_missing_final_not_guessed(self):
        g=proof(self.plan['protocol']['problems'][0]);a=stages.assemble({'nodes':g['nodes']},{'final_node_id':'missing'})
        self.assertEqual(measure.assess(self.plan['protocol']['problems'][0],a)['error_codes'],['missing_final_node'])
    def test_full_synthetic_summaries_independent(self):
        for mode in ('perfect','fixed_short','reversed','extra','bad_parent','wrong_final','direct_missing_final','staged_missing_final','reverse_nodes','reorder_independent','parse_error','nodes_parse_error','nodes_extra_field','invalid_schema','missing_usage','incomplete','over_budget'):
            with self.subTest(mode=mode):
                records,_=records_for(self.plan,mode);a=report.summarize(self.plan,records,'complete');b=verify._summary(self.plan,records,'complete')
                self.assertEqual(a,b);self.assertEqual(report.render(a),verify._render(b));self.assertIsNone(a['overall']['D_instruction_control'])
    def test_missing_results_null_not_zero_D(self):
        a=report.summarize(self.plan,[],'crashed');self.assertFalse(a['overall']['comparison_measured'])
        for t in a['trials']:self.assertIsNone(t['actual_D']);self.assertIsNone(t['reconstruction_success'])
    def test_budget_overflow_unmeasured(self):
        records,_=records_for(self.plan,'over_budget');a=report.summarize(self.plan,records,'stopped')
        self.assertEqual(a['rows'][0]['status'],'generation_budget_exceeded');self.assertIsNone(a['trials'][0]['actual_D'])
    def test_seed_and_arm_balance(self):
        for pi in range(3):
            for cond in self.plan['protocol']['conditions']:
                first=[]
                for si in range(2):
                    first.append(next(s['arm'] for s in self.plan['slots'] if s['block']==pi*2+si and s['condition']==cond))
                self.assertEqual(set(first),{'direct','staged'})
        counts={a:0 for a in ('direct','staged')}
        for b in range(6):
            for c in self.plan['protocol']['conditions']:
                arm=next(s['arm'] for s in self.plan['slots'] if s['block']==b and s['condition']==c);counts[arm]+=1
        self.assertEqual(counts,{'direct':6,'staged':6})
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
                for q in variants:
                    self.assertEqual(measure.assess(p,q),verify._semantic(p,q));count+=1
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
