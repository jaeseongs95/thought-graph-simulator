"""v073: 공백 한 글자와 후보 순서의 제한된 교차. 모델 원문 보정 경로 없음."""
from copy import deepcopy
from pathlib import Path
import common, previous
CONTRACT='v073-plan-r1'

def _slots(spec):
    slots=[]
    treatments=[('compact','shallow'),('compact','deep'),('comma_space','shallow'),('comma_space','deep')]
    for pi,pair in enumerate(spec['numeric_pairs']):
        for si,seed in enumerate(spec['seeds']):
            for oi,order in enumerate(spec['candidate_orders']):
                block=(pi*2+si)*2+oi;unit=f'b{block:02d}'
                offset=(pi+oi)%4
                seq=treatments[offset:]+treatments[:offset]
                if si==1:seq=list(reversed(seq))
                for period,(fmt,condition) in enumerate(seq):
                    slots.append({'id':unit+'_'+fmt+'_'+condition,'unit_id':unit,'pair_id':unit+'_'+fmt,
                        'block':block,'period':period,'numeric_pair_id':pair['id'],'seed':seed,'seed_index':si,
                        'candidate_order_index':oi,'format':fmt,'condition':condition,'stage':'select','history_ids':[]})
    if len(slots)!=64 or len({s['id'] for s in slots})!=64:raise ValueError('64 unique calls required')
    return slots

def _actions(slots,blocks):
    actions=[]
    for b in range(blocks):
        group=[s for s in slots if s['block']==b]
        if len(group)!=4:raise ValueError('four calls per block')
        actions.append({'kind':'metadata','id':f'b{b:02d}_before'})
        actions.extend({'kind':'call','id':s['id']} for s in group)
        actions.append({'kind':'metadata','id':f'b{b:02d}_after'})
    return actions

def archived_identity(files,old,spec):
    show=common.load(files['metadata/b00_before/2.response.raw.json'])
    native={k:show.get(k) for k in ('template','system','parameters','model_info','details','capabilities','projector_info')}
    if native['parameters'] is not None:native['parameters']=sorted(native['parameters'].split('\n'))
    return {'model':spec['model'],'digest':spec['model_digest'],'server':deepcopy(old['identity']['server']),
        'tag_details':deepcopy(old['identity']['tag_details']),'native':native,
        'native_fingerprint_source':'baseline/v072_evidence.zip:metadata/b00_before/2.response.raw.json'}

def build_plan(baseline_path,run_name,provenance='live'):
    if provenance not in ('live','synthetic'):raise ValueError('provenance')
    spec=common.spec()
    if spec['contract']!='v073-format-order-control-r1':raise ValueError('protocol')
    if spec['max_inference_calls']!=64 or spec['assigned_blocks']!=16 or spec['max_actions']!=96:raise ValueError('fixed budget')
    raw=Path(baseline_path).read_bytes();files,old,request,_=previous.inspect_prior(raw)
    for pair in spec['numeric_pairs']:
        if len(pair['values'])!=2 or not (0<=pair['values'][0]<pair['values'][1]):raise ValueError('distinct ascending values')
    slots=_slots(spec)
    plan={'contract':CONTRACT,'run_name':common.check_run_name(run_name),'provenance':provenance,
        'protocol':deepcopy(spec),'protocol_sha256':common.sha((common.ROOT/'data/protocol.json').read_bytes()),
        'source_hashes':common.source_hashes(),'baseline_sha256':common.sha(raw),'baseline_request':request,
        'identity':archived_identity(files,old,spec),'slots':slots,'actions':_actions(slots,16)}
    plan['plan_sha256']=common.sha(common.wire(plan));return plan

def depth_report(spec,slot):
    pair=next(p for p in spec['numeric_pairs'] if p['id']==slot['numeric_pair_id'])
    values=[pair['values'][i] for i in spec['candidate_orders'][slot['candidate_order_index']]]
    separator=',' if slot['format']=='compact' else ', ' if slot['format']=='comma_space' else None
    if separator is None:raise ValueError('unknown serialization')
    # 새 양성 대조에 미리 정의한 입력을 작성한다. 모델 응답을 정규화하지 않는다.
    return '{"depths":['+separator.join(str(x) for x in values)+']}'

def request_for(plan,slot,history_raw=None):
    if history_raw not in (None,{}) or slot['history_ids']:raise ValueError('no model history in this control')
    spec=plan['protocol'];body=deepcopy(plan['baseline_request'])
    if len(body['messages'])!=1 or body['messages'][0]['role']!='user':raise ValueError('baseline messages')
    if body['model']!=plan['identity']['model'] or body['format']!=spec['schema']:raise ValueError('baseline identity/schema')
    data={'depth_report':depth_report(spec,slot),'requested_depth':spec['headers'][slot['condition']]}
    body['messages'][0]['content']=spec['headers']['compare']+'\nJSON 객체 하나만 출력한다. 출력 형식(JSON Schema):\n'+common.wire(spec['schema']).decode('utf-8')+'\n\ninput: '+common.wire(data).decode('utf-8')
    body['options']['seed']=slot['seed']
    if len(common.wire(body))>spec['request_utf8_byte_limit']:raise ValueError('request byte limit; no truncation')
    return body
