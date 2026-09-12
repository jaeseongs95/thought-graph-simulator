"""로컬 Ollama 실행/원문 보존. 실행 중 정답 계산기·채점기를 호출하지 않는다."""
from __future__ import annotations
import os,platform,sys
from pathlib import Path
from paired_probe_v049.runner import OllamaHTTP,check_identity
from .contracts import *
from .plan import validate_plan,slots,dependency_ids
from .requests import request_bytes

def execute(plan_path,out):
    p=read_json(plan_path);validate_plan(p)
    require(not out.exists(),'기존 결과 폴더 덮어쓰기 금지: '+str(out))
    require_external_plan(plan_path,out)
    cfg=p['baseline']['config'];http=OllamaHTTP(cfg['endpoint'],cfg.get('timeout_seconds',180))
    out.mkdir(parents=True,exist_ok=False);write_json(out/'plan.snapshot.json',p,exclusive=True)
    root=Path(__file__).resolve().parent.parent
    for n in p['source_fingerprint']:
        dest=out/'source_snapshot'/n;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes((root/n).read_bytes())
    write_json(out/'run_manifest.json',{'plan_sha256':p['plan_sha256'],'source_fingerprint':source_fingerprint(),
        'started_at':utc_now(),'python':sys.version,'platform':platform.platform(),'endpoint':http.base,
        'evidence_kind':p['baseline']['evidence_kind'],'new_model_inference':p['baseline']['evidence_kind']!='synthetic_fixture',
        'retry_policy':'none','warmup_calls':0,'max_calls':p['max_calls']},exclusive=True)
    status={'state':'running','complete':False,'recorded_slots':0,'inference_calls':0,'event_tip':p['plan_sha256'],
            'runtime_identity_verified':False,'identity_checkpoints':[],'response_identity_mismatch':False,'error':None}
    write_json(out/'status.json',status);payloads={};recorded={};current_cycle=0
    with (out/'events.jsonl').open('xb') as stream:
        def append(e):
            e['previous_hash']=status['event_tip'];e['event_hash']=digest(e)
            stream.write(wire(e)+b'\n');stream.flush();os.fsync(stream.fileno())
            status['event_tip']=e['event_hash'];status['recorded_slots']+=1;recorded[e['slot']['id']]=e
            write_json(out/'status.json',status)
        def metadata(name):
            m=http.metadata(cfg['model']);write_json(out/name,m,exclusive=True);check_identity(m,p['baseline'])
            status['identity_checkpoints'].append(name)
        try:
            metadata('runtime.before.json')
            all_slots=slots(p)
            for i,slot in enumerate(all_slots):
                if slot['cycle']!=current_cycle:
                    current_cycle=slot['cycle'];metadata(f'runtime.round_{current_cycle:03d}.json')
                deps=dependency_ids(slot)
                parents=[{'id':d,'response_sha256':recorded[d].get('response_sha256')} for d in deps]
                event={'slot':slot,'at':utc_now(),'parents':parents}
                missing=[d for d in deps if payloads.get(d) is None]
                if missing:
                    event.update(kind='blocked',reason='invalid_parent_payload',missing_parents=missing)
                    append(event);payloads[slot['id']]=None;continue
                raw=request_bytes(p,slot,payloads)
                folder=out/'calls'/slot['id'];folder.mkdir(parents=True)
                (folder/'request.wire.json').write_bytes(raw)
                status['inference_calls']+=1;write_json(out/'status.json',status)
                print(f'[{i+1}/{len(all_slots)}] {slot["id"]}',flush=True)
                result=http.request('/api/chat',raw);(folder/'response.raw.json').write_bytes(result['raw'])
                event.update(kind='call',request_sha256=sha(raw),response_sha256=sha(result['raw']),
                    http_status=result['http_status'],transport_error=result['error'],elapsed_ns=result['elapsed_ns'])
                append(event);payloads[slot['id']]=None
                if result['http_status']!=200 or result['error'] is not None:
                    raise ContractError('통신 오류. 원문 보존, 자동 재시도 없음: '+str(result['error']))
                try:envelope=strict_json(result['raw'])
                except ContractError:envelope=None
                if isinstance(envelope,dict) and isinstance(envelope.get('model'),str) and envelope['model']!=cfg['model']:
                    status['response_identity_mismatch']=True;raise ContractError('다른 모델 응답. 원문 보존 후 중단')
                try:payloads[slot['id']]=decode_response(result['raw'],cfg['model'],slot['stage'])
                except ContractError:pass  # 형식 오류는 관측 실패이지 원문 수정의 이유가 아니다.
            metadata('runtime.after.json');status.update(state='complete',complete=True,runtime_identity_verified=True)
        except KeyboardInterrupt:status.update(state='interrupted',error='사용자 중단')
        except (ContractError,OSError,KeyError,ValueError,TypeError) as exc:
            status.update(state='incomplete',error=type(exc).__name__+': '+str(exc))
        finally:
            status['finished_at']=utc_now();write_json(out/'status.json',status)
    from .audit import audit_run
    return audit_run(plan_path,out,write_report=True)
