"""Offline preparation freezes audited source bytes and exact replay schedule."""
from copy import deepcopy
from .contracts import *
from .design import MODELS, MODES, SEQUENCES, BOUNDARY_CELLS, MAX_CALLS, POLICY, PROBLEMS, ARMS, DIRECTIONS, RULE_ORDERS, schedule, actions
from . import __version__

def make_plan(reference):
    p = {'contract': 'order-replay-v058-r1', 'software_version': __version__, 'created_at': utc_now(),
         'reference': deepcopy(reference), 'baseline': {'config': deepcopy(reference['config'])},
         'identities': deepcopy(reference['identities']), 'model_keys': list(MODELS), 'modes': list(MODES),
         'sequences': list(SEQUENCES), 'boundary_cells': deepcopy(BOUNDARY_CELLS), 'problems': deepcopy(PROBLEMS),
         'arms': list(ARMS), 'directions': ['shallow'], 'rule_orders': deepcopy(RULE_ORDERS),
         'seeds': deepcopy(reference['seeds']), 'max_calls': MAX_CALLS, 'policy': deepcopy(POLICY),
         'slots': schedule(reference), 'source_fingerprint': source_fingerprint()}
    p['actions'] = actions(p['slots'])
    p['plan_sha256'] = digest(p)
    validate_plan(p)
    return p

def prepare(bundle, out):
    from .evidence import import_v057
    require(not out.exists() and not out.with_suffix('.baseline.zip').exists(), 'Existing plan/baseline preserved')
    reference = import_v057(bundle)
    p = make_plan(reference)
    raw = bundle.read_bytes()
    require(sha(raw) == reference['bundle_sha256'], 'Baseline changed during preparation')
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.with_suffix('.baseline.zip').open('xb') as f:
        f.write(raw)
    write_json(out, p, exclusive=True)
    require(canonical(read_plan_json(out)) == canonical(p), 'Plan round-trip mismatch')
    return p

def validate_plan(p, *, check_sources=True):
    fields = {'contract','software_version','created_at','reference','baseline','identities','model_keys','modes','sequences',
              'boundary_cells','problems','arms','directions','rule_orders','seeds','max_calls','policy','slots','source_fingerprint','actions','plan_sha256'}
    require(isinstance(p,dict) and set(p)==fields, 'Plan fields')
    require(p['contract']=='order-replay-v058-r1' and p['software_version']==__version__, 'Plan contract/version')
    require(p['plan_sha256']==digest({k:v for k,v in p.items() if k!='plan_sha256'}), 'Plan hash')
    ref = p['reference']
    fields = {'contract','bundle_sha256','plan_sha256','event_tip','recorded_calls','selected_calls','evidence_kind','config',
              'identities','seeds','slots','request_bank','response_bank','independent_compared_fields','receipt_sha256'}
    require(isinstance(ref,dict) and set(ref)==fields and ref['contract']=='audited-v057-boundary-r1','Reference fields/contract')
    require(ref['receipt_sha256']==digest({k:v for k,v in ref.items() if k!='receipt_sha256'}),'Reference receipt hash')
    require(type(ref['recorded_calls']) is int and ref['recorded_calls']==480 and type(ref['selected_calls']) is int and ref['selected_calls']==40,'Reference counts')
    require(len(ref['seeds'])==10 and len(set(ref['seeds']))==10 and all(type(s) is int for s in ref['seeds']),'Ten unique integer seeds')
    require(len(ref['slots'])==40 and len({s['id'] for s in ref['slots']})==40,'Reference slot duplicates/count')
    ids = {s['id'] for s in ref['slots']}
    require(set(ref['request_bank'])==ids and set(ref['response_bank'])==ids,'Reference banks')
    require(set(ref['identities'])==set(MODELS),'Two identities')
    require(ref['identities']['reference']['digest']!=ref['identities']['candidate']['digest'],'Duplicate model identity')
    require(ref['evidence_kind'] in ('live_source_artifacts','synthetic_fixture'),'Evidence kind')
    require(type(ref['independent_compared_fields']) is int and ref['independent_compared_fields']>0,'Independent baseline evidence')
    seen = set()
    for s in ref['slots']:
        require(s['model_key'] in MODELS and s['mode'] in MODES and s['seed'] in ref['seeds'],'Reference condition')
        require(all(s[k]==v for k,v in BOUNDARY_CELLS[s['model_key']].items()),'Boundary cell changed')
        key=(s['model_key'],s['seed'],s['mode']);require(key not in seen,'Duplicate condition');seen.add(key)
        q=strict_json(unb64(ref['request_bank'][s['id']]))
        require(q['model']==ref['identities'][s['model_key']]['model'] and q['options']['seed']==s['seed'],'Source model/seed')
        require(len(q['messages'])==1 and set(q['messages'][0])=={'role','content'} and q['messages'][0]['role']=='user','Merged source message')
        unb64(ref['response_bank'][s['id']])
    expected={'baseline':{'config':ref['config']},'identities':ref['identities'],'model_keys':list(MODELS),'modes':list(MODES),
        'sequences':list(SEQUENCES),'boundary_cells':BOUNDARY_CELLS,'problems':PROBLEMS,'arms':list(ARMS),
        'directions':['shallow'],'rule_orders':RULE_ORDERS,'seeds':ref['seeds'],'max_calls':MAX_CALLS,'policy':POLICY,'slots':schedule(ref)}
    expected['actions']=actions(expected['slots'])
    for k,v in expected.items(): require(canonical(p[k])==canonical(v),'Frozen condition changed: '+k)
    require(len(p['slots'])==80 and len(p['actions'])==120,'Experiment size')
    if check_sources: require(p['source_fingerprint']==source_fingerprint(),'Source changed since plan freeze')
