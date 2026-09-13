"""v067 양성 대조의 입력과 스케줄. 정답 경로 제공을 provenance로 명시한다."""
from copy import deepcopy
from pathlib import Path
import common,previous,reference,measure
CONTRACT='v067-plan-r1'
BASE_DIRECTION='허용된 유효한 증명 중 최종 지지 깊이가 가장 작은 경로를 선택한다.'
REFERENCE_DIRECTIVE='제공된 참조 계획의 모든 규칙을 주어진 순서대로 사용하여 목표를 지지하는 증명 하나를 작성한다.'
REFERENCE_HEADER='아래 provided_route_plan은 실험자가 미리 검증하여 제공한 정상 참조 계획이다. 앞선 모델의 응답이 아니다.\nrule_ids의 규칙과 순서를 추가·삭제·치환·재정렬하지 않는다.\n실제 초기 사실 노드, 각 노드 ID와 부모 연결 및 final_node_id는 직접 작성한다.\n목표 증명에 필요 없는 노드를 넣거나 기존 출력 오류를 외부 프로그램이 고치도록 기대하지 않는다.'

def _slots(spec):
    result=[];prev=None;cond=None
    for pi,p in enumerate(spec['problems']):
        for si,seed in enumerate(spec['seeds']):
            b=pi*2+si
            for period,c in enumerate(spec['orders'][b]):
                if c not in spec['conditions']:raise ValueError('unknown reference condition')
                sid=f'b{b:02d}_p{pi}_{c}'
                result.append({'id':sid,'block':b,'period':period,'problem_id':p['id'],'seed':seed,'seed_index':si,'condition':c,'reference_rule_ids':spec['reference_plans'][p['id']][c][:],'reference_origin':'experimenter_verified_reference','previous_call_id':prev,'previous_condition':cond});prev,cond=sid,c
    if len(result)!=12 or len({r['id'] for r in result})!=12:raise ValueError('12 unique calls required')
    return result

def _actions(slots,blocks):
    result=[]
    for b in range(blocks):
        s=[r for r in slots if r['block']==b]
        if len(s)!=2:raise ValueError('two reference conditions')
        result.extend([{'kind':'metadata','id':f'b{b:02d}_before'},*[{'kind':'call','id':r['id']} for r in s],{'kind':'metadata','id':f'b{b:02d}_after'}])
    return result

def build_plan(baseline_path,run_name,provenance='live'):
    if provenance not in ('live','synthetic'):raise ValueError('provenance')
    spec=common.spec()
    if spec['contract']!='v067-reference-plan-positive-control-r1':raise ValueError('contract')
    for problem in spec['problems']:
        if measure.depth_ranges(problem)!=spec['depth_ranges'][problem['id']]:raise ValueError('frozen depth ranges')
        for i,c in enumerate(spec['conditions']):
            if reference.validate(problem,spec['reference_plans'][problem['id']][c])!=spec['depth_ranges'][problem['id']][i]:raise ValueError('reference depth mismatch')
    raw=Path(baseline_path).read_bytes();f,old,req,_=previous.inspect_prior(raw);slots=_slots(spec)
    p={'contract':CONTRACT,'run_name':common.check_run_name(run_name),'provenance':provenance,'protocol':deepcopy(spec),'protocol_sha256':common.sha((common.ROOT/'data/protocol.json').read_bytes()),'source_hashes':common.source_hashes(),'baseline_sha256':common.sha(raw),'baseline_request':req,'identity':deepcopy(old['identity']),'slots':slots,'actions':_actions(slots,6)}
    p['plan_sha256']=common.sha(common.wire(p));return p

def request_for(plan,slot):
    # 정상 참조 목록 자체는 이 검사의 입력이다. 깊이 계산·채점·모델 응답 교정은 하지 않는다.
    body=deepcopy(plan['baseline_request']);text=body['messages'][0]['content'];marker='\n\nproblem: '
    if len(body['messages'])!=1 or body['messages'][0]['role']!='user' or text.count(marker)!=1:raise ValueError('baseline message')
    prefix,_=text.rsplit(marker,1)
    if prefix.count(BASE_DIRECTION)!=1:raise ValueError('baseline direction anchor')
    problem=next(p for p in plan['protocol']['problems'] if p['id']==slot['problem_id'])
    ids=plan['protocol']['reference_plans'][slot['problem_id']][slot['condition']]
    if ids!=slot['reference_rule_ids'] or slot['reference_origin']!='experimenter_verified_reference':raise ValueError('reference input mismatch')
    provided={'origin':slot['reference_origin'],'rule_ids':ids}
    body['messages'][0]['content']=prefix.replace(BASE_DIRECTION,REFERENCE_DIRECTIVE)+marker+common.wire(problem).decode()+'\n\n'+REFERENCE_HEADER+'\nprovided_route_plan: '+common.wire(provided).decode()
    body['options']['seed']=slot['seed']
    if len(common.wire(body))>plan['protocol']['request_utf8_byte_limit']:raise ValueError('request byte limit')
    return body
