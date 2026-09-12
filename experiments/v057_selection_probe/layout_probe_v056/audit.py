"""호출 원문·모델 식별·행동 순서·측정을 오프라인에서 재구성한다."""
from __future__ import annotations
from pathlib import Path
from paired_probe_v049.runner import endpoint_base
from order_probe_v054.design import problem_for, role_for
from order_probe_v054.schema import schema_for
from order_probe_v054.measure import measure, role_match
from .contracts import *
from .plan import validate_plan
from .requests import request_bytes
from .runner import metadata_failure, call_failure
from .reporting import summarize, save_report

REPORT_FILES={'audit.json','summary.json','summary.ko.md'}

def audit_run(plan_path,out,*,write_report=False):
    try:
        require_external_plan(plan_path,out)
        report=_audit(plan_path,out)
        if write_report:save_report(out,report)
        return report
    except (ContractError,OSError,KeyError,ValueError,TypeError) as exc:
        if write_report and out.is_dir():
            bad={'contract':'v056-audit-failure-r1','data_integrity':False,'data_complete':False,
                'comparative_analysis_ready':False,'error':type(exc).__name__+': '+str(exc)}
            write_json(out/'audit.json',bad);write_json(out/'summary.json',bad)
            (out/'summary.ko.md').write_text('# v056 감사 실패\n\n이전 PASS는 무효입니다. 요청·응답은 보존했습니다.\n\n'+bad['error']+'\n',encoding='utf-8')
        raise

def _audit(plan_path,out):
    require(out.is_dir() and not out.is_symlink() and not any(p.is_symlink() for p in out.rglob('*')),'결과 없음/링크 거부')
    plan=read_plan_json(plan_path);validate_plan(plan)
    from .evidence import validate_reference_file
    validate_reference_file(out/'baseline/v055_evidence.zip',plan)
    require(canonical(read_plan_json(out/'plan.snapshot.json'))==canonical(plan),'외부 계획/snapshot 불일치')
    m=read_json(out/'run_manifest.json');status=read_json(out/'status.json')
    manifest_keys={'contract','plan_sha256','source_fingerprint','started_at','python','platform','endpoint','evidence_kind','new_model_inference','max_calls','retry_policy','warmup_calls'}
    require(set(m)==manifest_keys and m['contract']=='v056-run-manifest-r1','run manifest 필드/계약')
    require(m['plan_sha256']==plan['plan_sha256'] and m['source_fingerprint']==plan['source_fingerprint'],'manifest 계획/소스 변경')
    require(m['endpoint']==endpoint_base(plan['baseline']['config']['endpoint']),'endpoint 변경')
    require(m['evidence_kind']==plan['reference']['evidence_kind'] and m['new_model_inference'] is (m['evidence_kind']!='synthetic_fixture'),'출처 변경')
    require(type(m['max_calls']) is int and m['max_calls']==480 and m['retry_policy']=='none' and type(m['warmup_calls']) is int and m['warmup_calls']==0,'실행 정책 변경')
    snap=out/'source_snapshot';fingerprint=plan['source_fingerprint']
    require({p.relative_to(snap).as_posix() for p in snap.rglob('*') if p.is_file()}==set(fingerprint),'소스 snapshot 파일 목록 변경')
    for name,expected in fingerprint.items():
        raw=(snap/name).read_text(encoding='utf-8-sig').replace('\r\n','\n').replace('\r','\n').encode('utf-8')
        require(sha(raw)==expected,'소스 snapshot 내용 변경: '+name)
    statuskeys={'state','complete','recorded_actions','inference_calls','event_tip','active_action','failure_stage','failure_kind','failure_slot_id','error','finished_at'}
    require(set(status)==statuskeys,'status 필드 변경')
    require(status['state'] in ('complete','incomplete','interrupted') and type(status['complete']) is bool,'실행 상태 형식')
    complete=status['complete'];require(complete is (status['state']=='complete'),'상태/완료 모순')
    for key in ('recorded_actions','inference_calls'):require(type(status[key]) is int and status[key]>=0,'실행 수 자료형')
    lines=(out/'events.jsonl').read_bytes().splitlines();require(all(x.strip() for x in lines),'빈 event 행')
    events=[strict_json(x) for x in lines]
    require(len(events)==status['recorded_actions'] and len(events)<=len(plan['actions']),'event 수 변경')
    if complete:
        require(len(events)==520 and status['inference_calls']==480 and status['active_action'] is None,'완료 실행 누락')
        require(all(status[k] is None for k in ('failure_stage','failure_kind','failure_slot_id','error')),'완료 상태에 오류 잔존')
    else:
        require(isinstance(status['error'],str) and bool(status['error']),'미완료 원인 누락')
        require(type(status['active_action']) is int and 0<=status['active_action']<len(plan['actions']),'실패 action 누락')
    expected_files={'plan.snapshot.json','run_manifest.json','status.json','events.jsonl','baseline/v055_evidence.zip'}|{'source_snapshot/'+n for n in fingerprint}
    tip=plan['plan_sha256'];observed={};calls=[];last_failure=None
    for i,event in enumerate(events):
        action=plan['actions'][i]
        require(canonical(event['action'])==canonical(action),'동결 실행 순서/모델/조건 변경')
        require(event['previous_hash']==tip and event['event_hash']==digest({k:v for k,v in event.items() if k!='event_hash'}),'event 해시 연결 변경');tip=event['event_hash']
        base={'action','at','previous_hash','event_hash'}
        if action['kind']=='metadata':
            require(set(event)==base|{'metadata_sha256'},'metadata event 필드 변경')
            name='metadata/'+action['id']+'.json';expected_files.add(name)
            raw=(out/name).read_bytes();require(sha(raw)==event['metadata_sha256'],'metadata 원문 변경')
            record=strict_json(raw);failure,error=metadata_failure(record,plan['identities'][action['model_key']])
        else:
            require(set(event)==base|{'request_sha256','response_sha256','http_status','transport_error','elapsed_ns'},'call event 필드 변경')
            slot=action['slot'];sid=slot['id'];key=slot['model_key'];model=plan['identities'][key]['model']
            reqname='calls/'+sid+'/request.wire.json';rawname='calls/'+sid+'/response.raw.json'
            expected_files.update((reqname,rawname));request=(out/reqname).read_bytes();raw=(out/rawname).read_bytes()
            require(sha(request)==event['request_sha256'] and sha(raw)==event['response_sha256'],'요청/응답 바이트 변경')
            require(request==request_bytes(plan,slot),'동결 요청/실제 요청 불일치')
            require(type(event['http_status']) is int and 0<=event['http_status']<=599 and type(event['elapsed_ns']) is int and event['elapsed_ns']>=0,'HTTP 자료형')
            require(event['transport_error'] is None or isinstance(event['transport_error'],str),'HTTP 오류 자료형')
            failure,error=call_failure(raw,event['http_status'],event['transport_error'],model)
            payload=None;parse_error=None;record_status='transport_error' if failure=='transport_error' else 'invalid_response'
            if failure is None:
                try:
                    payload=decode_response(raw,model,'graph');record_status='valid_payload'
                    try:validate_payload(payload,schema_for(slot))
                    except ContractError as exc:record_status='invalid_payload_schema';parse_error=str(exc)
                except ContractError as exc:parse_error=str(exc)
            elif failure=='response_identity_error':record_status='response_identity_error'
            problem=problem_for(slot);measurement=measure(problem,payload,slot)
            role=role_for(slot);matched=role_match(measurement,role,problem) if role else None
            observed[sid]={**slot,'observed':True,'measurement':measurement,'role_match':matched,'status':record_status,'parse_error':parse_error}
            calls.append({**slot,'http_status':event['http_status'],'elapsed_ns':event['elapsed_ns'],
                'request_sha256':sha(request),'response_sha256':sha(raw),**usage(raw)})
        if failure:
            require(i==len(events)-1 and not complete,'검증 실패 후 재시도/계속 실행 금지')
            last_failure=(action,failure,error)
    require(tip==status['event_tip'],'event tip 불일치')
    if complete:require(len(calls)==status['inference_calls'],'추론 수 불일치')
    else:
        require(len(calls)<=status['inference_calls']<=len(calls)+1,'미완료 추론 시도수 불일치')
        if last_failure:
            action,failure,error=last_failure
            require(status['failure_stage']==action['kind'] and status['failure_kind']==failure and status['failure_slot_id']==action['id'] and status['error']==error,'실패 진단/원문 불일치')
            require(status['active_action']==action['index'] and status['inference_calls']==len(calls),'실패 action 불일치')
        else:
            require(status['failure_kind'] in ('execution_error','user_interrupt'),'미완료 실패 종류')
            require(len(events)<len(plan['actions']),'모든 action 이후 설명 없는 실패')
            pending=plan['actions'][len(events)]
            require(status['active_action']==len(events) and status['failure_slot_id']==pending['id'] and status['failure_stage']==pending['kind'],'중단 action 불일치')
            if pending['kind']=='call':
                name='calls/'+pending['id']+'/request.wire.json'
                if (out/name).exists():
                    require((out/name).read_bytes()==request_bytes(plan,pending['slot']),'중단 요청 변경');expected_files.add(name)
            require(status['inference_calls']==len(calls) or pending['kind']=='call','metadata 중단을 추론 호출로 계산')
    actual={p.relative_to(out).as_posix() for p in out.rglob('*') if p.is_file()}
    require(actual-REPORT_FILES==expected_files,'자료 파일 누락/추가: '+str(sorted((actual-REPORT_FILES)^expected_files)))
    trials=[observed.get(s['id'],{**s,'observed':False,'measurement':None,'role_match':None,'status':'unexecuted','parse_error':None}) for s in plan['slots']]
    result=summarize(plan,trials,calls,complete)
    result.update(data_integrity=True,data_complete=complete,comparative_analysis_ready=complete,
        evidence_kind=m['evidence_kind'],new_model_inference=m['new_model_inference'],
        inference_calls=status['inference_calls'],max_inference_calls=480,plan_sha256=plan['plan_sha256'],event_tip=tip,
        run_state=status['state'],run_error=status['error'],failure_stage=status['failure_stage'],failure_kind=status['failure_kind'],
        failure_slot_id=status['failure_slot_id'],trials=trials,calls=calls,source_fingerprint=fingerprint,
        reference_bundle_sha256=plan['reference']['bundle_sha256'])
    return result
