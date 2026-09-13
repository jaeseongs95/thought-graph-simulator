"""정답 경로가 주어진 direct와 nodes→final 출력 계약. 모델 값의 수정/정답 추출 없음."""
from copy import deepcopy
from pathlib import Path
import common,previous,reference,measure
CONTRACT='v068-plan-r1'
BASE_DIRECTION='허용된 유효한 증명 중 최종 지지 깊이가 가장 작은 경로를 선택한다.'
REFERENCE_DIRECTIVE='제공된 참조 계획의 모든 규칙을 주어진 순서대로 사용하여 목표를 지지하는 증명 하나를 작성한다.'
REFERENCE_HEADER='아래 provided_route_plan은 실험자가 미리 검증하여 제공한 정상 참조 계획이다. 앞선 모델의 응답이 아니다.\nrule_ids의 규칙과 순서를 추가·삭제·치환·재정렬하지 않는다.\n실제 초기 사실 노드, 각 노드 ID와 부모 연결 및 final_node_id는 직접 작성한다.\n목표 증명에 필요 없는 노드를 넣거나 기존 출력 오류를 외부 프로그램이 고치도록 기대하지 않는다.'

def _slots(spec):
    slots=[];last=None;lastcond=None
    for pi,p in enumerate(spec['problems']):
        for si,seed in enumerate(spec['seeds']):
            b=pi*2+si
            for ci,cond in enumerate(spec['orders'][b]):
                arms=['direct','staged'] if (pi+si+int(cond=='reference_long'))%2==0 else ['staged','direct']
                for arm in arms:
                    for stage in (['direct'] if arm=='direct' else ['nodes','final']):
                        sid=f'b{b:02d}_p{pi}_{cond}_{stage}'
                        parent=f'b{b:02d}_p{pi}_{cond}_nodes' if stage=='final' else None
                        slots.append({'id':sid,'block':b,'period':sum(s['block']==b for s in slots),
                          'problem_id':p['id'],'seed':seed,'seed_index':si,'condition':cond,'arm':arm,'stage':stage,
                          'parent_nodes_id':parent,'reference_rule_ids':spec['reference_plans'][p['id']][cond][:],
                          'reference_origin':'experimenter_verified_reference','previous_call_id':last,'previous_condition':lastcond})
                        last,lastcond=sid,cond
    if len(slots)!=36 or len({s['id'] for s in slots})!=36:raise ValueError('36 unique calls required')
    return slots

def _actions(slots,blocks):
    actions=[]
    for b in range(blocks):
        ss=[s for s in slots if s['block']==b]
        if len(ss)!=6:raise ValueError('six calls per block required')
        actions += [{'kind':'metadata','id':f'b{b:02d}_before'},*[{'kind':'call','id':s['id']} for s in ss],{'kind':'metadata','id':f'b{b:02d}_after'}]
    return actions

def build_plan(baseline_path,run_name,provenance='live'):
    if provenance not in ('live','synthetic'):raise ValueError('provenance')
    spec=common.spec()
    if spec['contract']!='v068-nodes-then-final-positive-control-r1':raise ValueError('protocol')
    raw=Path(baseline_path).read_bytes();_,old,req,_=previous.inspect_prior(raw)
    for problem in spec['problems']:
        if measure.depth_ranges(problem)!=spec['depth_ranges'][problem['id']]:raise ValueError('depth ranges')
        for i,c in enumerate(spec['conditions']):
            if reference.validate(problem,spec['reference_plans'][problem['id']][c])!=spec['depth_ranges'][problem['id']][i]:raise ValueError('reference invalid')
    slots=_slots(spec)
    p={'contract':CONTRACT,'run_name':common.check_run_name(run_name),'provenance':provenance,'protocol':deepcopy(spec),
       'protocol_sha256':common.sha((common.ROOT/'data/protocol.json').read_bytes()),'source_hashes':common.source_hashes(),
       'baseline_sha256':common.sha(raw),'baseline_request':req,'identity':deepcopy(old['identity']),'slots':slots,'actions':_actions(slots,6)}
    p['plan_sha256']=common.sha(common.wire(p));return p

def transfer(raw,parent_id):
    """응답 내용은 원문 문자열 그대로 운반한다. JSON 내부 nodes의 파싱/선택/교정 없음."""
    try:
        env=common.load(raw);msg=env.get('message')
        content=msg.get('content') if isinstance(msg,dict) else None
        if not isinstance(content,str):content=None
    except (ValueError,UnicodeError,AttributeError):content=None
    return {'source_slot_id':parent_id,'response_sha256':common.sha(raw),'content':content}

def request_for(plan,slot,parent_raw=None):
    body=deepcopy(plan['baseline_request']);text=body['messages'][0]['content'];marker='\n\nproblem: '
    if len(body['messages'])!=1 or body['messages'][0]['role']!='user' or text.count(marker)!=1:raise ValueError('baseline message')
    prefix,_=text.rsplit(marker,1)
    if prefix.count(BASE_DIRECTION)!=1:raise ValueError('baseline direction')
    problem=next(p for p in plan['protocol']['problems'] if p['id']==slot['problem_id'])
    ids=plan['protocol']['reference_plans'][slot['problem_id']][slot['condition']]
    if ids!=slot['reference_rule_ids'] or slot['reference_origin']!='experimenter_verified_reference':raise ValueError('reference input drift')
    provided={'origin':slot['reference_origin'],'rule_ids':ids};stage=slot['stage']
    if stage=='direct':
        if parent_raw is not None:raise ValueError('unexpected predecessor')
        message=prefix.replace(BASE_DIRECTION,REFERENCE_DIRECTIVE)+marker+common.wire(problem).decode()+'\n\n'+REFERENCE_HEADER+'\nprovided_route_plan: '+common.wire(provided).decode()
    else:
        schema=deepcopy(body['format'])
        if stage=='nodes':
            if parent_raw is not None:raise ValueError('unexpected predecessor')
            schema['properties'].pop('final_node_id');schema['required']=['nodes']
        elif stage=='final':
            if not isinstance(parent_raw,bytes) or not slot['parent_nodes_id']:raise ValueError('actual preceding raw required')
            schema['properties'].pop('nodes');schema['required']=['final_node_id']
        else:raise ValueError('stage')
        body['format']=schema
        message=plan['protocol']['headers'][stage]+'\nJSON 객체 하나만 출력한다. 출력 형식(JSON Schema):\n'+common.wire(schema).decode()
        message+=marker+common.wire(problem).decode()+'\n\n'+plan['protocol']['headers']['reference']+'\nprovided_route_plan: '+common.wire(provided).decode()
        if stage=='final':message+='\n\nnodes_response: '+common.wire(transfer(parent_raw,slot['parent_nodes_id'])).decode()
    body['messages'][0]['content']=message;body['options']['seed']=slot['seed']
    if len(common.wire(body))>plan['protocol']['request_utf8_byte_limit']:raise ValueError('request byte limit')
    return body
