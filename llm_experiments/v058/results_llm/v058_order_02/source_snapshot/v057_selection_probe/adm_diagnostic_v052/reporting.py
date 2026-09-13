"""본 가설·중립군·정답 복사·D 단독 진단의 분모를 분리한다."""
import collections,itertools,statistics
from .contracts import write_json
from .design import ROLES,PROBLEMS
from .measure import role_match,depth_bounds
from adm_pilot_v051.reporting import cost

FIELDS=('format_valid','all_local_nodes_valid','final_ref_valid','proof_valid','representation_valid',
        'review_target_valid','review_findings_valid','strict_valid')

def counts(trials,calls,complete):
    ms=[t['measurement'] for t in trials if t['measurement'] is not None]
    result={'assigned':len(trials),'observed':sum(t['observed'] for t in trials),'assessable':sum(t['assessable'] for t in trials),
            'role_match':sum(t['role_match'] is True for t in trials),'layers':{},'usage':cost(calls)}
    for field in FIELDS:
        result['layers'][field]={'correct':sum(m.get(field) is True for m in ms),
                                'incorrect':sum(m.get(field) is False for m in ms),
                                'unmeasured':len(trials)-sum(m.get(field) is True or m.get(field) is False for m in ms)}
    result['requested_success_rate']=result['role_match']/len(trials) if complete and trials and trials[0]['task'] in ('factorial','legacy') else None
    result['copy_exact']=sum(m.get('copy_exact') is True for m in ms)
    if trials and trials[0]['task']=='graph_only':
        result['depth_requested_success']=sum(t['measurement'] is not None and t['measurement']['strict_valid'] and t['measurement']['D']==depth_bounds(PROBLEMS[t['problem_id']])[0 if t['role']['D']=='shallow' else 1] for t in trials)
    return result

def axis_rows(p,trials,complete):
    rows=[]
    for pid in PROBLEMS:
        problem=PROBLEMS[pid]
        lookup={(t['seed'],t['role_id']):t for t in trials if t['task']=='factorial' and t['problem_id']==pid}
        for axis in ('A','D','M'):
            others=[a for a in ('A','D','M') if a!=axis]
            for l,r in itertools.combinations(ROLES,2):
                if any(l[a]!=r[a] for a in others):continue
                row={'problem_id':pid,'axis':axis,'left':l['id'],'right':r['id'],'assigned_pairs':len(p['seeds']),
                     'both_records_valid':0,'structural_selective':0,'strict_selective':0,'other_axis_change':0}
                for seed in p['seeds']:
                    lt,rt=lookup[seed,l['id']],lookup[seed,r['id']];ml,mr=lt['measurement'],rt['measurement']
                    if ml is None or mr is None:continue
                    both=ml['strict_valid'] and mr['strict_valid'];row['both_records_valid']+=bool(both)
                    unchanged=all(ml[a]==mr[a] for a in others)
                    if axis in ('A','M'):unchanged=unchanged and ml.get('proof_signature') is not None and ml['proof_signature']==mr['proof_signature']
                    changed=ml[axis]!=mr[axis]
                    clean=role_match(ml,l,problem,coordinates_only=True) and role_match(mr,r,problem,coordinates_only=True) and unchanged and changed
                    row['structural_selective']+=bool(clean)
                    row['strict_selective']+=bool(clean and both)
                    row['other_axis_change']+=bool(both and not unchanged)
                row['strict_rate_over_assigned']=row['strict_selective']/row['assigned_pairs'] if complete else None
                rows.append(row)
    return rows

def summarize(p,trials,calls,observations,complete):
    groups={}
    for pid in PROBLEMS:
        for task in ('legacy','factorial','neutral','copy_control','graph_only'):
            ts=[t for t in trials if t['problem_id']==pid and t['task']==task]
            if not ts:continue
            groups[pid+'/'+task]=counts(ts,[c for c in calls if c['problem_id']==pid and c['task']==task],complete)
    roles={}
    for pid in PROBLEMS:
        for r in ROLES:
            ts=[t for t in trials if t['task']=='factorial' and t['problem_id']==pid and t['role_id']==r['id']]
            roles[pid+'/'+r['id']]=counts(ts,[c for c in calls if c['task']=='factorial' and c['problem_id']==pid and c['role_id']==r['id']],complete)
    contrasts=axis_rows(p,trials,complete);neutral=[];core={}
    for pid,problem in PROBLEMS.items():
        seedrows=[]
        for seed in p['seeds']:
            ts=[t for t in trials if t['task']=='factorial' and t['problem_id']==pid and t['seed']==seed]
            n=next(t for t in trials if t['task']=='neutral' and t['problem_id']==pid and t['seed']==seed)
            assigned=sum(t['role_match'] is True for t in ts)/len(ROLES)
            # 한 neutral 출력의 12회 재채점이며 별도 독립 호출을 생성하지 않는다.
            expected=sum(role_match(n['measurement'],r,problem) for r in ROLES)/len(ROLES)
            row={'problem_id':pid,'seed':seed,'assigned_macro_success':assigned if complete else None,
                 'neutral_standardized_success':expected if complete else None,'difference':assigned-expected if complete else None}
            seedrows.append(row);neutral.append(row)
        g=groups[pid+'/factorial'];axis={a:sum(x['strict_selective'] for x in contrasts if x['problem_id']==pid and x['axis']==a) for a in ('A','D','M')}
        diff=statistics.mean(r['difference'] for r in seedrows) if complete else None
        core[pid]={'primary_assigned':g['assigned'],'valid_records':g['layers']['strict_valid']['correct'],
                   'assigned_role_success':g['role_match'],'neutral_macro_difference':diff,'selective_pairs':axis,
                   'diagnostic_controls_excluded':True,'complete':complete,
                   'interpretation':'incomplete' if not complete else ('no_valid_full_record' if g['layers']['strict_valid']['correct']==0 else ('target_control_observed_in_this_task' if diff>0 and all(axis.values()) else 'valid_records_but_full_axis_control_not_shown'))}
    reqs=collections.defaultdict(set)
    for c in calls:reqs[c['request_sha256']].add(c['content_sha256'])
    return {'contract':'v052-adm-diagnostic-report-r1','model':p['baseline']['config']['model'],
            'temperature':p['baseline']['config']['options'].get('temperature'),'seeds':p['seeds'],
            'groups':groups,'roles':roles,'paired':contrasts,'neutral_comparisons':neutral,'core_results':core,
            'all_primary_roles_succeeded':all(t['role_match'] is True for t in trials if t['task']=='factorial') if complete else None,
            'unique_execution_usage':cost(calls),'unique_request_count':len(reqs),
            'unstable_request_groups':sum(len(v)>1 for v in reqs.values()),'policy':p['policy'],
            'statistical_note':'seed 단위 기술적 차이만 보고. 반복/재채점/대응쌍을 독립 문제로 세지 않고 p-value를 계산하지 않음'}

def save_report(out,r):
    audit_keys=('contract','data_integrity','data_complete','comparative_analysis_ready','inference_calls','plan_sha256','event_tip',
                'run_state','failure_stage','failure_kind','failure_slot_id','run_error')
    write_json(out/'audit.json',{k:r[k] for k in audit_keys})
    write_json(out/'summary.json',r)
    lines=['# v052 A/D/M 핵심 가설과 실패 위치의 분리 검사','',
           f"자료 무결성: {r['data_integrity']} / 수집 완료: {r['data_complete']} / 호출: {r['inference_calls']}/{r['max_inference_calls']}",
           f"출처: {r['evidence_kind']} / 모델: {r['model']} / temperature: {r['temperature']}",'']
    if not r['data_complete']:
        lines += ['## 실행 중단 진단','',
                  f"- 상태: `{r['run_state']}`",
                  f"- 실패 단계: `{r['failure_stage']}`",
                  f"- 실패 종류: `{r['failure_kind']}`",
                  f"- 실패 슬롯: `{r['failure_slot_id']}`",
                  f"- 원인: `{r['run_error']}`",'',
                  '이 구간은 모델의 A/D/M 오답 판정이 아니라 실행 인프라/정체성/전송 실패 진단이다. 미실행 항목을 오답으로 바꾸지 않는다.','']
    lines += [
           '## 본 가설 결과','',
           'factorial만 본 가설 분모에 포함한다. 복사 진단·D 단독 생성은 아래 별도 표다.','',
           '| 문제 | 배정 | 전체 유효 | 역할 부합 | 중립 대비 차이 | A/D/M 선택적 대조 성공 |',
           '|---|---:|---:|---:|---:|---|']
    for pid,k in r['core_results'].items():
        d=k['neutral_macro_difference'];ds='미완료' if d is None else f'{d*100:.2f}%p'
        lines.append(f"| {pid} | {k['primary_assigned']} | {k['valid_records']} | {k['assigned_role_success']} | {ds} | {k['selective_pairs']} |")
    lines+=['','## 층별 결과','',
            '칸은 성공/실패/미측정이다. 앞 단계 실패로 측정하지 못한 층은 오답 0점과 구분한다.',
            '| 문제/과제 | 배정 | 개별 노드 | 최종 참조 | 증명 전체 | 표현 | 검토 판정 | 전체 유효 |',
            '|---|---:|---|---|---|---|---|---|']
    for name,g in r['groups'].items():
        vals=[]
        for f in ('all_local_nodes_valid','final_ref_valid','proof_valid','representation_valid','review_findings_valid','strict_valid'):
            v=g['layers'][f];vals.append(f"{v['correct']}/{v['incorrect']}/{v['unmeasured']}")
        lines.append(f"| {name} | {g['assigned']} | "+' | '.join(vals)+' |')
    lines+=['','## 진단과 범위','',
            'copy_control은 정답 제공 JSON 복사다. 성공해도 A/D/M 가설의 성공이 아니다.',
            'graph_only는 D 단독 생성이다. 성공해도 A/M 동시 조작을 입증하지 않는다.',
            'neutral 출력 하나를 12역할로 재채점해 비교한다. 새 호출이나 12개 독립 문제로 세지 않는다.',
            'T02는 다전제·깊이 4 구조 전이 탐색이다. 문제 내부에서 facts/rules/goal은 모두 고정이다.',
            'legacy 대조는 v051 요청과 동일하다. explicit의 차이는 인터페이스 변경 묶음이며 단일 내부 원인으로 해석하지 않는다.',
            'JSON 참조를 고치거나, 원하는 경로를 호스트가 선택하거나, 중간 정답을 보충하지 않는다.',
            '출력 기록의 조작을 평가한다. 숨은 레이어·내부 사고 상태를 계측한 실험은 아니다.',
            '',f"계획 SHA-256: {r['plan_sha256']}",f"마지막 event: {r['event_tip']}",
            '원문·동봉 외부 계획의 일관성을 감사한다. 외부 실행을 인증하는 전자서명은 아니다.']
    (out/'summary.ko.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
