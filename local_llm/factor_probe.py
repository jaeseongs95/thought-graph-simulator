"""v0.4.4: 동일한 네 입력에서 한 요인씩 바꾸는 대조. 기본 16회, 추가 0도 조건은 선택형.
replay / json / b_last / neutral_keys의 결과를 다수결하거나 최선 응답만 고르지 않는다.
"""
from __future__ import annotations
import argparse
import copy
import json
import random
import sys
from pathlib import Path
from .common import ContractError, require, load_core, digest, wire_json, bytes_hash
from .decision_source import load_decision_source
from .decision_probe import assess_payload as original_assess, validate_runtime
from .protocol import obj
from .micro_probe import FINDING
from .decision_evidence import FIELDS

CONTRACT='factor-v044'
DEFAULT_ARMS=('replay','json','b_last','neutral_keys')
ARMS=DEFAULT_ARMS+('temperature_zero',)
NEUTRAL=dict(zip(FIELDS,('r0','r1','r2')))


def output_schema(case: dict) -> dict:
    mapping=case.get('output_key_map',{k:k for k in FIELDS})
    return obj({'finding':obj({mapping[k]:{'type':'boolean'} for k in FIELDS})})


def make_request(config: dict, case: dict, problem: dict) -> dict:
    body=copy.deepcopy(case['source_request']);arm=case['arm']
    require(case['probe_contract']==CONTRACT and arm in ARMS,'진단 계약 오류')
    require(body['model']==config['model'] and body['options']==dict(config['options'],seed=case['seed']),
            '기준선의 모델·샘플링 설정이 바뀌었습니다.')
    if arm=='json':
        body['format']='json'
    elif arm=='b_last':
        projection=copy.deepcopy(case['source_projection'])
        bits=projection['primitives']
        projection['primitives']={'same_as_goal':bits['same_as_goal'],'in_facts':bits['in_facts']}
        body['messages'][1]['content']='previous_model_output: '+wire_json(projection)
    elif arm=='neutral_keys':
        # 필드명만 일대일 치환한다. 입력 값·연산 식·샘플링·반환 값은 교정하지 않는다.
        for old,new in NEUTRAL.items():
            body['messages'][0]['content']=body['messages'][0]['content'].replace(old,new)
        body['format']=output_schema(case)
    elif arm=='temperature_zero':
        body['options']['temperature']=0
    return body


def check_delta(case: dict, body: dict) -> dict:
    """실제 전송 문자열 수준의 허용 변경만 검사. JSON 키 순서 비교를 잊지 않는다."""
    old=copy.deepcopy(case['source_request']);new=copy.deepcopy(body);arm=case['arm']
    if arm=='json':
        require(new.pop('format')=='json','json 조건 오류');old.pop('format')
    elif arm=='b_last':
        old_text=old['messages'][1]['content'];new_text=new['messages'][1]['content']
        old_value=json.loads(old_text.split(': ',1)[1]);new_value=json.loads(new_text.split(': ',1)[1])
        require(old_value==new_value,'키 순서 대조에서 입력 값이 바뀌었습니다.')
        require(list(new_value['primitives'])==['same_as_goal','in_facts'],'b_last 순서 오류')
        new['messages'][1]['content']=old_text
    elif arm=='neutral_keys':
        require(new['format']==output_schema(case),'이름 치환 스키마 오류')
        new['format']=old['format']
        for original,neutral in NEUTRAL.items():new['messages'][0]['content']=new['messages'][0]['content'].replace(neutral,original)
    elif arm=='temperature_zero':
        require(new['options']['temperature']==0,'온도 대조 오류');new['options']['temperature']=old['options']['temperature']
    require(wire_json(old)==wire_json(new),'허용하지 않은 조건 변경 발견')
    return {'allowed_delta_verified':True,'arm':arm,
            'request_identical':wire_json(body)==wire_json(case['source_request']),
            'request_wire_sha256':bytes_hash(wire_json(body).encode('utf-8')),
            'note':'대조는 요청 수준에서 통제한다. 캐시·GPU 수치 경로·서버 내부 상태를 통제했다는 뜻은 아니다.'}


def assess_payload(core, problem: dict, case: dict, payload: dict) -> dict:
    from .protocol import validate_schema
    validate_schema(payload,output_schema(case))
    mapping=case.get('output_key_map',{k:k for k in FIELDS})
    mapped={'finding':{k:payload['finding'][mapping[k]] for k in FIELDS}}
    oldcase=copy.deepcopy(case['source_case'])
    result=original_assess(core,problem,oldcase,mapped)
    result['details']['transport_key_mapping']=copy.deepcopy(mapping)
    result['details']['boolean_values_modified']=False
    result['interpretation']='필드명 수송 대응만 복원한 단계형 진단. 실제 부울값·원본 실패·ADM 점수는 교정하지 않는다.'
    return result


def build_plan(source: dict, arms: list[str] | None=None) -> dict:
    arms=list(DEFAULT_ARMS) if arms is None else arms
    require(bool(arms) and len(arms)==len(set(arms)) and set(arms)<=set(ARMS),'arm 선택 오류')
    f=source['manifest']['frozen'];cases=[]
    for original in source['selected']:
        old=original['case']
        for arm in arms:
            c={'problem_id':old['problem_id'],'problem_sha256':old['problem_sha256'],
               'role':copy.deepcopy(old['role']),'role_id':old['source_case']['role_id']+'__v044_'+arm,
               'repeat':old['repeat'],'seed':old['seed'],'task':'decision_stage','calibration_version':4,
               'probe_contract':CONTRACT,'arm':arm,'diagnostic_group':arm,'probe_atom':old['probe_atom'],
               'source_case':copy.deepcopy(old),'source_projection':copy.deepcopy(old['source_projection']),
               'source_request':copy.deepcopy(original['request']),
               'source_original_status':original['record']['status'],'source_response_sha256':original['response_sha256'],
               'output_key_map':copy.deepcopy(NEUTRAL if arm=='neutral_keys' else {k:k for k in FIELDS})}
            c['case_id']=digest(c)[:24];cases.append(c)
    # 각 군 4입력 포함. 실행 순서가 항상 TT→FF→TF→FT가 되지 않도록 고정 시드 순열을 기록한다.
    random.Random(441729).shuffle(cases)
    plan={'profile':'factor-probe','experiment_kind':'calibration','probe_contract':CONTRACT,
          'problems':copy.deepcopy(f['plan']['problems']),'roles':[],'cases':cases,'assigned_calls':len(cases),
          'repeats':1,'seed':f['plan']['seed'],'reference_depths':copy.deepcopy(f['plan']['reference_depths']),
          'warnings':[],'scope':'diagnostic_only_no_ADM_success_pooling','arms':arms,
          'source_run_sha256':source['manifest']['run_sha256'],'source_validation':source['validation'],
          'source_identity':{k:copy.deepcopy(f[k]) for k in ('config','core','model','ollama_server')},
          'design_note':'재실행·format·b 순서·출력 필드명을 각각 대조한다. 한 군의 성공으로 이전 응답을 대체하지 않는다.'}
    for c in cases:check_delta(c,make_request(f['config'],c,None))
    return plan


def main(argv=None):
    from .runner import run
    from .client import APIError
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--out',type=Path)
    p.add_argument('--arm',action='append',choices=ARMS);p.add_argument('--plan-only',action='store_true');p.add_argument('--resume',action='store_true')
    args=p.parse_args(argv)
    try:
        core,info=load_core();source=load_decision_source(core,info,args.input);plan=build_plan(source,args.arm)
        if args.plan_only:
            print(json.dumps({'model_called':False,'new_llm_calls':plan['assigned_calls'],'arms':plan['arms'],
                              'source_validation':source['validation'],
                              'core_compatibility':source['core_compatibility'],
                              'note':plan['design_note']},ensure_ascii=False,indent=2));return 0
        require(args.out is not None,'--out 새 폴더를 지정하세요.')
        a=args.input.resolve();b=args.out.resolve()
        require(a!=b and not a.is_relative_to(b) and not b.is_relative_to(a),'원본과 다른 위치에 결과를 저장하세요.')
        print(f"조건별 대조: {plan['assigned_calls']}회 / 군={','.join(plan['arms'])}")
        return run(core,info,plan,copy.deepcopy(source['manifest']['frozen']['config']),b,resume=args.resume)
    except (ContractError,APIError,OSError,KeyError,TypeError,ValueError) as exc:
        print('오류: '+str(exc),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
