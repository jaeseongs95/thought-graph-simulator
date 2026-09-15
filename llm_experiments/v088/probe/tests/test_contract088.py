from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys,os,unittest,zipfile,ast,subprocess,shutil
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core088 as c,design088 as d,audit088 as a,fixtures088 as f,baseline088 as b
BASE=Path(os.environ.get('V088_BASELINE',str(Path.home()/'Downloads'/c.spec()['baseline_name'])))

class Contract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.p=f.plan()
    def test_frozen_schedule_counts(self):self.assertEqual((len(self.p['trials']),len(self.p['slots']),len(self.p['actions'])),(944,3200,3232))
    def test_independent_schedule(self):self.assertTrue(c.exact((self.p['trials'],self.p['slots'],self.p['actions']),a.reconstruct_schedule(c.spec())))
    def test_protocol_independent_validation(self):a.validate_protocol(c.spec())
    def test_source_anchor_frozen_hash(self):self.assertEqual(c.sha((c.ROOT/'data/anchors.json').read_bytes()),c.spec()['anchors_sha256'])
    def test_anchor_selection_does_not_read_target_or_future(self):
        class Guard:
            def __init__(self,z):self.z=z
            def namelist(self):return self.z.namelist()
            def read(self,name):
                if name!='plan.json' and not name.endswith('/request.wire.json'):raise AssertionError('forbidden target/outcome '+name)
                return self.z.read(name)
        with zipfile.ZipFile(BASE)as z:anchors,pv=b.select_prefix_anchors(Guard(z),c.spec())
        self.assertEqual(anchors,d.anchors());self.assertTrue(all(not x['target_response_used_for_selection']for x in pv))
    def test_all_prefixes_reversible_semantics(self):
        for anchor in d.anchors():
            orig=d.data_from(anchor['request_body'])['history']
            for style in c.spec()['probe_arms']:
                h,m=d.rename_history(orig,style);ns=d.history_nodes(h);inverse={v:k for k,v in m.items()}
                for n in ns:n['id']=inverse[n['id']];n['parents']=[inverse[p]for p in n['parents']]
                self.assertEqual(ns,d.history_nodes(orig));self.assertEqual((h,m),a.renamed(orig,style))
    def test_local_other_fields_header_schema_unchanged(self):
        for t in self.p['trials']:
            if t['phase']!='rename_probe':continue
            o=next(o for o in self.p['slots']if o['trial_id']==t['id']);body=d.request_for(self.p,o,{});old=d.anchor_for(t)['request_body']
            x,y=d.data_from(body),d.data_from(old);x.pop('history');y.pop('history');self.assertEqual(x,y)
            self.assertEqual(body['format'],old['format']);self.assertEqual(body['messages'][0]['content'].split(d.SEPARATOR)[0],old['messages'][0]['content'].split(d.SEPARATOR)[0])
    def test_observed_also_uses_canonical_serializer(self):
        h=d.data_from(d.anchors()[0]['request_body'])['history'];out,m=d.rename_history(h,'observed')
        self.assertTrue(all(x['content']==c.wire(c.load(x['content'])).decode()for x in out));self.assertTrue(all(k==v for k,v in m.items()))
    def test_atom_alias_is_semantic_name_not_neutral(self):
        for anchor in d.anchors():
            h,_=d.rename_history(d.data_from(anchor['request_body'])['history'],'atom_alias');self.assertTrue(all(n['id']==n['atom']for n in d.history_nodes(h)))
    def test_probes_include_already_renamed_parents(self):
        counts=[]
        for t in self.p['trials']:
            if t['phase']=='rename_probe'and t['generator_arm']=='legacy_long':
                h,_=d.rename_history(d.data_from(d.anchor_for(t)['request_body'])['history'],'legacy_long');counts.extend(n['id'].startswith('v087_node_')for n in d.history_nodes(h))
        self.assertTrue(counts and all(counts))
    def test_no_inventory_added(self):
        for t in self.p['trials']:
            if t['phase']=='end_to_end':continue
            o=next(o for o in self.p['slots']if o['trial_id']==t['id']);self.assertNotIn('observed_node_inventory',d.data_from(d.request_for(self.p,o,{})))
    def test_same_output_ids_across_scopes(self):
        for t in self.p['trials']:
            if t['phase']!='continuation'or not t['generator_arm'].endswith('_mixed'):continue
            u=dict(t,generator_arm=t['generator_arm'].replace('_mixed','_uniform'))
            h,ids,_=d.continuation_seed(t);uh,uids,_=d.continuation_seed(u)
            self.assertEqual(ids,uids);self.assertEqual(len(ids),len(set(ids)))
            self.assertFalse(set(ids)&{n['id']for n in d.history_nodes(h)+d.history_nodes(uh)})
    def test_independent_continuation_transform(self):
        for t in self.p['trials']:
            if t['phase']=='continuation':self.assertEqual(d.continuation_seed(t),a.continuing(t))
    def test_new_reply_never_renamed(self):
        t=next(t for t in self.p['trials']if t['phase']=='continuation');ops=[o for o in self.p['slots']if o['trial_id']==t['id']];raw=f.answer(d.request_for(self.p,ops[0],{}))
        x=c.load(raw);obj=c.load(x['message']['content']);obj['node']['parents']=['RAW_WRONG'];x['message']['content']=' '+c.wire(obj).decode()+'\n';raw=c.wire(x)
        with patch.object(d,'rename_history',wraps=d.rename_history)as rename:
            req=d.request_for(self.p,ops[1],{ops[0]['id']:raw})
            self.assertEqual(d.data_from(req)['history'][-1]['content'],x['message']['content'])
            self.assertTrue(all('RAW_WRONG'not in str(call.args[0])for call in rename.call_args_list))
    def test_continuation_does_not_call_selector_or_new_facts(self):
        ids={t['id']for t in self.p['trials']if t['phase']=='continuation'}
        self.assertTrue(all(o['stage']in ('rule','final')for o in self.p['slots']if o['trial_id']in ids))
    def test_all_structures_included(self):
        self.assertEqual({t['problem_id']for t in self.p['trials']},{'U%02d'%i for i in range(1,9)})
    def test_legacy_baseline_source_is_byte_preserved(self):
        with zipfile.ZipFile(BASE)as z:
            originals={n[len('source/'):]:z.read(n)for n in z.namelist()if n.startswith('source/')}
        actual={p.relative_to(c.ROOT/'frozen087').as_posix():p.read_bytes()for p in (c.ROOT/'frozen087').rglob('*')if p.is_file()and '__pycache__'not in p.parts}
        self.assertEqual(actual,originals);self.assertEqual(len(actual),77)
    def test_previous_actual_monitor_request_regression(self):
        with zipfile.ZipFile(BASE)as z:
            bp=c.load(z.read('plan.json'));ids={t['id']for t in self.p['trials']if t['phase']=='end_to_end'}
            raws={o['id']:z.read('wire/'+o['id']+'/response.raw.json')for o in bp['slots']if 'wire/'+o['id']+'/response.raw.json'in z.namelist()}
            count=0
            for o in self.p['slots']:
                if o['trial_id']not in ids:continue
                name='wire/'+o['id']+'/request.wire.json'
                if name not in z.namelist():continue
                self.assertEqual(c.wire(d.request_for(self.p,o,raws)),z.read(name));count+=1
        self.assertEqual(count,1888)
    def test_no_holdout_claim(self):self.assertFalse(c.spec()['holdout']);self.assertEqual(c.spec()['new_independent_structures'],0)
    def test_python312_syntax(self):
        for p in c.ROOT.rglob('*.py'):ast.parse(p.read_text(encoding='utf-8-sig'),filename=str(p),feature_version=(3,12))
    def test_independent_modules_no_production_imports(self):
        banned={'core088','design088','rows088','report088','measure','stages'}
        for name in ('audit088.py','audit_rows088.py','verify088.py'):
            tree=ast.parse((c.ROOT/name).read_text());imports=[]
            for node in ast.walk(tree):
                if isinstance(node,ast.Import):imports.extend(a.name.split('.')[0]for a in node.names)
                elif isinstance(node,ast.ImportFrom):imports.append((node.module or '').split('.')[0])
            self.assertFalse(banned&set(imports),(name,imports))
    def test_powershell_parser_when_available(self):
        exe=shutil.which('pwsh')or shutil.which('powershell')
        if not exe:self.skipTest('PowerShell native parser unavailable')
        path=str(c.ROOT/'windows/Auto.template.ps1').replace("'","''")
        script=f"$e=$null;$t=$null;[void][System.Management.Automation.Language.Parser]::ParseFile('{path}',[ref]$t,[ref]$e);if($e.Count -gt 0){{$e;exit 1}}"
        self.assertEqual(subprocess.run([exe,'-NoProfile','-Command',script],capture_output=True).returncode,0)
