"""v054 완료 증거를 생산 채점기 import 없이 재검사한다.
사용: python tools/independent_verify_v054.py 결과_evidence.zip --out 검증.json
완료·HTTP 정상인 120호출을 지원한다. JSON/출력계약 실패는 미측정으로 보존한다.
source/runtime/동결 요청의 검사는 생산 오프라인 감사와 함께 수행한다.
"""
from __future__ import annotations
import argparse, collections, json
from pathlib import Path
from independent_review_v052 import Invalid, need, load, sha, canon, check, bound_depths
from forensic_replay_v053 import checked_zip

def payload_from(raw, model):
    try:
        env=load(raw)
        need(isinstance(env,dict) and env.get('model')==model,'model_identity')
        need(env.get('done') is True and env.get('done_reason')=='stop','not_normal_stop')
        msg=env.get('message');need(isinstance(msg,dict) and msg.get('role')=='assistant','message_role')
        need(not msg.get('images') and not msg.get('tool_calls'),'side_channel')
        thinking=msg.get('thinking');need(thinking is None or (isinstance(thinking,str) and not thinking.strip()),'thinking')
        text=msg.get('content');need(isinstance(text,str) and '<think>' not in text and '</think>' not in text,'content')
        payload=load(text);need(isinstance(payload,dict),'object')
        return payload
    except Invalid:
        return None

def verify(bundle: Path):
    data,manifest=checked_zip(bundle)
    need(manifest['contract']=='v054-evidence-bundle-r1','bundle_contract')
    plan=load(data['external_plan/v054.plan.json']);report=load(data['run/summary.json'])
    need(report['data_complete'] is True,'complete_run_required')
    need(plan['plan_sha256']==sha(canon({k:v for k,v in plan.items() if k!='plan_sha256'})),'plan_digest')
    need(load(data['run/plan.snapshot.json'])==plan,'external_plan')
    events=[load(x) for x in data['run/events.jsonl'].splitlines()]
    need(len(events)==len(plan['slots'])==len(report['trials'])==120,'complete_120')
    stored={r['id']:r for r in report['trials']};need(len(stored)==120,'unique_trials')
    previous=plan['plan_sha256'];rows=[];discrepancies=[];count=0
    def compare(path,actual,expected):
        nonlocal count
        count+=1
        if actual!=expected:discrepancies.append({'path':path,'stored':actual,'independent':expected})
    for slot,event in zip(plan['slots'],events):
        sid=slot['id'];need(event['slot']==slot and event['previous_hash']==previous,'event_order')
        need(event['event_hash']==sha(canon({k:v for k,v in event.items() if k!='event_hash'})),'event_hash');previous=event['event_hash']
        need(event['kind']=='call' and event['parents']==[] and event['http_status']==200 and event['transport_error'] is None,'transport_or_dependencies')
        request=data['run/calls/'+sid+'/request.wire.json'];raw=data['run/calls/'+sid+'/response.raw.json']
        need(event['request_sha256']==sha(request) and event['response_sha256']==sha(raw),'wire_hash')
        request=load(request);problem=load(request['messages'][1]['content'][9:]);base=plan['problems'][slot['problem_id']]
        need({k:v for k,v in problem.items() if k!='rules'}=={k:v for k,v in base.items() if k!='rules'},'problem_changed')
        need(sorted(problem['rules'],key=lambda r:r['id'])==sorted(base['rules'],key=lambda r:r['id']),'rule_content_changed')
        need([r['id'] for r in problem['rules']]==plan['rule_orders'][slot['problem_id']][slot['arm']],'rule_order_changed')
        m=check(problem,payload_from(raw,plan['baseline']['config']['model']),request['format'],'explicit','graph_only')
        for field in ('format_valid','proof_valid','strict_valid','D'):
            compare(sid+'/'+field,stored[sid]['measurement'][field],m[field])
        compare(sid+'/final_ref_valid',stored[sid]['measurement']['final_ref_valid'],m['final_reference_exists'])
        role=None
        if slot['direction']!='neutral':
            bounds=bound_depths(problem)
            role=bool(m['strict_valid'] and m['D']==bounds[0 if slot['direction']=='shallow' else 1])
            compare(sid+'/role_match',stored[sid]['role_match'],role)
        rows.append({**slot,**m,'role_match':role})
    need(previous==report['event_tip'],'event_tip')
    lookup={(r['problem_id'],r['arm'],r['seed'],r['direction']):r for r in rows}
    storedpairs={(r['problem_id'],r['arm'],r['seed']):r for r in report['pairs']}
    pairs={};robust=0;order_changes=0
    for pid in plan['problems']:
        for arm in plan['arms']:
            for seed in plan['seeds']:
                a,b=(lookup[pid,arm,seed,d] for d in ('shallow','deep'))
                value=bool(a['role_match'] and b['role_match'] and a['D']!=b['D'])
                pairs[pid,arm,seed]=value
                compare(f'{pid}/{arm}/{seed}/selective',storedpairs[pid,arm,seed]['direction_selective_success'],value)
    oldrobust={(r['problem_id'],r['seed']):r for r in report['robust_pairs']}
    for pid in plan['problems']:
        for seed in plan['seeds']:
            value=all(pairs[pid,arm,seed] for arm in plan['arms']);robust+=value
            compare(f'{pid}/{seed}/robust',oldrobust[pid,seed]['both_orders_selective_success'],value)
    oldorder={(r['problem_id'],r['direction'],r['seed']):r for r in report['order_contrasts']}
    for pid in plan['problems']:
        for direction in plan['directions']:
            for seed in plan['seeds']:
                a,b=(lookup[pid,arm,seed,direction] for arm in plan['arms'])
                valid=a['strict_valid'] and b['strict_valid']
                depth=(a['D']!=b['D']) if valid else None
                structure=(a.get('proof_signature')!=b.get('proof_signature')) if valid else None
                order_changes+=depth is True
                compare(f'{pid}/{direction}/{seed}/order_depth',oldorder[pid,direction,seed]['depth_changed'],depth)
                compare(f'{pid}/{direction}/{seed}/order_structure',oldorder[pid,direction,seed]['structure_changed'],structure)
    return {'bundle_sha256':sha(bundle.read_bytes()),'manifest_files':len(manifest['file_hashes']),
        'evidence_kind':report['evidence_kind'],'raw_responses':len(rows),'semantic_fields_compared':count,
        'discrepancies':discrepancies,'valid_proofs':sum(r['strict_valid'] for r in rows),
        'selective_pairs':sum(pairs.values()),'order_robust_seed_groups':robust,'order_changed_pairs':order_changes,
        'scope':'생산 채점기 없는 원문 의미 재계산. 완료·HTTP 정상 120회. source/runtime/request 동결은 별도 감사 필요'}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('bundle',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();result=verify(a.bundle)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2));return 1 if result['discrepancies'] else 0

if __name__=='__main__':raise SystemExit(main())
