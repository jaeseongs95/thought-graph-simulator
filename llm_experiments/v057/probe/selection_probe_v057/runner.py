"""두 모델을 사전 동결된 순서로 실행한다. 답안 계산/자동 재시도/자동 다운로드 없음."""
from __future__ import annotations
import os, platform, sys
from pathlib import Path
from paired_probe_v049.runner import OllamaHTTP
from .contracts import *
from model_probe_v055.metadata import collect, decode_metadata, identity
from .plan import validate_plan
from .requests import request_bytes

def metadata_failure(record, expected):
    try:decode_metadata(record,expected['model'])
    except (ContractError,KeyError,TypeError,ValueError) as exc:return 'runtime_metadata_error',str(exc)
    try:
        current=identity(record,expected['model'])
        require(canonical(current)==canonical(expected),'동결한 모델 digest/show/server/details와 다릅니다')
    except (ContractError,KeyError,TypeError,ValueError) as exc:return 'runtime_identity_error',str(exc)
    return None,None

def call_failure(raw, status, error, expected_model):
    if status!=200 or error is not None:return 'transport_error',f'HTTP {status}: {error}'
    try:e=strict_json(raw)
    except ContractError:return None,None
    if isinstance(e,dict) and isinstance(e.get('model'),str) and e['model']!=expected_model:
        return 'response_identity_error','요청 모델과 응답 모델이 다릅니다: '+e['model']
    return None,None

def execute(plan_path, out):
    plan=read_plan_json(plan_path);validate_plan(plan);require_external_plan(plan_path,out)
    from .evidence import validate_reference_file
    baseline_path=plan_path.with_suffix('.baseline.zip')
    validate_reference_file(baseline_path,plan)
    baseline_bytes=baseline_path.read_bytes()
    require(sha(baseline_bytes)==plan['reference']['bundle_sha256'],'실행 전 기준선 ZIP 변경')
    require(not out.exists(),'기존 실행 자료 보존. 새 RunName 필요: '+str(out))
    cfg=plan['baseline']['config'];http=OllamaHTTP(cfg['endpoint'],cfg.get('timeout_seconds',300))
    out.mkdir(parents=True,exist_ok=False)
    (out/'baseline').mkdir();(out/'baseline/v056_evidence.zip').write_bytes(baseline_bytes)
    write_json(out/'plan.snapshot.json',plan,exclusive=True)
    root=Path(__file__).resolve().parent.parent
    for name in plan['source_fingerprint']:
        dest=out/'source_snapshot'/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes((root/name).read_bytes())
    write_json(out/'run_manifest.json',{'contract':'v057-run-manifest-r1','plan_sha256':plan['plan_sha256'],
        'source_fingerprint':source_fingerprint(),'started_at':utc_now(),'python':sys.version,'platform':platform.platform(),
        'endpoint':http.base,'evidence_kind':plan['reference']['evidence_kind'],
        'new_model_inference':plan['reference']['evidence_kind']!='synthetic_fixture',
        'max_calls':480,'retry_policy':'none','warmup_calls':0},exclusive=True)
    status={'state':'running','complete':False,'recorded_actions':0,'inference_calls':0,'event_tip':plan['plan_sha256'],
        'active_action':None,'failure_stage':None,'failure_kind':None,'failure_slot_id':None,'error':None}
    write_json(out/'status.json',status)
    with (out/'events.jsonl').open('xb') as stream:
        def persist():write_json(out/'status.json',status)
        def append(event):
            event['previous_hash']=status['event_tip'];event['event_hash']=digest(event)
            stream.write(wire(event)+b'\n');stream.flush();os.fsync(stream.fileno())
            status['recorded_actions']+=1;status['event_tip']=event['event_hash'];persist()
        try:
            for action in plan['actions']:
                status['active_action']=action['index'];persist()
                event={'action':action,'at':utc_now()}
                key=action['model_key'] if action['kind']=='metadata' else action['slot']['model_key']
                expected=plan['identities'][key]
                if action['kind']=='metadata':
                    record=collect(http,expected['model']);path=out/'metadata'/(action['id']+'.json')
                    write_json(path,record,exclusive=True);event['metadata_sha256']=sha(path.read_bytes())
                    failure,error=metadata_failure(record,expected)
                else:
                    slot=action['slot'];folder=out/'calls'/slot['id'];folder.mkdir(parents=True,exist_ok=False)
                    raw=request_bytes(plan,slot);(folder/'request.wire.json').write_bytes(raw)
                    status['inference_calls']+=1;persist()
                    print(f'[{status["inference_calls"]}/480] {slot["id"]}',flush=True)
                    result=http.request('/api/chat',raw);(folder/'response.raw.json').write_bytes(result['raw'])
                    event.update(request_sha256=sha(raw),response_sha256=sha(result['raw']),http_status=result['http_status'],
                        transport_error=result['error'],elapsed_ns=result['elapsed_ns'])
                    failure,error=call_failure(result['raw'],result['http_status'],result['error'],expected['model'])
                append(event)
                if failure:
                    status.update(state='incomplete',failure_stage=action['kind'],failure_kind=failure,
                        failure_slot_id=action['id'],error=error);break
            else:status.update(state='complete',complete=True,active_action=None)
        except KeyboardInterrupt:
            a=plan['actions'][status['active_action']] if status['active_action'] is not None else None
            status.update(state='interrupted',failure_stage=a['kind'] if a else 'created',failure_kind='user_interrupt',
                failure_slot_id=a['id'] if a else None,error='사용자 중단. 자동 재개하지 않습니다.')
        except (ContractError,OSError,KeyError,ValueError,TypeError) as exc:
            a=plan['actions'][status['active_action']] if status['active_action'] is not None else None
            status.update(state='incomplete',failure_stage=a['kind'] if a else 'created',failure_kind='execution_error',
                failure_slot_id=a['id'] if a else None,error=type(exc).__name__+': '+str(exc))
        finally:status['finished_at']=utc_now();persist()
    from .audit import audit_run
    return audit_run(plan_path,out,write_report=True)
