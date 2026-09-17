"""원문 기준 최초 오류, facts 계약, 위험집합, 참조 오류 유형 및 계산량 진단."""
from collections import defaultdict,Counter
from copy import deepcopy
from audit_bytes091 import load,dump,digest
from tables091 import generation_error
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


def collect_base(plan,requests,responses,rows):
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
    return dict(contract='v091-diagnostics-r1',groups=normalized,input_states=states,fresh_fact_contracts=facts,
        missing_parent_aliases=missing,rule_checks=rule_checks,first_failures=first,
        step_risk_sets=[dict(arm=arm,rule_position=pos,**value) for (arm,pos),value in sorted(risks.items())],
        limitations=['위험집합은 새 facts 의미와 ID 계약부터 직전까지 모두 유효한 경로만 포함한다.',
        '누적 규칙 오류와 최초 실패 graph 수는 합산하지 않는다. 미관측/전송 오류를 논리 오답으로 채우지 않는다.',
        '응답 토큰과 시간 합은 launcher 경과시간이나 청구비용이 아니다. 공유 선택은 한 번만 집계한다.'])


def render_base(d):
    lines=['# v091 새 facts·최초 오류·후속 참조 진단','',
        f"없는 부모 ID를 출력한 규칙: {len(d['missing_parent_aliases'])}",
        f"최초 비정상 생성 단계가 있는 graph: {len(d['first_failures'])}",'',
        '| 군 | 규칙 위치(0부터) | 직전 유효 | 관측 | 성공 | 실패 | 미관측 |','|---|---:|---:|---:|---:|---:|---:|']
    for r in d['step_risk_sets']:
        lines.append(f"| {r['arm']} | {r['rule_position']} | {r['eligible']} | {r['observed']} | {r['success']} | {r['failure']} | {r['unobserved']} |")
    return '\n'.join(lines+['']+d['limitations'])+'\n'


def trace_features(data,obj,rule_position,valid,prefix_valid_before):
    """검증을 대체하지 않는 관측. 같은 부모를 쓰는 정상 규칙을 실패로 표시하지 않는다."""
    nodes=[];prior_rules=[]
    for h in data.get('history',[]):
        try:
            x=load(h['content'])
            if isinstance(x,dict) and isinstance(x.get('node'),dict):
                nodes.append(x['node']);prior_rules.append(x['node'])
            elif isinstance(x,dict) and isinstance(x.get('nodes'),list):
                nodes.extend(n for n in x['nodes'] if isinstance(n,dict))
        except (TypeError,KeyError,ValueError,UnicodeError):pass
    node=obj.get('node') if isinstance(obj,dict) else None
    if not isinstance(node,dict) or not isinstance(node.get('parents'),list):return None
    parents=node['parents'];rule=data['operation']['requested_rule']
    previous=prior_rules[-1] if prior_rules else None
    equal_previous=previous is not None and parents==previous.get('parents')
    equal_prior=[i for i,n in enumerate(prior_rules) if parents==n.get('parents')]
    correct_rule=node.get('rule')==rule['id'] and node.get('atom')==rule['conclusion']
    unique={};ambiguous=set()
    for n in nodes:
        if not isinstance(n,dict) or not isinstance(n.get('id'),str):continue
        if n['id'] in unique:ambiguous.add(n['id'])
        unique[n['id']]=n
    def ancestors(nid):
        if not isinstance(nid,str) or nid not in unique or nid in ambiguous:return set()
        pp=unique[nid].get('parents',[])
        todo=list(pp) if isinstance(pp,list) else [];seen=set()
        while todo:
            v=todo.pop()
            if not isinstance(v,str) or v in seen:continue
            seen.add(v)
            if v in unique and v not in ambiguous and isinstance(unique[v].get('parents'),list):todo.extend(unique[v]['parents'])
        return seen
    resolved=all(isinstance(pid,str) and pid in unique and pid not in ambiguous and isinstance(unique[pid].get('atom'),str) for pid in parents)
    premise_match=bool(resolved and Counter(unique[pid].get('atom') for pid in parents)==Counter(rule['premises']))
    incorrect_parents=valid is False and not premise_match
    relations=[];wrong=[]
    for pid in parents:
        if not isinstance(pid,str) or pid not in unique or pid in ambiguous:continue
        atom=unique[pid].get('atom')
        if atom not in rule['premises']:
            wrong.append(pid)
            targets=[r['id'] for r in nodes if r.get('atom') in rule['premises'] and pid in ancestors(r.get('id'))]
            if targets:relations.append(dict(wrong_parent_id=pid,ancestor_of_required_node_ids=sorted(set(targets))))
    return dict(parents_equal_previous_rule=equal_previous,parents_equal_any_prior_rule=bool(equal_prior),
        matching_prior_rule_indices=equal_prior,current_rule_and_atom_correct=correct_rule,
        parent_atoms_match_current_rule=premise_match,
        current_rule_correct_but_parents_stale=bool(incorrect_parents and correct_rule and equal_previous),
        incorrect_prior_parents_reuse=bool(incorrect_parents and equal_prior),
        wrong_parents_are_ancestors_of_required_parent=bool(valid is False and wrong and len(relations)==len(wrong)),
        wrong_parent_ancestor_relations=relations,
        first_rule_empty_after_facts=bool(rule_position==0 and valid is False and parents==[] and rule['premises']),
        prefix_valid_before=prefix_valid_before,requested_rule=rule,emitted_node=node,previous_rule_node=previous)


def normalize_source_ids_for_audit(raw):
    """비교용 사본에만 적용. 모델 응답 content는 공백을 포함해 원문 그대로 둔다."""
    body=load(raw);text=body['messages'][0]['content'];head,payload=text.split('\n\ninput: ',1);data=load(payload)
    if isinstance(data.get('selection_original'),dict) and 'source_id' in data['selection_original']:
        data['selection_original']['source_id']='AUDIT_SOURCE'
    for i,h in enumerate(data.get('history',[])):
        if 'source_slot_id' in h:h['source_slot_id']='AUDIT_HISTORY_%04d'%i
    body['messages'][0]['content']=head+'\n\ninput: '+dump(data).decode()
    return dump(body)


def collect(plan,requests,responses,rows):
    d=collect_base(plan,requests,responses,rows)
    tm={t['id']:t for t in plan['trials']};rm={r['trial_id']:r for r in rows}
    rowchecks={r['trial_id']:{x['id']:x for x in r['step_checks']} for r in rows}
    traces=[];request_ids=[]
    for slot in plan['slots']:
        sid=slot['id']
        if sid not in requests:continue
        t=tm[slot['trial_id']]
        identity={k:t[k] for k in ('cohort','topology_id','renaming_id','presentation_id','sampling_seed','replicate_id','input_unit_id')}
        identity.update(execution_id=plan['run_name']+'::'+sid,slot_id=sid,trial_id=t['id'],stage=slot['stage'],generator_arm='shared_selection' if slot['stage'] in ('compare','select') else t['generator_arm'])
        request_ids.append(dict(identity,wire_request_sha256=digest(requests[sid]),source_ids_normalized_sha256=digest(normalize_source_ids_for_audit(requests[sid]))))
        if slot['stage']!='rule':continue
        try:
            outer=load(responses.get(sid,b''));obj=load(outer['message']['content']);body=load(requests[sid]);data=load(body['messages'][0]['content'].split('\n\ninput: ',1)[1])
            check=rowchecks[t['id']].get(sid,{})
            value=trace_features(data,obj,slot['rule_position'],check.get('valid'),check.get('prefix_valid_before'))
            if value is not None:traces.append(dict(identity,rule_position=slot['rule_position'],**value))
        except (TypeError,KeyError,ValueError,UnicodeError):continue
    for name in ('first_failures','rule_checks','fresh_fact_contracts','input_states'):
        for item in d[name]:
            t=tm[item['trial_id']]
            item.update({k:t[k] for k in ('cohort','topology_id','renaming_id','presentation_id','sampling_seed','replicate_id')})
    # 계산량 groups는 전체 실행의 관측 총량이며 연구 주평가로 쓰지 않는다.
    d['resource_groups_scope']='all cohorts operational totals only; hypothesis results separated in summary.cohorts'
    d['trace_diagnostics']=traces;d['request_identities']=request_ids
    cohort_summary={}
    for cohort in plan['protocol']['cohorts']:
        arm_summary={}
        for arm in plan['protocol']['generator_arms']:
            rr=[r for r in traces if r['cohort']==cohort and r['generator_arm']==arm]
            arms=['current_rule_correct_but_parents_stale','incorrect_prior_parents_reuse','wrong_parents_are_ancestors_of_required_parent','first_rule_empty_after_facts']
            arm_summary[arm]=dict(observed_rule_diagnostics=len(rr),
                all_observed={k:sum(x[k] is True for x in rr) for k in arms},
                valid_prefix_only={k:sum(x[k] is True and x['prefix_valid_before'] is True for x in rr) for k in arms})
        cohort_summary[cohort]=arm_summary
    risks={}
    for row in rows:
        prefix=True
        for step in row['step_checks']:
            if step['stage']=='rule' and prefix:
                pos=int(step['id'].rsplit('_',1)[1]);key=(row['cohort'],row['generator_arm'],pos)
                value=risks.setdefault(key,dict(eligible=0,success=0,failure=0,unobserved=0));value['eligible']+=1
                if step['status']=='ok':value['success' if step['valid'] is True and step['support_contract_success'] is True else 'failure']+=1
                elif step['status'] in ('invalid_json','invalid_schema'):value['failure']+=1
                else:value['unobserved']+=1
            prefix=bool(prefix and step['status']=='ok' and step['valid'] is True and step['support_contract_success'] is True)
    d['step_risk_sets_by_cohort']=[dict(cohort=k[0],arm=k[1],rule_position=k[2],**v) for k,v in sorted(risks.items())]
    d['trace_counts_by_cohort']=cohort_summary
    d['limitations']+=['직전 부모 일치는 관측 플래그다. 현재 규칙에 유효하면 stale 오류로 분류하지 않는다.',
        'source ID 정규화 해시는 감사용 사본에서만 계산한다. 실행 입력·원응답을 바꾸지 않는다.',
        '구조/재명명/표시/seed/반복/실행 ID를 별도 기록한다. 원형과 재명명을 독립 구조로 합산하지 않는다.']
    return d


def render(d):
    lines=['# v091 cohort별 최초 오류·후속 참조 진단','',
        '주평가는 summary.ko.md의 신규 구조 대조이다. 아래 위험집합·오류는 cohort를 합산하지 않는다.',
        'groups의 토큰·호출 합만 전체 배치의 운영 총량이며 연구 표본 수가 아니다.','']
    for cohort,arms in d['trace_counts_by_cohort'].items():
        lines+=['## '+cohort,'',
            '| 군 | 규칙 위치(0부터) | 직전 유효 | 성공 | 실패 | 미관측 |',
            '|---|---:|---:|---:|---:|---:|']
        for row in d['step_risk_sets_by_cohort']:
            if row['cohort']==cohort:
                lines.append(f"| {row['arm']} | {row['rule_position']} | {row['eligible']} | {row['success']} | {row['failure']} | {row['unobserved']} |")
        lines+=['','직전까지 유효했던 경로에서 관측한 추가 플래그:']
        for arm,record in arms.items():lines.append(arm+': '+str(record['valid_prefix_only']))
        lines.append('')
    return '\n'.join(lines+d['limitations'])+'\n'
