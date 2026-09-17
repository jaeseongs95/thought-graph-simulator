from pathlib import Path
from copy import deepcopy
from collections import Counter,defaultdict
from unittest.mock import patch
import sys,os,unittest,zipfile,ast,subprocess,shutil
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core091 as c,design091 as d,audit091 as a,fixtures091 as f,baseline091 as b
BASE=Path(os.environ.get('V091_BASELINE',str(Path.home()/'Downloads'/c.spec()['baseline_name'])))

class Contract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p,cls.records,cls.raws,cls.requests=f.oracle_cache()
    def test_frozen_counts(self):self.assertEqual((len(self.p['trials']),len(self.p['slots']),len(self.p['actions'])),(1536,10944,10976))
    def test_independent_schedule(self):self.assertEqual((self.p['trials'],self.p['slots'],self.p['actions']),a.reconstruct_schedule(c.spec()))
    def test_protocol_validation(self):a.validate_protocol(c.spec())
    def test_safety_mutations_rejected(self):
        for key in ('automatic_retry','posthoc_repair','automatic_server_start','automatic_download','raw_output_repair','old_output_reuse'):
            s=c.spec();s[key]=True
            with self.subTest(key=key),self.assertRaises(ValueError):a.validate_protocol(s)
    def test_changed_primary_rejected(self):
        s=c.spec();s['primary_comparison']=['baseline','atom_tagged']
        with self.assertRaises(ValueError):a.validate_protocol(s)
    def test_sampling_and_runtime_unchanged(self):
        old=c.load((c.ROOT/'data/protocol_v090_snapshot.json').read_bytes());new=c.spec()
        for key in b.CONTRACT_KEYS:self.assertEqual(old[key],new[key],key)
    def test_four_arms_every_unit(self):
        groups=defaultdict(set)
        for t in self.p['trials']:groups[t['unit_id']].add(t['generator_arm'])
        self.assertEqual(len(groups),384);self.assertTrue(all(v==set(d.ARMS) for v in groups.values()))
    def test_arm_order_balanced_within_each_block(self):
        for block in range(16):
            counts=Counter();ts=[t for t in self.p['trials'] if t['block']==block]
            for i in range(0,len(ts),4):
                for rank,t in enumerate(ts[i:i+4]):counts[t['generator_arm'],rank]+=1
            self.assertEqual(len(counts),16);self.assertTrue(all(v==6 for v in counts.values()))
    def test_shared_selector_128_compare_128_lookup(self):
        self.assertEqual(Counter(o['stage'] for o in self.p['slots'])['compare'],384)
        self.assertEqual(Counter(o['stage'] for o in self.p['slots'])['select'],384)
        self.assertTrue(all(o['trial_id'].endswith('_baseline') for o in self.p['slots'] if o['stage'] in ('compare','select')))
    def test_fresh_facts_for_each_arm(self):
        facts=[o for o in self.p['slots'] if o['stage']=='facts'];self.assertEqual(len(facts),1536)
        for o in facts:self.assertEqual(d.data_from(c.load(self.requests[o['id']]))['history'],[])
    def test_no_old_fact_anchor_loader(self):
        src=(c.ROOT/'design091.py').read_text()
        for term in ('anchors.json','rename_initial','continuation_seed'):self.assertNotIn(term,src)
    def test_independent_all_requests(self):
        n=0
        for o in self.p['slots']:
            skip,raw=a.expected_request(self.p,o,self.raws)
            if o['id'] in self.requests:self.assertEqual(raw,self.requests[o['id']],o['id']);n+=1
            else:self.assertEqual(skip,self.records[o['id']]['reason'])
        self.assertEqual(n,10560)
    def test_naming_allocation_independent(self):
        for p in c.spec()['problems']:
            for arm in d.ARMS[1:]:
                self.assertEqual(d.fact_allocation(p,arm),a.facts_table(p,arm))
                for path in c.spec()['reference_plans'][p['id']].values():
                    names=[x['id'] for x in d.fact_allocation(p,arm)]
                    for i,rid in enumerate(path):
                        rule=next(r for r in p['rules'] if r['id']==rid)
                        name=d.rule_allocation(p,rule,i,arm)
                        self.assertEqual(name,a.rule_id(p,rule,i,arm));self.assertNotIn(name,names);names.append(name)
    def test_only_id_support_is_added(self):
        for o in self.p['slots']:
            if o['id'] not in self.requests or o['stage'] not in ('facts','rule'):continue
            t=d.trial_for(self.p,o)
            if t['generator_arm']=='baseline':continue
            body=c.load(self.requests[o['id']]);original=d.frozen.request_for(d.render_view(self.p,o),o,self.raws)
            data=d.data_from(body);old=d.data_from(original)
            extra='allocated_fact_ids' if o['stage']=='facts' else 'allocated_node_id'
            self.assertEqual(set(data)-set(old),{extra});data.pop(extra);self.assertEqual(data,old)
            shape=deepcopy(body['format']);prior=original['format']
            if o['stage']=='facts':shape['properties']['nodes']['items']['properties']['id'].pop('enum')
            else:shape['properties']['node']['properties']['id']=deepcopy(prior['properties']['node']['properties']['id'])
            self.assertEqual(shape,prior)
    def test_three_supported_arms_share_prompt_header(self):
        headers=defaultdict(set)
        for o in self.p['slots']:
            if o['id'] not in self.requests or o['stage'] not in ('facts','rule'):continue
            t=d.trial_for(self.p,o)
            if t['generator_arm']=='baseline':continue
            text=c.load(self.requests[o['id']])['messages'][0]['content']
            headers[o['stage']].add(text.split(d.SEPARATOR)[0])
        self.assertEqual({k:len(v) for k,v in headers.items()},{'facts':1,'rule':1})
    def test_facts_wrong_id_is_passed_without_repair(self):
        t=next(t for t in self.p['trials'] if t['generator_arm']=='atom_alias');ops=[o for o in self.p['slots'] if o['trial_id']==t['id'] and o['stage'] in ('facts','rule')]
        op=ops[0];outer=c.load(self.raws[op['id']]);obj=c.load(outer['message']['content']);obj['nodes'][0]['id']='RAW_BAD_ID'
        content=' '+c.wire(obj).decode()+'\n';outer['message']['content']=content;raws=dict(self.raws);raws[op['id']]=c.wire(outer)
        body=d.request_for(self.p,ops[1],raws);self.assertEqual(d.data_from(body)['history'][0]['content'],content)
    def test_wrong_rule_parent_is_passed_without_repair(self):
        t=self.p['trials'][0];ops=[o for o in self.p['slots'] if o['trial_id']==t['id'] and o['stage']=='rule']
        outer=c.load(self.raws[ops[0]['id']]);obj=c.load(outer['message']['content']);obj['node']['parents']=['RAW_BAD_PARENT'];outer['message']['content']=' '+c.wire(obj).decode()+'\n'
        raws=dict(self.raws);raws[ops[0]['id']]=c.wire(outer)
        self.assertEqual(d.data_from(d.request_for(self.p,ops[1],raws))['history'][-1]['content'],outer['message']['content'])
    def test_allocation_not_repaired_for_bad_history_collision(self):
        t=next(t for t in self.p['trials'] if t['generator_arm']=='short_uniform');op=next(o for o in self.p['slots'] if o['trial_id']==t['id'] and o['stage']=='rule')
        expected=d.data_from(d.request_for(self.p,op,self.raws))['allocated_node_id']
        fs=t['id']+'_facts';raws=dict(self.raws);outer=c.load(raws[fs]);obj=c.load(outer['message']['content']);obj['nodes'][0]['id']=expected;outer['message']['content']=c.wire(obj).decode();raws[fs]=c.wire(outer)
        self.assertEqual(d.data_from(d.request_for(self.p,op,raws))['allocated_node_id'],expected)
    def test_prior_source_178_files_byte_identical(self):
        with zipfile.ZipFile(BASE) as z:old={n[7:]:z.read(n) for n in z.namelist() if n.startswith('source/')}
        now={p.relative_to(c.ROOT/'frozen090').as_posix():p.read_bytes() for p in (c.ROOT/'frozen090').rglob('*') if p.is_file() and '__pycache__' not in p.parts}
        self.assertEqual(old,now);self.assertEqual(len(old),178)
    def test_actual_v090_all_3520_requests_byte_identical(self):
        with zipfile.ZipFile(BASE) as z:
            names=set(z.namelist());old=c.load(z.read('plan.json'))
            raw={"o_"+o['id']:z.read('wire/'+o['id']+'/response.raw.json') for o in old['slots'] if 'wire/'+o['id']+'/response.raw.json' in names}
            n=0
            for op in self.p['slots']:
                if d.trial_for(self.p,op)['cohort']!='known_original':continue
                name='wire/'+op['id'][2:]+'/request.wire.json'
                if name in names:self.assertEqual(c.wire(d.request_for(self.p,op,raw)),z.read(name),op['id']);n+=1
        self.assertEqual(n,3520)
    def test_previous_evidence_validation(self):
        r=b.validate_inputs(BASE,True);self.assertTrue(r['prior_receipt']['verified']);self.assertEqual(r['old_responses_reused_as_facts'],0)
    def test_only_eight_new_structures(self):self.assertTrue(c.spec()['holdout']);self.assertEqual(c.spec()['new_independent_structures'],8);self.assertEqual(c.spec()['distinct_structures'],16)
    def test_python312_syntax(self):
        for p in c.ROOT.rglob('*.py'):ast.parse(p.read_text(encoding='utf-8-sig'),filename=str(p),feature_version=(3,12))
    def test_audit_modules_do_not_import_production(self):
        banned={'core091','design091','rows091','report091','measure','stages'}
        for name in ('audit091.py','audit_rows091.py','audit_metrics091.py','verify091.py','audit_corpus091.py'):
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
