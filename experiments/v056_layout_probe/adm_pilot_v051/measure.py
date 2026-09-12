"""요청 역할을 받지 않는 의미 검증기. 실제 지지 DAG/도식/검토를 재계산한다."""
from __future__ import annotations
import itertools
from .contracts import ContractError, require, validate_payload, canonical, OUTPUT_SCHEMA, M1, M2


def unique(items, label):
    require(len(items) == len(set(items)), label + ': 중복 참조')


def inspect_graph(problem, trace):
    rules = {r['id']: r for r in problem['rules']}
    nodes, depth, closure = {}, {}, {}
    for node in trace['nodes']:
        key = node['id']
        require(key not in nodes, 'GRAPH: 중복 node id')
        unique(node['parents'], 'GRAPH')
        require(all(p in nodes for p in node['parents']), 'GRAPH: 순환/전방/누락 참조')
        if node['rule'] is None:
            require(not node['parents'] and node['atom'] in problem['facts'], 'PROOF: 초기 facts에 없는 단독 주장')
            depth[key] = 0
        else:
            require(node['rule'] in rules, 'PROOF: 미등록 규칙')
            rule = rules[node['rule']]
            require(node['atom'] == rule['conclusion'], 'PROOF: 규칙 결론 불일치')
            actual = sorted(nodes[x]['atom'] for x in node['parents'])
            require(actual == sorted(rule['premises']), 'PROOF: 전제 누락/추가/불일치')
            depth[key] = 1 + max(depth[x] for x in node['parents'])
        closure[key] = {key}.union(*(closure[x] for x in node['parents']))
        nodes[key] = node
    final = trace['final']
    require(final in nodes, 'GOAL: 최종 노드 누락')
    require(nodes[final]['atom'] == problem['goal'], 'GOAL: 고정 목표 불일치')
    require(closure[final] == set(nodes), 'GRAPH: 목표와 무관한 노드')
    return {'nodes': nodes, 'depth': depth, 'closure': closure, 'D': depth[final]}


def inspect_views(problem, trace, graph):
    require(set(trace['views']) == set(graph['nodes']), 'VIEW: 누락/추가 노드 표현')
    rules = {r['id']: r for r in problem['rules']}; modes = []
    for key, view in trace['views'].items():
        node = graph['nodes'][key]
        if view['kind'] == 'instance':
            require(view['atom'] == node['atom'], 'VIEW: 사례 원자 불일치')
            modes.append('instance'); continue
        binding = view['binding']; variables = list(binding)
        used = [graph['nodes'][n] for n in graph['closure'][key]]
        atoms = {n['atom'] for n in used}
        require(len(binding) == len(atoms) and set(binding.values()) == atoms, 'VIEW: 일대일 치환/실제 사용 원자 오류')
        require(view['conclusion'] in binding and binding[view['conclusion']] == node['atom'], 'VIEW: 결론 접지 불일치')
        expected = set()
        for n in used:
            if n['rule'] is None:
                expected.add(((), n['atom']))
            else:
                r = rules[n['rule']]; expected.add((tuple(sorted(r['premises'])), r['conclusion']))
        ground = []
        for clause in view['assumptions']:
            unique(clause['if'], 'VIEW')
            require(all(v in binding for v in clause['if']) and clause['then'] in binding, 'VIEW: 미등록 변수')
            ground.append((tuple(sorted(binding[v] for v in clause['if'])), binding[clause['then']]))
        require(len(ground) == len(set(ground)) and set(ground) == expected, 'VIEW: 실제 근거의 추가/삭제/중복')
        # 접지와 별개로 보편 함의의 진리표를 검사한다.
        for values in itertools.product((False, True), repeat=len(variables)):
            assignment = dict(zip(variables, values))
            antecedent = all((not all(assignment[v] for v in c['if'])) or assignment[c['then']]
                             for c in view['assumptions'])
            require(not antecedent or assignment[view['conclusion']], 'VIEW: 보편 도식 반례 존재')
        modes.append('schema')
    return modes[0] if len(set(modes)) == 1 else 'mixed'


def inspect_reviews(problem, trace, proof_valid):
    """대상 수준은 finding 진위와 분리한다. 틀린 M2도 대상은 M2일 수 있다."""
    require(isinstance(trace.get('reviews'), list) and len(trace['reviews']) <= 4, 'REVIEW: 배열 필요/길이 초과')
    require(all(isinstance(r, dict) and isinstance(r.get('id'), str) for r in trace['reviews']), 'REVIEW: id/객체 필요')
    ids = [r['id'] for r in trace['reviews']]
    unique(ids, 'REVIEW')
    levels, targets, details = [], [], []
    for review in trace['reviews']:
        kind = review.get('target_kind'); target_ok = False; correct = False; error = None
        level = 1 if kind == 'argument' else (2 if kind == 'acceptance_criterion' else None)
        try:
            require(level is not None, 'REVIEW: 미등록 검토 대상 종류')
            if level == 1:
                target_ok = review.get('target') == trace.get('final') and review.get('check') == 'support_replay' and any(isinstance(n,dict) and n.get('id') == trace.get('final') for n in trace.get('nodes',[]) if isinstance(trace.get('nodes'),list))
                require(target_ok, 'M1: 실제 최종 노드 대상 아님')
                validate_payload(review, M1, '$.reviews.argument')
                unique(review['evidence'], 'M1 evidence')
                require(set(review['evidence']) == {n['id'] for n in trace['nodes']}, 'M1: 근거 목록 불일치')
                f = review['finding']; unique(f['used_rules'], 'M1 rules')
                used_rules = sorted({n['rule'] for n in trace['nodes'] if n['rule'] is not None})
                final_node = next(n for n in trace['nodes'] if n['id'] == trace['final'])
                require(f['grounded'] is proof_valid and sorted(f['used_rules']) == used_rules
                        and f['conclusion'] == final_node['atom'], 'M1: 재검토 판정/규칙/결론 오류')
            else:
                target_ok = review.get('target') == 'valid_proof_and_goal' and review.get('check') == 'counterexample_probe'
                require(target_ok, 'M2: 평가 기준 대상 불일치')
                validate_payload(review, M2, '$.reviews.acceptance_criterion')
                p = review['probe']
                require(p == {'atom': problem['goal'], 'rule': None, 'parents': []}, 'M2: 고정 단독 목표 시험 주장 불일치')
                f = review['finding']; a = p['atom'] == problem['goal']; b = p['atom'] in problem['facts']
                require(f['answer_only_accepts'] is a and f['proof_and_goal_accepts'] is (a and b)
                        and f['gap_detected'] is (a and not b), 'M2: 기준의 실제 판정 오류')
            correct = True
        except (ContractError, KeyError, TypeError, ValueError) as exc:
            error = str(exc)
        levels.append(level if target_ok else None); targets.append(kind)
        details.append({'level': level, 'target_valid': target_ok, 'finding_valid': correct, 'error': error})
    measured = (max(levels) if levels and all(x is not None for x in levels) else (0 if not levels else None))
    return measured, targets, details


def measure(problem, payload):
    """이 함수의 서명에 requested role은 없다. 부분 실패가 다른 층 관측을 지우지 않는다."""
    out = {'format_valid': False, 'goal_string_correct': None, 'proof_valid': None,
           'representation_valid': None, 'review_target_valid': None, 'review_findings_valid': None,
           'strict_valid': False, 'A': None, 'D': None, 'M': None, 'review_count': None,
           'review_targets': [], 'review_details': [], 'node_count': None, 'errors': []}
    try:
        validate_payload(payload)
        out['format_valid'] = True
    except (ContractError, TypeError, KeyError) as exc:
        out['errors'].append('FORMAT: ' + str(exc))
    if not isinstance(payload, dict):
        return out
    graph = None
    try:
        validate_payload(payload.get('nodes'), OUTPUT_SCHEMA['properties']['nodes'], '$.nodes')
        validate_payload(payload.get('final'), OUTPUT_SCHEMA['properties']['final'], '$.final')
        out['node_count'] = len(payload['nodes'])
        out['goal_string_correct'] = any(n['id'] == payload['final'] and n['atom'] == problem['goal'] for n in payload['nodes'])
        graph = inspect_graph(problem, payload); out['proof_valid'] = True; out['D'] = graph['D']
    except (ContractError, KeyError, TypeError) as exc:
        out['proof_valid'] = False; out['errors'].append(str(exc))
    if graph is not None:
        try:
            validate_payload(payload.get('views'), OUTPUT_SCHEMA['properties']['views'], '$.views')
            out['A'] = inspect_views(problem, payload, graph); out['representation_valid'] = True
        except (ContractError, KeyError, TypeError) as exc:
            out['representation_valid'] = False; out['errors'].append(str(exc))
    if isinstance(payload.get('reviews'), list):
        out['review_count'] = len(payload['reviews'])
    try:
        level, targets, details = inspect_reviews(problem, payload, out['proof_valid'])
        out.update(M=level, review_targets=targets, review_details=details,
                   review_target_valid=all(d['target_valid'] for d in details),
                   review_findings_valid=all(d['finding_valid'] for d in details))
        out['errors'].extend(d['error'] for d in details if d['error'])
    except (ContractError, KeyError, TypeError, ValueError) as exc:
        out['review_target_valid'] = False; out['review_findings_valid'] = False; out['errors'].append(str(exc))
    out['strict_valid'] = all(out[k] is True for k in ('format_valid', 'proof_valid', 'representation_valid', 'review_target_valid', 'review_findings_valid'))
    return out


def role_match(measured, role):
    """요청 이행 여부는 의미 검증 이후 별도 계산. 측정값을 요청값으로 채우지 않는다."""
    target = [] if role['M'] == 0 else (['argument'] if role['M'] == 1 else ['acceptance_criterion'])
    return (measured['strict_valid'] and measured['A'] == role['A']
            and measured['D'] == (1 if role['D'] == 'shallow' else 2)
            and measured['M'] == role['M'] and measured['review_targets'] == target)
