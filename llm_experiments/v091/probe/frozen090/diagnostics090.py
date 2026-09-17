"""원문 기준 최초 오류, facts 계약, 위험집합, 참조 오류 유형 및 계산량 진단."""
from collections import defaultdict
from copy import deepcopy
from audit_bytes090 import load,dump,digest
from tables090 import generation_error
FIELDS=('prompt_eval_count','eval_count','total_duration','prompt_eval_duration','eval_duration')


def features(problem,route,rid):
    rules={r['id']:r for r in problem['rules']}
    parents={rules[k]['conclusion']:rules[k]['premises'] for k in route}
    def ancestors(atom):
        seen=set();todo=list(parents.get(atom,[]))
        while todo:
            x=todo.pop()
            if x not in seen:
                seen.add(x);todo.extend(parents.get(x,[]))
        return seen
    ps=rules[rid]['premises']
    return dict(premise_count=len(ps),has_ancestor_among_direct_premises=any(a!=b and a in ancestors(b) for a in ps for b in ps))


def collect(plan,requests,responses,rows):
    trials={t['id']:t for t in plan['trials']};rowmap={r['trial_id']:r for r in rows}
    groups=defaultdict(lambda:dict(requests=0,unique=set(),without_seed=set(),usage={k:dict(sum=0,missing=0) for k in FIELDS}))
    missing=[];states=[];rule_checks=[];facts=[]
    for slot in plan['slots']:
        sid=slot['id']
        if sid not in requests:continue
        body=load(requests[sid]);data=load(body['messages'][0]['content'].split('\n\ninput: ',1)[1]);t=trials[slot['trial_id']]
        arm='shared_selection' if slot['stage'] in ('compare','select') else t['generator_arm']
        g=groups[arm];g['requests']+=1;g['unique'].add(digest(requests[sid]))
        reduced=deepcopy(body);reduced['options'].pop('seed',None);g['without_seed'].add(digest(dump(reduced)))
        try:outer=load(responses.get(sid,b''))
        except (ValueError,UnicodeError):outer={}
        if not isinstance(outer,dict):outer={}
        for k in FIELDS:
            x=outer.get(k)
            if type(x) is int and x>=0:g['usage'][k]['sum']+=x
            else:g['usage'][k]['missing']+=1
        if slot['stage']=='facts':
            facts.append(dict(trial_id=t['id'],arm=arm,problem_id=t['problem_id'],seed=t['seed'],
                allocated_fact_ids=data.get('allocated_fact_ids'),history_count=len(data['history']),
                semantic_success=rowmap[t['id']]['initial_fact_success'],id_contract_success=rowmap[t['id']]['initial_id_contract_success']))
        if slot['stage']!='rule':continue
        nodes=[];unreadable=[]
        for h in data['history']:
            try:
                obj=load(h['content']);ns=obj['nodes'] if 'nodes' in obj else [obj['node']]
                nodes.extend(n for n in ns if isinstance(n,dict))
            except (ValueError,KeyError,TypeError,UnicodeError):unreadable.append(h['source_slot_id'])
        ids=[n.get('id') for n in nodes];atoms=[n.get('atom') for n in nodes]
        states.append(dict(slot_id=sid,trial_id=t['id'],arm=arm,rule_position=slot['rule_position'],prefix_nodes=len(nodes),
            prior_id_equals_atom=sum(n.get('id')==n.get('atom') for n in nodes),unreadable_sources=unreadable))
        try:parents=load(outer['message']['content'])['node']['parents']
        except (ValueError,TypeError,KeyError,UnicodeError):parents=None
        if isinstance(parents,list):
            absent=[x for x in parents if x not in ids]
            if absent:missing.append(dict(slot_id=sid,arm=arm,missing_ids=absent,missing_all_match_existing_atoms=all(x in atoms for x in absent)))
        check=next((x for x in rowmap[t['id']]['step_checks'] if x['id']==sid),None)
        if check:
            rule_checks.append(dict(slot_id=sid,trial_id=t['id'],arm=arm,problem_id=t['problem_id'],seed=t['seed'],condition=t['condition'],
                rule_position=slot['rule_position'],features=features(data['problem'],data['provided_route_plan']['rule_ids'],data['operation']['requested_rule_id']),check=check))
    risks=defaultdict(lambda:dict(eligible=0,observed=0,success=0,failure=0,unobserved=0))
    first=[]
    for row in rows:
        prefix=True
        for step in row['step_checks']:
            if step['stage']=='rule' and prefix:
                pos=int(step['id'].rsplit('_',1)[1]);r=risks[row['generator_arm'],pos];r['eligible']+=1
                if step['status']=='ok':
                    r['observed']+=1;good=step['valid'] is True and step['support_contract_success'] is True;r['success' if good else 'failure']+=1
                elif step['status'] in ('invalid_json','invalid_schema'):
                    r['observed']+=1;r['failure']+=1
                else:r['unobserved']+=1
            if not(step['status']=='ok' and step['valid'] is True and step['support_contract_success'] is True):
                if prefix:
                    first.append(dict(trial_id=row['trial_id'],arm=row['generator_arm'],problem_id=row['problem_id'],seed=row['seed'],
                        condition=row['condition'],first_slot=step['id'],stage=step['stage'],status=step['status'],errors=step.get('error_codes'),
                        first_error_class=generation_error(row)))
                prefix=False
    normalized={arm:dict(requests=g['requests'],unique_with_seed=len(g['unique']),unique_without_seed=len(g['without_seed']),usage=g['usage']) for arm,g in sorted(groups.items())}
    return dict(contract='v090-diagnostics-r1',groups=normalized,input_states=states,fresh_fact_contracts=facts,
        missing_parent_aliases=missing,rule_checks=rule_checks,first_failures=first,
        step_risk_sets=[dict(arm=arm,rule_position=pos,**value) for (arm,pos),value in sorted(risks.items())],
        limitations=['위험집합은 새 facts 의미와 ID 계약부터 직전까지 모두 유효한 경로만 포함한다.',
        '누적 규칙 오류와 최초 실패 graph 수는 합산하지 않는다. 미관측/전송 오류를 논리 오답으로 채우지 않는다.',
        '응답 토큰과 시간 합은 launcher 경과시간이나 청구비용이 아니다. 공유 선택은 한 번만 집계한다.'])


def render(d):
    lines=['# v090 새 facts·최초 오류·후속 참조 진단','',
        f"없는 부모 ID를 출력한 규칙: {len(d['missing_parent_aliases'])}",
        f"최초 비정상 생성 단계가 있는 graph: {len(d['first_failures'])}",'',
        '| 군 | 규칙 위치(0부터) | 직전 유효 | 관측 | 성공 | 실패 | 미관측 |','|---|---:|---:|---:|---:|---:|---:|']
    for r in d['step_risk_sets']:
        lines.append(f"| {r['arm']} | {r['rule_position']} | {r['eligible']} | {r['observed']} | {r['success']} | {r['failure']} | {r['unobserved']} |")
    return '\n'.join(lines+['']+d['limitations'])+'\n'
