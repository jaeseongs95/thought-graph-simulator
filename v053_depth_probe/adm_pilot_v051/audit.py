"""외부 고정 계획+요청·응답 원문+실제 DAG 간선의 오프라인 재계산."""
from __future__ import annotations
from pathlib import Path
from paired_probe_v049.runner import check_identity
from .contracts import *
from .plan import validate_plan,slots,dependency_ids
from .design import role_for
from .requests import request_bytes
from .measure import measure, role_match

def audit_run(plan_path,out,*,write_report=False):
    try:
        require_external_plan(plan_path,out)
        report=_audit(plan_path,out)
        if write_report:
            from .reporting import save_report
            save_report(out,report)
        return report
    except (ContractError,OSError,KeyError,TypeError,ValueError) as exc:
        if write_report and out.is_dir():
            bad={'contract':'v051-audit-failure-r1','data_integrity':False,'data_complete':False,
                 'comparative_analysis_ready':False,'error':type(exc).__name__+': '+str(exc),'at':utc_now()}
            write_json(out/'audit.json',bad);write_json(out/'summary.json',bad)
            (out/'summary.ko.md').write_text('# v051 감사 실패\n\n직전 PASS 보고서는 무효입니다. 요청·응답 원문은 보존했습니다.\n\n'+bad['error']+'\n',encoding='utf-8')
        raise

def _audit(plan_path,out):
    require(out.is_dir() and not out.is_symlink() and not any(q.is_symlink() for q in out.rglob('*')),'링크/누락 결과 거부')
    p=read_json(plan_path);validate_plan(p)
    require(canonical(read_json(out/'plan.snapshot.json'))==canonical(p),'외부 계획/snapshot 불일치')
    manifest=read_json(out/'run_manifest.json');status=read_json(out/'status.json')
    require(manifest['plan_sha256']==p['plan_sha256'] and manifest['source_fingerprint']==p['source_fingerprint'],'manifest 계획/소스 불일치')
    require(manifest['evidence_kind']==p['baseline']['evidence_kind'] and manifest['new_model_inference'] is (p['baseline']['evidence_kind']!='synthetic_fixture'),'실제/합성 출처 변경')
    require(manifest['retry_policy']=='none' and manifest['warmup_calls']==0 and manifest['max_calls']==p['max_calls'],'실행 정책 변경')
    snap=out/'source_snapshot';actual={}
    require({q.relative_to(snap).as_posix() for q in snap.rglob('*') if q.is_file()}==set(p['source_fingerprint']),'소스 snapshot 파일 목록 불일치')
    for n in p['source_fingerprint']:actual[n]=sha((snap/n).read_text(encoding='utf-8-sig').replace('\r\n','\n').replace('\r','\n').encode())
    require(actual==p['source_fingerprint'],'소스 snapshot 해시 변경')
    require(type(status['complete']) is bool and status['state'] in ('complete','incomplete','interrupted','running'),'실행 상태 형식 오류')
    complete=status['complete'];require(complete is (status['state']=='complete'),'상태/완료 불일치')
    for k in ('recorded_slots','inference_calls'):require(type(status[k]) is int and status[k]>=0,'기록수 자료형 오류')
    checkpoints=status['identity_checkpoints'];expected_cp=['runtime.before.json','runtime.round_001.json','runtime.after.json']
    require(isinstance(checkpoints,list) and checkpoints==expected_cp[:len(checkpoints)],'런타임 점검 순서/경로 변경')
    identities=[]
    for name in checkpoints:identities.append(check_identity(read_json(out/name),p['baseline']))
    if complete:
        require(checkpoints==expected_cp and status['runtime_identity_verified'] is True and status['error'] is None,'완료 실행 메타데이터 누락')
    else:require(status['runtime_identity_verified'] is False,'미완료 실행을 검증 완료로 변경')
    lines=(out/'events.jsonl').read_bytes().splitlines();require(all(l.strip() for l in lines),'빈 event행')
    events=[strict_json(l) for l in lines];expected_slots=slots(p)
    require(len(events)<=len(expected_slots) and status['recorded_slots']==len(events),'event 수 오류')
    if complete:require(len(events)==len(expected_slots),'완료 실행 슬롯 누락')
    previous=p['plan_sha256'];payloads={};observations={};entries={};calls=[];infra=0;identity_errors=0
    for i,e in enumerate(events):
        slot=expected_slots[i];sid=slot['id'];deps=dependency_ids(slot)
        require(canonical(e['slot'])==canonical(slot),'계획/실제 슬롯 불일치')
        require(e['previous_hash']==previous and e['event_hash']==digest({k:v for k,v in e.items() if k!='event_hash'}),'event 연결/해시 오류')
        previous=e['event_hash']
        parents=[{'id':d,'response_sha256':entries[d].get('response_sha256')} for d in deps]
        require(e['parents']==parents,'부모 ID/응답 원문 해시 연결 변경')
        missing=[d for d in deps if payloads.get(d) is None];payload=None;err=None
        if e['kind']=='blocked':
            require(bool(missing) and e['reason']=='invalid_parent_payload' and e['missing_parents']==missing,'정당하지 않은 단계 생략')
            require(not (out/'calls'/sid).exists(),'blocked 단계에 숨겨진 호출 원문')
            record_status='blocked'
        else:
            require(e['kind']=='call' and not missing,'부모 없이 실행한 호출')
            folder=out/'calls'/sid;req=(folder/'request.wire.json').read_bytes();raw=(folder/'response.raw.json').read_bytes()
            require(sha(req)==e['request_sha256'] and sha(raw)==e['response_sha256'],'요청/응답 바이트 해시 변경')
            require(req==request_bytes(p,slot,payloads),'실제 부모값/동결 요청 바이트 불일치')
            require(type(e['http_status']) is int and 0<=e['http_status']<=599 and type(e['elapsed_ns']) is int and e['elapsed_ns']>=0 and (e['transport_error'] is None or isinstance(e['transport_error'],str)),'HTTP 메타데이터 형식 오류')
            record_status='transport_error';local_correct=None;content_hash=None
            if e['http_status']==200 and e['transport_error'] is None:
                try:
                    payload=decode_response(raw,p['baseline']['config']['model'],slot['stage']);record_status='valid_payload'
                    try:validate_payload(payload)
                    except ContractError as schema_error:record_status='invalid_payload_schema';err=str(schema_error)
                except ContractError as exc:record_status='invalid_response';err=str(exc)
            else:infra+=1
            try:
                env=strict_json(raw)
                if isinstance(env,dict):
                    if isinstance(env.get('model'),str) and env['model']!=p['baseline']['config']['model']:
                        identity_errors+=1;record_status='response_identity_error'
                    msg=env.get('message')
                    if isinstance(msg,dict) and isinstance(msg.get('content'),str):content_hash=sha(msg['content'].encode())
            except ContractError:pass
            calls.append({**slot,'event_index':i,'request_sha256':sha(req),'response_sha256':sha(raw),
                'content_sha256':content_hash,'payload_sha256':digest(payload) if payload is not None else None,'status':record_status,'local_correct':local_correct,
                'elapsed_ns':e['elapsed_ns'],**usage(raw)})
        payloads[sid]=payload;observations[sid]={'status':record_status,'error':err};entries[sid]=e
    require(status['event_tip']==previous,'event tip 불일치')
    require(status['response_identity_mismatch'] is (identity_errors>0),'다른 모델 응답 상태 불일치')
    if complete:require(infra==0 and identity_errors==0 and len(calls)==status['inference_calls'],'완료 상태/통신/호출수 모순')
    else:require(len(calls)<=status['inference_calls']<=len(calls)+1,'미완료 시도수 불일치')
    # 미완료 시 전송 중단된 마지막 요청 하나만 원문이 불완전할 수 있다.
    expected_files={e['slot']['id']+'/'+f for e in events if e['kind']=='call' for f in ('request.wire.json','response.raw.json')}
    callroot=out/'calls';actual_files={q.relative_to(callroot).as_posix() for q in callroot.rglob('*') if q.is_file()}
    if complete:require(actual_files==expected_files,'미등록/누락 호출 파일')
    else:
        extras=actual_files-expected_files
        allowed=set()
        if len(events)<len(expected_slots):
            sid=expected_slots[len(events)]['id'];allowed={sid+'/request.wire.json',sid+'/response.raw.json'}
        require(expected_files<=actual_files and extras<=allowed,'미완료 실행의 미등록 호출 파일')
    trials=[]
    for slot in expected_slots:
        observation=observations.get(slot['id']);role=role_for(slot)
        assessable=observation is not None and observation['status'] not in ('transport_error','response_identity_error')
        m=measure(p['problem'],payloads.get(slot['id'])) if assessable else None
        trials.append({**slot,'role':role,'observed':observation is not None,'assessable':assessable,
                       'measurement':m,'role_match':role_match(m,role) if m is not None else None,
                       'status':observation['status'] if observation else 'not_executed'})
    from .reporting import summarize
    report=summarize(p,trials,calls,observations,complete)
    report.update({'data_integrity':True,'data_complete':complete,'comparative_analysis_ready':complete,
        'evidence_kind':manifest['evidence_kind'],'new_model_inference':manifest['new_model_inference'],
        'plan_sha256':p['plan_sha256'],'event_tip':previous,'recorded_slots':len(events),'inference_calls':len(calls),
        'max_inference_calls':p['max_calls'],'run_state':status['state'],'run_error':status['error'],
        'runtime_identity':identities[-1] if identities else None,'trials':trials,'calls':calls,
        'source_fingerprint':p['source_fingerprint'],'reference_bundle_sha256':p['reference']['bundle_sha256']})
    return report
