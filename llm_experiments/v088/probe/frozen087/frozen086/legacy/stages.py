"""형식 검사·무보정 결합·단계 감사. 이 모듈의 감사 결과는 실행 요청을 바꾸지 않는다."""
from collections import Counter

def text(value):
    return isinstance(value,str) and 1<=len(value)<=128

def node_valid(node):
    return (isinstance(node,dict) and set(node)=={'id','atom','rule','parents'}
        and text(node['id']) and text(node['atom']) and (node['rule'] is None or text(node['rule']))
        and isinstance(node['parents'],list) and len(node['parents'])<=16 and all(text(p) for p in node['parents']))

def format_valid(stage,payload):
    if not isinstance(payload,dict):return False
    if stage=='facts':
        return set(payload)=={'nodes'} and isinstance(payload['nodes'],list) and 1<=len(payload['nodes'])<=16 and all(node_valid(n) for n in payload['nodes'])
    if stage=='rule':return set(payload)=={'node'} and node_valid(payload['node'])
    if stage=='final':return set(payload)=={'final_node_id'} and text(payload['final_node_id'])
    return False

def assemble(slots,payloads):
    """배정된 사실 배열+단일 노드들을 순서대로 연결한다. 값의 수정·선택은 없다."""
    if not slots or slots[0]['stage']!='facts' or slots[-1]['stage']!='final':raise ValueError('trial schedule')
    if not all(format_valid(s['stage'],payloads[s['id']]) for s in slots):return None
    nodes=list(payloads[slots[0]['id']]['nodes'])
    for slot in slots[1:-1]:
        if slot['stage']!='rule':raise ValueError('rule schedule')
        nodes.append(payloads[slot['id']]['node'])
    return {'nodes':nodes,'final_node_id':payloads[slots[-1]['id']]['final_node_id']}

def audit_steps(problem,slots,payloads,ready_ids):
    """실행 뒤에만 계산한다. 뒤의 성공으로 앞의 실패를 덮지 않는다."""
    emitted=[];prefix_available=True;checks=[];rules={r['id']:r for r in problem['rules']}
    for slot in slots:
        sid=slot['id'];stage=slot['stage'];errors=[];value=None
        if sid not in ready_ids:
            checks.append({'id':sid,'stage':stage,'valid':None,'error_codes':None})
            prefix_available=False;continue
        obj=payloads[sid]
        if stage=='facts':
            ns=obj['nodes']
            if Counter(n['atom'] for n in ns)!=Counter(problem['facts']):errors.append('initial_fact_multiset')
            if any(n['rule'] is not None or n['parents'] for n in ns):errors.append('initial_fact_shape')
            if len({n['id'] for n in ns})!=len(ns):errors.append('duplicate_node_id')
            emitted.extend(ns)
        elif prefix_available:
            known={n['id']:n for n in emitted}
            if stage=='rule':
                node=obj['node'];rule=rules.get(node['rule'])
                if node['id'] in known:errors.append('duplicate_node_id')
                if node['rule']!=slot['requested_rule_id']:errors.append('requested_rule_mismatch')
                if rule is None:errors.append('unregistered_rule')
                else:
                    if node['atom']!=rule['conclusion']:errors.append('wrong_atom')
                    if any(p not in known for p in node['parents']):errors.append('missing_parent')
                    elif Counter(known[p]['atom'] for p in node['parents'])!=Counter(rule['premises']):errors.append('premise_counter_mismatch')
                emitted.append(node)
            else:
                node=known.get(obj['final_node_id'])
                if node is None:errors.append('missing_final_node')
                elif node['atom']!=problem['goal']:errors.append('wrong_goal')
        else:
            checks.append({'id':sid,'stage':stage,'valid':None,'error_codes':None});continue
        value=not errors
        checks.append({'id':sid,'stage':stage,'valid':value,'error_codes':sorted(set(errors))})
    return checks
