"""보존 요청/응답의 오류·고유 입력·비용 진단. 모델 출력을 수정하지 않는다."""
from collections import Counter,defaultdict
from copy import deepcopy
from hashlib import sha256
import json
import core088 as core
FIELDS=('prompt_eval_count','eval_count','total_duration','prompt_eval_duration','eval_duration')

def collect(plan,requests,responses,rows):
    trials={t['id']:t for t in plan['trials']};groups=defaultdict(lambda:dict(requests=0,unique=set(),without_seed=set(),usage={k:dict(sum=0,missing=0)for k in FIELDS}))
    failures=[];alias=[];input_states=[];rename_certificates=[];initial_conditions=[]
    for op in plan['slots']:
        sid=op['id'];t=trials[op['trial_id']];phase=t['phase'];arm='shared_selection'if op['stage']in ('compare','select')else t['generator_arm']
        key=phase+'/'+arm+'/'+op['stage']
        if sid not in requests:continue
        body=core.load(requests[sid]);d=core.load(body['messages'][0]['content'].split('\n\ninput: ',1)[1]);g=groups[key]
        g['requests']+=1;g['unique'].add(core.sha(requests[sid]));reduced=deepcopy(body);reduced['options'].pop('seed',None);g['without_seed'].add(core.sha(core.wire(reduced)))
        try:outer=core.load(responses.get(sid,b''))
        except (ValueError,UnicodeError):outer={}
        for k in FIELDS:
            v=outer.get(k)
            if type(v)is int and v>=0:g['usage'][k]['sum']+=v
            else:g['usage'][k]['missing']+=1
        if op['stage']!='rule':continue
        nodes=[];unreadable=[]
        for h in d['history']:
            try:
                x=core.load(h['content']);ns=x['nodes']if 'nodes'in x else [x['node']]
                nodes.extend(n for n in ns if isinstance(n,dict))
            except (ValueError,TypeError,KeyError,UnicodeError):unreadable.append(h['source_slot_id'])
        ids=[n.get('id')for n in nodes];atoms=[n.get('atom')for n in nodes]
        input_states.append(dict(slot_id=sid,phase=phase,arm=arm,rule_position=op['rule_position'],prefix_nodes=len(nodes),
            prior_long_ids=sum(isinstance(x,str)and x.startswith('v087_node_')for x in ids),prior_id_equals_atom=sum(n.get('id')==n.get('atom')for n in nodes),unreadable_sources=unreadable))
        if phase=='continuation' and op['rule_position']==0:
            initial_conditions.append(dict(trial_id=t['id'],unit_id=t['unit_id'],problem_id=t['problem_id'],seed=t['seed'],condition=t['condition'],
                arm=arm,anchor_id=t['anchor_id'],node_ids=ids,atoms=atoms,current_allocated_id=d.get('allocated_node_id')))
        if phase=='rename_probe':
            rename_certificates.append(dict(slot_id=sid,anchor_id=t['anchor_id'],arm=arm,history_sha256=core.sha(core.wire(d['history'])),node_ids=ids,
                atoms=atoms,rules=[n.get('rule')for n in nodes],parents=[n.get('parents')for n in nodes]))
        try:obj=core.load(outer['message']['content']);parents=obj['node']['parents']
        except (ValueError,KeyError,TypeError,UnicodeError):continue
        if not isinstance(parents,list):continue
        missing=[p for p in parents if p not in ids]
        if missing:alias.append(dict(slot_id=sid,phase=phase,arm=arm,missing_ids=missing,missing_all_match_existing_atoms=all(p in atoms for p in missing)))
    for r in rows:
        if r['phase']=='rename_probe':
            if r.get('probe_success')is False:failures.append(dict(trial_id=r['trial_id'],phase=r['phase'],arm=r['generator_arm'],rule_errors=(r.get('rule_check')or{}).get('error_codes'),graph_errors=None))
        else:
            key='continuation_success'if r['phase']=='continuation'else'end_to_end_success'
            if r.get(key)is False:
                failures.append(dict(trial_id=r['trial_id'],phase=r['phase'],arm=r['generator_arm'],
                    graph_errors=(r.get('graph_result')or{}).get('error_codes'),
                    rule_errors=[dict(id=x['id'],errors=x.get('error_codes'))for x in r['step_checks']if x.get('valid')is False]))
    output={}
    for key,g in sorted(groups.items()):output[key]=dict(requests=g['requests'],unique_with_seed=len(g['unique']),unique_without_seed=len(g['without_seed']),usage=g['usage'])
    scopes=[];grouped=defaultdict(dict)
    for item in initial_conditions:
        family,scope=item['arm'].split('_');grouped[(item['unit_id'],family)][scope]=item
    for (unit,family),items in sorted(grouped.items()):
        if set(items)!={'mixed','uniform'}:continue
        left,right=items['mixed'],items['uniform']
        scopes.append(dict(unit_id=unit,family=family,same_atom_sequence=left['atoms']==right['atoms'],
            same_current_output_id=left['current_allocated_id']==right['current_allocated_id'],
            changed_fact_ids=sum(x!=y for x,y in zip(left['node_ids'],right['node_ids'])),
            node_count_left=len(left['node_ids']),node_count_right=len(right['node_ids'])))
    return dict(contract='v088-diagnostics-r1',groups=output,input_states=input_states,missing_parent_aliases=alias,
        continuation_initial_conditions=initial_conditions,continuation_scope_pairs=scopes,
        failures=failures,rename_certificates=rename_certificates,
        limitations=['고유 바이트 수는 독립 문제 수가 아니다.','과거 사실·재명명 입력은 진단 지원이며 새 모델 증거로 세지 않는다.',
        '초기 이력과 신규 응답을 구별한다. 원자 이름을 부모 ID로 자동 변환하지 않는다.','usage는 응답별 합이며 벽시계 시간이나 API 청구액이 아니다.'])

def render(d):
    lines=['# v088 바이트·후속 참조 진단','',f"실패 trial: {len(d['failures'])}",f"존재하지 않는 부모를 출력한 규칙: {len(d['missing_parent_aliases'])}",
        f"그 중 모든 누락 이름이 기존 원자와 같은 규칙: {sum(x['missing_all_match_existing_atoms']for x in d['missing_parent_aliases'])}",'',
        '| 단계 | 요청 | 고유(시드 포함) | 고유(시드 제외) |','|---|---:|---:|---:|']
    for k,g in d['groups'].items():lines.append(f"| {k} | {g['requests']} | {g['unique_with_seed']} | {g['unique_without_seed']} |")
    lines+=['']+d['limitations'];return '\n'.join(lines)+'\n'
