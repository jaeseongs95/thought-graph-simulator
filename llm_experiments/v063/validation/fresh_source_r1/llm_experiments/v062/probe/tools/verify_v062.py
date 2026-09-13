"""Independently verify v062 evidence without importing production modules."""
from __future__ import annotations

import argparse
import base64
import collections
import hashlib
import io
import json
import statistics
import sys
import tempfile
import urllib.parse
import zipfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
V057_ROOT = ROOT.parents[1] / 'v057' / 'probe'
V058_ROOT = ROOT.parents[1] / 'v058' / 'probe'
sys.path.insert(0, str(V058_ROOT / 'tools'))

# These are independent verifiers/helpers from older, sealed source trees.  This
# file never imports construction_probe_v062 or an evidence source snapshot.
from verify_v058 import verify as baseline_verify, metadata as prior_metadata
from independent_graph_forensic import need, load, canonical, sha, extract_payload


MODELS = ('candidate',)
MODES = ('graph',)
VARIANTS = ('target_k03', 'target_k17')
TARGET_RULES = {'target_k03': 'k03', 'target_k17': 'k17'}
SCHEDULE_SEED = 6202026
MAX_CALLS = 40
SOURCE_RULE_ORDER = ['k10', 'k17', 'k03']
RULE_ORDER = ['k03', 'k17', 'k10']
BOUNDARY_CELLS = {
    'candidate': {'problem_id': 'K01', 'arm': 'original', 'direction': 'shallow'},
}
NODE_SCHEMA = {
    'type': 'object',
    'properties': {
        'id': {'type': 'string', 'minLength': 1, 'maxLength': 128},
        'atom': {'type': 'string', 'minLength': 1, 'maxLength': 128},
        'rule_id': {'anyOf': [
            {'type': 'string', 'minLength': 1, 'maxLength': 128},
            {'type': 'null'},
        ]},
        'parents': {'type': 'array', 'minItems': 0, 'maxItems': 8,
                    'items': {'type': 'string', 'minLength': 1, 'maxLength': 128}},
    },
    'required': ['id', 'atom', 'rule_id', 'parents'],
    'additionalProperties': False,
}
GRAPH_SCHEMA = {
    'type': 'object',
    'properties': {
        'nodes': {'type': 'array', 'minItems': 1, 'maxItems': 16,
                  'items': NODE_SCHEMA},
        'final_node_id': {'type': 'string', 'minLength': 1, 'maxLength': 128},
    },
    'required': ['nodes', 'final_node_id'],
    'additionalProperties': False,
}
POLICY = {
    'question': 'Can a fixed Gemma K01 configuration construct a minimal valid DAG when its terminal rule is externally designated?',
    'intervention': 'Fix the common k03/k17/k10 rule array and replace the historical merged instruction/schema with a common conditional minimal-DAG task; only the target rule ID varies.',
    'sampling': 'All 10 historical seeds; four dependent observations per seed, not 40 independent problems.',
    'schedule': 'SHA256-ranked seeds; five ABBA and five BAAB blocks, frozen schedule_seed=6202026.',
    'history': 'No state reset. Same-condition repeat distance and preceding calls remain possible explanations.',
    'interpretation': 'This is conditional construction after a target is supplied. It does not test free terminal selection, depth-direction following, A control, M1/M2 review, an internal mechanism, or general depth control.',
    'measurement': 'Format, proof validity, strict ancestry closure, final-goal reach, target-rule match, actual parent-D, rule position/rank, node count and target fulfillment are separate.',
    'gate': 'Only complete 40/40 strict-valid target matches with k03 D=1, k17 D=2 and all ten seed profiles stable may motivate a separately frozen free-choice minimal-DAG design.',
    'missing': 'Unobserved and unmeasured remain null; full rates require complete measured denominators.',
    'retry': False, 'repair': False, 'resume': False, 'download_models': False,
    'budget': '40 inference calls and 20 metadata records; no warmup.',
}


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def wire(value):
    return compact(value).encode('utf-8')


def unpack(raw):
    """Read a bounded regular ZIP and check every content hash before use."""
    need(len(raw) <= 100 * 1024**2, 'archive size')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        need(0 < len(infos) <= 12000
             and sum(item.file_size for item in infos) <= 256 * 1024**2,
             'archive expansion')
        seen = set()
        reserved = {'CON', 'PRN', 'AUX', 'NUL', 'CLOCK$', 'CONIN$', 'CONOUT$'}
        reserved |= {prefix + str(index) for prefix in ('COM', 'LPT')
                     for index in range(1, 10)}
        for item in infos:
            name = item.filename
            path = PurePosixPath(name)
            need(not item.is_dir() and bool(name) and not path.is_absolute()
                 and path.as_posix() == name and '\\' not in name and ':' not in name
                 and all(part not in ('.', '..') for part in path.parts), 'archive path')
            need(name.casefold() not in seen, 'duplicate/case ZIP member')
            seen.add(name.casefold())
            need(all(part and not part.endswith((' ', '.'))
                     and part.split('.')[0].upper() not in reserved
                     and not any(ord(char) < 32 or char in '<>"|?*' for char in part)
                     for part in path.parts), 'Windows path')
            need(((item.external_attr >> 16) & 0o170000) != 0o120000
                 and not item.flag_bits & 1, 'archive link/encryption')
            limit = 8 * 1024**2
            if name in ('external_plan/v062.plan.json', 'run/plan.snapshot.json'):
                limit = 32 * 1024**2
            if name == 'run/baseline/v058_evidence.zip':
                limit = 100 * 1024**2
            need(item.file_size <= limit, 'member size: ' + name)
        need(any(item.filename == 'BUNDLE_MANIFEST.json' for item in infos),
             'manifest absent')
        data = {item.filename: archive.read(item.filename) for item in infos}
    manifest = load(data.pop('BUNDLE_MANIFEST.json'))
    need(isinstance(manifest, dict) and isinstance(manifest.get('file_hashes'), dict),
         'manifest shape')
    need(set(manifest['file_hashes']) == set(data), 'manifest member set')
    for name, content in data.items():
        need(sha(content) == manifest['file_hashes'][name], 'manifest hash: ' + name)
    return data, manifest


def rank(seed, purpose):
    return hashlib.sha256(f'{SCHEDULE_SEED}:{purpose}:{seed}'.encode('ascii')).hexdigest()


def schedule(reference):
    seeds = reference['seeds']
    need(len(seeds) == 10 and len(set(seeds)) == 10
         and all(type(seed) is int for seed in seeds), 'ten integer seeds')
    cells = {slot['seed']: slot for slot in reference['slots']}
    need(len(cells) == len(reference['slots']) == 10, 'ten source requests')
    abba = set(sorted(seeds, key=lambda seed: rank(seed, 'assignment'))[:5])
    result = []
    for block, seed in enumerate(sorted(seeds, key=lambda seed: rank(seed, 'blocks'))):
        sequence = 'ABBA' if seed in abba else 'BAAB'
        counts = {variant: 0 for variant in VARIANTS}
        previous_same = {}
        for period, letter in enumerate(sequence):
            variant = VARIANTS[letter == 'B']
            repeat = counts[variant]
            old = cells[seed]
            base = {key: value for key, value in old.items()
                    if key not in ('previous_call_mode', 'position_in_group')}
            previous = result[-1] if result else None
            previous_same_id = previous_same.get(variant)
            distance = None
            if repeat:
                prior = next(slot for slot in result if slot['id'] == previous_same_id)
                distance = period - prior['period']
            slot = {
                **base,
                'id': f'b{block:02d}_p{period}_{variant}_r{repeat}',
                'reference_slot_id': old['id'], 'task': 'conditional_construction',
                'mode': 'graph', 'stage': 'graph', 'direction': 'neutral',
                'role_id': variant, 'target_rule_id': TARGET_RULES[variant],
                'position': len(result), 'block': block, 'period': period,
                'seed_index': seeds.index(seed), 'variant': variant, 'repeat': repeat,
                'sequence': sequence,
                'previous_call_id': previous['id'] if previous else None,
                'previous_variant': previous['variant'] if previous else None,
                'previous_same_variant_slot_id': previous_same_id,
                'repeat_distance': distance,
            }
            result.append(slot)
            previous_same[variant] = slot['id']
            counts[variant] += 1
    need(sum(slot['sequence'] == 'ABBA' for slot in result) == 20
         and sum(slot['sequence'] == 'BAAB' for slot in result) == 20,
         'balanced sequences')
    return result


def actions(slots):
    result = []
    for block in range(10):
        block_slots = [slot for slot in slots if slot['block'] == block]
        need(len(block_slots) == 4, 'four calls per block')
        result.append({'kind': 'metadata', 'id': f'b{block:02d}.before',
                       'block': block, 'model_key': 'candidate'})
        result.extend({'kind': 'call', 'id': slot['id'], 'slot': slot}
                      for slot in block_slots)
        result.append({'kind': 'metadata', 'id': f'b{block:02d}.after',
                       'block': block, 'model_key': 'candidate'})
    return [dict(action, index=index) for index, action in enumerate(result)]


def prompt_for(target_rule_id):
    need(target_rule_id in TARGET_RULES.values(), 'target rule')
    return (
        'facts와 rules만 사용하여 goal을 지지하는 비순환 증명 DAG 하나를 작성한다.\n'
        f'final_node_id가 가리키는 goal 노드에는 지정된 마지막 규칙 id {target_rule_id}를 사용한다.\n'
        '각 node는 id, atom, rule_id, parents를 모두 쓴다. 초기 사실 node는 rule_id=null, parents=[]이다.\n'
        '규칙 적용 node는 입력 rules에 등록된 rule_id와 그 규칙의 모든 전제 node id를 parents에 쓴다.\n'
        '모든 node는 최종 node 자신이거나 그 조상이어야 한다. 설명, 후보 목록, 깊이 숫자는 출력하지 않는다.\n'
        'JSON 객체 하나만 출력한다. 출력 형식(JSON Schema):\n'
        + compact(GRAPH_SCHEMA)
    )


def transform_request(raw, target_rule_id):
    """Rebuild the request without importing the production request generator."""
    request = load(raw)
    need(isinstance(request, dict) and isinstance(request.get('messages'), list)
         and len(request['messages']) == 1
         and set(request['messages'][0]) == {'role', 'content'}
         and request['messages'][0]['role'] == 'user', 'one merged user message')
    content = request['messages'][0]['content']
    need(isinstance(content, str) and content.count('\n\nproblem: ') == 1,
         'problem boundary')
    problem = load(content.rsplit('\n\nproblem: ', 1)[1].encode('utf-8'))
    need(problem.get('id') == 'K01'
         and [rule.get('id') for rule in problem.get('rules', [])] == SOURCE_RULE_ORDER,
         'source rule order')
    by_id = {rule['id']: rule for rule in problem['rules']}
    need(set(by_id) == set(RULE_ORDER), 'source rule IDs')
    problem['rules'] = [by_id[rule_id] for rule_id in RULE_ORDER]
    output = json.loads(json.dumps(request, ensure_ascii=False))
    output['messages'] = [{'role': 'user', 'content': prompt_for(target_rule_id)
                           + '\n\nproblem: ' + compact(problem)}]
    output['format'] = json.loads(json.dumps(GRAPH_SCHEMA, ensure_ascii=False))
    return wire(output)


def reconstruct_reference(baseline, baseline_result):
    """Derive the receipt from raw, independently verified v058 evidence."""
    with zipfile.ZipFile(io.BytesIO(baseline)) as archive:
        names = archive.namelist()
        need(len(names) == len(set(names)), 'nested duplicate ZIP member')
        baseline_plan = load(archive.read('external_plan/v058.plan.json'))
        baseline_report = load(archive.read('run/summary.json'))
        candidates = [slot for slot in baseline_plan['slots']
                      if slot['model_key'] == 'candidate'
                      and slot['mode'] == 'choice'
                      and slot['sequence'] == 'graph_choice'
                      and all(slot[key] == value
                              for key, value in BOUNDARY_CELLS['candidate'].items())]
        need(len(candidates) == 10 and {slot['seed'] for slot in candidates}
             == set(baseline_plan['seeds']), 'v058 source choice cells')
        opposite = {(slot['seed'], slot['sequence']): slot
                    for slot in baseline_plan['slots']
                    if slot['model_key'] == 'candidate' and slot['mode'] == 'choice'
                    and all(slot[key] == value
                            for key, value in BOUNDARY_CELLS['candidate'].items())}
        request_bank = {}
        for slot in candidates:
            source_name = f"run/calls/{slot['id']}/request.wire.json"
            raw = archive.read(source_name)
            other = opposite.get((slot['seed'], 'choice_graph'))
            need(other is not None, 'opposite sequence source absent')
            need(raw == archive.read(f"run/calls/{other['id']}/request.wire.json"),
                 'opposite sequence request differs')
            for target_rule_id in TARGET_RULES.values():
                transform_request(raw, target_rule_id)
            request_bank[slot['id']] = base64.b64encode(raw).decode('ascii')
    reference = {
        'contract': 'audited-v058-choice-r1', 'bundle_sha256': sha(baseline),
        'plan_sha256': baseline_plan['plan_sha256'],
        'event_tip': baseline_report['event_tip'], 'recorded_calls': 80,
        'selected_calls': 10, 'evidence_kind': baseline_report['evidence_kind'],
        'config': baseline_plan['baseline']['config'],
        'identities': {'candidate': baseline_plan['identities']['candidate']},
        'seeds': baseline_plan['seeds'], 'slots': candidates,
        'request_bank': request_bank,
        'independent_compared_fields': baseline_result['compared_fields'],
    }
    reference['receipt_sha256'] = sha(canonical(reference))
    return reference


def schema_valid(payload):
    if not isinstance(payload, dict) or set(payload) != {'nodes', 'final_node_id'}:
        return False
    nodes = payload['nodes']
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= 16:
        return False
    if not isinstance(payload['final_node_id'], str) or not 1 <= len(payload['final_node_id']) <= 128:
        return False
    for node in nodes:
        if not isinstance(node, dict) or set(node) != {'id', 'atom', 'rule_id', 'parents'}:
            return False
        if (not isinstance(node['id'], str) or not 1 <= len(node['id']) <= 128
                or not isinstance(node['atom'], str) or not 1 <= len(node['atom']) <= 128):
            return False
        if node['rule_id'] is not None and (not isinstance(node['rule_id'], str)
                                            or not 1 <= len(node['rule_id']) <= 128):
            return False
        if not isinstance(node['parents'], list) or len(node['parents']) > 8:
            return False
        if any(not isinstance(parent, str) or not 1 <= len(parent) <= 128
               for parent in node['parents']):
            return False
    return True


def append_error(errors, code):
    if code not in errors:
        errors.append(code)


def kahn(nodes):
    """Return a topological order, independently of output node ordering."""
    children = {node_id: [] for node_id in nodes}
    indegree = {node_id: 0 for node_id in nodes}
    for node_id, node in nodes.items():
        for parent in node['parents']:
            if parent in nodes:
                children[parent].append(node_id)
                indegree[node_id] += 1
    ready = collections.deque(sorted(node_id for node_id, degree in indegree.items()
                                     if degree == 0))
    order = []
    while ready:
        node_id = ready.popleft()
        order.append(node_id)
        for child in sorted(children[node_id]):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
    return order if len(order) == len(nodes) else None


def final_ancestors(nodes, final_node_id):
    seen, pending = set(), [final_node_id]
    while pending:
        node_id = pending.pop()
        if node_id in seen or node_id not in nodes:
            continue
        seen.add(node_id)
        pending.extend(nodes[node_id]['parents'])
    return seen


def empty_measurement():
    return {
        'kind': 'conditional_proof_dag', 'format_valid': False,
        'proof_valid': None, 'strict_valid': None, 'D': None, 'actual_D': None,
        'selected_rule_id': None, 'selected_rule_position': None, 'terminal_rank': None,
        'goal_reached': None, 'target_rule_match': None,
        'instruction_fulfilled': None, 'node_count': None, 'errors': [],
    }


def independent_measure(problem, payload, slot):
    """Verify actual parent edges with Kahn ordering; no production scorer import."""
    result = empty_measurement()
    if payload is None:
        return result
    if not schema_valid(payload):
        result['errors'] = ['schema_invalid']
        return result
    result['format_valid'] = True
    result['node_count'] = len(payload['nodes'])
    errors = result['errors']
    nodes = {}
    for node in payload['nodes']:
        if node['id'] in nodes:
            append_error(errors, 'duplicate_id')
        else:
            nodes[node['id']] = node
    rules = {rule['id']: rule for rule in problem['rules']}
    rule_ids = [rule['id'] for rule in problem['rules']]
    terminal_ids = [rule['id'] for rule in problem['rules']
                    if rule['conclusion'] == problem['goal']]
    final_node = nodes.get(payload['final_node_id'])
    if final_node is None:
        append_error(errors, 'missing_final_node')
    else:
        result['selected_rule_id'] = final_node['rule_id']
        if final_node['rule_id'] in rule_ids:
            result['selected_rule_position'] = rule_ids.index(final_node['rule_id'])
        if final_node['rule_id'] in terminal_ids:
            result['terminal_rank'] = terminal_ids.index(final_node['rule_id'])
        if final_node['atom'] != problem['goal']:
            append_error(errors, 'final_goal_mismatch')
    for node in nodes.values():
        parents, rule_id = node['parents'], node['rule_id']
        if len(parents) != len(set(parents)):
            append_error(errors, 'duplicate_parent')
        if any(parent not in nodes for parent in parents):
            append_error(errors, 'missing_parent')
        if rule_id is None:
            if parents:
                append_error(errors, 'fact_with_parents')
            if node['atom'] not in problem['facts']:
                append_error(errors, 'unreachable_fact')
        else:
            rule = rules.get(rule_id)
            if rule is None:
                append_error(errors, 'unregistered_rule')
            else:
                if node['atom'] != rule['conclusion']:
                    append_error(errors, 'wrong_atom')
                if all(parent in nodes for parent in parents):
                    atoms = collections.Counter(nodes[parent]['atom'] for parent in parents)
                    if atoms != collections.Counter(rule['premises']):
                        append_error(errors, 'premise_counter_mismatch')
    topological = kahn(nodes)
    if topological is None:
        append_error(errors, 'cycle')
    result['proof_valid'] = not errors
    result['goal_reached'] = result['proof_valid']
    if result['proof_valid']:
        depths = {}
        for node_id in topological:
            node = nodes[node_id]
            depths[node_id] = (0 if node['rule_id'] is None else
                               1 + max((depths[parent] for parent in node['parents']),
                                       default=0))
        result['D'] = result['actual_D'] = depths[payload['final_node_id']]
        result['strict_valid'] = (final_ancestors(nodes, payload['final_node_id'])
                                  == set(nodes))
        if not result['strict_valid']:
            append_error(errors, 'extra_unused_node')
    else:
        result['strict_valid'] = False
    result['target_rule_match'] = bool(result['proof_valid'] and final_node is not None
                                       and final_node['rule_id'] == slot['target_rule_id'])
    result['instruction_fulfilled'] = bool(result['strict_valid']
                                            and result['target_rule_match'])
    # Logical diagnostics are a set: traversal or node-list order must not
    # affect a scientific measurement or the report's exact field comparison.
    result['errors'] = sorted(set(result['errors']))
    return result


def call_status(raw, model, http_status, transport_error):
    if http_status != 200 or transport_error is not None:
        return 'transport_error', 'transport_error', None
    try:
        envelope = load(raw)
    except (ValueError, UnicodeError):
        envelope = None
    if (isinstance(envelope, dict) and isinstance(envelope.get('model'), str)
            and envelope['model'] != model):
        return 'response_identity_error', 'response_identity_error', None
    payload = extract_payload(raw, model)
    if payload is None:
        return None, 'invalid_response', None
    return None, 'valid_payload' if schema_valid(payload) else 'invalid_payload_schema', payload


def execution_usage(calls):
    keys = ('prompt_eval_count', 'prompt_eval_cached_count', 'eval_count',
            'total_duration', 'load_duration', 'prompt_eval_duration', 'eval_duration')
    result = {'calls': len(calls)}
    for key in keys:
        values = [call[key] for call in calls]
        result[key] = sum(values) if values and all(value is not None for value in values) else None
        result[key + '_missing'] = sum(value is None for value in values)
    elapsed = [call['elapsed_ns'] / 1e6 for call in calls]
    result['http_median_ms'] = statistics.median(elapsed) if elapsed else None
    result['http_mean_ms'] = statistics.mean(elapsed) if elapsed else None
    return result


def compare_rows(a, b):
    observed = a['observed'] and b['observed']
    ma, mb = a['measurement'], b['measurement']
    ia, ib = a['role_match'], b['role_match']
    selected_a = ma['selected_rule_id'] if ma else None
    selected_b = mb['selected_rule_id'] if mb else None
    outcome = ('unobserved' if not observed else 'unmeasured'
               if ia is None or ib is None else 'both_success' if ia and ib
               else 'a_only' if ia else 'b_only' if ib else 'neither')
    return {
        'a_slot_id': a['id'], 'b_slot_id': b['id'], 'both_observed': observed,
        'both_measured': bool(observed and ia is not None and ib is not None),
        'a_success': ia, 'b_success': ib,
        'a_selected_rule_id': selected_a, 'b_selected_rule_id': selected_b,
        'a_actual_D': ma['actual_D'] if ma else None,
        'b_actual_D': mb['actual_D'] if mb else None,
        'selected_rule_changed': (selected_a != selected_b
                                  if selected_a is not None and selected_b is not None else None),
        'actual_D_changed': (ma['actual_D'] != mb['actual_D']
                             if ma and mb and ma['actual_D'] is not None
                             and mb['actual_D'] is not None else None),
        'outcome': outcome,
    }


def group_summary(rows, complete):
    seen = [trial for trial in rows if trial['observed']]
    measured = [trial for trial in seen
                if trial['measurement']['instruction_fulfilled'] is not None]

    def count(name):
        return sum(trial['measurement'][name] is True for trial in seen)

    def distribution(name):
        return dict(collections.Counter(
            str(trial['measurement'][name])
            if trial['measurement'][name] is not None else 'unmeasured'
            for trial in seen))

    return {
        'assigned_calls': len(rows), 'observed_calls': len(seen),
        'format_valid': sum(trial['measurement']['format_valid'] for trial in seen),
        'proof_valid': count('proof_valid'), 'strict_valid': count('strict_valid'),
        'goal_reached': count('goal_reached'), 'target_rule_match': count('target_rule_match'),
        'instruction_fulfilled': count('instruction_fulfilled'),
        'instruction_rate': (count('instruction_fulfilled') / len(rows)
                             if complete and len(measured) == len(rows) else None),
        'unmeasured': len(seen) - len(measured),
        'selected_rule_ids': distribution('selected_rule_id'),
        'selected_rule_positions': distribution('selected_rule_position'),
        'terminal_ranks': distribution('terminal_rank'),
        'actual_depths': distribution('actual_D'),
        'node_counts': distribution('node_count'),
        'errors': dict(collections.Counter(error for trial in seen
                                           for error in trial['measurement']['errors'])),
    }


def contrast_summary(rows, complete):
    outcomes = collections.Counter(pair['outcome'] for pair in rows)
    comparable_ids = sum(pair['selected_rule_changed'] is not None for pair in rows)
    comparable_depths = sum(pair['actual_D_changed'] is not None for pair in rows)
    measured = sum(pair['both_measured'] for pair in rows)
    return {
        'assigned_pairs': len(rows), 'observed_pairs': sum(pair['both_observed'] for pair in rows),
        'measured_pairs': measured, 'selected_rule_comparable_pairs': comparable_ids,
        'selected_rule_changed_pairs': sum(pair['selected_rule_changed'] is True for pair in rows),
        'actual_D_comparable_pairs': comparable_depths,
        'actual_D_changed_pairs': sum(pair['actual_D_changed'] is True for pair in rows),
        'both_success_and_changed_pairs': sum(
            pair['outcome'] == 'both_success' and pair['selected_rule_changed'] is True
            for pair in rows),
        'selected_rule_changed_rate': (
            sum(pair['selected_rule_changed'] is True for pair in rows) / len(rows)
            if complete and comparable_ids == len(rows) else None),
        'outcomes': {name: outcomes[name] for name in (
            'both_success', 'a_only', 'b_only', 'neither', 'unmeasured', 'unobserved')},
    }


def independent_summary(plan, trials, calls, complete):
    lookup = {(trial['seed'], trial['variant'], trial['repeat']): trial for trial in trials}
    need(len(lookup) == 40, 'independent trial key duplicates')
    pairs, repeats, seed_rows = [], [], []
    for seed in plan['seeds']:
        cells = {variant: [lookup[seed, variant, repeat] for repeat in (0, 1)]
                 for variant in VARIANTS}
        for repeat in (0, 1):
            pairs.append({'seed': seed, 'repeat': repeat,
                          **compare_rows(cells[VARIANTS[0]][repeat],
                                         cells[VARIANTS[1]][repeat])})
        for variant in VARIANTS:
            repeats.append({'seed': seed, 'variant': variant,
                            **compare_rows(cells[variant][0], cells[variant][1])})
        ordered = [cells[variant][repeat] for variant in VARIANTS for repeat in (0, 1)]
        measurements = [trial['measurement'] for trial in ordered]
        signatures = [
            (measurement['selected_rule_id'], measurement['actual_D'],
             measurement['strict_valid'], measurement['instruction_fulfilled'])
            if measurement else None for measurement in measurements
        ]
        all_strict = all(measurement is not None
                         and measurement['strict_valid'] is True
                         for measurement in measurements)
        stable = ((signatures[0] == signatures[1] and signatures[2] == signatures[3])
                  if all_strict else None)
        seed_rows.append({
            'seed': seed, 'sequence': ordered[0]['sequence'],
            'slot_ids': [trial['id'] for trial in ordered],
            'selected_rule_ids_A0_A1_B0_B1': [signature[0] if signature else None
                                               for signature in signatures],
            'actual_D_A0_A1_B0_B1': [signature[1] if signature else None
                                      for signature in signatures],
            'strict_A0_A1_B0_B1': [signature[2] if signature else None
                                    for signature in signatures],
            'instruction_A0_A1_B0_B1': [signature[3] if signature else None
                                         for signature in signatures],
            'stable_within_both': stable,
        })
    variants = {variant: group_summary(
        [trial for trial in trials if trial['variant'] == variant], complete)
        for variant in VARIANTS}
    strata = {}
    for axis in ('sequence', 'period', 'previous_variant', 'repeat_distance'):
        strata[axis] = {}
        for value in sorted({str(trial[axis]) for trial in trials}):
            strata[axis][value] = {
                variant: group_summary([trial for trial in trials
                                        if str(trial[axis]) == value
                                        and trial['variant'] == variant], complete)
                for variant in VARIANTS
                if any(str(trial[axis]) == value and trial['variant'] == variant
                       for trial in trials)
            }
    expected_depth = {'target_k03': 1, 'target_k17': 2}
    gate_trials = all(
        trial['observed'] and trial['measurement']['strict_valid'] is True
        and trial['measurement']['target_rule_match'] is True
        and trial['measurement']['actual_D'] == expected_depth[trial['variant']]
        for trial in trials)
    seed_stable = all(row['stable_within_both'] is True for row in seed_rows)
    return {
        'contract': 'v062-conditional-construction-report-r1',
        'model': plan['identities']['candidate']['model'], 'problem_id': 'K01',
        'task': 'conditional_construction', 'variants': variants, 'strata': strata,
        'pairs': pairs, 'within_variant_repeats': repeats, 'seed_rows': seed_rows,
        'cross_variant': contrast_summary(pairs, complete),
        'repeat_instability': {
            variant: contrast_summary([pair for pair in repeats
                                       if pair['variant'] == variant], complete)
            for variant in VARIANTS},
        'admission_gate_passed': (bool(gate_trials and seed_stable)
                                  if complete else None),
        'admission_gate': {
            'required_calls': 40,
            'strict_target_depth_calls': sum(
                trial['observed'] and trial['measurement']['strict_valid'] is True
                and trial['measurement']['target_rule_match'] is True
                and trial['measurement']['actual_D'] == expected_depth[trial['variant']]
                for trial in trials),
            'stable_seed_blocks': sum(row['stable_within_both'] is True
                                      for row in seed_rows),
            'expected_actual_D': expected_depth,
        },
        'assigned_calls': 40, 'unique_seed_blocks': 10, 'independent_problem_count': 1,
        'causal_effect_identified': False, 'historical_responses_are_new_observations': False,
        'policy': plan['policy'], 'unique_execution_usage': execution_usage(calls),
    }


def independent_summary_ko(report):
    lines = [
        '# v062 K01 조건부 최소 DAG 구성', '',
        f"무결성: {report['data_integrity']} / 완료: {report['data_complete']} / 호출: {report['inference_calls']}/40 / 출처: {report['evidence_kind']}", '',
        '10개 seed 블록에서 target_k03와 target_k17을 각각 두 번 관측한다. 40호출은 독립 문제 40개가 아니다.',
        '이 과제는 마지막 규칙을 외부에서 지정한 조건부 구성이다. 자유 선택, 깊이 지시 이행, A/M1/M2 또는 일반 D 제어를 측정하지 않는다.',
        '|조건|관측|형식 유효|proof 유효|strict 유효|goal|target 일치|이행|미측정|',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for variant in VARIANTS:
        group = report['variants'][variant]
        lines.append(
            f"|{variant}|{group['observed_calls']}/20|{group['format_valid']}|{group['proof_valid']}|{group['strict_valid']}|{group['goal_reached']}|{group['target_rule_match']}|{group['instruction_fulfilled']}|{group['unmeasured']}|")
    lines += [
        '', f"조건 간 선택 ID 변화: {report['cross_variant']['selected_rule_changed_pairs']}/20 대응 비교",
        f"양쪽 이행과 ID 변화 동시 충족: {report['cross_variant']['both_success_and_changed_pairs']}/20 대응 비교",
        f"사전 진입 gate: {report['admission_gate_passed']} ({report['admission_gate']['strict_target_depth_calls']}/40 strict·target·예상 D, 안정 seed {report['admission_gate']['stable_seed_blocks']}/10)",
        'strict가 아니어도 proof_valid이면 D는 실제 parents에서 계산한다. 미측정은 실패나 0으로 바꾸지 않는다.',
        'metadata와 블록 경계는 캐시 초기화를 뜻하지 않으며, 내부 기제나 일반 효과를 확정하지 않는다.', '',
        f"계획 SHA-256: {report['plan_sha256']}", f"event tip: {report['event_tip']}",
    ]
    return ('\n'.join(lines) + '\n').encode('utf-8')


def verify(bundle):
    raw_bundle = bundle.read_bytes()
    data, manifest = unpack(raw_bundle)
    need(manifest.get('contract') == 'v062-evidence-bundle-r1', 'bundle contract')
    plan = load(data['external_plan/v062.plan.json'])
    report = load(data['run/summary.json'])
    status = load(data['run/status.json'])
    run_manifest = load(data['run/run_manifest.json'])
    plan_fields = {
        'contract', 'software_version', 'created_at', 'reference', 'baseline',
        'identities', 'model_keys', 'modes', 'variants', 'target_rules',
        'schedule_seed', 'rule_order', 'boundary_cells', 'seeds', 'max_calls',
        'policy', 'slots', 'actions', 'source_fingerprint', 'request_hashes',
        'plan_sha256',
    }
    run_fields = {
        'contract', 'plan_sha256', 'source_fingerprint', 'started_at', 'python',
        'platform', 'endpoint', 'evidence_kind', 'new_model_inference',
        'max_calls', 'retry_policy', 'warmup_calls',
    }
    status_fields = {
        'state', 'complete', 'recorded_actions', 'inference_calls', 'event_tip',
        'active_action', 'failure_stage', 'failure_kind', 'failure_slot_id',
        'error', 'finished_at',
    }
    need(set(plan) == plan_fields, 'plan exact fields')
    need(set(run_manifest) == run_fields, 'run manifest exact fields')
    need(set(status) == status_fields, 'status exact fields')
    need(plan == load(data['run/plan.snapshot.json']), 'plan snapshot')
    need(plan['contract'] == 'conditional-construction-v062-r1'
         and plan['software_version'] == '0.62.0'
         and type(plan['max_calls']) is int and plan['max_calls'] == MAX_CALLS,
         'design contract/version')
    need(type(manifest.get('data_complete')) is bool, 'manifest complete type')
    need(plan['plan_sha256'] == sha(canonical(
        {key: value for key, value in plan.items() if key != 'plan_sha256'})),
        'plan hash')
    need(manifest.get('plan_sha256') == plan['plan_sha256']
         and manifest['data_complete'] is status['complete'], 'manifest state')

    baseline = data['run/baseline/v058_evidence.zip']
    need(sha(baseline) == plan['reference']['bundle_sha256'], 'baseline bytes')
    with tempfile.TemporaryDirectory(prefix='v062_independent_') as temporary:
        baseline_path = Path(temporary) / 'v058.zip'
        baseline_path.write_bytes(baseline)
        baseline_result = baseline_verify(baseline_path)
    need(baseline_result.get('complete') is True
         and baseline_result.get('differences') == []
         and type(baseline_result.get('observed_calls')) is int
         and baseline_result['observed_calls'] == 80
         and type(baseline_result.get('metadata_records')) is int
         and baseline_result['metadata_records'] == 40
         and type(baseline_result.get('compared_fields')) is int
         and baseline_result['compared_fields'] > 0
         and baseline_result.get('production_imports') is False,
         'complete independently verified 80-call baseline required')
    reference = reconstruct_reference(baseline, baseline_result)
    need(canonical(plan['reference']) == canonical(reference),
         'reference receipt reconstruction')
    need(plan['baseline'] == {'config': reference['config']}
         and plan['identities'] == reference['identities']
         and plan['seeds'] == reference['seeds'], 'inherited config/identity/seeds')
    need(plan['model_keys'] == list(MODELS) and plan['modes'] == list(MODES)
         and plan['variants'] == list(VARIANTS), 'design axes')
    need(plan['target_rules'] == TARGET_RULES
         and plan['schedule_seed'] == SCHEDULE_SEED
         and plan['rule_order'] == RULE_ORDER
         and plan['boundary_cells'] == BOUNDARY_CELLS
         and plan['policy'] == POLICY, 'frozen intervention')
    need(all(plan['policy'][key] is False for key in
             ('retry', 'repair', 'resume', 'download_models')), 'execution policy')

    slots = schedule(reference)
    frozen_actions = actions(slots)
    need(canonical(plan['slots']) == canonical(slots)
         and canonical(plan['actions']) == canonical(frozen_actions),
         'reconstructed schedule')
    request_bytes = {}
    for slot in slots:
        source = base64.b64decode(
            reference['request_bank'][slot['reference_slot_id']], validate=True)
        request_bytes[slot['id']] = transform_request(source, slot['target_rule_id'])
    expected_hashes = {slot_id: sha(raw) for slot_id, raw in request_bytes.items()}
    need(plan['request_hashes'] == expected_hashes, 'request hash plan')
    for seed in plan['seeds']:
        rows = [slot for slot in slots if slot['seed'] == seed]
        for variant in VARIANTS:
            raws = {request_bytes[slot['id']] for slot in rows
                    if slot['variant'] == variant}
            need(len(raws) == 1, 'same-condition request repeat differs')
        k03 = next(request_bytes[slot['id']] for slot in rows
                   if slot['variant'] == 'target_k03')
        k17 = next(request_bytes[slot['id']] for slot in rows
                   if slot['variant'] == 'target_k17')
        literal_03 = '지정된 마지막 규칙 id k03를 사용한다.'.encode('utf-8')
        literal_17 = '지정된 마지막 규칙 id k17를 사용한다.'.encode('utf-8')
        need(k03.count(literal_03) == 1 and literal_17 not in k03
             and k03.replace(literal_03, literal_17, 1) == k17,
             'only target-rule literal may differ between arms')

    fingerprint = plan['source_fingerprint']
    trusted = {}
    source_roots = (
        (V057_ROOT, 'v057_selection_probe'),
        (V058_ROOT, 'v058_order_replay'),
        (ROOT.parents[1] / 'v059' / 'probe', 'v059_rule_order'),
        (ROOT.parents[1] / 'v060' / 'probe', 'v060_terminal_position'),
        (ROOT.parents[1] / 'v061' / 'probe', 'v061_direction_choice'),
        (ROOT, 'v062_construction_probe'),
    )
    for source_root, logical_root in source_roots:
        need(source_root.is_dir() and not source_root.is_symlink(),
             'trusted source root')
        for path in sorted(source_root.rglob('*.py')):
            need(not path.is_symlink(), 'trusted source symlink')
            trusted[logical_root + '/' + path.relative_to(source_root).as_posix()] = sha(path.read_bytes())
    need(fingerprint == trusted, 'complete trusted source fingerprint')
    need(run_manifest['source_fingerprint'] == fingerprint
         and run_manifest['plan_sha256'] == plan['plan_sha256'], 'run binding')
    snapshot_names = {name.removeprefix('run/source_snapshot/') for name in data
                      if name.startswith('run/source_snapshot/')}
    need(snapshot_names == set(fingerprint), 'snapshot file set')
    for name, expected_hash in fingerprint.items():
        need(sha(data['run/source_snapshot/' + name]) == expected_hash,
             'snapshot bytes: ' + name)

    need(run_manifest['contract'] == 'v062-run-manifest-r1'
         and type(run_manifest['max_calls']) is int
         and run_manifest['max_calls'] == MAX_CALLS
         and run_manifest['retry_policy'] == 'none'
         and type(run_manifest['warmup_calls']) is int
         and run_manifest['warmup_calls'] == 0, 'run policy')
    endpoint = urllib.parse.urlsplit(plan['baseline']['config']['endpoint'])
    need(endpoint.scheme in ('http', 'https')
         and endpoint.hostname in ('localhost', '127.0.0.1', '::1')
         and not endpoint.username and not endpoint.password
         and not endpoint.query and not endpoint.fragment
         and endpoint.path.rstrip('/') in ('', '/api/chat'), 'source loopback endpoint')
    expected_endpoint = urllib.parse.urlunsplit((endpoint.scheme, endpoint.netloc, '', '', ''))
    need(run_manifest['endpoint'] == expected_endpoint, 'runtime endpoint binding')
    need(run_manifest['evidence_kind'] == reference['evidence_kind']
         and run_manifest['new_model_inference'] is
             (reference['evidence_kind'] != 'synthetic_fixture'), 'source label')
    need(type(status['complete']) is bool
         and status['complete'] is (status['state'] == 'complete'), 'state/complete')
    need(status['state'] in ('complete', 'incomplete', 'interrupted'), 'finished state')
    for key in ('inference_calls', 'recorded_actions'):
        need(type(status[key]) is int and status[key] >= 0, 'status count type')

    lines = data['run/events.jsonl'].splitlines()
    need(all(line.strip() for line in lines), 'blank event')
    events = [load(line) for line in lines]
    need(len(events) == status['recorded_actions'] and len(events) <= 60,
         'action count')
    trials = report['trials']
    need(len(trials) == 40 and [trial['id'] for trial in trials]
         == [slot['id'] for slot in slots], 'report trial order/duplicates')
    stored = {trial['id']: trial for trial in trials}
    fields = 0

    def eq(label, stored_value, independent_value):
        nonlocal fields
        fields += 1
        need(canonical(stored_value) == canonical(independent_value),
             'independent mismatch: ' + label)

    expected_files = {
        'external_plan/v062.plan.json', 'run/plan.snapshot.json',
        'run/run_manifest.json', 'run/status.json', 'run/events.jsonl',
        'run/baseline/v058_evidence.zip', 'run/summary.json', 'run/audit.json',
        'run/summary.ko.md',
    }
    expected_files |= {'run/source_snapshot/' + name for name in fingerprint}
    observed = {}
    tip = plan['plan_sha256']
    failed = None
    metadata_count = 0
    call_rows = []
    independent_calls = []
    measurement_fields = {
        'kind', 'format_valid', 'proof_valid', 'strict_valid', 'D', 'actual_D',
        'selected_rule_id', 'selected_rule_position', 'terminal_rank', 'goal_reached',
        'target_rule_match', 'instruction_fulfilled', 'node_count', 'errors',
    }
    for index, event in enumerate(events):
        action = frozen_actions[index]
        event_fields = {'action', 'at', 'previous_hash', 'event_hash'}
        event_fields |= ({'metadata_sha256'} if action['kind'] == 'metadata' else
                         {'request_sha256', 'response_sha256', 'http_status',
                          'transport_error', 'elapsed_ns'})
        need(set(event) == event_fields, 'event exact fields')
        need(canonical(event['action']) == canonical(action)
             and event['previous_hash'] == tip, 'action order/hash link')
        need(event['event_hash'] == sha(canonical(
            {key: value for key, value in event.items() if key != 'event_hash'})),
            'event hash')
        tip = event['event_hash']
        failure = None
        if action['kind'] == 'metadata':
            name = f"run/metadata/{action['id']}.json"
            expected_files.add(name)
            need(sha(data[name]) == event['metadata_sha256'], 'metadata bytes')
            failure = prior_metadata(load(data[name]),
                                     plan['identities'][action['model_key']])
            metadata_count += 1
        else:
            slot = action['slot']
            slot_id = slot['id']
            request_name = f'run/calls/{slot_id}/request.wire.json'
            response_name = f'run/calls/{slot_id}/response.raw.json'
            expected_files.update((request_name, response_name))
            request_raw = data[request_name]
            response_raw = data[response_name]
            need(request_raw == request_bytes[slot_id], 'exact transformed request')
            need(sha(request_raw) == event['request_sha256']
                 and sha(response_raw) == event['response_sha256'], 'call bytes')
            need(type(event['http_status']) is int
                 and 0 <= event['http_status'] <= 599
                 and type(event['elapsed_ns']) is int
                 and event['elapsed_ns'] >= 0, 'HTTP fields')
            need(event['transport_error'] is None
                 or isinstance(event['transport_error'], str), 'transport field')
            request = load(request_raw)
            need(request.get('model') == plan['identities']['candidate']['model']
                 and request.get('options', {}).get('seed') == slot['seed'],
                 'request model/seed')
            problem = load(request['messages'][0]['content'].rsplit(
                '\n\nproblem: ', 1)[1].encode('utf-8'))
            need(problem['id'] == 'K01'
                 and [rule['id'] for rule in problem['rules']] == RULE_ORDER,
                 'request problem/order')
            failure, record_status, payload = call_status(
                response_raw, plan['identities']['candidate']['model'],
                event['http_status'], event['transport_error'])
            measurement = independent_measure(problem, payload, slot)
            trial = stored[slot_id]
            need(set(trial['measurement']) == measurement_fields,
                 'measurement exact fields')
            eq(slot_id + '/slot', {key: trial[key] for key in slot}, slot)
            for key in measurement_fields - {'errors'}:
                eq(slot_id + '/' + key, trial['measurement'][key], measurement[key])
            if measurement['format_valid']:
                eq(slot_id + '/errors', trial['measurement']['errors'], measurement['errors'])
            else:
                need(isinstance(trial['measurement']['errors'], list)
                     and all(isinstance(value, str) for value in trial['measurement']['errors']),
                     'format diagnostic type')
            eq(slot_id + '/role_match', trial['role_match'],
               measurement['instruction_fulfilled'])
            eq(slot_id + '/observed', trial['observed'], True)
            eq(slot_id + '/status', trial['status'], record_status)
            need(trial['parse_error'] is None or isinstance(trial['parse_error'], str),
                 'parse error type')
            if record_status in ('valid_payload', 'transport_error',
                                 'response_identity_error'):
                eq(slot_id + '/parse_error', trial['parse_error'], None)
            observed[slot_id] = {**slot, 'observed': True,
                                 'measurement': measurement,
                                 'role_match': measurement['instruction_fulfilled'],
                                 'status': record_status,
                                 'parse_error': trial['parse_error']}
            call_rows.append(slot_id)
            try:
                envelope = load(response_raw)
            except (ValueError, UnicodeError):
                envelope = {}
            if not isinstance(envelope, dict):
                envelope = {}
            usage_keys = ('prompt_eval_count', 'prompt_eval_cached_count', 'eval_count',
                          'total_duration', 'load_duration', 'prompt_eval_duration',
                          'eval_duration')
            cost = {key: envelope[key]
                    if type(envelope.get(key)) is int and envelope[key] >= 0 else None
                    for key in usage_keys}
            cost.update(done=envelope.get('done')
                        if type(envelope.get('done')) is bool else None,
                        done_reason=envelope.get('done_reason')
                        if isinstance(envelope.get('done_reason'), str) else None)
            current = {**slot, 'http_status': event['http_status'],
                       'elapsed_ns': event['elapsed_ns'],
                       'request_sha256': sha(request_raw),
                       'response_sha256': sha(response_raw), **cost}
            eq('call raw-derived metadata', report['calls'][len(independent_calls)], current)
            independent_calls.append(current)
        if failure:
            need(index == len(events) - 1 and not status['complete'],
                 'continue after failure')
            failed = (action, failure)

    need(tip == status['event_tip'] == report['event_tip'], 'event tip')
    if status['complete']:
        need(len(events) == 60 and len(observed) == 40
             and metadata_count == 20 and status['inference_calls'] == 40,
             'complete counts')
        need(status['active_action'] is None
             and all(status[key] is None for key in
                     ('failure_stage', 'failure_kind', 'failure_slot_id', 'error')),
             'complete failure fields')
    else:
        need(isinstance(status['error'], str) and bool(status['error']), 'failure reason')
        need(len(observed) <= status['inference_calls'] <= len(observed) + 1,
             'partial call count')
        if failed:
            action, failure = failed
            need(status['failure_kind'] == failure
                 and status['failure_slot_id'] == action['id']
                 and status['failure_stage'] == action['kind']
                 and status['active_action'] == action['index']
                 and status['inference_calls'] == len(observed), 'recorded failure binding')
        else:
            need(len(events) < 60
                 and status['failure_kind'] in ('execution_error', 'user_interrupt'),
                 'unrecorded failure')
            action = frozen_actions[len(events)]
            need(status['active_action'] == action['index']
                 and status['failure_slot_id'] == action['id']
                 and status['failure_stage'] == action['kind'], 'pending action')
            if action['kind'] == 'call':
                name = f"run/calls/{action['id']}/request.wire.json"
                if name in data:
                    need(data[name] == request_bytes[action['id']], 'pending request')
                    expected_files.add(name)
            else:
                need(status['inference_calls'] == len(observed),
                     'metadata not inference')
    need(set(data) == expected_files, 'unexpected/missing evidence files')
    eq('call order/duplicates', [call['id'] for call in report['calls']], call_rows)

    independent_trials = []
    for slot in slots:
        if slot['id'] in observed:
            independent_trials.append(observed[slot['id']])
        else:
            expected = {**slot, 'observed': False, 'measurement': None,
                        'role_match': None, 'status': 'unexecuted', 'parse_error': None}
            eq(slot['id'] + '/unobserved', stored[slot['id']], expected)
            independent_trials.append(expected)

    summary = independent_summary(plan, independent_trials, independent_calls,
                                  status['complete'])
    for key, value in summary.items():
        eq('report/' + key, report[key], value)
    report_fields = set(summary) | {
        'data_integrity', 'data_complete', 'comparative_analysis_ready',
        'evidence_kind', 'new_model_inference', 'inference_calls',
        'max_inference_calls', 'plan_sha256', 'event_tip', 'run_state', 'run_error',
        'failure_stage', 'failure_kind', 'failure_slot_id', 'trials', 'calls',
        'source_fingerprint', 'reference_bundle_sha256',
    }
    need(set(report) == report_fields, 'report exact fields')
    for key, value in {
        'data_integrity': True,
        'data_complete': status['complete'],
        'comparative_analysis_ready': status['complete'],
        'evidence_kind': run_manifest['evidence_kind'],
        'new_model_inference': run_manifest['new_model_inference'],
        'inference_calls': status['inference_calls'], 'max_inference_calls': 40,
        'plan_sha256': plan['plan_sha256'], 'event_tip': tip,
        'run_state': status['state'], 'run_error': status['error'],
        'failure_stage': status['failure_stage'], 'failure_kind': status['failure_kind'],
        'failure_slot_id': status['failure_slot_id'], 'trials': trials,
        'calls': report['calls'], 'source_fingerprint': fingerprint,
        'reference_bundle_sha256': sha(baseline),
    }.items():
        eq('report/' + key, report[key], value)
    eq('report/trials', report['trials'], independent_trials)
    eq('report/calls', report['calls'], independent_calls)

    human_report = {
        **summary, 'data_integrity': True, 'data_complete': status['complete'],
        'inference_calls': status['inference_calls'],
        'evidence_kind': run_manifest['evidence_kind'],
        'plan_sha256': plan['plan_sha256'], 'event_tip': tip,
    }
    need(data['run/summary.ko.md'] == independent_summary_ko(human_report),
         'independent mismatch: Korean summary exact UTF-8/LF bytes')
    audit = load(data['run/audit.json'])
    audit_keys = (
        'contract', 'data_integrity', 'data_complete', 'comparative_analysis_ready',
        'inference_calls', 'max_inference_calls', 'plan_sha256', 'event_tip',
        'run_state', 'failure_stage', 'failure_kind', 'failure_slot_id', 'run_error',
    )
    eq('audit summary', audit, {key: report[key] for key in audit_keys})
    return {
        'contract': 'independent-v062-r1', 'bundle_sha256': sha(raw_bundle),
        'complete': status['complete'], 'observed_calls': len(observed),
        'metadata_records': metadata_count, 'compared_fields': fields,
        'differences': [], 'production_imports': False,
        'baseline_compared_fields': baseline_result['compared_fields'],
        'limitation': ('원문·계획·측정 일관성 검산이며 외부 실행 인증, 자유 선택, '
                       'A/M 제어 또는 내부 기제의 인과 검증은 아니다.'),
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('--out', type=Path)
    arguments = parser.parse_args()
    result = verify(arguments.bundle)
    output = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    if arguments.out:
        with arguments.out.open('x', encoding='utf-8', newline='\n') as handle:
            handle.write(output)
    print(output)
