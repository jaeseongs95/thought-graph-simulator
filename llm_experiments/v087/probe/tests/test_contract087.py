from pathlib import Path
from copy import deepcopy
from collections import Counter
import os,sys,unittest,zipfile,ast,shutil,subprocess
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core087 as c,design087 as d,audit087 as a,fixtures087 as f,rows087 as r,audit_rows087 as ar,tables087 as tables
from baseline087 import validate_inputs

BASE=Path(os.environ.get('V087_BASELINE',str(Path.home()/'Downloads'/c.spec()['baseline_name'])))

class Contract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.p=f.plan();cls.anchors=d.anchors()
    def test_schedule_independently_reconstructed(self):self.assertEqual(a.reconstruct_schedule(self.p['protocol']),(self.p['trials'],self.p['slots'],self.p['actions']))
    def test_schedule_counts(self):self.assertEqual((len(self.p['trials']),len(self.p['slots']),len(self.p['actions'])),(1072,4208,4240))
    def test_phase_counts(self):self.assertEqual(Counter(t['phase']for t in self.p['trials']),{'rule_probe':560,'end_to_end':512})
    def test_shared_selection_count(self):self.assertEqual(sum(o['stage']in ('compare','select')for o in self.p['slots']),256)
    def test_no_W_or_oracle_requests(self):self.assertTrue(all(t['metric']=='D'and t['selector_variant']=='two_stage_values'for t in self.p['trials']))
    def test_not_new_holdout(self):self.assertFalse(self.p['protocol']['holdout']);self.assertEqual(self.p['protocol']['new_independent_structures'],0)
    def test_anchors_cover_all_16_paths(self):self.assertEqual(len({(x['problem_id'],x['route_kind'])for x in self.anchors}),16);self.assertEqual(len(self.anchors),70)
    def test_all_main_arms_have_same_selection_ids(self):
        for uid in {t['unit_id']for t in self.p['trials']if t['phase']=='end_to_end'}:
            ts=[t for t in self.p['trials']if t['unit_id']==uid];self.assertEqual(len(ts),4);self.assertEqual(len({t['selection_slot_id']for t in ts}),1);self.assertEqual(len({t['comparison_slot_id']for t in ts}),1)
    def test_main_arm_orders_balanced(self):
        positions=Counter();seq=[o for o in self.p['slots']if o['stage']=='facts'];byid={t['id']:t for t in self.p['trials']}
        for j in range(0,len(seq),4):
            for pos,op in enumerate(seq[j:j+4]):positions[byid[op['trial_id']]['generator_arm'],pos]+=1
        self.assertEqual(set(positions.values()),{32})
    def test_protocol_frozen_contract(self):a.validate_protocol(self.p['protocol'])
    def test_schema_does_not_supply_parents(self):
        b=self.anchors[0]['request_body'];out=d.extend_request(b,'inventory_allocated',c.spec())
        for key in ('parents','atom','rule'):self.assertEqual(out['format']['properties']['node']['properties'][key],b['format']['properties']['node']['properties'][key])
    def test_only_id_schema_restricted(self):
        b=self.anchors[0]['request_body'];out=d.extend_request(b,'allocated_id',c.spec());sc=deepcopy(out['format']);sc['properties']['node']['properties']['id']=b['format']['properties']['node']['properties']['id'];self.assertEqual(sc,b['format'])
    def test_inventory_keeps_all_nodes_not_only_correct_parents(self):
        b=self.anchors[-1]['request_body'];original=f.data(b);out=f.data(d.extend_request(b,'node_inventory',c.spec()));rows=out['observed_node_inventory']['rows']
        count=sum(len(c.load(h['content']).get('nodes',[]))+int('node'in c.load(h['content']))for h in original['history']);self.assertEqual(len(rows),count);self.assertGreater(count,len(original['operation']['requested_rule']['premises']))
    def test_inventory_preserves_duplicates_and_false_atom(self):
        h=[{'source_slot_id':'s','content':c.wire({'nodes':[{'id':'dup','atom':'WRONG'},{'id':'dup','atom':'X'}]}).decode()}]
        inv=d.history_inventory(h);self.assertEqual([n['id']for n in inv['rows']],['dup','dup']);self.assertEqual(inv['rows'][0]['atom'],'WRONG');self.assertEqual(inv,a.independent_inventory(h))
    def test_inventory_marks_unreadable_history(self):
        h=[{'source_slot_id':'s','content':'{bad'}];self.assertEqual(d.history_inventory(h),{'rows':[],'unreadable_source_slots':['s']})
    def test_inventory_never_changes_history(self):
        b=self.anchors[0]['request_body'];self.assertEqual(f.data(d.extend_request(b,'node_inventory',c.spec()))['history'],f.data(b)['history'])
    def test_new_id_excludes_existing_and_malformed_literal(self):
        h=[{'source_slot_id':'s','content':'{bad v087_node_0001'}];self.assertEqual(d.allocate_id(h,'v087_node_'),'v087_node_0002')
    def test_new_id_handles_escaped_and_nonstandard_node(self):
        h=[{'source_slot_id':'s','content':'{"node":{"id":"\\u0076087_node_0001","atom":null}}'}];self.assertEqual(d.allocate_id(h,'v087_node_'),'v087_node_0002')
    def test_no_posthoc_repair_flags(self):self.assertTrue(all(self.p['protocol'][k]is False for k in ('posthoc_repair','automatic_retry','automatic_download','automatic_server_start')))
    def test_baseline_body_is_unchanged(self):
        b=self.anchors[0]['request_body'];self.assertEqual(c.wire(d.extend_request(b,'baseline',c.spec())),c.wire(b))
    def test_diagnostic_independent_requests_every_arm_and_seed(self):
        for op in self.p['slots']:
            if d.trial_for(self.p,op)['phase']=='rule_probe':self.assertEqual(a.expected_request(self.p,op,{})[1],c.wire(d.request_for(self.p,op,{})))
    def test_bad_comparison_not_corrected(self):
        op=next(o for o in self.p['slots']if o['stage']=='compare');raw=f.answer(d.request_for(self.p,op,{}),'compare_wrong');raws={op['id']:raw};t=d.trial_for(self.p,op);lookup=next(o for o in self.p['slots']if o['id']==t['selection_slot_id']);body=d.request_for(self.p,lookup,raws);self.assertEqual(f.data(body)['value_original'],c.load(raw)['message']['content'])
    def test_comparison_and_lookup_information_boundaries(self):
        op=next(o for o in self.p['slots']if o['stage']=='compare');body=d.request_for(self.p,op,{});self.assertEqual(set(f.data(body)),{'metric','direction','values'})
        t=d.trial_for(self.p,op);o=next(o for o in self.p['slots']if o['id']==t['selection_slot_id']);request=d.request_for(self.p,o,{op['id']:f.answer(body)});self.assertEqual(set(f.data(request)),{'metric','candidate_measurements','value_original'})
    def test_python312_syntax(self):
        for path in c.ROOT.rglob('*.py'):ast.parse(path.read_text(encoding='utf-8'),filename=str(path),feature_version=(3,12))
    def test_powershell_native_parser(self):
        executable=shutil.which('pwsh')or shutil.which('powershell')
        if not executable:self.skipTest('PowerShell native parser unavailable')
        path=str(c.ROOT/'windows/Auto.template.ps1').replace("'","''")
        code="$t=$null;$e=$null;[System.Management.Automation.Language.Parser]::ParseFile('"+path+"',[ref]$t,[ref]$e)|Out-Null;if($e.Count){$e|Out-String|Write-Error;exit 2}"
        proc=subprocess.run([executable,'-NoProfile','-Command',code],capture_output=True);self.assertEqual(proc.returncode,0,proc.stderr)
    def test_actual_v086_baseline_and_anchors(self):
        self.assertTrue(BASE.is_file(),'V087_BASELINE 파일 필요');result=validate_inputs(BASE,True);self.assertEqual(result['prior_receipt']['observed_calls'],3618);self.assertEqual(result['observed_paths'],16)
    def test_v086_main_request_regression_1072(self):
        self.assertTrue(BASE.is_file());n=0
        with zipfile.ZipFile(BASE)as z:
            raws={name.split('/')[1]:z.read(name)for name in z.namelist()if name.startswith('wire/')and name.endswith('/response.raw.json')}
            for t in self.p['trials']:
                if t['phase']!='end_to_end' or t['generator_arm']!='baseline':continue
                old=t['unit_id']+'_two_stage_values'
                for o in self.p['slots']:
                    if o['trial_id']!=t['id']or o['stage']not in ('facts','rule','final'):continue
                    suffix=o['id'][len(t['id']):];sid=old+suffix
                    if sid in raws:raws[o['id']]=raws[sid]
            for o in self.p['slots']:
                t=d.trial_for(self.p,o)
                if t['phase']!='end_to_end'or t['generator_arm']!='baseline':continue
                sid=t['unit_id']+'_two_stage_values_'+(f"rule_{o['rule_position']:02d}"if o['stage']=='rule'else o['stage'])
                name='wire/'+sid+'/request.wire.json'
                if name not in z.namelist():self.assertIsNotNone(d.disposition(self.p,o,raws));continue
                self.assertEqual(c.wire(d.request_for(self.p,o,raws)),z.read(name),sid);n+=1
        self.assertEqual(n,1072)

class PrefixPolicy(unittest.TestCase):
    def test_selection_does_not_read_summary_or_target_responses(self):
        from baseline087 import select_prefix_anchors
        class RequestOnly:
            def __init__(self,z):self.z=z
            def namelist(self):return self.z.namelist()
            def read(self,name):
                if name!='plan.json'and not name.endswith('/request.wire.json'):raise AssertionError('target/outcome read: '+name)
                return self.z.read(name)
        with zipfile.ZipFile(BASE)as z:aa,pp=select_prefix_anchors(RequestOnly(z),c.spec())
        self.assertEqual(aa,d.anchors());self.assertEqual(len(pp),70);self.assertTrue(all(not x['target_response_used_for_selection']for x in pp))
    def test_invalid_preceding_history_is_excluded(self):
        from baseline087 import validated_prefix
        body=deepcopy(d.anchors()[1]['request_body']);data=f.data(body);x=c.load(data['history'][0]['content']);x['nodes'][0]['atom']='INVALID';data['history'][0]['content']=c.wire(x).decode();body['messages'][0]['content']=body['messages'][0]['content'].split('\n\ninput: ',1)[0]+'\n\ninput: '+c.wire(data).decode();self.assertIsNone(validated_prefix(body))
