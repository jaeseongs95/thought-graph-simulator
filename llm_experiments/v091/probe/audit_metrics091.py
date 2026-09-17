"""공유 집계의 핵심 수치를 별도 루프로 재계산한다. tables091은 import하지 않는다."""
from audit_bytes091 import same,need


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


def check_cohort(plan,rows,summary,state):
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


def check_aggregate(plan,rows,summary,state):
    s=plan['protocol'];need(set(summary['cohorts'])==set(s['cohorts']),'cohort keys')
    for cohort in s['cohorts']:
        rr=[r for r in rows if r['cohort']==cohort];pids={r['problem_id'] for r in rr}
        view=dict(plan,protocol=dict(s,problems=[p for p in s['problems'] if p['id'] in pids]))
        check_cohort(view,rr,summary['cohorts'][cohort],state)
    need(same(summary['primary'],dict(summary['cohorts']['new_topology']['primary'],cohort='new_topology')),'primary excludes known/renaming')
    for result in summary['renaming_contrasts']:
        arm=result['generator_arm'];rr=[r for r in rows if r['generator_arm']==arm and r['cohort']!='new_topology']
        bucket={}
        for r in rr:
            key=(r['topology_id'],r['seed'],r['order'],r['labels'],r['condition'])
            bucket.setdefault(key,{})[r['cohort']]=r['end_to_end_success']
        counts={};table=[];bys={}
        for k,value in sorted(bucket.items()):
            x=value['known_original'];y=value['known_renamed']
            label='unobserved' if x is None or y is None else 'both_success' if x and y else 'original_only' if x else 'renamed_only' if y else 'both_failure'
            counts[label]=counts.get(label,0)+1
            table.append(dict(topology_id=k[0],seed=k[1],order=k[2],labels=k[3],condition=k[4],original=x,renamed=y))
            bys.setdefault(k[:4],{}).update({k[4]:(x,y)})
        need(same(result['outcomes'],counts) and same(result['paired_trials'],table),'renaming paired trials')
        delta=[]
        for topology in sorted({k[0] for k in bys}):
            left=[];right=[]
            for k,vals in bys.items():
                if k[0]!=topology:continue
                need(set(vals)=={'shallow','deep'},'renaming directions')
                left.append(conjunction(v[0] for v in vals.values()));right.append(conjunction(v[1] for v in vals.values()))
            delta.append(None if None in left+right else (sum(right)-sum(left))/len(left))
        expected=None if state!='complete' or None in delta else sum(delta)/len(delta)
        need(same(result['mean_delta'],expected),'renaming structure-equal mean')
    need(len(summary['pairs'])==768 and len(summary['robust'])==192,'whole pair/bundle counts')
    return dict(checked=True,cohorts=3,pairs=768,robust=192)
