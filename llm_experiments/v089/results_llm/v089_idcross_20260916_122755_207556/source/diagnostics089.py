"""원응답·최초 실패·유효 prefix 위험집합을 구분하는 사전 진단. 집계기는 공유한다."""
from collections import Counter, defaultdict
from copy import deepcopy
from audit_bytes089 import load, dump, digest
from tables089 import first_error
FIELDS = ('prompt_eval_count','eval_count','total_duration','prompt_eval_duration','eval_duration')

def _features(problem, route, rid):
    rules = {r['id']:r for r in problem['rules']}
    ancestry = {atom:set() for atom in problem['facts']}
    for current in route:
        r = rules[current]
        ancestry[r['conclusion']] = set(r['premises']).union(*(ancestry[a] for a in r['premises']))
    premises = rules[rid]['premises']
    return dict(premise_count=len(premises), has_ancestor_among_direct_premises=any(
        a != b and a in ancestry[b] for a in premises for b in premises))

def collect(plan, requests, responses, rows):
    trials = {t['id']:t for t in plan['trials']}
    rowmap = {r['trial_id']:r for r in rows}
    groups = defaultdict(lambda:dict(requests=0,unique=set(),without_seed=set(),
        usage={k:dict(sum=0,missing=0) for k in FIELDS}))
    states, missing, initial, rule_checks = [], [], [], []
    for slot in plan['slots']:
        sid = slot['id']
        if sid not in requests:
            continue
        t = trials[slot['trial_id']]
        arm = 'shared_selection' if slot['stage'] in ('compare','select') else t['generator_arm']
        key = t['phase']+'/'+arm+'/'+slot['stage']
        body = load(requests[sid])
        payload = load(body['messages'][0]['content'].split('\n\ninput: ',1)[1])
        group = groups[key]
        group['requests'] += 1
        group['unique'].add(digest(requests[sid]))
        reduced = deepcopy(body)
        reduced['options'].pop('seed',None)
        group['without_seed'].add(digest(dump(reduced)))
        try:
            outer = load(responses.get(sid,b''))
        except (ValueError,UnicodeError):
            outer = {}
        if not isinstance(outer,dict):
            outer = {}
        for field in FIELDS:
            value = outer.get(field)
            if type(value) is int and value >= 0:
                group['usage'][field]['sum'] += value
            else:
                group['usage'][field]['missing'] += 1
        if slot['stage'] != 'rule':
            continue
        nodes, unreadable = [], []
        for h in payload['history']:
            try:
                x = load(h['content'])
                ns = x['nodes'] if 'nodes' in x else [x['node']]
                nodes.extend(n for n in ns if isinstance(n,dict))
            except (ValueError,TypeError,KeyError,UnicodeError):
                unreadable.append(h['source_slot_id'])
        ids = [n.get('id') for n in nodes]
        atoms = [n.get('atom') for n in nodes]
        states.append(dict(slot_id=sid,trial_id=t['id'],phase=t['phase'],arm=arm,
            rule_position=slot['rule_position'],prefix_nodes=len(nodes),
            prior_id_equals_atom=sum(n.get('id')==n.get('atom') for n in nodes),
            unreadable_sources=unreadable))
        if t['phase']=='continuation' and slot['rule_position']==0:
            initial.append(dict(trial_id=t['id'],unit_id=t['unit_id'],problem_id=t['problem_id'],seed=t['seed'],
                condition=t['condition'],initial_id_style=t['initial_id_style'],output_id_style=t['output_id_style'],
                initial_ids=ids,initial_atoms=atoms,current_allocated_id=payload['allocated_node_id']))
        try:
            parents = load(outer['message']['content'])['node']['parents']
        except (KeyError,TypeError,ValueError,UnicodeError):
            parents = None
        if isinstance(parents,list):
            absent = [p for p in parents if p not in ids]
            if absent:
                missing.append(dict(slot_id=sid,phase=t['phase'],arm=arm,missing_ids=absent,
                    missing_all_match_existing_atoms=all(p in atoms for p in absent)))
        row = rowmap[t['id']]
        check = next((c for c in row['step_checks'] if c['id']==sid),None)
        if check is not None:
            rid = payload['operation']['requested_rule_id']
            features = _features(payload['problem'],payload['provided_route_plan']['rule_ids'],rid)
            rule_checks.append(dict(slot_id=sid,trial_id=t['id'],phase=t['phase'],arm=arm,
                problem_id=t['problem_id'],seed=t['seed'],condition=t['condition'],
                rule_position=slot['rule_position'],features=features,check=check))
    risks = defaultdict(lambda:dict(eligible=0,observed=0,success=0,failure=0,unobserved=0))
    first_failures=[]
    for r in rows:
        if r['phase']!='continuation':
            continue
        prefix_valid = True
        for step in r['step_checks']:
            if step['stage']=='rule':
                position=int(step['id'].rsplit('_',1)[1])
                risk=risks[(r['generator_arm'],position)]
                if prefix_valid:
                    risk['eligible']+=1
                    if step['status']=='ok':
                        risk['observed']+=1
                        good=step['valid'] is True and step['support_contract_success'] is True
                        risk['success' if good else 'failure']+=1
                    elif step['status'] in ('invalid_json','invalid_schema'):
                        risk['observed']+=1; risk['failure']+=1
                    else:
                        risk['unobserved']+=1
            if not (step['status']=='ok' and step['valid'] is True and step['support_contract_success'] is True):
                if prefix_valid:
                    first_failures.append(dict(trial_id=r['trial_id'],arm=r['generator_arm'],problem_id=r['problem_id'],
                        seed=r['seed'],condition=r['condition'],first_slot=step['id'],stage=step['stage'],
                        status=step['status'],errors=step.get('error_codes'),first_error_class=first_error(r)))
                prefix_valid=False
    serialized={key:dict(requests=g['requests'],unique_with_seed=len(g['unique']),unique_without_seed=len(g['without_seed']),usage=g['usage'])
                for key,g in sorted(groups.items())}
    certificates=[]
    by_unit=defaultdict(dict)
    for item in initial:
        by_unit[(item['unit_id'],item['output_id_style'])][item['initial_id_style']]=item
    for (unit,output), cells in sorted(by_unit.items()):
        if len(cells)!=4:
            continue
        values=list(cells.values())
        certificates.append(dict(unit_id=unit,output_id_style=output,
            same_initial_atom_order=all(x['initial_atoms']==values[0]['initial_atoms'] for x in values),
            same_current_output_id=len({x['current_allocated_id'] for x in values})==1))
    return dict(contract='v089-diagnostics-r1',groups=serialized,input_states=states,
        missing_parent_aliases=missing,initial_conditions=initial,allocation_invariance=certificates,
        rule_checks=rule_checks,first_failures=first_failures,
        step_risk_sets=[dict(arm=arm,rule_position=pos,**values) for (arm,pos),values in sorted(risks.items())],
        limitations=['risk set은 직전까지 모든 의미/지원 계약이 유효한 경로만 포함한다.',
            '규칙 오류 수와 최초 오류 graph 수를 합산하지 않는다. 전송/미관측은 논리 오답과 별도다.',
            '응답 사용량 합은 wall-clock 또는 API 청구액이 아니다.',
            '원응답과 모델이 생성한 history는 사후 수정하지 않는다.'])

def render(d):
    lines=['# v089 원문·최초 실패·연속 참조 진단','',
        f"없는 부모 ID를 출력한 규칙: {len(d['missing_parent_aliases'])}",
        f"최초 비정상 단계가 있는 연속 graph: {len(d['first_failures'])}",'',
        '| 군 | 규칙 위치(0부터) | 직전 유효 | 관측 | 성공 | 실패 | 미관측 |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for x in d['step_risk_sets']:
        lines.append(f"| {x['arm']} | {x['rule_position']} | {x['eligible']} | {x['observed']} | {x['success']} | {x['failure']} | {x['unobserved']} |")
    return '\n'.join(lines+['']+d['limitations'])+'\n'
