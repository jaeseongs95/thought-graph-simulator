"""v055 원문 재검산. 생산/기존 독립 채점기는 import하지 않는다.

표준 라이브러리와 이 버전의 forensic_v054 해시/ZIP 유틸리티만 사용한다.
정상·무효·미측정·부분 실행을 구분하며, 저장 report 값을 정답으로 쓰지 않는다.
사용: python tools/independent_verify_v055.py evidence.zip --out independent.json
"""
from __future__ import annotations
import argparse, base64, collections, itertools, json
from pathlib import Path
from forensic_v054 import canonical, sha, load, checked_zip, bounds

if not __debug__:
    raise RuntimeError("독립 검증은 assert 검사를 끄는 Python -O에서 실행할 수 없습니다.")


def need(condition, message):
    if not condition:
        raise ValueError(message)


def measure(problem, payload):
    """외부 그래프만 측정한다. 요청 방향은 이 함수의 입력이 아니다."""
    result={'format_valid':False,'proof_valid':None,'strict_valid':False,'D':None,'final_ref_valid':None,'structure':None}
    if not isinstance(payload,dict):return result
    nodes=payload.get('nodes');final=payload.get('final_node_id')
    if isinstance(nodes,list):
        result['final_ref_valid']=isinstance(final,str) and bool(final) and sum(isinstance(n,dict) and n.get('id')==final for n in nodes)==1
    def text(x):return isinstance(x,str) and 1<=len(x)<=128
    graph_shape=text(final) and isinstance(nodes,list) and 1<=len(nodes)<=16
    if graph_shape:
        graph_shape=all(isinstance(n,dict) and set(n)=={'id','atom','rule','parents'} and text(n['id']) and text(n['atom'])
            and (n['rule'] is None or text(n['rule'])) and isinstance(n['parents'],list) and len(n['parents'])<=16
            and all(text(p) for p in n['parents']) for n in nodes)
    result['format_valid']=graph_shape and set(payload)=={'nodes','final_node_id'}
    result['proof_valid']=False
    if not graph_shape:return result
    rules={r['id']:r for r in problem['rules']};seen={};depth={};closure={};signature={}
    try:
        for n in nodes:
            k=n['id'];rid=n['rule'];parents=n['parents']
            need(k not in seen,'duplicate node')
            need(len(set(parents))==len(parents),'duplicate parent')
            need(all(p in seen for p in parents),'missing/forward parent')
            if rid is None:
                need(not parents and n['atom'] in problem['facts'],'unsupported fact');d=0
            else:
                need(rid in rules,'unregistered rule')
                r=rules[rid]
                need(n['atom']==r['conclusion'],'wrong rule conclusion')
                need(sorted(seen[p]['atom'] for p in parents)==sorted(r['premises']),'wrong rule premises')
                d=1+max(depth[p] for p in parents)
            seen[k]=n;depth[k]=d;closure[k]={k}.union(*(closure[p] for p in parents))
            signature[k]=sha(canonical([n['atom'],rid,sorted(signature[p] for p in parents)]))
        need(final in seen and seen[final]['atom']==problem['goal'],'final/goal')
        need(closure[final]==set(seen),'extraneous path')
        result.update(proof_valid=True,strict_valid=result['format_valid'],D=depth[final],structure=signature[final])
    except (ValueError,KeyError,TypeError):pass
    return result


def payload_from(raw,model,status=200,error=None):
    if status!=200 or error is not None:return None
    try:
        e=load(raw);need(isinstance(e,dict),'envelope')
        need(e.get('model')==model and e.get('done') is True and e.get('done_reason')=='stop','identity/termination')
        m=e.get('message');need(isinstance(m,dict) and m.get('role')=='assistant','role')
        need(not m.get('images') and not m.get('tool_calls'),'side channel')
        thinking=m.get('thinking');need(thinking is None or (isinstance(thinking,str) and not thinking.strip()),'thinking')
        content=m.get('content');need(isinstance(content,str) and '<think>' not in content and '</think>' not in content,'content')
        p=load(content);need(isinstance(p,dict),'payload object');return p
    except (ValueError,UnicodeError,TypeError):return None


def verify(bundle:Path):
    data,manifest=checked_zip(bundle)
    need(manifest['contract']=='v055-evidence-bundle-r1','bundle contract')
    p=load(data['external_plan/v055.plan.json']);r=load(data['run/summary.json']);status=load(data['run/status.json'])
    need(p['plan_sha256']==sha(canonical({k:v for k,v in p.items() if k!='plan_sha256'})),'plan hash')
    need(p==load(data['run/plan.snapshot.json']),'external plan/snapshot')
    need(manifest['plan_sha256']==p['plan_sha256'] and manifest['data_complete']==status['complete'],'manifest state')
    need(len(p['slots'])==240 and len(p['actions'])==280,'assigned dimensions')
    need(len({s['id'] for s in p['slots']})==240,'unique slot ids')
    for name,digest in p['source_fingerprint'].items():
        raw=data['run/source_snapshot/'+name].decode('utf-8-sig').replace('\r\n','\n').replace('\r','\n').encode()
        need(sha(raw)==digest,'source snapshot: '+name)
    events=[load(line) for line in data['run/events.jsonl'].splitlines()]
    need(len(events)==status['recorded_actions'],'event count')
    tip=p['plan_sha256'];stored={t['id']:t for t in r['trials']};observed={};count=0;differences=[];metadata_count=0
    def compare(where,actual,expected):
        nonlocal count
        count+=1
        if type(actual)!=type(expected) or actual!=expected:
            differences.append({'field':where,'stored':actual,'independent':expected})
    for i,e in enumerate(events):
        action=p['actions'][i];need(e['action']==action,'schedule order')
        need(e['previous_hash']==tip and e['event_hash']==sha(canonical({k:v for k,v in e.items() if k!='event_hash'})),'event chain');tip=e['event_hash']
        if action['kind']=='metadata':
            raw=data['run/metadata/'+action['id']+'.json'];need(sha(raw)==e['metadata_sha256'],'metadata bytes');metadata_count+=1
            # 이 유틸리티는 metadata raw 해시까지만 검사. identity 의미/실패 분류는 생산 감사 및 별도 변이 시험의 범위.
            continue
        slot=action['slot'];sid=slot['id'];key=slot['model_key'];model=p['identities'][key]['model']
        req=data['run/calls/'+sid+'/request.wire.json'];raw=data['run/calls/'+sid+'/response.raw.json']
        need(sha(req)==e['request_sha256'] and sha(raw)==e['response_sha256'],'call bytes')
        oldraw=base64.b64decode(p['reference']['request_bank'][slot['reference_slot_id']],validate=True)
        q=load(req);old=load(oldraw)
        if key=='reference':need(req==oldraw,'reference wire changed')
        else:old['model']=model;need(q==old,'candidate changes beyond model')
        problem=load(q['messages'][1]['content'][9:]);m=measure(problem,payload_from(raw,model,e['http_status'],e['transport_error']))
        lo,hi=bounds(problem);matched=None if slot['direction']=='neutral' else bool(m['strict_valid'] and m['D']==(lo if slot['direction']=='shallow' else hi))
        for field in ('format_valid','proof_valid','strict_valid','D','final_ref_valid'):
            compare(sid+'/'+field,stored[sid]['measurement'][field],m[field])
        compare(sid+'/observed',stored[sid]['observed'],True)
        compare(sid+'/role_match',stored[sid]['role_match'],matched)
        observed[sid]={**slot,**m,'role_match':matched,'observed':True}
    need(tip==status['event_tip']==r['event_tip'],'event tip')
    if status['complete']:need(len(observed)==240 and metadata_count==40,'complete count')
    compare('complete',r['data_complete'],status['complete']);compare('comparative_ready',r['comparative_analysis_ready'],status['complete'])
    compare('inference_calls',r['inference_calls'],status['inference_calls'])
    for slot in p['slots']:
        if slot['id'] not in observed:
            compare(slot['id']+'/unexecuted',stored[slot['id']]['status'],'unexecuted')
            compare(slot['id']+'/measurement',stored[slot['id']]['measurement'],None)
            observed[slot['id']]={**slot,'observed':False,'format_valid':None,'proof_valid':None,'strict_valid':False,'D':None,'structure':None,'role_match':None}
    by={(x['model_key'],x['problem_id'],x['arm'],x['seed'],x['direction']):x for x in observed.values()}
    pairs={};model_results={}
    for key in ('reference','candidate'):
        model=r['models'][key];pm={(x['problem_id'],x['arm'],x['seed']):x for x in model['pairs']}
        orders={(x['problem_id'],x['direction'],x['seed']):x for x in model['order_contrasts']}
        robust={(x['problem_id'],x['seed']):x for x in model['robust_pairs']}
        num_success=0;num_robust=0;num_order=0;unmeasured_order=0
        for pid,arm,seed in itertools.product(p['problems'],p['arms'],p['seeds']):
            a,b=(by[key,pid,arm,seed,d] for d in ('shallow','deep'))
            present=a['observed'] and b['observed'];valid=a['strict_valid'] and b['strict_valid']
            success=bool(present and valid and a['role_match'] and b['role_match'] and a['D']!=b['D'])
            pair={'observed':present,'valid':valid,'success':success};pairs[key,pid,arm,seed]=pair;num_success+=success
            compare(f'{key}/{pid}/{arm}/{seed}/pair',pm[pid,arm,seed]['direction_selective_success'],success)
            compare(f'{key}/{pid}/{arm}/{seed}/present',pm[pid,arm,seed]['both_observed'],present)
        for pid,d,seed in itertools.product(p['problems'],p['directions'],p['seeds']):
            a,b=(by[key,pid,arm,seed,d] for arm in p['arms']);valid=a['strict_valid'] and b['strict_valid']
            changed=a['D']!=b['D'] if valid else None;structure=a['structure']!=b['structure'] if valid else None
            compare(f'{key}/{pid}/{d}/{seed}/order_depth',orders[pid,d,seed]['depth_changed'],changed)
            compare(f'{key}/{pid}/{d}/{seed}/order_structure',orders[pid,d,seed]['structure_changed'],structure)
            num_order+=changed is True;unmeasured_order+=changed is None
        for pid,seed in itertools.product(p['problems'],p['seeds']):
            val=all(pairs[key,pid,arm,seed]['success'] for arm in p['arms']);num_robust+=val
            compare(f'{key}/{pid}/{seed}/robust',robust[pid,seed]['both_orders_selective_success'],val)
        for pid,arm,d in itertools.product(p['problems'],p['arms'],p['directions']):
            rows=[by[key,pid,arm,s,d] for s in p['seeds']];cell=model['groups'][f'{pid}/{arm}/{d}']
            compare(f'{key}/{pid}/{arm}/{d}/valid',cell['layers']['strict_valid']['correct'],sum(x['strict_valid'] for x in rows))
            compare(f'{key}/{pid}/{arm}/{d}/observed',cell['observed'],sum(x['observed'] for x in rows))
        model_results[key]={'observed':sum(x['observed'] for x in observed.values() if x['model_key']==key),
            'valid_proofs':sum(x['strict_valid'] for x in observed.values() if x['model_key']==key),
            'selective_pairs':num_success,'robust_groups':num_robust,'order_depth_changed':num_order,'order_unmeasured':unmeasured_order}
    for pid,arm in itertools.product(p['problems'],p['arms']):
        rows=[(pairs['reference',pid,arm,s],pairs['candidate',pid,arm,s]) for s in p['seeds']]
        good=[(a,b) for a,b in rows if a['observed'] and b['observed']]
        both=sum(a['success'] and b['success'] for a,b in good)
        qa=sum(a['success'] and not b['success'] for a,b in good);gb=sum(b['success'] and not a['success'] for a,b in good)
        neither=sum(not a['success'] and not b['success'] for a,b in good)
        expected={'assigned':10,'observed_pairs':len(good),'unobserved_pairs':10-len(good),'both_success':both,'reference_only':qa,'candidate_only':gb,'neither_success':neither,'candidate_minus_reference_rate':(gb-qa)/10 if status['complete'] else None}
        for k,v in expected.items():compare(f'{pid}/{arm}/cross/{k}',r['cross_model_results'][f'{pid}/{arm}'][k],v)
    result={'evidence_kind':r['evidence_kind'],'bundle_sha256':sha(bundle.read_bytes()),'manifest_files':len(manifest['file_hashes']),
        'observed_responses':sum(x['observed'] for x in observed.values()),'metadata_records':metadata_count,
        'data_complete':status['complete'],'semantic_fields_compared':count,'differences':differences,'models':model_results,
        'scope':'독립 원문 그래프·대응 비교·해시 검사. metadata identity 의미와 파일 허용목록/계획 계약은 생산 감사와 병행. 새 실제 LLM 추론 결과 아님.'}
    need(not differences,'independent discrepancies: '+json.dumps(differences[:8],ensure_ascii=False))
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('bundle',type=Path);parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    result=verify(args.bundle);args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,ensure_ascii=False,indent=2))
