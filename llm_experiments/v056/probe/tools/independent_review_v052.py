"""v052 증거의 독립 원문 재검사. 생산 채점기·fixture·첨부 source_snapshot을 실행하지 않는다."""
from __future__ import annotations
import argparse
import collections
import hashlib
import itertools
import json
from pathlib import Path, PurePosixPath
import zipfile

class Invalid(ValueError):
    """형식·의미·자료 계약 위반."""

def need(condition, message):
    if not condition:
        raise Invalid(message)

def load(raw):
    def pairs(entries):
        out = {}
        for key, value in entries:
            need(key not in out, 'duplicate_json_key:' + key)
            out[key] = value
        return out
    def constant(value):
        raise Invalid('non_finite_json:' + value)
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise Invalid('invalid_json:' + str(exc)) from exc

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def canon(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')

def schema_check(value, spec):
    """요청의 JSON Schema를 별도로 해석한다. 값 보정·enum 답안 주입 없음."""
    if 'anyOf' in spec:
        for alternative in spec['anyOf']:
            try:
                schema_check(value, alternative)
                return
            except Invalid:
                pass
        raise Invalid('anyOf')
    kind = spec.get('type')
    if kind == 'object':
        need(isinstance(value, dict), 'object')
        need(set(spec.get('required', [])) <= set(value), 'required')
        props = spec.get('properties', {})
        extra = spec.get('additionalProperties', True)
        need(extra is not False or set(value) <= set(props), 'extra_property')
        need(spec.get('minProperties', 0) <= len(value) <= spec.get('maxProperties', 10**8), 'property_count')
        for key, entry in value.items():
            if key in props:
                schema_check(entry, props[key])
            elif isinstance(extra, dict):
                need(1 <= len(key) <= 128, 'property_name')
                schema_check(entry, extra)
    elif kind == 'array':
        need(isinstance(value, list), 'array')
        need(spec.get('minItems', 0) <= len(value) <= spec.get('maxItems', 10**8), 'array_count')
        for entry in value:
            schema_check(entry, spec['items'])
    elif kind == 'string':
        need(isinstance(value, str), 'string')
        need(spec.get('minLength', 0) <= len(value) <= spec.get('maxLength', 10**8), 'string_length')
    elif kind == 'boolean':
        need(type(value) is bool, 'boolean')
    elif kind == 'null':
        need(value is None, 'null')
    elif kind == 'integer':
        need(type(value) is int, 'integer')
    else:
        raise Invalid('unsupported_schema_type:' + str(kind))
    if 'const' in spec:
        need(type(value) is type(spec['const']) and value == spec['const'], 'const')


def final_reference(payload, final_key):
    """참조 존재 여부는 참조된 노드의 논리적 유효성과 별도로 측정한다."""
    if not isinstance(payload, dict) or not isinstance(payload.get('nodes'), list):
        return None
    final = payload.get(final_key)
    if not isinstance(final, str) or not final:
        return False
    return sum(isinstance(node, dict) and node.get('id') == final for node in payload['nodes']) == 1


def graph(problem, nodes, final):
    need(isinstance(nodes, list) and nodes, 'nodes_missing')
    rule_map = {rule['id']: rule for rule in problem['rules']}
    index = {}; depth = {}; ancestry = {}; signatures = {}
    for node in nodes:
        key = node['id']; parents = node['parents']; rid = node['rule']
        need(key not in index, 'duplicate_node')
        need(len(parents) == len(set(parents)), 'duplicate_parent')
        need(all(parent in index for parent in parents), 'forward_or_missing_parent')
        if rid is None:
            need(parents == [] and node['atom'] in problem['facts'], 'unsupported_fact')
            depth[key] = 0
        else:
            need(rid in rule_map, 'unknown_rule')
            rule = rule_map[rid]
            need(node['atom'] == rule['conclusion'], 'wrong_rule_conclusion')
            need(sorted(index[parent]['atom'] for parent in parents) == sorted(rule['premises']), 'wrong_premises')
            depth[key] = 1 + max(depth[parent] for parent in parents)
        ancestry[key] = {key}
        for parent in parents:
            ancestry[key].update(ancestry[parent])
        signatures[key] = sha(canon([node['atom'], rid, sorted(signatures[parent] for parent in parents)]))
        index[key] = node
    need(final in index, 'final_missing')
    need(index[final]['atom'] == problem['goal'], 'wrong_goal')
    need(ancestry[final] == set(index), 'unused_nodes_or_alternative_path')
    return index, depth, ancestry, signatures


def bound_depths(problem):
    def walk(atom, path):
        if atom in path:
            return set()
        values = {0} if atom in problem['facts'] else set()
        for rule in problem['rules']:
            if rule['conclusion'] == atom:
                for ds in itertools.product(*(walk(a, path | {atom}) for a in rule['premises'])):
                    values.add(1 + max(ds))
        return values
    ds = walk(problem['goal'], set())
    need(bool(ds), 'unreachable_goal')
    return min(ds), max(ds)


def inspect_views(problem, views, g):
    index, _, ancestry, _ = g
    need(isinstance(views, dict) and set(views) == set(index), 'view_node_coverage')
    rules = {rule['id']: rule for rule in problem['rules']}
    modes = []
    for key, view in views.items():
        if view['kind'] == 'instance':
            need(view['atom'] == index[key]['atom'], 'instance_atom')
            modes.append('instance'); continue
        need(view['kind'] == 'universal_schema' and view['quantifier'] == 'forall_boolean_valuations', 'schema_kind')
        binding = view['binding']; used = [index[n] for n in ancestry[key]]
        atoms = {n['atom'] for n in used}
        need(len(binding) == len(atoms) and set(binding.values()) == atoms, 'binding_coverage')
        need(binding[view['conclusion']] == index[key]['atom'], 'schema_conclusion')
        expected = set()
        for node in used:
            if node['rule'] is None:
                expected.add(((), node['atom']))
            else:
                rule = rules[node['rule']]
                expected.add((tuple(sorted(rule['premises'])), rule['conclusion']))
        actual = []
        for clause in view['assumptions']:
            need(len(clause['if']) == len(set(clause['if'])), 'duplicate_assumption_parent')
            actual.append((tuple(sorted(binding[v] for v in clause['if'])), binding[clause['then']]))
        need(len(actual) == len(set(actual)) and set(actual) == expected, 'actual_support_mismatch')
        for values in itertools.product((False, True), repeat=len(binding)):
            assignment = dict(zip(binding, values))
            premises = all(not all(assignment[v] for v in c['if']) or assignment[c['then']] for c in view['assumptions'])
            need(not premises or assignment[view['conclusion']], 'truth_table_counterexample')
        modes.append('schema')
    return modes[0] if len(set(modes)) == 1 else 'mixed'


def check(problem, payload, req_schema, arm, task):
    fields = ('format_valid', 'proof_valid', 'representation_valid', 'review_target_valid', 'review_findings_valid')
    out = {field: None for field in fields}
    out.update(format_valid=False, strict_valid=False, A=None, D=None, M=None, review_targets=[], errors=[], final_reference_exists=None)
    if not isinstance(payload, dict):
        return out
    final_key = 'final' if arm == 'legacy' else 'final_node_id'
    out['final_reference_exists'] = final_reference(payload, final_key)
    try:
        schema_check(payload, req_schema); out['format_valid'] = True
    except Invalid as exc:
        out['errors'].append('format:' + str(exc))
    final = payload.get(final_key)
    views = payload.get('views') if arm == 'legacy' else {}
    if arm != 'legacy' and task != 'graph_only':
        try:
            for entry in payload['node_views']:
                key = entry['node_id']; need(key not in views, 'duplicate_node_view')
                view = dict(entry['representation'])
                if view.get('kind') == 'universal_schema':
                    binding = {}
                    for item in view.pop('bindings'):
                        need(item['variable'] not in binding, 'duplicate_binding')
                        binding[item['variable']] = item['atom']
                    view['binding'] = binding
                views[key] = view
        except (KeyError, TypeError, Invalid) as exc:
            out['format_valid'] = False; views = None; out['errors'].append('projection:' + str(exc))
    g = None
    try:
        schema_check(payload.get('nodes'), req_schema['properties']['nodes'])
        schema_check(final, req_schema['properties'][final_key])
        g = graph(problem, payload['nodes'], final)
        out['proof_valid'] = True; out['D'] = g[1][final]; out['proof_signature'] = g[3][final]
    except (KeyError, TypeError, ValueError) as exc:
        out['proof_valid'] = False; out['errors'].append('proof:' + str(exc))
    if task == 'graph_only':
        out['strict_valid'] = out['format_valid'] and out['proof_valid']
        return out
    if g is not None:
        try:
            out['A'] = inspect_views(problem, views, g); out['representation_valid'] = True
        except (KeyError, TypeError, ValueError) as exc:
            out['representation_valid'] = False; out['errors'].append('view:' + str(exc))
    levels = []; targets = []; results = []
    try:
        reviews = payload['reviews']; need(isinstance(reviews, list) and len(reviews) <= 4, 'reviews_type')
        ids = [review['id'] for review in reviews]; need(len(ids) == len(set(ids)), 'duplicate_review_id')
        for review in reviews:
            target_ok = False; finding_ok = False; kind = review.get('target_kind')
            level = {'argument': 1, 'acceptance_criterion': 2}.get(kind)
            try:
                if level == 1:
                    target_ok = review.get('target') == final and review.get('check') == 'support_replay' and any(n.get('id') == final for n in payload['nodes'])
                    need(target_ok, 'M1_target')
                    schema_check(review, req_schema['properties']['reviews']['items']['anyOf'][0])
                    need(len(review['evidence']) == len(set(review['evidence'])) and set(review['evidence']) == {n['id'] for n in payload['nodes']}, 'M1_evidence')
                    finding = review['finding']; used = [n['rule'] for n in payload['nodes'] if n['rule'] is not None]
                    need(len(finding['used_rules']) == len(set(finding['used_rules'])) and sorted(finding['used_rules']) == sorted(set(used)), 'M1_rules')
                    need(finding['grounded'] is out['proof_valid'] and finding['conclusion'] == next(n['atom'] for n in payload['nodes'] if n['id'] == final), 'M1_finding')
                elif level == 2:
                    target_ok = review.get('target') == 'valid_proof_and_goal' and review.get('check') == 'counterexample_probe'
                    need(target_ok, 'M2_target')
                    schema_check(review, req_schema['properties']['reviews']['items']['anyOf'][1])
                    need(review['probe'] == {'atom': problem['goal'], 'rule': None, 'parents': []}, 'M2_probe')
                    expected = {'answer_only_accepts': True, 'proof_and_goal_accepts': problem['goal'] in problem['facts'], 'gap_detected': problem['goal'] not in problem['facts']}
                    need(review['finding'] == expected, 'M2_finding')
                else:
                    raise Invalid('unknown_review_kind')
                finding_ok = True
            except (KeyError, TypeError, ValueError, StopIteration) as exc:
                out['errors'].append('review:' + str(exc))
            levels.append(level if target_ok else None); targets.append(kind); results.append((target_ok, finding_ok))
        out['M'] = 0 if not levels else (max(levels) if all(v is not None for v in levels) else None)
        out['review_targets'] = targets
        out['review_target_valid'] = all(v[0] for v in results)
        out['review_findings_valid'] = all(v[1] for v in results)
    except (KeyError, TypeError, ValueError) as exc:
        out['review_target_valid'] = False; out['review_findings_valid'] = False
        out['errors'].append('reviews:' + str(exc))
    out['strict_valid'] = all(out[f] is True for f in fields)
    return out


def verify(bundle):
    with zipfile.ZipFile(bundle) as archive:
        names = archive.namelist()
        need(len(names) == len(set(names)), 'duplicate_zip_path')
        need(sum(info.file_size for info in archive.infolist()) <= 256 * 1024**2, 'zip_size_limit')
        for name in names:
            path = PurePosixPath(name)
            need(not path.is_absolute() and '..' not in path.parts and '\\' not in name, 'unsafe_zip_path')
        manifest = load(archive.read('BUNDLE_MANIFEST.json'))
        need(set(names) == set(manifest['file_hashes']) | {'BUNDLE_MANIFEST.json'}, 'manifest_inventory')
        for name, expected in manifest['file_hashes'].items():
            need(sha(archive.read(name)) == expected, 'manifest_hash:' + name)
        plan = load(archive.read('external_plan/v052.plan.json'))
        report = load(archive.read('run/summary.json'))
        need(sha(canon({k: v for k, v in plan.items() if k != 'plan_sha256'})) == plan['plan_sha256'], 'plan_digest')
        need(load(archive.read('run/plan.snapshot.json')) == plan, 'external_snapshot_plan')
        stored = {t['id']: t for t in report['trials']}
        events = [load(line) for line in archive.read('run/events.jsonl').splitlines()]
        need(len(events) == len(plan['slots']) == 440, 'event_slot_count')
        previous = plan['plan_sha256']; rows = []; ref_corrections = []; discrepancies = []; json_failures = collections.Counter()
        for slot, event in zip(plan['slots'], events):
            sid = slot['id']; need(event['slot'] == slot and event['previous_hash'] == previous, 'event_order_or_previous')
            need(event['event_hash'] == sha(canon({k: v for k, v in event.items() if k != 'event_hash'})), 'event_hash')
            previous = event['event_hash']
            need(event['kind'] == 'call' and event['parents'] == [], 'unexpected_event_or_parents')
            req = archive.read('run/calls/' + sid + '/request.wire.json'); raw = archive.read('run/calls/' + sid + '/response.raw.json')
            need(sha(req) == event['request_sha256'] and sha(raw) == event['response_sha256'], 'wire_hash')
            request = load(req); env = load(raw); need(event['http_status'] == 200 and event['transport_error'] is None, 'transport')
            need(env['model'] == plan['baseline']['config']['model'] and env['done'] is True and env['done_reason'] == 'stop', 'response_identity_or_completion')
            message = env['message']; need(message['role'] == 'assistant' and not message.get('thinking') and not message.get('tool_calls') and not message.get('images'), 'response_contract')
            payload = None; parse_error = None
            try:
                payload = load(message['content']); need(isinstance(payload, dict), 'non_object')
            except Invalid as exc:
                parse_error = str(exc); json_failures[parse_error.split(':')[0]] += 1
            result = check(plan['problems'][slot['problem_id']], payload, request['format'], slot['arm'], slot['task'])
            old = stored[sid]['measurement']
            for key in ('format_valid', 'proof_valid', 'representation_valid', 'review_target_valid', 'review_findings_valid', 'strict_valid', 'A', 'D', 'M', 'review_targets'):
                if result[key] != old[key]:
                    discrepancies.append({'slot_id': sid, 'field': key, 'stored': old[key], 'independent': result[key]})
            old_ref = old.get('final_ref_valid'); new_ref = result['final_reference_exists']
            if old_ref != new_ref:
                ref_corrections.append({'slot_id': sid, 'task': slot['task'], 'problem_id': slot['problem_id'], 'stored': old_ref, 'corrected': new_ref})
            role_match = None; depth_match = None
            if slot['role_id']:
                a, d, m = slot['role_id'].split('_'); target_m = int(m[1:]); bounds = bound_depths(plan['problems'][slot['problem_id']])
                depth_match = result['strict_valid'] and result['D'] == bounds[0 if d == 'shallow' else 1]
                if slot['task'] in ('factorial', 'legacy'):
                    role_match = bool(depth_match and result['A'] == a and result['M'] == target_m and result['review_targets'] == ([] if target_m == 0 else ['argument' if target_m == 1 else 'acceptance_criterion']))
                    need(role_match == stored[sid]['role_match'], 'role_match_disagreement:' + sid)
            rows.append({**slot, **result, 'role_match': role_match, 'depth_match': depth_match, 'parse_error': parse_error})
        need(previous == report['event_tip'], 'event_tip')
        groups = {}
        for pid, task in sorted({(r['problem_id'], r['task']) for r in rows}):
            rs = [r for r in rows if r['problem_id'] == pid and r['task'] == task]
            groups[pid + '/' + task] = {'assigned': len(rs), 'strict_valid': sum(r['strict_valid'] for r in rs), 'role_match': sum(r['role_match'] is True for r in rs), 'final_reference_exists': sum(r['final_reference_exists'] is True for r in rs)}
        drows = []
        for pid in plan['problems']:
            rs = [r for r in rows if r['problem_id'] == pid and r['task'] == 'graph_only']
            pairs = []; bounds = bound_depths(plan['problems'][pid])
            for seed in plan['seeds']:
                pair = [next(r for r in rs if r['seed'] == seed and ('_' + d + '_') in r['role_id']) for d in ('shallow', 'deep')]
                pairs.append({'problem_id': pid, 'seed': seed, 'shallow_actual': pair[0]['D'], 'deep_actual': pair[1]['D'], 'selective_success': bool(pair[0]['depth_match'] and pair[1]['depth_match'] and pair[0]['D'] != pair[1]['D'])})
            drows.extend(pairs)
            groups[pid + '/graph_only'].update(depth_requested_success=sum(r['depth_match'] is True for r in rs), paired_selective_success=sum(p['selective_success'] for p in pairs), assigned_pairs=len(pairs), allowed_depths=list(bounds))
        return {'bundle_sha256': sha(Path(bundle).read_bytes()), 'manifest_files_verified': len(manifest['file_hashes']), 'event_count': len(events), 'raw_response_count': len(rows), 'parse_failures': dict(json_failures), 'semantic_discrepancies': discrepancies, 'semantic_fields_compared': 10 * len(rows), 'final_reference_corrections': ref_corrections, 'groups': groups, 'D_pairs': drows, 'rows': rows, 'scope': '원문·계획·의미의 독립 재계산. 기존 판정기 import 없음. runtime/source/request 원형 재검사는 별도 생산 감사 결과와 함께 사용.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path); parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(); result = verify(args.bundle)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    compact = {k: v for k, v in result.items() if k not in ('rows', 'D_pairs', 'final_reference_corrections')}
    compact['final_reference_correction_count'] = len(result['final_reference_corrections'])
    print(json.dumps(compact, ensure_ascii=False, indent=2))
    return 1 if result['semantic_discrepancies'] else 0

if __name__ == '__main__':
    raise SystemExit(main())
