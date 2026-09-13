"""v053 원문을 생산 모듈 없이 다시 검사한다. 원본 ZIP은 읽기만 한다.
사용: python forensic_replay.py v053_depth_01_evidence.zip --previous v052_adm_02_evidence.zip --out 새폴더
"""
from __future__ import annotations
import argparse, collections, csv, hashlib, itertools, json, statistics, zipfile
from pathlib import Path, PurePosixPath
from typing import Any

class Invalid(ValueError):
    pass

def need(value: Any, reason: str) -> None:
    if not value:
        raise Invalid(reason)

def load(raw: str | bytes) -> Any:
    def pairs(items):
        out = {}
        for k, v in items:
            need(k not in out, 'duplicate_key:' + k)
            out[k] = v
        return out
    def constant(text):
        raise Invalid('nonfinite:' + text)
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError) as exc:
        raise Invalid(str(exc)) from exc

def canon(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()

def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def encode(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()

def text(value: Any, maximum: int = 128) -> bool:
    return isinstance(value, str) and 1 <= len(value) <= maximum

def graph(problem: dict, payload: Any) -> dict:
    """배정된 arm/direction은 받지 않는다. 원문을 보정하지 않는다."""
    result = dict(format_valid=False, final_ref_valid=None, proof_valid=None,
                  strict_valid=False, D=None, signature=None, error=None)
    if isinstance(payload, dict) and isinstance(payload.get('nodes'), list):
        final = payload.get('final_node_id')
        result['final_ref_valid'] = bool(text(final) and sum(isinstance(n, dict) and n.get('id') == final for n in payload['nodes']) == 1)
    try:
        need(isinstance(payload, dict) and set(payload) == {'nodes', 'final_node_id'}, 'root_shape')
        ns = payload['nodes']
        need(isinstance(ns, list) and 1 <= len(ns) <= 16 and text(payload['final_node_id']), 'root_values')
        for n in ns:
            need(isinstance(n, dict) and set(n) == {'id', 'atom', 'rule', 'parents'}, 'node_shape')
            need(text(n['id']) and text(n['atom']) and (n['rule'] is None or text(n['rule'])), 'node_values')
            need(isinstance(n['parents'], list) and len(n['parents']) <= 16 and all(text(v) for v in n['parents']), 'parents_shape')
        result['format_valid'] = True
    except Invalid as exc:
        result['error'] = str(exc)
        return result
    try:
        facts = set(problem['facts']); rules = {r['id']: r for r in problem['rules']}
        seen, depths, supports, signatures = {}, {}, {}, {}
        for n in ns:
            ident, atom, rule, parents = (n[k] for k in ('id', 'atom', 'rule', 'parents'))
            need(ident not in seen, 'duplicate_node:' + ident)
            need(len(set(parents)) == len(parents), 'duplicate_parent:' + ident)
            need(all(p in seen for p in parents), 'non_topological_parent:' + ident)
            if rule is None:
                need(not parents and atom in facts, 'false_fact:' + ident)
                depth = 0
            else:
                need(rule in rules, 'unknown_rule:' + rule)
                r = rules[rule]
                need(atom == r['conclusion'], 'wrong_conclusion:' + ident)
                need(collections.Counter(seen[p]['atom'] for p in parents) == collections.Counter(r['premises']), 'wrong_premises:' + ident)
                need(bool(parents), 'empty_rule_parents:' + ident)
                depth = 1 + max(depths[p] for p in parents)
            seen[ident] = n; depths[ident] = depth
            supports[ident] = {ident}.union(*(supports[p] for p in parents))
            signatures[ident] = sha(canon([atom, rule, sorted(signatures[p] for p in parents)]))
        final = payload['final_node_id']
        need(final in seen, 'missing_final')
        need(seen[final]['atom'] == problem['goal'], 'wrong_goal')
        need(supports[final] == set(seen), 'unused_nodes')
        result.update(proof_valid=True, strict_valid=True, D=depths[final], signature=signatures[final])
    except Invalid as exc:
        result.update(proof_valid=False, error=str(exc))
    return result

def possible_depths(problem: dict) -> list[int]:
    """목표에서 모든 근거 트리를 열거하는 평가 전용 함수. 생성에는 쓰지 않는다."""
    def visit(atom, ancestors):
        if atom in ancestors:
            return set()
        ds = {0} if atom in problem['facts'] else set()
        for rule in problem['rules']:
            if rule['conclusion'] == atom:
                children = [visit(a, ancestors | {atom}) for a in rule['premises']]
                for combination in itertools.product(*children):
                    if combination:
                        ds.add(1 + max(combination))
        return ds
    answer = sorted(visit(problem['goal'], set()))
    need(bool(answer), 'unreachable_goal')
    return answer

def checked_zip(path: Path) -> tuple[dict[str, bytes], dict]:
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        need(len(names) == len(set(n.casefold() for n in names)), 'duplicate_archive_path')
        need(sum(i.file_size for i in z.infolist()) <= 256 * 1024**2, 'archive_size')
        for n in names:
            p = PurePosixPath(n)
            need(not p.is_absolute() and '..' not in p.parts and '\\' not in n and ':' not in n, 'unsafe_path')
        data = {n: z.read(n) for n in names}
    manifest = load(data['BUNDLE_MANIFEST.json'])
    need(set(data) == set(manifest['file_hashes']) | {'BUNDLE_MANIFEST.json'}, 'manifest_inventory')
    for n, h in manifest['file_hashes'].items():
        need(sha(data[n]) == h, 'manifest_hash:' + n)
    return data, manifest

def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

def analyze(bundle: Path, previous: Path | None, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    data, manifest = checked_zip(bundle)
    p = load(data['external_plan/v053.plan.json']); stored = load(data['run/summary.json'])
    need(sha(canon({k: v for k, v in p.items() if k != 'plan_sha256'})) == p['plan_sha256'], 'plan_hash')
    need(load(data['run/plan.snapshot.json']) == p, 'external_plan')
    events = [load(x) for x in data['run/events.jsonl'].splitlines()]
    need(len(events) == len(p['slots']) == 120, 'complete_120')
    old_trials = {r['id']: r for r in stored['trials']}
    bounds = {pid: possible_depths(pr) for pid, pr in p['problems'].items()}
    rows, errors, differences, requests = [], [], [], {}
    tip = p['plan_sha256']; fields = 0
    for slot, event in zip(p['slots'], events):
        need(slot == event['slot'] and event['previous_hash'] == tip, 'event_order')
        need(event['event_hash'] == sha(canon({k: v for k, v in event.items() if k != 'event_hash'})), 'event_hash')
        tip = event['event_hash']; sid = slot['id']
        reqraw, raw = (data['run/calls/' + sid + '/' + name] for name in ('request.wire.json', 'response.raw.json'))
        need(event['request_sha256'] == sha(reqraw) and event['response_sha256'] == sha(raw), 'wire_hash')
        need(event['http_status'] == 200 and event['transport_error'] is None, 'transport')
        request, envelope = load(reqraw), load(raw)
        need(envelope['model'] == p['baseline']['config']['model'] and envelope['done'] is True and envelope['done_reason'] == 'stop', 'model_or_completion')
        message = envelope['message']; need(message['role'] == 'assistant' and not message.get('thinking') and not message.get('tool_calls') and not message.get('images'), 'message_envelope')
        payload = load(message['content']); measured = graph(p['problems'][slot['problem_id']], payload)
        target = None if slot['direction'] == 'neutral' else bounds[slot['problem_id']][0 if slot['direction'] == 'shallow' else -1]
        match = None if target is None else bool(measured['strict_valid'] and measured['D'] == target)
        for k in ('format_valid', 'final_ref_valid', 'proof_valid', 'strict_valid', 'D'):
            fields += 1
            if measured[k] != old_trials[sid]['measurement'][k]: differences.append({'id': sid, 'field': k})
        if target is not None:
            fields += 1
            if match != old_trials[sid]['role_match']: differences.append({'id': sid, 'field': 'role_match'})
        if measured['error']:
            errors.append({'id': sid, 'seed': slot['seed'], 'error': measured['error'], 'payload': payload})
        rows.append({**{k: slot[k] for k in ('id', 'position', 'problem_id', 'seed', 'arm', 'direction')},
                     **measured, 'role_match': match, 'target_depth': target,
                     'prompt_tokens': envelope.get('prompt_eval_count'), 'generated_tokens': envelope.get('eval_count'),
                     'server_ns': envelope.get('total_duration'), 'http_ns': event['elapsed_ns']})
        requests[(slot['problem_id'], slot['seed'], slot['arm'], slot['direction'])] = reqraw
    need(tip == stored['event_tip'], 'event_tip')
    lookup = {(r['problem_id'], r['seed'], r['arm'], r['direction']): r for r in rows}
    pairs = []
    for pid in p['problems']:
        for arm in p['arms']:
            for seed in p['seeds']:
                a, b, n = (lookup[(pid, seed, arm, d)] for d in ('shallow', 'deep', 'neutral'))
                pairs.append({'problem_id': pid, 'arm': arm, 'seed': seed, 'shallow_D': a['D'], 'deep_D': b['D'], 'neutral_D': n['D'],
                              'both_valid': a['strict_valid'] and b['strict_valid'],
                              'selective_success': bool(a['role_match'] and b['role_match'] and a['D'] != b['D']),
                              'same_valid_structure_as_neutral': bool(a['strict_valid'] and b['strict_valid'] and n['strict_valid'] and a['signature'] == b['signature'] == n['signature'])})
    groups = {}
    for pid, arm, direction in itertools.product(p['problems'], p['arms'], p['directions']):
        rs = [r for r in rows if (r['problem_id'], r['arm'], r['direction']) == (pid, arm, direction)]
        groups['/'.join((pid, arm, direction))] = {'assigned': len(rs), 'format_valid': sum(r['format_valid'] for r in rs), 'proof_valid': sum(r['proof_valid'] is True for r in rs),
            'unmeasured_depth': sum(r['D'] is None for r in rs), 'depth_distribution': dict(collections.Counter(str(r['D']) for r in rs)),
            'direction_success': None if direction == 'neutral' else sum(r['role_match'] is True for r in rs),
            'prompt_tokens': sum(r['prompt_tokens'] for r in rs), 'generated_tokens': sum(r['generated_tokens'] for r in rs),
            'server_ns': sum(r['server_ns'] for r in rs)}
    definition_matches = 0
    marker = '\n깊이의 계산 정의:'
    for key, raw in requests.items():
        pid, seed, arm, direction = key
        if arm != 'defined': continue
        a = load(raw); b = load(requests[(pid, seed, 'original', direction)])
        s, old = (x['messages'][0]['content'] for x in (a, b))
        start = s.index(marker); end = s.index('\n경로 지시:' if direction != 'neutral' else '\nJSON 객체 하나만', start)
        a['messages'][0]['content'] = s[:start] + s[end:]
        need(encode(a) == encode(b), 'more_than_definition_changed')
        definition_matches += 1
    historical = []
    if previous:
        olddata, _ = checked_zip(previous); oldreport = load(olddata['run/summary.json'])
        for t in oldreport['trials']:
            if t['task'] != 'graph_only': continue
            pid, seed = t['problem_id'], t['seed']; direction = 'shallow' if '_shallow_' in t['role_id'] else 'deep'
            oldwire = olddata['run/calls/' + t['id'] + '/request.wire.json']; current = lookup[pid, seed, 'original', direction]
            oldpayload = load(load(olddata['run/calls/' + t['id'] + '/response.raw.json'])['message']['content'])
            oldmeasured = graph(p['problems'][pid], oldpayload)
            old_target = bounds[pid][0 if direction == 'shallow' else -1]
            old_role = bool(oldmeasured['strict_valid'] and oldmeasured['D'] == old_target)
            historical.append({'problem_id': pid, 'seed': seed, 'direction': direction,
                               'request_bytes_equal': oldwire == requests[pid, seed, 'original', direction],
                               'v052_D': oldmeasured['D'], 'v053_D': current['D'],
                               'validity_equal': oldmeasured['strict_valid'] == current['strict_valid'],
                               'role_match_equal': old_role == current['role_match']})
        need(len(historical) == 40 and all(x['request_bytes_equal'] for x in historical), 'history_request_40')
    summary = {'bundle_sha256': sha(bundle.read_bytes()), 'manifest_files': len(manifest['file_hashes']), 'calls': len(rows),
               'compared_semantic_fields': fields, 'semantic_discrepancies': differences, 'all_possible_depths': bounds,
               'valid_proofs': sum(r['strict_valid'] for r in rows), 'format_valid': sum(r['format_valid'] for r in rows),
               'selective_pairs': sum(r['selective_success'] for r in pairs), 'assigned_pairs': len(pairs),
               'all_three_valid_same_structure': sum(r['same_valid_structure_as_neutral'] for r in pairs),
               'definition_only_request_pairs': definition_matches, 'historical_request_pairs': len(historical),
               'historical_measurement_matches': sum(r['v052_D'] == r['v053_D'] and r['validity_equal'] and r['role_match_equal'] for r in historical),
               'groups': groups, 'errors': errors}
    (out/'forensic_results.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    write_csv(out/'all_trials.csv', rows); write_csv(out/'D_pairs.csv', pairs)
    if historical: write_csv(out/'v052_v053_replication.csv', historical)
    need(not differences, 'semantic_replay_mismatch')
    return summary

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('bundle', type=Path); p.add_argument('--previous', type=Path); p.add_argument('--out', type=Path, required=True)
    a = p.parse_args(); r = analyze(a.bundle, a.previous, a.out)
    print(json.dumps({k: v for k, v in r.items() if k not in ('groups', 'errors')}, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
