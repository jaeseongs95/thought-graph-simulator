from pathlib import Path
from copy import deepcopy
from collections import Counter,defaultdict
from unittest.mock import patch
import sys,os,unittest,zipfile,ast,subprocess,shutil
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core089 as c,design089 as d,audit089 as a,fixtures089 as f,baseline089 as b
BASE=Path(os.environ.get('V089_BASELINE',str(Path.home()/'Downloads'/c.spec()['baseline_name'])))

class Contract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.p=f.plan()
    def test_frozen_counts(self):self.assertEqual((len(self.p['trials']),len(self.p['slots']),len(self.p['actions'])),(640,3856,3888))
    def test_independent_schedule(self):self.assertTrue(c.exact((self.p['trials'],self.p['slots'],self.p['actions']),a.reconstruct_schedule(c.spec())))
    def test_protocol_validation(self):a.validate_protocol(c.spec())
    def test_protocol_safety_mutation_rejected(self):
        for key in ('automatic_retry','posthoc_repair','automatic_server_start','automatic_download','holdout','raw_output_repair'):
            x=c.spec();x[key]=True
            with self.subTest(key=key),self.assertRaises(ValueError):a.validate_protocol(x)
    def test_sampling_and_runtime_identical(self):
        old=c.load((c.ROOT/'data/protocol_v088_snapshot.json').read_bytes());new=c.spec()
        for key in b.CONTRACT_KEYS:self.assertEqual(old[key],new[key],key)
    def test_complete_crossing_every_structure_route_seed(self):
        groups=defaultdict(set)
        for t in self.p['trials']:
            if t['phase']=='continuation':groups[t['unit_id']].add((t['initial_id_style'],t['output_id_style']))
        self.assertEqual(len(groups),32)
        self.assertTrue(all(v=={(i,j) for i in d.STYLES for j in d.STYLES} for v in groups.values()))
    def test_order_balanced_over_blocks(self):
        counts=Counter()
        for block in range(16):
            for kind in ('shallow','deep'):
                ts=[t for t in self.p['trials'] if t['phase']=='continuation' and t['block']==block and t['condition']==kind]
                for rank,t in enumerate(ts):counts[kind,t['generator_arm'],rank]+=1
        self.assertEqual(len(counts),2*16*16);self.assertTrue(all(n==1 for n in counts.values()))
    def test_fixed_new_ids_across_initial_styles(self):
        groups=defaultdict(list)
        for t in self.p['trials']:
            if t['phase']=='continuation':groups[t['unit_id'],t['output_id_style']].append(d.continuation_seed(t))
        self.assertEqual(len(groups),128)
        for items in groups.values():
            self.assertTrue(all(ids==items[0][1] for _,ids,_ in items))
            used={n['id'] for h,_,_ in items for n in d.history_nodes(h)}
            self.assertFalse(used & set(items[0][1]))
    def test_independent_seed_transform(self):
        for t in self.p['trials']:
            if t['phase']=='continuation':self.assertEqual(d.continuation_seed(t),a.continuing(t))
    def test_initial_id_transform_is_reversible(self):
        for anchor in d.anchors():
            before=d.data_from(anchor['request_body'])['history']
            for style in d.STYLES:
                h,mapping=d.rename_initial(before,style);nodes=d.history_nodes(h);inverse={v:k for k,v in mapping.items()}
                for node in nodes:node['id']=inverse[node['id']]
                self.assertEqual(nodes,d.history_nodes(before));self.assertEqual((h,mapping),a.renamed_initial(before,style))
    def test_only_initial_facts_can_be_renamed(self):
        h=d.data_from(d.anchors()[0]['request_body'])['history']
        with self.assertRaises(ValueError):d.rename_initial(h+h,'short')
        x=deepcopy(h);obj=c.load(x[0]['content']);obj['nodes'][0]['rule']='some_rule';x[0]['content']=c.wire(obj).decode()
        with self.assertRaises(ValueError):d.rename_initial(x,'short')
    def test_alias_and_tagged_are_semantic_support(self):
        for t in self.p['trials']:
            if t['phase']!='continuation' or t['output_id_style'] not in ('atom_alias','atom_tagged'):continue
            _,ids,_=d.continuation_seed(t);problem=next(x for x in self.p['protocol']['problems'] if x['id']==t['problem_id'])
            conclusions=[next(x['conclusion'] for x in problem['rules'] if x['id']==rid) for rid in t['route_rule_ids']]
            expected=conclusions if t['output_id_style']=='atom_alias' else ['node_'+x for x in conclusions]
            self.assertEqual(ids,expected)
    def test_first_requests_only_initial_names_vary(self):
        groups=defaultdict(list)
        for t in self.p['trials']:
            if t['phase']!='continuation':continue
            op=next(o for o in self.p['slots'] if o['trial_id']==t['id']);body=d.request_for(self.p,op,{})
            data=d.data_from(body);obj=c.load(data['history'][0]['content'])
            for i,node in enumerate(obj['nodes']):node['id']=f'canonical_{i}'
            data['history'][0]['content']=c.wire(obj).decode()
            body['messages'][0]['content']=body['messages'][0]['content'].split('\n\ninput: ',1)[0]+'\n\ninput: '+c.wire(data).decode()
            groups[t['unit_id'],t['output_id_style']].append(body)
        self.assertTrue(all(all(x==bs[0] for x in bs) for bs in groups.values()))
    def test_allocation_support_shape_is_equal(self):
        for t in self.p['trials']:
            if t['phase']!='continuation':continue
            op=next(o for o in self.p['slots'] if o['trial_id']==t['id']);body=d.request_for(self.p,op,{})
            props=body['format']['properties']['node']['properties'];old=d.anchor_for(t)['request_body']['format']['properties']['node']['properties']
            for key in ('atom','rule','parents'):self.assertEqual(props[key],old[key])
            self.assertEqual(len(props['id']['enum']),1)
            self.assertNotIn('observed_node_inventory',d.data_from(body))
    def test_raw_new_output_is_not_repaired(self):
        t=next(t for t in self.p['trials'] if t['phase']=='continuation');ops=[o for o in self.p['slots'] if o['trial_id']==t['id']]
        x=c.load(f.answer(d.request_for(self.p,ops[0],{})));obj=c.load(x['message']['content']);obj['node']['parents']=['RAW_WRONG'];x['message']['content']=' '+c.wire(obj).decode()+'\n'
        raw=c.wire(x);req=d.request_for(self.p,ops[1],{ops[0]['id']:raw})
        self.assertEqual(d.data_from(req)['history'][-1]['content'],x['message']['content'])
    def test_no_select_or_new_facts_in_crossing(self):
        ids={t['id'] for t in self.p['trials'] if t['phase']=='continuation'}
        self.assertTrue(all(o['stage'] in ('rule','final') for o in self.p['slots'] if o['trial_id'] in ids))
    def test_anchor_selection_reads_no_outcomes(self):
        class Guard:
            def __init__(self,z):self.z=z
            def namelist(self):return self.z.namelist()
            def read(self,name):
                if name!='plan.json' and not name.endswith('/request.wire.json'):raise AssertionError(name)
                return self.z.read(name)
        with zipfile.ZipFile(BASE) as z:anchors,pv=b.select_initial_anchors(Guard(z),c.spec())
        self.assertEqual(anchors,d.anchors());self.assertEqual(len(anchors),16)
        self.assertTrue(all(not x['target_response_used_for_selection'] and not x['future_responses_used_for_selection'] and not x['summary_used_for_selection'] for x in pv))
    def test_prior_source_115_files_byte_identical(self):
        with zipfile.ZipFile(BASE) as z:old={n[7:]:z.read(n) for n in z.namelist() if n.startswith('source/')}
        now={p.relative_to(c.ROOT/'frozen088').as_posix():p.read_bytes() for p in (c.ROOT/'frozen088').rglob('*') if p.is_file() and '__pycache__' not in p.parts}
        self.assertEqual(old,now);self.assertEqual(len(old),115)
    def test_actual_v088_baseline_requests_byte_identical(self):
        with zipfile.ZipFile(BASE) as z:
            names=set(z.namelist());old=c.load(z.read('plan.json'))
            raws={o['id']:z.read('wire/'+o['id']+'/response.raw.json') for o in old['slots'] if 'wire/'+o['id']+'/response.raw.json' in names}
            trials={t['id'] for t in self.p['trials'] if t['phase']=='end_to_end'};n=0
            for op in self.p['slots']:
                if op['trial_id'] not in trials:continue
                name='wire/'+op['id']+'/request.wire.json'
                if name not in names:continue
                self.assertEqual(c.wire(d.request_for(self.p,op,raws)),z.read(name));n+=1
        self.assertEqual(n,1072)
    def test_previous_evidence_validation(self):
        result=b.validate_inputs(BASE,True);self.assertTrue(result['prior_receipt']['verified']);self.assertEqual(result['new_model_calls'],0)
    def test_no_holdout_or_hidden_state_claim(self):
        s=c.spec();self.assertFalse(s['holdout']);self.assertEqual(s['new_independent_structures'],0);self.assertIn('hidden-state/hidden-layer control',s['scope_exclusions'])
    def test_python312_syntax(self):
        for p in c.ROOT.rglob('*.py'):ast.parse(p.read_text(encoding='utf-8-sig'),filename=str(p),feature_version=(3,12))
    def test_audit_does_not_import_production_design_or_semantics(self):
        banned={'core089','design089','rows089','report089','measure','stages'}
        for name in ('audit089.py','audit_rows089.py','verify089.py'):
            mods=[]
            for n in ast.walk(ast.parse((c.ROOT/name).read_text())):
                if isinstance(n,ast.Import):mods.extend(x.name.split('.')[0] for x in n.names)
                if isinstance(n,ast.ImportFrom):mods.append((n.module or '').split('.')[0])
            self.assertFalse(banned & set(mods),(name,mods))
    def test_powershell_native_parser_when_available(self):
        exe=shutil.which('pwsh') or shutil.which('powershell')
        if not exe:self.skipTest('PowerShell native parser unavailable')
        path=str(c.ROOT/'windows/Auto.template.ps1').replace("'","''")
        script=f"$e=$null;$t=$null;[void][System.Management.Automation.Language.Parser]::ParseFile('{path}',[ref]$t,[ref]$e);if($e.Count -gt 0){{$e;exit 1}}"
        self.assertEqual(subprocess.run([exe,'-NoProfile','-Command',script],capture_output=True).returncode,0)
