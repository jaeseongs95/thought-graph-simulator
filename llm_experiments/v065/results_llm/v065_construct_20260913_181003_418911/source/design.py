"""v065 조건부 구성 검사. 필요한 마지막 규칙은 명시하며 이를 자율 D 선택으로 부르지 않는다."""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import common,measure,previous
CONTRACT='v065-plan-r1'
_BASELINE_DIRECTION='허용된 유효한 증명 중 최종 지지 깊이가 가장 작은 경로를 선택한다.'
CONDITIONS=('prescribed_short','prescribed_long')

def _baseline_material(path,spec):
    raw=Path(path).read_bytes();files,plan,request,_=previous.inspect_prior(raw)
    return common.sha(raw),request,deepcopy(plan['identity'])

def _slots(spec):
    slots=[];last=None;condition=None
    for pi,p in enumerate(spec['problems']):
        for si,seed in enumerate(spec['seeds']):
            block=pi*len(spec['seeds'])+si;order=spec['orders'][block]
            if len(order)!=2 or set(order)!=set(CONDITIONS):raise ValueError('two prescribed conditions required')
            for period,c in enumerate(order):
                sid=f'b{block:02d}_p{pi}_{c}'
                slots.append({'id':sid,'problem_id':p['id'],'seed':seed,'seed_index':si,'block':block,'period':period,
                              'condition':c,'required_terminal_rule':spec['required_terminal_rules'][p['id']][c],
                              'previous_call_id':last,'previous_condition':condition})
                last,condition=sid,c
    if len(slots)!=spec['max_inference_calls']:raise ValueError('call count')
    return slots

def _actions(slots,blocks):
    out=[]
    for block in range(blocks):
        ss=[s for s in slots if s['block']==block]
        if len(ss)!=2:raise ValueError('block count')
        out.append({'kind':'metadata','id':f'b{block:02d}_before'})
        out.extend({'kind':'call','id':s['id']} for s in ss)
        out.append({'kind':'metadata','id':f'b{block:02d}_after'})
    return out

def build_plan(baseline_path,run_name,provenance='live'):
    if provenance not in {'live','synthetic'}:raise ValueError('provenance')
    spec=common.spec()
    if spec['contract']!='v065-prescribed-construction-r1':raise ValueError('protocol')
    # 최소/최대 깊이의 마지막 규칙이 실제 문제에 존재하는지 사전 검사한다.
    for p in spec['problems']:
        if measure.depth_ranges(p)!=spec['depth_ranges'][p['id']]:raise ValueError('frozen problem depth ranges')
        for idx,c in enumerate(CONDITIONS):
            rid=spec['required_terminal_rules'][p['id']][c]
            rs=[r for r in p['rules'] if r['conclusion']!=p['goal'] or r['id']==rid]
            if not any(r['id']==rid and r['conclusion']==p['goal'] for r in rs):raise ValueError('terminal rule')
            check={**p,'rules':rs};ds=measure.depth_ranges(check)
            if ds!=[spec['depth_ranges'][p['id']][idx]]*2:raise ValueError('prescribed rule does not identify the frozen depth')
    baseline_sha,req,identity=_baseline_material(baseline_path,spec);slots=_slots(spec)
    p={'contract':CONTRACT,'run_name':common.check_run_name(run_name),'provenance':provenance,'protocol':deepcopy(spec),
       'protocol_sha256':common.sha((common.ROOT/'data/protocol.json').read_bytes()),'source_hashes':common.source_hashes(),
       'baseline_sha256':baseline_sha,'baseline_request':req,'identity':identity,'slots':slots,
       'actions':_actions(slots,len(spec['problems'])*len(spec['seeds']))}
    p['plan_sha256']=common.sha(common.wire(p));return p

def request_for(plan,slot):
    # 채점기/깊이 계산기를 호출하지 않는다. prescribed 조건의 목표 규칙은 과제의 명시 입력이다.
    body=deepcopy(plan['baseline_request']);p=next(x for x in plan['protocol']['problems'] if x['id']==slot['problem_id'])
    if slot['condition'] not in CONDITIONS:raise ValueError('unknown construction condition')
    rid=slot['required_terminal_rule']
    if rid!=plan['protocol']['required_terminal_rules'][slot['problem_id']][slot['condition']]:raise ValueError('slot rule mismatch')
    messages=body['messages']
    if len(messages)!=1 or messages[0]['role']!='user':raise ValueError('single user baseline')
    text=messages[0]['content'];marker='\n\nproblem: '
    if text.count(marker)!=1:raise ValueError('problem delimiter')
    prefix,_=text.rsplit(marker,1)
    if prefix.count(_BASELINE_DIRECTION)!=1:raise ValueError('baseline direction delimiter')
    instruction="최종 goal 노드의 rule은 반드시 '"+rid+"'로 지정한다. 이 규칙을 마지막으로 사용하는 유효한 증명 하나를 구성한다."
    messages[0]['content']=prefix.replace(_BASELINE_DIRECTION,instruction)+marker+common.wire(p).decode('utf-8')
    seed=slot['seed']
    if type(seed)is not int:raise ValueError('integer seed')
    body['options']['seed']=seed
    if len(common.wire(body))>plan['protocol']['request_utf8_byte_limit']:raise ValueError('request UTF-8 byte budget')
    return body
