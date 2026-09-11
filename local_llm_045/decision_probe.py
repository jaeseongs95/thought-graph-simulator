"""v0.4.3: 기존 4개 기준 과제의 format 대조와 모델 중간값 재사용을 각각 4회 실행.

원본 실패/원문은 보존한다. 정답 상수 강제, 잘못된 중간값 교정, 성공 조건 선별은 없다.
--plan-only는 네트워크 없이 계획만 검증한다. 새 실행은 저장된 모델/서버/설정을 고정한다.
"""
from __future__ import annotations
import argparse
import copy
import json
import re
import sys
from pathlib import Path
from typing import Any
from .common import (ContractError, bytes_hash, digest, load_core, read_json, require,
                     strict_json, wire_json, write_json, source_text_identity,
                     require_core_compatible)
from .approved_v042 import APPROVED_SOURCES
from .protocol import obj, validate_schema
from .micro_probe import FINDING, output_schema as source_schema, assess_payload as source_assess
from .decision_evidence import FIELDS, witness_evidence

CONTRACT = 'decision-v043'
ARMS = ('format_json', 'staged')
EXPECTED_ROLES = {'criterion_goal_not_fact', 'criterion_fact_not_goal',
                  'criterion_goal_is_fact', 'criterion_neither'}


def output_schema(case: dict) -> dict:
    return source_schema(case['source_case']) if case['arm'] == 'format_json' else obj({'finding': copy.deepcopy(FINDING)})


def load_source(core: Any, core_info: dict, source: Path) -> dict:
    """스냅샷 지문과 실제 요청/원문/기존 판정을 확인. 외부 Python을 실행하지 않는다."""
    from .report import read_records
    from .runner import request_body, assess_response
    source = source.resolve()
    manifest = read_json(source/'manifest.json'); frozen = manifest['frozen']
    require(frozen.get('extension_version') == '0.4.2', '현재 이관은 검토한 v0.4.2 원본만 지원합니다.')
    require(frozen.get('runtime_sources_sha256') == APPROVED_SOURCES, '승인된 v0.4.2 소스가 아닙니다.')
    require(frozen['plan'].get('probe_contract') == 'micro-v042', 'micro-v042 원본이 필요합니다.')
    for name, expected in APPROVED_SOURCES.items():
        require(bytes_hash((source/'source_snapshot'/name).read_bytes()) == expected,
                '소스 스냅샷 변조/누락: '+name)
    core_snapshot = source/'source_snapshot/adm_minimal.py'
    snapshot_bytes = core_snapshot.read_bytes()
    require(bytes_hash(snapshot_bytes) == frozen['core']['sha256'], '기록된 core 스냅샷 자체가 manifest와 다릅니다.')
    snapshot_info = source_text_identity(snapshot_bytes)
    core_compat = require_core_compatible(snapshot_info, core_info,
        '원본과 현재 adm_minimal.py의 실제 소스 내용이 다릅니다.')
    records = read_records(source, manifest)
    require(len(records) == len(frozen['plan']['cases']), '원본의 모든 배정 기록이 있어야 합니다.')
    problems = {p['id']:p for p in frozen['plan']['problems']}
    selected = []
    for record in records:
        case=record['case']; cid=case['case_id']
        require(re.fullmatch('[a-f0-9]{24}',cid) is not None, '원본 case_id 형식 오류')
        folder=source/'cases'/cid; envelope=read_json(folder/'request.json')
        wire=(folder/'request.wire.json').read_text(encoding='utf-8')
        require(bytes_hash(wire.encode('utf-8')) == envelope['wire_sha256'], '원본 wire 해시 불일치')
        require(wire_json(envelope['body']) == wire, '저장된 요청 객체와 실제 전송 문자열 불일치')
        problem=problems[case['problem_id']]
        require(wire_json(request_body(frozen['config'],case,problem)) == wire, '원본 요청 재현 불일치')
        response=read_json(folder/'response.raw.json')
        result,_=assess_response(core,problem,case,frozen['plan']['reference_depths'][problem['id']],
                                envelope['body'],response,frozen['config'].get('mode_policy'))
        # v043은 채점/요청을 바꾸지 않았다. 진단 객체 추가는 상태·오류·audit 대조 대상 밖이다.
        for key in ('status','error','audit','usage','done_reason','response_channels'):
            require(result.get(key)==record.get(key), '원본 판정 재현 불일치: '+case['role_id']+'/'+key)
        if case['task'] != 'criterion_witness': continue
        require(case.get('format_mode')=='schema', 'format 대조 기준은 schema 원본이어야 합니다.')
        payload=strict_json(response['message']['content']);validate_schema(payload,source_schema(case))
        require(response.get('done') is True and response.get('done_reason')=='stop','완료된 원본 응답이 필요합니다.')
        # 성공한 조건만 선택하지 않는다. 잘못된 중간값도 수정 없이 다음 단계로 전달한다.
        ev=witness_evidence(problem,case,payload)
        selected.append({'case':copy.deepcopy(case),'problem':copy.deepcopy(problem),
            'request':copy.deepcopy(envelope['body']),'response_sha256':bytes_hash((folder/'response.raw.json').read_bytes()),
            'content_sha256':bytes_hash(response['message']['content'].encode('utf-8')),
            'original_status':record['status'],'original_audit':copy.deepcopy(record['audit']),
            'projection':{k:copy.deepcopy(payload[k]) for k in ('observed','primitives')},
            'source_evidence':ev})
    require(len(selected)==4 and {x['case']['role_id'] for x in selected}==EXPECTED_ROLES,
            '네 가지 기준 조건이 각각 한 번 있어야 합니다. 실패 조건을 제외하지 마세요.')
    return {'manifest':manifest,'selected':selected,
            'validation':{'all_source_records_replayed':len(records),'criterion_cases':len(selected),
                          'snapshot_files_verified':len(APPROVED_SOURCES),'network_called':False},
            'core_compatibility':core_compat}


def staged_messages(projection: dict) -> list[dict]:
    """모델이 앞선 호출에서 낸 두 객체만 입력으로 제공한다. 판정 정답은 포함하지 않는다."""
    system = (
        '앞선 모델 응답의 observed와 primitives가 입력으로 제공된다. 아래 식에 따라 finding만 작성한다.\n'
        'a는 primitives.same_as_goal, b는 primitives.in_facts다.\n'
        'finding.answer_only_accepts = a; finding.proof_and_goal_accepts = a AND b; '
        'finding.gap_detected = a AND NOT b.\n'
        '제공된 중간값을 바꾸거나 새 증명을 만들지 않는다. 각 판정은 모델이 직접 계산한다. '
        '정답값을 고정하는 스키마는 없으며, JSON 객체 하나만 출력한다.\n'
        '출력 JSON Schema(정답값이 아닌 형식 명세):\n'+wire_json(obj({'finding':copy.deepcopy(FINDING)})))
    return [{'role':'system','content':system},
            {'role':'user','content':'previous_model_output: '+wire_json(projection)}]


def build_plan(source: dict, arms: list[str] | None = None) -> dict:
    arms = list(ARMS) if arms is None else list(arms)
    require(arms and len(arms)==len(set(arms)) and set(arms)<=set(ARMS),'arm 선택 오류')
    mf=source['manifest'];f=mf['frozen'];cases=[]
    for original in source['selected']:
        old=original['case']
        for arm in arms:
            case={'problem_id':old['problem_id'],'problem_sha256':old['problem_sha256'],
                  'role':copy.deepcopy(old['role']),'role_id':old['role_id']+'__'+arm,
                  'repeat':old['repeat'],'seed':old['seed'],'task':'decision_stage' if arm=='staged' else 'criterion_witness',
                  'calibration_version':4,'probe_contract':CONTRACT,'diagnostic_group':arm,'arm':arm,
                  'probe_atom':old['probe_atom'],'source_case':copy.deepcopy(old),
                  'source_run_sha256':mf['run_sha256'],
                  'source_request':copy.deepcopy(original['request']),
                  'source_response_sha256':original['response_sha256'],
                  'source_content_sha256':original['content_sha256'],
                  'source_original_status':original['original_status'],
                  'source_projection':copy.deepcopy(original['projection']),
                  'source_original_audit':copy.deepcopy(original['original_audit']),
                  'source_evidence':copy.deepcopy(original['source_evidence'])}
            case['case_id']=digest(case)[:24];cases.append(case)
    return {'profile':'decision-probe','experiment_kind':'calibration','probe_contract':CONTRACT,
            'problems':copy.deepcopy(f['plan']['problems']),'roles':[], 'cases':cases,
            'assigned_calls':len(cases),'repeats':1,'seed':f['plan']['seed'],
            'reference_depths':copy.deepcopy(f['plan']['reference_depths']), 'warnings':[],
            'scope':'diagnostic_only_no_combined_ADM_rate', 'arms':arms,
            'source_run_sha256':mf['run_sha256'],'source_validation':source['validation'],
            'source_identity':{k:copy.deepcopy(f[k]) for k in ('config','core','model','ollama_server')},
            'design_note':'format_json은 실제 요청의 format만 변경. staged는 원래 모델 중간값의 두 객체를 '
                          '다음 호출 입력으로 투영한 새 파이프라인이며 순수 필드 순서 효과가 아니다. '
                          '원래 실패는 보존하고 파이프라인 성공을 본 ADM 결과로 합산하지 않는다.'}


def validate_runtime(plan: dict, info: dict, config: dict, metadata: dict) -> None:
    identity=plan['source_identity']
    require_core_compatible(identity['core'], info, '원본과 core의 실제 소스 내용이 다릅니다.')
    require(config==identity['config'],'대조는 원본의 확정된 생성 설정을 그대로 사용해야 합니다.')
    require(metadata['tag']['digest']==identity['model']['digest'],'모델 digest 변경: 이번 단일 조건 대조를 중단합니다.')
    require(digest(metadata['show'])==identity['model']['show_sha256'],'템플릿/모델 메타데이터 변경')
    require(metadata['server']==identity['ollama_server'],'Ollama 버전도 바뀌어 대조를 시작하지 않습니다.')


def make_request(config: dict, case: dict, problem: dict) -> dict:
    require(case.get('probe_contract')==CONTRACT,'진단 계약 오류')
    body=copy.deepcopy(case['source_request'])
    require(body['model']==config['model'] and body['options']==dict(config['options'],seed=case['seed']),
            '원본과 모델/샘플링 요청 불일치')
    require(body.get('think')==config.get('think'),'원본과 thinking 요청 불일치')
    if case['arm']=='format_json':
        body['format']='json'
    else:
        require(case['arm']=='staged','지원하지 않는 arm')
        body['messages']=staged_messages(case['source_projection'])
        body['format']=output_schema(case)
    return body


def assess_payload(core: Any, problem: dict, case: dict, payload: dict) -> dict:
    if case['arm']=='format_json':
        return source_assess(core,problem,case['source_case'],payload)
    validate_schema(payload,output_schema(case))
    source=case['source_projection'];x=source['primitives']['same_as_goal'];y=source['primitives']['in_facts']
    a=case['probe_atom']==problem['goal'];b=case['probe_atom'] in problem['facts']
    expected=dict(zip(FIELDS,(a,a and b,a and not b)))
    conditional=dict(zip(FIELDS,(x,x and y,x and not y)))
    correct_observed={'probe_atom':case['probe_atom'],'goal_atom':problem['goal'],'facts':problem['facts']}
    comparisons=[]
    def add(field,actual,want):
        comparisons.append({'field':field,'actual':copy.deepcopy(actual),'expected':copy.deepcopy(want),
                            'matches':type(actual) is type(want) and actual==want})
    add('source.observed',source['observed'],correct_observed)
    add('source.primitives',source['primitives'],{'same_as_goal':a,'in_facts':b})
    for k in FIELDS:add('finding.'+k,payload['finding'][k],expected[k])
    checks={v['field']:v['matches'] for v in comparisons}
    return {'valid_completion':all(checks.values()),'role_adherent':None,'calibration_task':'decision_stage',
            'task_checks':checks,'task_comparisons':comparisons,
            'details':{'output_modified':False,'projection_only_no_answer_correction':True,
                       'source_original_status':case['source_original_status'],
                       'source_response_sha256':case['source_response_sha256'],
                       'actual':copy.deepcopy(payload['finding']),
                       'conditional_consistency':payload['finding']==conditional,
                       'expected_from_unmodified_model_primitives':conditional,
                       'source_prerequisites_correct':checks['source.observed'] and checks['source.primitives']},
            'negative_controls':[],'negative_controls_ok':None,
            'interpretation':'별도 호출로 완성한 단계형 파이프라인. 원래 원샷 실패와 별도 기록하며 본 ADM 성공으로 합산하지 않는다.'}


def summarize(plan: dict, records: list[dict]) -> dict:
    byid={r['case']['case_id']:r for r in records};groups={};rows=[]
    for c in plan['cases']:
        r=byid.get(c['case_id']);g=groups.setdefault(c['arm'],{'assigned':0,'recorded':0,'accepted':0})
        g['assigned']+=1;g['recorded']+=int(r is not None);g['accepted']+=int(bool(r and r['status']=='accepted'))
        body=make_request(plan['source_identity']['config'],c,next(p for p in plan['problems'] if p['id']==c['problem_id']))
        source=copy.deepcopy(c['source_request']);a=copy.deepcopy(body);source.pop('format',None);a.pop('format',None)
        rows.append({'condition':c['source_case']['role_id'],'arm':c['arm'], 'source_case_id':c['source_case']['case_id'],
                     'source_status':c['source_original_status'],'new_status':r['status'] if r else 'not_started',
                     'source_response_sha256':c['source_response_sha256'],
                     'only_format_field_changed':wire_json(a)==wire_json(source) if c['arm']=='format_json' else None,
                     'new_audit':(r or {}).get('audit'),'new_diagnostics':(r or {}).get('task_diagnostics')})
    return {'contract':CONTRACT,'source_run_sha256':plan['source_run_sha256'], 'arms':groups,'cases':rows,
            'new_llm_calls_assigned':len(plan['cases']),'baseline_schema_calls_reexecuted':0,
            'source_statuses_not_overwritten':True,'decision_method':'per_case_evidence_not_majority_vote',
            'interpretation':'두 군은 다른 질문을 검사한다. format만의 대응 비교와 단계형 파이프라인의 수행을 구분한다. '
             'staged 성공은 순서/문맥/출력 부담의 묶음 변경 결과이며 순수 순서의 인과 증명이 아니다. '
             '캐시·가중치·서버 내부 상태까지 통제한 실험이 아니다.'}


def main(argv: list[str] | None=None) -> int:
    from .runner import run
    from .client import APIError
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True);p.add_argument('--out',type=Path)
    p.add_argument('--arm',action='append',choices=ARMS);p.add_argument('--plan-only',action='store_true')
    p.add_argument('--resume',action='store_true');p.add_argument('--fail-on-model-failure',action='store_true')
    args=p.parse_args(argv)
    try:
        core,info=load_core();source=load_source(core,info,args.input);plan=build_plan(source,args.arm)
        if args.plan_only:
            print(json.dumps({'model_called':False,'new_llm_calls':plan['assigned_calls'],
                 'source_validation':plan['source_validation'],'arms':plan['arms'],
                 'source_failures_preserved':True,'note':plan['design_note']},ensure_ascii=False,indent=2));return 0
        require(args.out is not None,'실행에는 새 --out 결과 폴더를 지정하세요.')
        out=args.out.resolve();source_path=args.input.resolve()
        require(out!=source_path and not out.is_relative_to(source_path) and not source_path.is_relative_to(out),
                '원본과 분리된 결과 폴더가 필요합니다.')
        print(f"단계형 기준 판정·format 대조: {plan['assigned_calls']}회 / 원본 4조건 재사용",flush=True)
        return run(core,info,plan,copy.deepcopy(source['manifest']['frozen']['config']),out,
                   resume=args.resume,fail_on_model_failure=args.fail_on_model_failure)
    except (ContractError,APIError,OSError,ValueError,KeyError,TypeError) as exc:
        print(f'오류: {exc}',file=sys.stderr);return 2
    except KeyboardInterrupt:return 130

if __name__=='__main__':raise SystemExit(main())
