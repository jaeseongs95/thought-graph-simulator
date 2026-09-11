"""검토한 v0.4.3 결과의 원문과 채점을 재검증한다. 스냅샷 코드를 실행하지 않는다."""
from __future__ import annotations
import copy
import re
from pathlib import Path
from .approved_v043 import APPROVED_SOURCES
from .common import (read_json, require, bytes_hash, wire_json, digest,
                     source_text_identity, require_core_compatible)
from .report import read_records
from .decision_probe import EXPECTED_ROLES


def load_decision_source(core, core_info: dict, source: Path) -> dict:
    from .runner import request_body, assess_response
    source = source.resolve()
    manifest = read_json(source/'manifest.json'); f = manifest['frozen'];plan=f['plan']
    require(f.get('extension_version') == '0.4.3', 'v0.4.3 decision_probe 원본을 지정하세요.')
    require(plan.get('probe_contract') == 'decision-v043', 'decision-v043 실행만 지원합니다.')
    require(f.get('runtime_sources_sha256') == APPROVED_SOURCES, '검토한 배포 소스 지문과 다릅니다.')
    for name,h in APPROVED_SOURCES.items():
        require(bytes_hash((source/'source_snapshot'/name).read_bytes()) == h, '소스 스냅샷 불일치: '+name)
    core_snapshot = source/'source_snapshot/adm_minimal.py'
    snapshot_bytes = core_snapshot.read_bytes()
    require(bytes_hash(snapshot_bytes) == f['core']['sha256'], '기록된 core 스냅샷 자체가 manifest와 다릅니다.')
    snapshot_info = source_text_identity(snapshot_bytes)
    core_compat = require_core_compatible(snapshot_info, core_info,
        '현재 core와 기록된 core의 실제 소스 내용이 다릅니다.')
    for c in plan['cases']:
        require(re.fullmatch('[a-f0-9]{24}', c.get('case_id','')) is not None, 'case_id 경로 오류')
        unsigned={k:v for k,v in c.items() if k!='case_id'}
        require(digest(unsigned)[:24] == c['case_id'], 'case 내용 해시 불일치')
    records=read_records(source,manifest)
    require(len(records)==len(plan['cases'])==8,'원본 배정 8건 모두가 필요합니다. 실패 조건도 포함하세요.')
    problems={p['id']:p for p in plan['problems']};selected=[];replayed=[]
    for record in records:
        c=record['case'];folder=source/'cases'/c['case_id'];p=problems[c['problem_id']]
        req=read_json(folder/'request.json');raw=read_json(folder/'response.raw.json');wire=(folder/'request.wire.json').read_bytes()
        require(req['case_id']==c['case_id'] and req['run_sha256']==manifest['run_sha256'],'요청 식별자 불일치')
        body=request_body(f['config'],c,p)
        require(wire==wire_json(body).encode('utf-8')==wire_json(req['body']).encode('utf-8'),'실제 전송 원문 재현 불일치')
        require(req['wire_sha256']==bytes_hash(wire),'wire 해시 불일치')
        outcome,_=assess_response(core,p,c,plan['reference_depths'][p['id']],body,raw,f['config'].get('mode_policy'))
        for key in ('status','error','audit','usage','done_reason','response_channels'):
            require(outcome.get(key)==record.get(key),'원문 판정 재현 불일치: '+c['role_id']+'/'+key)
        replayed.append(dict(record,**outcome))
        if c['arm']=='staged':
            selected.append({'case':copy.deepcopy(c),'problem':copy.deepcopy(p),'request':copy.deepcopy(body),
                             'raw_response':copy.deepcopy(raw),'record':dict(record,**outcome),
                             'response_sha256':bytes_hash((folder/'response.raw.json').read_bytes())})
    require(len(selected)==4 and {x['case']['source_case']['role_id'] for x in selected}==EXPECTED_ROLES,
            '서로 다른 네 단계형 입력을 모두 보존해야 합니다.')
    return {'manifest':manifest,'records':replayed,'selected':selected,
            'validation':{'records_replayed':8,'selected_staged':4,'source_files_checked':len(APPROVED_SOURCES),
                          'network_called':False,'snapshot_code_executed':False},
            'core_compatibility':core_compat}
