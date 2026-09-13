"""v058 ZIP을 생산 요청·채점·집계 모듈 import 없이 검산한다."""
from __future__ import annotations

import argparse
import base64
import collections
import io
import json
import statistics
import sys
import tempfile
import urllib.parse
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
DEPENDENCY_ROOT = ROOT.parents[1] / 'v057' / 'probe'
sys.path.insert(0, str(DEPENDENCY_ROOT / 'tools'))
from independent_graph_forensic import need, load, canonical, sha, inspect, extract_payload
from independent_verify_v057 import verify as baseline_verify, choice, problem_depths
from independent_verify_v056 import metadata as legacy_metadata

MODELS = ('reference', 'candidate')
MODES = ('graph', 'choice')
OUTCOMES = ('both_success', 'first_only', 'second_only', 'neither', 'unmeasured', 'unobserved')
POLICY_SHA256 = '65af2e8507623dea811020879b9b928f825773d7f747689687f63fdc960406bc'


def _stable_identity(value):
    fields = {'model','digest','show_sha256','server','details','template','parameters','model_info'}
    if not isinstance(value,dict) or set(value) != fields:
        return None
    parameters = value['parameters']
    if parameters is not None and not isinstance(parameters,str):
        return None
    result = {key:value[key] for key in fields-{'show_sha256','parameters'}}
    result['parameter_lines'] = None if parameters is None else sorted(parameters.split('\n'))
    return result


def metadata(record, expected):
    """Independently allow only /api/show parameter-line permutations."""
    failure = legacy_metadata(record,expected)
    if failure != 'runtime_identity_error':
        return failure
    try:
        items=record['requests'];names=('server','tags','show');data={}
        for i,item in enumerate(items):
            raw=base64.b64decode(item['response_b64'],validate=True)
            data[names[i]]=load(raw)
        tags=[tag for tag in data['tags']['models']
              if tag.get('name')==expected['model'] or tag.get('model')==expected['model']]
        if len(items)!=3 or len(tags)!=1:
            return failure
        show=data['show']
        got={'model':expected['model'],'digest':tags[0]['digest'],'show_sha256':sha(canonical(show)),
             'server':data['server'],'details':show.get('details',tags[0].get('details',{})),
             'template':show.get('template'),'parameters':show.get('parameters'),
             'model_info':show.get('model_info',{})}
        stable_got=_stable_identity(got);stable_expected=_stable_identity(expected)
        return None if stable_got is not None and canonical(stable_got)==canonical(stable_expected) else failure
    except (KeyError,IndexError,TypeError,ValueError,UnicodeError):
        return failure


def unpack(raw):
    need(len(raw) <= 100 * 1024**2, 'archive size')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        infos = z.infolist()
        need(0 < len(infos) <= 12000 and sum(i.file_size for i in infos) <= 256*1024**2, 'archive expansion')
        seen = set()
        reserved = {'CON','PRN','AUX','NUL','CLOCK$','CONIN$','CONOUT$'} | {p+str(i) for p in ('COM','LPT') for i in range(1,10)}
        for i in infos:
            n = i.filename
            p = PurePosixPath(n)
            need(not i.is_dir() and bool(n) and not p.is_absolute() and p.as_posix() == n
                 and '\\' not in n and ':' not in n and all(x not in ('.','..') for x in p.parts), 'archive path')
            need(n.casefold() not in seen, 'duplicate/case ZIP member')
            seen.add(n.casefold())
            need(all(not x.endswith((' ','.')) and x.split('.')[0].upper() not in reserved
                     and not any(ord(c)<32 or c in '<>"|?*' for c in x) for x in p.parts), 'Windows path')
            need(((i.external_attr >> 16) & 0o170000) != 0o120000 and not i.flag_bits & 1, 'archive link/encryption')
            limit = 8*1024**2
            if n in ('external_plan/v058.plan.json','run/plan.snapshot.json'):
                limit = 32*1024**2
            if n == 'run/baseline/v057_evidence.zip':
                limit = 100*1024**2
            need(i.file_size <= limit, 'member size: ' + n)
        need('BUNDLE_MANIFEST.json' in seen or any(i.filename == 'BUNDLE_MANIFEST.json' for i in infos), 'manifest absent')
        data = {i.filename: z.read(i.filename) for i in infos}
    manifest = load(data.pop('BUNDLE_MANIFEST.json'))
    need(set(manifest['file_hashes']) == set(data), 'manifest member set')
    for name, content in data.items():
        need(sha(content) == manifest['file_hashes'][name], 'manifest hash: ' + name)
    return data, manifest


def schedule(source):
    by_cell = {(s['model_key'],s['seed'],s['mode']):s for s in source['slots']}
    need(len(by_cell) == 40 == len(source['slots']), '40 unique source cells')
    slots = []
    for i, seed in enumerate(source['seeds']):
        for j, model in enumerate(MODELS if i % 2 == 0 else MODELS[::-1]):
            sequences = ('graph_choice','choice_graph') if i % 2 == 0 else ('choice_graph','graph_choice')
            for sequence in sequences:
                for pos, mode in enumerate(sequence.split('_')):
                    old = by_cell[model,seed,mode]
                    prior = slots[-1] if slots else None
                    slots.append({**old, 'id':sequence+'__'+old['id'], 'reference_slot_id':old['id'],
                                  'task':'order_replay','stage':mode,'block':2*i+j,'seed_index':i,
                                  'sequence':sequence,'position_in_group':pos,'position':len(slots),
                                  'previous_call_id':prior['id'] if prior else None,
                                  'previous_call_mode':prior['mode'] if prior else None})
    actions = []
    for block in range(20):
        block_slots = slots[4*block:4*block+4]
        key = block_slots[0]['model_key']
        actions.append({'kind':'metadata','id':f'b{block:02d}.before','block':block,'model_key':key})
        actions.extend({'kind':'call','id':s['id'],'slot':s} for s in block_slots)
        actions.append({'kind':'metadata','id':f'b{block:02d}.after','block':block,'model_key':key})
    return slots, [dict(a,index=i) for i,a in enumerate(actions)]


def verify(bundle):
    raw_bundle = bundle.read_bytes()
    data, manifest = unpack(raw_bundle)
    need(manifest['contract'] == 'v058-evidence-bundle-r1', 'bundle contract')
    p = load(data['external_plan/v058.plan.json'])
    r = load(data['run/summary.json'])
    status = load(data['run/status.json'])
    runm = load(data['run/run_manifest.json'])
    need(set(p)=={'contract','software_version','created_at','reference','baseline','identities','model_keys','modes','sequences',
                  'boundary_cells','problems','arms','directions','rule_orders','seeds','max_calls','policy','slots',
                  'source_fingerprint','actions','plan_sha256'}, 'plan exact fields')
    need(set(runm)=={'contract','plan_sha256','source_fingerprint','started_at','python','platform','endpoint','evidence_kind',
                     'new_model_inference','max_calls','retry_policy','warmup_calls'}, 'run manifest exact fields')
    need(set(status)=={'state','complete','recorded_actions','inference_calls','event_tip','active_action','failure_stage',
                       'failure_kind','failure_slot_id','error','finished_at'}, 'status exact fields')
    need(p == load(data['run/plan.snapshot.json']), 'plan snapshot')
    need(p['contract'] == 'order-replay-v058-r1' and p['software_version']=='0.58.0'
         and type(p['max_calls']) is int and p['max_calls'] == 80, 'design contract/version')
    need(type(manifest['data_complete']) is bool, 'manifest complete type')
    need(p['plan_sha256'] == sha(canonical({k:v for k,v in p.items() if k!='plan_sha256'})), 'plan hash')
    need(manifest['plan_sha256'] == p['plan_sha256'] and manifest['data_complete'] is status['complete'], 'manifest state')
    baseline = data['run/baseline/v057_evidence.zip']
    need(sha(baseline) == p['reference']['bundle_sha256'], 'baseline bytes')
    with tempfile.TemporaryDirectory(prefix='v058_independent_') as td:
        prior_path = Path(td)/'baseline.zip'
        prior_path.write_bytes(baseline)
        baseline_result = baseline_verify(prior_path)
        need(baseline_result['complete'] is True and baseline_result['differences']==[]
             and type(baseline_result['observed_calls']) is int and baseline_result['observed_calls']==480,
             'complete verified 480-call baseline required')
        with zipfile.ZipFile(io.BytesIO(baseline)) as z:
            bp = load(z.read('external_plan/v057.plan.json'))
            br = load(z.read('run/summary.json'))
            selected = [s for s in bp['slots'] if s['arm']=='original' and s['direction']=='shallow'
                        and s['problem_id']==('T02' if s['model_key']=='reference' else 'K01')]
            ref = {'contract':'audited-v057-boundary-r1','bundle_sha256':sha(baseline),'plan_sha256':bp['plan_sha256'],
                   'event_tip':br['event_tip'],'recorded_calls':480,'selected_calls':40,'evidence_kind':br['evidence_kind'],
                   'config':bp['baseline']['config'],'identities':bp['identities'],'seeds':bp['seeds'],'slots':selected,
                   'request_bank':{s['id']:base64.b64encode(z.read(f"run/calls/{s['id']}/request.wire.json")).decode() for s in selected},
                   'response_bank':{s['id']:base64.b64encode(z.read(f"run/calls/{s['id']}/response.raw.json")).decode() for s in selected},
                   'independent_compared_fields':baseline_result['compared_fields']}
    ref['receipt_sha256'] = sha(canonical(ref))
    need(canonical(p['reference']) == canonical(ref), 'reference receipt reconstruction')
    need(canonical(p['identities'])==canonical(bp['identities']) and canonical(p['seeds'])==canonical(bp['seeds'])
         and canonical(p['baseline'])==canonical(bp['baseline']), 'inherited identity/config/seed')
    need(p['model_keys']==list(MODELS) and p['modes']==list(MODES) and p['directions']==['shallow'], 'design axes')
    need(p['boundary_cells']=={'reference':{'problem_id':'T02','arm':'original','direction':'shallow'},
                              'candidate':{'problem_id':'K01','arm':'original','direction':'shallow'}}, 'boundary cells')
    for k in ('problems','arms','rule_orders'):
        need(p[k] == bp[k], 'inherited specification: '+k)
    need(p['sequences']==['graph_choice','choice_graph'], 'sequences')
    need(all(p['policy'][k] is False for k in ('retry','repair','host_answer_fill','download_models')), 'execution policy')
    need(sha(canonical(p['policy']))==POLICY_SHA256, 'frozen policy text')
    slots, actions = schedule(ref)
    need(canonical(p['slots'])==canonical(slots) and canonical(p['actions'])==canonical(actions), 'reconstructed schedule')
    fingerprint = p['source_fingerprint']
    trusted = {}
    for source_root, logical_root in ((DEPENDENCY_ROOT, 'v057_selection_probe'),
                                      (ROOT, 'v058_order_replay')):
        for path in sorted(source_root.rglob('*.py')):
            need(not path.is_symlink(), 'trusted source symlink')
            trusted[logical_root+'/'+path.relative_to(source_root).as_posix()]=sha(path.read_bytes())
    need(fingerprint==trusted, 'complete trusted source fingerprint')
    need(runm['source_fingerprint']==fingerprint and runm['plan_sha256']==p['plan_sha256'], 'run binding')
    snapnames = {n.removeprefix('run/source_snapshot/') for n in data if n.startswith('run/source_snapshot/')}
    need(snapnames==set(fingerprint), 'snapshot file set')
    for name, h in fingerprint.items():
        need(sha(data['run/source_snapshot/'+name])==h, 'snapshot bytes: '+name)
    need(runm['contract']=='v058-run-manifest-r1' and type(runm['max_calls']) is int and runm['max_calls']==80
         and runm['retry_policy']=='none' and type(runm['warmup_calls']) is int and runm['warmup_calls']==0, 'run policy')
    endpoint=urllib.parse.urlsplit(p['baseline']['config']['endpoint'])
    need(endpoint.scheme in ('http','https') and endpoint.hostname in ('localhost','127.0.0.1','::1')
         and not endpoint.username and not endpoint.password and not endpoint.query and not endpoint.fragment
         and endpoint.path.rstrip('/') in ('','/api/chat'), 'source loopback endpoint')
    need(runm['endpoint']==urllib.parse.urlunsplit((endpoint.scheme,endpoint.netloc,'','','')), 'runtime endpoint binding')
    need(runm['evidence_kind']==ref['evidence_kind'] and runm['new_model_inference'] is (ref['evidence_kind']!='synthetic_fixture'), 'source label')
    need(type(status['complete']) is bool and status['complete'] is (status['state']=='complete'), 'state/complete')
    need(status['state'] in ('complete','incomplete','interrupted'), 'finished state')
    for k in ('inference_calls','recorded_actions'):
        need(type(status[k]) is int and status[k]>=0, 'status count type')
    lines = data['run/events.jsonl'].splitlines()
    need(all(line.strip() for line in lines), 'blank event')
    events = [load(x) for x in lines]
    need(len(events)==status['recorded_actions'] and len(events)<=120, 'action count')
    trials = r['trials']
    need(len(trials)==80 and [t['id'] for t in trials]==[s['id'] for s in slots], 'report trial order/duplicates')
    stored = {t['id']:t for t in trials}
    fields = 0
    def eq(label,a,b):
        nonlocal fields
        fields += 1
        need(canonical(a)==canonical(b), 'independent mismatch: '+label)
    expected_files = {'external_plan/v058.plan.json','run/plan.snapshot.json','run/run_manifest.json','run/status.json',
                      'run/events.jsonl','run/baseline/v057_evidence.zip','run/summary.json','run/audit.json','run/summary.ko.md'}
    expected_files |= {'run/source_snapshot/'+n for n in fingerprint}
    observed = {}
    tip = p['plan_sha256']
    failed = None
    metadata_count = 0
    call_rows = []
    independent_calls = []
    for i,e in enumerate(events):
        a = actions[i]
        event_fields={'action','at','previous_hash','event_hash'}
        event_fields |= {'metadata_sha256'} if a['kind']=='metadata' else {'request_sha256','response_sha256','http_status','transport_error','elapsed_ns'}
        need(set(e)==event_fields, 'event exact fields')
        need(canonical(e['action'])==canonical(a) and e['previous_hash']==tip, 'action order/hash link')
        need(e['event_hash']==sha(canonical({k:v for k,v in e.items() if k!='event_hash'})), 'event hash')
        tip = e['event_hash']
        failure = None
        if a['kind']=='metadata':
            name = f"run/metadata/{a['id']}.json"
            expected_files.add(name)
            need(sha(data[name])==e['metadata_sha256'], 'metadata bytes')
            failure = metadata(load(data[name]), p['identities'][a['model_key']])
            metadata_count += 1
        else:
            s = a['slot']
            sid = s['id']
            reqname = f'run/calls/{sid}/request.wire.json'
            resname = f'run/calls/{sid}/response.raw.json'
            expected_files.update((reqname,resname))
            qraw, response = data[reqname],data[resname]
            need(qraw==base64.b64decode(ref['request_bank'][s['reference_slot_id']],validate=True), 'exact request replay')
            need(sha(qraw)==e['request_sha256'] and sha(response)==e['response_sha256'], 'call bytes')
            need(type(e['http_status']) is int and 0<=e['http_status']<=599 and type(e['elapsed_ns']) is int and e['elapsed_ns']>=0, 'HTTP fields')
            need(e['transport_error'] is None or isinstance(e['transport_error'],str), 'transport field')
            q = load(qraw)
            model = p['identities'][s['model_key']]['model']
            problem = load(q['messages'][0]['content'].rsplit('\n\nproblem: ',1)[1])
            payload = extract_payload(response,model)
            if e['http_status']!=200 or e['transport_error'] is not None:
                failure,payload='transport_error',None
            else:
                try:
                    env=load(response)
                    if isinstance(env,dict) and isinstance(env.get('model'),str) and env['model']!=model:
                        failure,payload='response_identity_error',None
                except (ValueError,UnicodeError):
                    pass
            m = inspect(problem,payload) if s['mode']=='graph' else choice(problem,payload)
            valid = (m['strict_valid'] if s['mode']=='graph' else m['choice_valid']) if m['format_valid'] else None
            depth = m['D'] if s['mode']=='graph' else m['implied_depth']
            success = bool(valid is True and depth==min(problem_depths(problem).values())) if m['format_valid'] else None
            keys = ('format_valid','proof_valid','strict_valid','D','final_ref_valid') if s['mode']=='graph' else ('format_valid','proof_valid','strict_valid','D','choice_valid','selected_rule_id','implied_depth')
            t = stored[sid]
            eq(sid+'/slot',{k:t[k] for k in s},s)
            for k in keys:
                eq(sid+'/'+k,t['measurement'][k],m[k])
            eq(sid+'/task_valid',t['measurement']['task_valid'],valid)
            eq(sid+'/shallow_success',t['measurement']['shallow_success'],success)
            eq(sid+'/role_match',t['role_match'],success)
            eq(sid+'/observed',t['observed'],True)
            observed[sid]={'slot':s,'m':m,'valid':valid,'success':success}
            call_rows.append(sid)
            try:
                envelope=load(response)
            except (ValueError,UnicodeError):
                envelope={}
            if not isinstance(envelope,dict): envelope={}
            usage_keys=('prompt_eval_count','prompt_eval_cached_count','eval_count','total_duration',
                        'load_duration','prompt_eval_duration','eval_duration')
            cost={k:envelope[k] if type(envelope.get(k)) is int and envelope[k]>=0 else None for k in usage_keys}
            cost.update(done=envelope.get('done') if type(envelope.get('done')) is bool else None,
                        done_reason=envelope.get('done_reason') if isinstance(envelope.get('done_reason'),str) else None)
            current={**s,'http_status':e['http_status'],'elapsed_ns':e['elapsed_ns'],
                     'request_sha256':sha(qraw),'response_sha256':sha(response),**cost}
            eq('call raw-derived metadata',r['calls'][len(independent_calls)],current)
            independent_calls.append(current)
        if failure:
            need(i==len(events)-1 and not status['complete'], 'continue after failure')
            failed=(a,failure)
    need(tip==status['event_tip']==r['event_tip'], 'event tip')
    if status['complete']:
        need(len(events)==120 and len(observed)==80 and metadata_count==40 and status['inference_calls']==80, 'complete counts')
        need(status['active_action'] is None and all(status[k] is None for k in ('failure_stage','failure_kind','failure_slot_id','error')), 'complete failure fields')
    else:
        need(isinstance(status['error'],str) and bool(status['error']), 'failure reason')
        need(len(observed)<=status['inference_calls']<=len(observed)+1, 'partial call count')
        if failed:
            a, failure = failed
            need(status['failure_kind']==failure and status['failure_slot_id']==a['id']
                 and status['failure_stage']==a['kind'] and status['active_action']==a['index']
                 and status['inference_calls']==len(observed), 'recorded failure binding')
        else:
            need(len(events)<120 and status['failure_kind'] in ('execution_error','user_interrupt'), 'unrecorded failure')
            a=actions[len(events)]
            need(status['active_action']==a['index'] and status['failure_slot_id']==a['id'] and status['failure_stage']==a['kind'], 'pending action')
            if a['kind']=='call':
                name=f"run/calls/{a['id']}/request.wire.json"
                if name in data:
                    need(data[name]==base64.b64decode(ref['request_bank'][a['slot']['reference_slot_id']],validate=True), 'pending request')
                    expected_files.add(name)
            else:
                need(status['inference_calls']==len(observed), 'metadata not inference')
    need(set(data)==expected_files, 'unexpected/missing evidence files')
    eq('call order/duplicates',[c['id'] for c in r['calls']],call_rows)
    for s in slots:
        if s['id'] not in observed:
            t=stored[s['id']]
            eq('unobserved',t['observed'],False)
            eq('unobserved measurement',t['measurement'],None)
            eq('unobserved role',t['role_match'],None)
    need(len(r['pairs'])==40 and len({(x['model_key'],x['seed'],x['mode']) for x in r['pairs']})==40, 'pair duplicates/count')
    lookup={(s['model_key'],s['seed'],s['mode'],s['position_in_group']):s['id'] for s in slots}
    pairs={}
    for pair in r['pairs']:
        key,seed,mode=(pair[k] for k in ('model_key','seed','mode'))
        ids=[lookup[key,seed,mode,pos] for pos in (0,1)]
        first,second=[observed.get(sid) for sid in ids]
        both=first is not None and second is not None
        a=first['success'] if first else None
        b=second['success'] if second else None
        measured=both and a is not None and b is not None
        outcome='unobserved' if not both else ('unmeasured' if not measured else ('both_success' if a and b else ('first_only' if a else ('second_only' if b else 'neither'))))
        computed={'first_slot_id':ids[0],'second_slot_id':ids[1],'both_observed':both,'both_measured':measured,
                  'first_success':a,'second_success':b,'outcome':outcome,'second_minus_first':int(b)-int(a) if measured else None,
                  'first_task_valid':first['valid'] if first else None,'second_task_valid':second['valid'] if second else None,
                  'first_D':first['m']['D'] if first else None,'second_D':second['m']['D'] if second else None}
        first_id=first['m'].get('selected_rule_id') if first and mode=='choice' else None
        second_id=second['m'].get('selected_rule_id') if second and mode=='choice' else None
        computed.update(first_selected_rule_id=first_id,second_selected_rule_id=second_id,
                        selected_rule_changed=None if first_id is None or second_id is None else first_id!=second_id)
        for k,v in computed.items(): eq('pair/'+k,pair[k],v)
        pairs[key,seed,mode]=computed
    for key in MODELS:
        for mode in MODES:
            values=[v for (ke,se,mo),v in pairs.items() if (ke,mo)==(key,mode)]
            rows=[v for v in observed.values() if (v['slot']['model_key'],v['slot']['mode'])==(key,mode)]
            counts=collections.Counter(v['outcome'] for v in values)
            measured=sum(v['both_measured'] for v in values)
            summary={'assigned_calls':20,'observed_calls':len(rows),'format_valid':sum(v['m']['format_valid'] for v in rows),
                     'task_valid':sum(v['valid'] is True for v in rows),'task_unmeasured':sum(v['valid'] is None for v in rows),
                     'assigned_pairs':10,'observed_pairs':sum(v['both_observed'] for v in values),'measured_pairs':measured,
                     'order_outcomes':{o:counts[o] for o in OUTCOMES},'discordant_pairs':counts['first_only']+counts['second_only'],
                     'second_minus_first_rate':(counts['second_only']-counts['first_only'])/10 if status['complete'] and measured==10 else None}
            for k,v in summary.items(): eq(key+'/'+mode+'/'+k,r['models'][key]['modes'][mode][k],v)
            if mode=='choice':
                comparable=sum(v['selected_rule_changed'] is not None for v in values)
                changed=sum(v['selected_rule_changed'] is True for v in values)
                for k,v in {'selected_rule_comparable_pairs':comparable,'selected_rule_changed_pairs':changed,
                            'selected_rule_changed_rate':changed/10 if status['complete'] and comparable==10 else None}.items():
                    eq(key+'/'+mode+'/'+k,r['models'][key]['modes'][mode][k],v)
            costs=[c for c in independent_calls if (c['model_key'],c['mode'])==(key,mode)]
            usage={'calls':len(costs)}
            for k in ('prompt_eval_count','prompt_eval_cached_count','eval_count','total_duration',
                      'load_duration','prompt_eval_duration','eval_duration'):
                vs=[c[k] for c in costs]
                usage[k]=sum(vs) if vs and all(v is not None for v in vs) else None
                usage[k+'_missing']=sum(v is None for v in vs)
            elapsed=[c['elapsed_ns']/1e6 for c in costs]
            usage['http_median_ms']=statistics.median(elapsed) if elapsed else None
            usage['http_mean_ms']=statistics.mean(elapsed) if elapsed else None
            eq('execution cost',r['models'][key]['modes'][mode]['unique_execution_usage'],usage)
            for pos in (0,1):
                selected_rows=[v for v in rows if v['slot']['position_in_group']==pos]
                def distribution(field):
                    return dict(collections.Counter(str(v['m'][field]) if v['m'][field] is not None else 'unmeasured' for v in selected_rows))
                group={'model_key':key,'mode':mode,'position_in_group':pos,'assigned':10,'observed':len(selected_rows),
                       'format_valid':sum(v['m']['format_valid'] for v in selected_rows),
                       'task_valid':sum(v['valid'] is True for v in selected_rows),
                       'shallow_success':sum(v['success'] is True for v in selected_rows),
                       'unmeasured_success':sum(v['success'] is None for v in selected_rows),
                       'actual_D_distribution':distribution('D') if mode=='graph' else None,
                       'choice_implied_depth_distribution':distribution('implied_depth') if mode=='choice' else None}
                eq('group',r['groups'][f'{key}/{mode}/{pos}'],group)
        eq('model label',r['models'][key]['model'],p['identities'][key]['model'])
        eq('boundary label',r['models'][key]['boundary_cell'],p['boundary_cells'][key])
    need(set(r['models'])==set(MODELS) and len(r['groups'])==8, 'model/group extras')
    for k,v in {'data_integrity':True,'data_complete':status['complete'],'comparative_analysis_ready':status['complete'],
                'inference_calls':status['inference_calls'],'max_inference_calls':80,'plan_sha256':p['plan_sha256'],
                'source_fingerprint':fingerprint,'reference_bundle_sha256':sha(baseline),'evidence_kind':ref['evidence_kind'],
                'new_model_inference':runm['new_model_inference'],'selective_D_control':None,
                'historical_responses_are_new_observations':False,'assigned_calls':80,'unique_model_seed_blocks':20}.items():
        eq('report/'+k,r[k],v)
    for k in ('failure_kind','failure_stage','failure_slot_id'):
        eq('report/'+k,r[k],status[k])
    eq('report/run_error',r['run_error'],status['error'])
    eq('report/run_state',r['run_state'],status['state'])
    eq('report/contract',r['contract'],'v058-order-replay-report-r1')
    eq('report/policy',r['policy'],p['policy'])
    audit=load(data['run/audit.json'])
    audit_keys=('contract','data_integrity','data_complete','comparative_analysis_ready','inference_calls','max_inference_calls',
                'plan_sha256','event_tip','run_state','failure_stage','failure_kind','failure_slot_id','run_error')
    eq('audit summary',audit,{k:r[k] for k in audit_keys})
    return {'contract':'independent-v058-r1','bundle_sha256':sha(raw_bundle),'complete':status['complete'],
            'observed_calls':len(observed),'metadata_records':metadata_count,'compared_fields':fields,
            'differences':[],'production_imports':False,'baseline_compared_fields':baseline_result['compared_fields'],
            'limitation':'원문·계획·측정 일관성 검산이며 외부 실행 인증이나 캐시 인과 검증은 아니다.'}


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('bundle',type=Path)
    ap.add_argument('--out',type=Path)
    args=ap.parse_args()
    result=verify(args.bundle)
    output=json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n'
    if args.out:
        with args.out.open('x',encoding='utf-8',newline='\n') as f: f.write(output)
    print(output)
