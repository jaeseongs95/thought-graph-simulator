"""D/W 요구와 위치×ID를 교차한다. 모델 원문을 교체하거나 정답으로 보정하지 않는다."""
from copy import deepcopy
from pathlib import Path
import bootstrap
import design as legacy_design
import core080 as core


def schedule(spec):
    trials, slots, actions = [], [], []
    number = 0
    for pi, problem in enumerate(spec['problems']):
        for si, seed in enumerate(spec['seeds']):
            block = pi * len(spec['seeds']) + si
            entries = [('reference', si % 2, 0, 'D', 'shallow'),
                       ('reference', si % 2, 0, 'D', 'deep')]
            for order in range(2):
                for labels in range(2):
                    metrics = list(spec['metrics_by_problem'][problem['id']])
                    if (pi + si + order + labels) % 2:
                        metrics.reverse()
                    for metric in metrics:
                        directions = list(spec['conditions'])
                        if (pi + si + order + labels + int(metric == 'W')) % 2:
                            directions.reverse()
                        entries += [('model', order, labels, metric, d) for d in directions]
            if si % 2:
                entries.reverse()
            actions.append({'kind':'metadata','id':f'b{block:02d}_before'})
            for arm, order, labels, metric, condition in entries:
                uid=f't{number:03d}';number+=1
                tid=uid+'_explicit_rule'
                selection=uid+'_select' if arm=='model' else None
                pair=f'p{pi}_s{si}_o{order}_l{labels}_{metric}' if arm=='model' else None
                physical_ids=[spec['candidate_ids'][j] for j in spec['id_assignments'][labels]]
                selected_position=spec['candidate_orders'][order].index(0 if condition=='shallow' else 1)
                trial={'id':tid,'unit_id':uid,'variant':'explicit_rule','selection_slot_id':selection,
                       'block':block,'arm':arm,'problem_id':problem['id'],'seed':seed,
                       'candidate_order_index':order,'id_assignment_index':labels,
                       'metric':metric,'condition':condition,'pair_id':pair,'base_pair_id':pair,
                       'control_candidate_id':physical_ids[selected_position] if arm=='reference' else None}
                trials.append(trial)
                if selection:
                    slots.append({'id':selection,'trial_id':tid,'logical_id':selection,'stage':'select','rule_position':None})
                    actions.append({'kind':'slot','id':selection})
                paths=spec['reference_plans'][problem['id']]
                n=max(map(len,paths.values())) if arm=='model' else len(paths[spec['reference_conditions'][0 if condition=='shallow' else 1]])
                for stage,pos in [('facts',None)]+[('rule',i) for i in range(n)]+[('final',None)]:
                    suffix=f'rule_{pos:02d}' if stage=='rule' else stage
                    sid=tid+'_'+suffix
                    slots.append({'id':sid,'trial_id':tid,'logical_id':uid+'_'+suffix,'stage':stage,'rule_position':pos})
                    actions.append({'kind':'slot','id':sid})
            actions.append({'kind':'metadata','id':f'b{block:02d}_after'})
    if (len(trials)!=112 or len(slots)!=spec['max_inference_calls'] or len(actions)!=spec['max_action_slots']):
        raise ValueError('동결 배정 수 불일치')
    return trials,slots,actions


def make_plan(baseline_path,run_name,provenance='live',audit_previous=True):
    if provenance not in ('live','synthetic'):raise ValueError('provenance')
    spec=core.spec()
    from audit080 import validate_protocol
    validate_protocol(spec)
    raw=Path(baseline_path).read_bytes()
    if core.sha(raw)!=spec['baseline_sha256']:raise ValueError('v079 baseline hash mismatch')
    if audit_previous:
        from previous080 import audit
        audit(raw)
    trials,slots,actions=schedule(spec)
    plan={'contract':'v080-plan-r1','run_name':core.check_run_name(run_name),'provenance':provenance,
          'protocol':spec,'protocol_sha256':core.sha((core.ROOT/'data/protocol.json').read_bytes()),
          'baseline_sha256':core.sha(raw),'source_hashes':core.source_hashes(),
          'trials':trials,'slots':slots,'actions':actions}
    plan['plan_sha256']=core.sha(core.wire(plan))
    return plan


def trial_for(plan,slot):
    return next(t for t in plan['trials'] if t['id']==slot['trial_id'])


def view(plan,trial):
    """표시 ID와 측정 요청만 바꾼다. 정답이나 깊이 계산은 읽지 않는다."""
    spec=deepcopy(plan['protocol'])
    spec['candidate_ids']=[spec['candidate_ids'][i] for i in spec['id_assignments'][trial['id_assignment_index']]]
    if trial['metric']=='W':
        spec['headers']['select']=spec['count_select_header']
        spec['headers'].update(spec['count_conditions'])
    return {**plan,'protocol':spec}


def cards(plan,trial):return legacy_design.cards(view(plan,trial),trial)
def problem_for(plan,trial):return legacy_design.problem_for(plan,trial)
def selected_route(plan,trial,responses):return legacy_design.selected_route(view(plan,trial),trial,responses)
def disposition(plan,slot,responses):return legacy_design.disposition(view(plan,trial_for(plan,slot)),slot,responses)


def request_for(plan,slot,responses):
    t=trial_for(plan,slot)
    body=legacy_design.request_for(view(plan,t),slot,responses)
    if slot['stage']=='select' and t['metric']=='W':
        head,raw=body['messages'][0]['content'].split('\n\ninput: ',1)
        data=core.load(raw)
        data['requested_rule_count']=data.pop('requested_depth')
        body['messages'][0]['content']=head+'\n\ninput: '+core.wire(data).decode('utf-8')
    if len(core.wire(body))>plan['protocol']['request_utf8_byte_limit']:raise ValueError('request budget; no truncation')
    return body
