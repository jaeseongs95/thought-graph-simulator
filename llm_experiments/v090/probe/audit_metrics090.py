"""공유 집계의 핵심 수치를 별도 루프로 재계산한다. tables090은 import하지 않는다."""
from audit_bytes090 import same,need


def tally(values):
    n=yes=no=missing=0
    for v in values:
        n+=1
        if v is True:yes+=1
        elif v is False:no+=1
        elif v is None:missing+=1
        else:raise ValueError('invalid tri-state')
    return {'planned':n,'success':yes,'failure':no,'unobserved':missing}


def conjunction(values):
    seen=list(values)
    if False in seen:return False
    if None in seen:return None
    return True


def check_aggregate(plan,rows,summary,state):
    s=plan['protocol'];pairs_by={};robust_by={}
    for arm in s['generator_arms']:
        subset=[r for r in rows if r['generator_arm']==arm]
        group=summary['groups']['end_to_end'][arm]
        for field,key in [('outcome','end_to_end_success'),('graph_semantic','generator_semantic_success'),
            ('support_contract','support_contract_success'),('fresh_facts','initial_fact_success'),('facts_id_contract','initial_id_contract_success')]:
            need(same(group[field],tally(r[key] for r in subset)),'independent group tally '+arm+'/'+field)
        pairs={}
        for r in subset:
            pairs.setdefault(r['base_pair_id'],[]).append(r)
        own=[]
        for base,values in sorted(pairs.items()):
            need(len(values)==2,'independent pair length')
            own.append((values[0]['problem_id'],values[0]['seed'],base,conjunction(x['end_to_end_success'] for x in values)))
        pairs_by[arm]=own
        need(same(group['bidirectional'],tally(x[3] for x in own)),'independent pair tally')
        robust={}
        for pid,seed,base,okay in own:
            robust.setdefault((pid,seed),[]).append(okay)
        outcomes=[conjunction(vals) for vals in robust.values()]
        need(all(len(vals)==4 for vals in robust.values()),'independent four-display assignment')
        need(same(group['four_display'],tally(outcomes)),'independent four-display tally')
        for p in s['problems']:
            expected={'outcome':tally(r['end_to_end_success'] for r in subset if r['problem_id']==p['id']),
                      'bidirectional':tally(x[3] for x in own if x[0]==p['id'])}
            need(same(group['per_structure'][p['id']],expected),'independent structural tally')
    unique={}
    for r in rows:
        if r['unit_id'] in unique:
            need(unique[r['unit_id']] is r['selection_success'],'shared selection divergence')
        unique[r['unit_id']]=r['selection_success']
    need(same(summary['shared_selection'],tally(unique.values())),'shared selection counted once')
    for left,right,actual in [(s['primary_comparison'][0],s['primary_comparison'][1],summary['primary'])]+[(a,b,v) for (a,b),v in zip(s['secondary_comparisons'],summary['secondary'])]:
        ds=[]
        for p in s['problems']:
            aa=[x[3] for x in pairs_by[left] if x[0]==p['id']]
            bb=[x[3] for x in pairs_by[right] if x[0]==p['id']]
            need(len(aa)==len(bb)==8,'8 paired assignments per structure')
            ds.append(None if None in aa or None in bb else (sum(x is True for x in bb)-sum(x is True for x in aa))/8)
        expected=None if state!='complete' or None in ds else sum(ds)/8
        need(same(actual['mean_delta'],expected),'independent effect')
        need(same([v['delta'] for v in actual['per_structure']],ds),'independent structure effects')
    need(len(summary['pairs'])==256 and len(summary['robust'])==64,'pair/bundle totals')
    return {'checked':True,'independent_group_arms':4,'independent_pairs':256,'independent_robust_bundles':64,'independent_contrasts':6}
