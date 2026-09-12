"""완료한 v053 원문을 독립 그래프 검증기로 재채점한다. 생산 채점기 import 없음."""
from __future__ import annotations
import argparse
import collections
import json
from pathlib import Path, PurePosixPath
import zipfile
from independent_review_v052 import Invalid, need, load, sha, canon, check, bound_depths


def verify(bundle: Path):
    with zipfile.ZipFile(bundle) as z:
        names=z.namelist()
        need(len(names)==len(set(names)), 'duplicate_zip_path')
        need(sum(i.file_size for i in z.infolist())<=256*1024**2, 'zip_size_limit')
        for name in names:
            p=PurePosixPath(name)
            need(not p.is_absolute() and '..' not in p.parts and '\\' not in name,'unsafe_path')
        manifest=load(z.read('BUNDLE_MANIFEST.json'))
        need(manifest['contract']=='v053-evidence-bundle-r1','bundle_contract')
        need(set(names)==set(manifest['file_hashes'])|{'BUNDLE_MANIFEST.json'},'inventory')
        for name,h in manifest['file_hashes'].items():need(sha(z.read(name))==h,'file_hash:'+name)
        plan=load(z.read('external_plan/v053.plan.json'));report=load(z.read('run/summary.json'))
        need(sha(canon({k:v for k,v in plan.items() if k!='plan_sha256'}))==plan['plan_sha256'],'plan_digest')
        need(load(z.read('run/plan.snapshot.json'))==plan,'external_plan_snapshot')
        need(report['data_complete'] is True,'complete_run_required')
        events=[load(x) for x in z.read('run/events.jsonl').splitlines()]
        need(len(events)==len(plan['slots'])==120,'complete_120')
        stored={r['id']:r for r in report['trials']};rows=[];discrepancies=[];previous=plan['plan_sha256']
        for slot,event in zip(plan['slots'],events):
            need(event['slot']==slot and event['previous_hash']==previous,'event_order')
            need(event['event_hash']==sha(canon({k:v for k,v in event.items() if k!='event_hash'})),'event_hash')
            previous=event['event_hash'];sid=slot['id']
            need(event['kind']=='call' and event['parents']==[], 'event_contract')
            request=z.read('run/calls/'+sid+'/request.wire.json');raw=z.read('run/calls/'+sid+'/response.raw.json')
            need(sha(request)==event['request_sha256'] and sha(raw)==event['response_sha256'],'wire_hash')
            request=load(request);env=load(raw)
            need(event['http_status']==200 and event['transport_error'] is None,'transport')
            need(env['model']==plan['baseline']['config']['model'] and env['done'] is True and env['done_reason']=='stop','response_identity_completion')
            msg=env['message'];need(msg['role']=='assistant' and not msg.get('thinking') and not msg.get('tool_calls') and not msg.get('images'),'message_contract')
            payload=None
            try:payload=load(msg['content']);need(isinstance(payload,dict),'object')
            except Invalid:payload=None
            problem=plan['problems'][slot['problem_id']]
            m=check(problem,payload,request['format'],'explicit','graph_only')
            for key in ('format_valid','proof_valid','strict_valid','D'):
                if m[key]!=stored[sid]['measurement'][key]:discrepancies.append({'slot_id':sid,'field':key})
            if m['final_reference_exists']!=stored[sid]['measurement']['final_ref_valid']:
                discrepancies.append({'slot_id':sid,'field':'final_ref_valid'})
            role=None
            if slot['direction']!='neutral':
                target=bound_depths(problem)[0 if slot['direction']=='shallow' else 1]
                role=bool(m['strict_valid'] and m['D']==target)
                if role!=stored[sid]['role_match']:discrepancies.append({'slot_id':sid,'field':'role_match'})
            rows.append({**slot,'strict_valid':m['strict_valid'],'D':m['D'],'role_match':role})
        need(previous==report['event_tip'],'event_tip')
        lookup={(r['problem_id'],r['arm'],r['seed'],r['direction']):r for r in rows};pairs=[]
        for pid in plan['problems']:
            for arm in plan['arms']:
                for seed in plan['seeds']:
                    a,b=(lookup[pid,arm,seed,d] for d in ('shallow','deep'))
                    success=bool(a['role_match'] and b['role_match'] and a['D']!=b['D'])
                    pairs.append({'problem_id':pid,'arm':arm,'seed':seed,'selective_success':success})
        groups={}
        for pid in plan['problems']:
            for arm in plan['arms']:
                rs=[r for r in rows if r['problem_id']==pid and r['arm']==arm]
                ps=[p for p in pairs if p['problem_id']==pid and p['arm']==arm]
                groups[pid+'/'+arm]={'valid':sum(r['strict_valid'] for r in rs),'requested_depth_success':sum(r['role_match'] is True for r in rs),'selective_pairs':sum(p['selective_success'] for p in ps)}
                if groups[pid+'/'+arm]['selective_pairs']!=report['core_results'][pid+'/'+arm]['direction_selective_success']:
                    discrepancies.append({'group':pid+'/'+arm,'field':'direction_selective_success'})
        return {'bundle_sha256':sha(bundle.read_bytes()),'source':'raw_only_independent_semantic_replay',
                'evidence_kind':report['evidence_kind'],'raw_responses':len(rows),'manifest_files':len(manifest['file_hashes']),
                'semantic_fields_compared':5*len(rows)+80,'discrepancies':discrepancies,'groups':groups,'pairs':pairs,
                'scope':'완료·정상 전송 120회만 지원. 생산 감사기의 source/runtime/request 재생성 검사와 함께 사용.'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('bundle',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();r=verify(a.bundle);a.out.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in r.items() if k!='pairs'},ensure_ascii=False,indent=2));return 1 if r['discrepancies'] else 0

if __name__=='__main__':raise SystemExit(main())
