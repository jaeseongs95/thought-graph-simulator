"""동결된 후보-규칙 카드 선택 → 원문 전달 → 증명 생성. 채점은 이 모듈을 제어하지 않는다."""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import common


def schedule(spec):
    trials, slots, actions = [], [], []
    for pi, problem in enumerate(spec['problems']):
        for si, seed in enumerate(spec['seeds']):
            block = pi * len(spec['seeds']) + si
            # 네 모델 조건 모두 실행. 참조 대조는 두 seed 사이에 후보 순서/선후를 반전한다.
            entries = [('reference', si, 'shallow'), ('reference', si, 'deep'),
                       ('model', 0, 'shallow'), ('model', 0, 'deep'),
                       ('model', 1, 'deep'), ('model', 1, 'shallow')]
            if si: entries.reverse()
            actions.append({'kind':'metadata','id':f'b{block:02d}_before'})
            routes = spec['reference_plans'][problem['id']]
            longest = max(map(len, routes.values()))
            for arm, order, condition in entries:
                tid = f't{len(trials):03d}'
                t = {'id':tid, 'block':block, 'arm':arm, 'problem_id':problem['id'],
                     'seed':seed, 'candidate_order_index':order, 'condition':condition,
                     'pair_id':f'p{pi}_s{si}_o{order}' if arm=='model' else None}
                t['control_candidate_id'] = (spec['candidate_ids'][spec['candidate_orders'][order].index(0 if condition=='shallow' else 1)]
                                               if arm=='reference' else None)
                trials.append(t)
                rule_count = longest if arm=='model' else len(routes[spec['reference_conditions'][0 if condition=='shallow' else 1]])
                ops = ([('select',None)] if arm=='model' else []) + [('facts',None)]
                ops += [('rule',i) for i in range(rule_count)] + [('final',None)]
                for stage, pos in ops:
                    sid = tid + '_' + (f'rule_{pos:02d}' if stage=='rule' else stage)
                    s = {'id':sid,'trial_id':tid,'stage':stage,'rule_position':pos}
                    slots.append(s); actions.append({'kind':'slot','id':sid})
            actions.append({'kind':'metadata','id':f'b{block:02d}_after'})
    if len(trials)!=36 or len(slots)!=214 or len(actions)!=226:
        raise ValueError('frozen 36 trials / 214 possible inference slots / 226 action slots')
    return trials, slots, actions


def make_plan(baseline_path, run_name, provenance='live', audit_previous=True):
    if provenance not in ('live','synthetic'): raise ValueError('provenance')
    spec = common.spec(); raw = Path(baseline_path).read_bytes()
    if common.sha(raw)!=spec['baseline_sha256']: raise ValueError('v073 baseline hash mismatch')
    if audit_previous:
        import previous
        previous.audit(raw)
    trials, slots, actions = schedule(spec)
    plan = {'contract':'v074-plan-r1','run_name':common.check_run_name(run_name),'provenance':provenance,
            'protocol':spec,'protocol_sha256':common.sha((common.ROOT/'data/protocol.json').read_bytes()),
            'baseline_sha256':common.sha(raw),'source_hashes':common.source_hashes(),
            'trials':trials,'slots':slots,'actions':actions}
    plan['plan_sha256'] = common.sha(common.wire(plan))
    return plan


def problem_for(plan, trial):
    return next(p for p in plan['protocol']['problems'] if p['id']==trial['problem_id'])


def cards(plan, trial):
    spec=plan['protocol'];problem=problem_for(plan,trial)
    rules={r['id']:r for r in problem['rules']}
    routes=spec['reference_plans'][problem['id']]
    # 후보 규칙의 단순 참조다. D 계산·비교·정렬은 하지 않는다.
    return [{'candidate_id':spec['candidate_ids'][i],
             'rules':[deepcopy(rules[rid]) for rid in routes[spec['reference_conditions'][kind]]]}
            for i,kind in enumerate(spec['candidate_orders'][trial['candidate_order_index']])]


def raw_content(raw):
    try:
        outer=common.load(raw)
        value=outer.get('message',{}).get('content') if isinstance(outer,dict) and isinstance(outer.get('message'),dict) else None
        return value if isinstance(value,str) else None
    except (ValueError,UnicodeError): return None


def source_for(plan, trial, responses):
    if trial['arm']=='reference':
        return {'source_type':'experimenter_reference','source_id':trial['id']+'_reference',
                'response_sha256':None,'content':common.wire({'candidate_id':trial['control_candidate_id']}).decode('utf-8')}
    sid=trial['id']+'_select';raw=responses.get(sid)
    return {'source_type':'model','source_id':sid,'response_sha256':None if raw is None else common.sha(raw),
            'content':None if raw is None else raw_content(raw)}


def selected_route(plan, trial, responses):
    source=source_for(plan,trial,responses)
    try: obj=common.load(source['content']) if source['content'] is not None else None
    except (ValueError,UnicodeError):return None
    if not isinstance(obj,dict) or set(obj)!={'candidate_id'} or obj['candidate_id'] not in plan['protocol']['candidate_ids']:
        return None
    c=next(c for c in cards(plan,trial) if c['candidate_id']==obj['candidate_id'])
    return {'candidate_id':c['candidate_id'],'rule_ids':[r['id'] for r in c['rules']]}


def disposition(plan, slot, responses):
    if slot['stage']=='select': return None
    t=next(t for t in plan['trials'] if t['id']==slot['trial_id'])
    route=selected_route(plan,t,responses)
    if route is None:return 'unmappable_selection'
    if slot['stage']=='rule' and slot['rule_position']>=len(route['rule_ids']):return 'outside_selected_route'
    return None


def request_for(plan, slot, responses):
    """선택의 정오/기대 D를 읽지 않고 고정 매핑과 실제 원문만 사용한다."""
    if disposition(plan,slot,responses) is not None:raise ValueError('skipped slot must not dispatch')
    t=next(t for t in plan['trials'] if t['id']==slot['trial_id']);spec=plan['protocol']
    problem=problem_for(plan,t);body=deepcopy(spec['api_defaults']);body['options']['seed']=t['seed']
    stage=slot['stage']
    if stage=='select':
        schema=deepcopy(spec['selector_schema'])
        data={'problem':{k:problem[k] for k in ('facts','rules','goal')},
              'candidates':cards(plan,t),'requested_depth':spec['headers'][t['condition']]}
        header=spec['headers']['select']
    else:
        route=selected_route(plan,t,responses);schema_props=spec['generation_schema']['properties']
        prop={'facts':('nodes',schema_props['nodes']), 'rule':('node',schema_props['nodes']['items']),
              'final':('final_node_id',schema_props['final_node_id'])}[stage]
        schema={'type':'object','properties':{prop[0]:deepcopy(prop[1])},'required':[prop[0]],'additionalProperties':False}
        # 이전 그래프 응답 전체를 바이트에 충실한 문자열로 운반. 문법/의미 오류도 자르거나 고치지 않는다.
        preceding=[]
        for s in plan['slots']:
            if s['id']==slot['id']:break
            if s['trial_id']==t['id'] and s['stage']!='select' and s['id'] in responses:
                raw=responses[s['id']]
                preceding.append({'source_slot_id':s['id'],'response_sha256':common.sha(raw),'content':raw_content(raw)})
        rule_id=route['rule_ids'][slot['rule_position']] if stage=='rule' else None
        operation_index=0 if stage=='facts' else slot['rule_position']+1 if stage=='rule' else len(route['rule_ids'])+1
        data={'problem':problem,'selection_original':source_for(plan,t,responses),
              'provided_route_plan':route,'operation':{'stage':stage,'index':operation_index,'requested_rule_id':rule_id},
              'history':preceding}
        header=spec['headers']['generator']+'\n\n'+spec['headers'][stage]
    text=header+'\nJSON 객체 하나만 출력한다. 출력 형식(JSON Schema):\n'+common.wire(schema).decode()
    text+='\n\ninput: '+common.wire(data).decode()
    body['messages']=[{'role':'user','content':text}];body['format']=schema
    if len(common.wire(body))>spec['request_utf8_byte_limit']:raise ValueError('request budget; no truncation')
    return body
