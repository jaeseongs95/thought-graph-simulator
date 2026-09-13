"""v060 ZIP을 생산 요청·채점·집계 모듈 import 없이 독립 검산한다."""
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
V058_ROOT = ROOT.parents[1] / 'v058' / 'probe'
V057_ROOT = ROOT.parents[1] / 'v057' / 'probe'
sys.path.insert(0, str(V058_ROOT / 'tools'))
from verify_v058 import verify as baseline_verify, metadata as prior_metadata
from independent_graph_forensic import need, load, canonical, sha, extract_payload
from independent_verify_v057 import problem_depths

MODELS = ('candidate',)
MODES = ('choice',)
VARIANTS = ('deep_first', 'shallow_first')
SCHEDULE_SEED = 6002026
MAX_CALLS = 40
RULE_ORDERS = {'deep_first': ['k17', 'k03', 'k10'],
               'shallow_first': ['k03', 'k17', 'k10']}
SOURCE_RULE_ORDER = ['k10', 'k17', 'k03']
BOUNDARY_CELLS = {
    'candidate': {'problem_id': 'K01', 'arm': 'original', 'direction': 'shallow'},
}
POLICY = {
    'question': 'Distinguish first-terminal from absolute-second selection in Gemma K01 shallow terminal-rule choice.',
    'intervention': 'Put k10 last and swap only k17/k03; preserve every rule, ID, fact, goal, prompt, schema and option.',
    'sampling': 'All 10 historical seeds; four dependent observations per seed, not 40 independent problems.',
    'schedule': 'SHA256-ranked seeds; five ABBA and five BAAB blocks, frozen schedule_seed=6002026.',
    'history': 'No state reset. Same-condition repeat distance and preceding calls remain possible explanations.',
    'interpretation': 'The two frozen hypotheses make opposite joint predictions; k10 postposition and broader position heuristics remain alternatives.',
    'measurement': 'Choice ID, overall position, terminal rank, reachable choice and instruction fulfillment are separate; implied_depth is not actual proof D.',
    'missing': 'Unobserved and unmeasured remain null; full rates require complete measured denominators.',
    'retry': False, 'repair': False, 'resume': False, 'download_models': False,
    'budget': '40 inference calls and 20 metadata records; no warmup.',
}


def unpack(raw):
    """Read a bounded, regular ZIP and verify its complete byte manifest."""
    need(len(raw) <= 100 * 1024**2, 'archive size')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        need(0 < len(infos) <= 12000
             and sum(item.file_size for item in infos) <= 256 * 1024**2,
             'archive expansion')
        seen = set()
        reserved = {'CON', 'PRN', 'AUX', 'NUL', 'CLOCK$', 'CONIN$', 'CONOUT$'}
        reserved |= {prefix + str(i) for prefix in ('COM', 'LPT') for i in range(1, 10)}
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
                     and not any(ord(c) < 32 or c in '<>"|?*' for c in part)
                     for part in path.parts), 'Windows path')
            need(((item.external_attr >> 16) & 0o170000) != 0o120000
                 and not item.flag_bits & 1, 'archive link/encryption')
            limit = 8 * 1024**2
            if name in ('external_plan/v060.plan.json', 'run/plan.snapshot.json'):
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
    raw = f'{SCHEDULE_SEED}:{purpose}:{seed}'.encode('ascii')
    return hashlib.sha256(raw).hexdigest()


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
            slot = {**base,
                    'id': f'b{block:02d}_p{period}_{variant}_r{repeat}',
                    'reference_slot_id': old['id'], 'task': 'rule_order',
                    'stage': 'choice', 'position': len(result), 'block': block,
                    'period': period, 'seed_index': seeds.index(seed),
                    'variant': variant, 'repeat': repeat, 'sequence': sequence,
                    'previous_call_id': previous['id'] if previous else None,
                    'previous_variant': previous['variant'] if previous else None,
                    'previous_same_variant_slot_id': previous_same_id,
                    'repeat_distance': distance}
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


def transform_request(raw, variant):
    """Reconstruct the one allowed rule-array byte edit without reserializing."""
    need(variant in VARIANTS, 'unknown variant')
    request = load(raw)
    need(isinstance(request, dict) and isinstance(request.get('messages'), list)
         and len(request['messages']) == 1
         and set(request['messages'][0]) == {'role', 'content'}
         and request['messages'][0]['role'] == 'user', 'one merged user message')
    text = request['messages'][0]['content']
    need(isinstance(text, str) and text.count('\n\nproblem: ') == 1,
         'problem boundary')
    prefix, problem_text = text.rsplit('\n\nproblem: ', 1)
    problem = load(problem_text.encode('utf-8'))
    need(problem.get('id') == 'K01'
         and [rule.get('id') for rule in problem.get('rules', [])]
         == SOURCE_RULE_ORDER, 'source rule order')
    encode = lambda obj: json.dumps(obj, ensure_ascii=False, separators=(',', ':'),
                                    allow_nan=False)
    old_rules = encode(problem['rules'])
    by_id = {rule['id']: rule for rule in problem['rules']}
    need(len(by_id) == 3, 'source rule IDs')
    new_rules = encode([by_id[rule_id] for rule_id in RULE_ORDERS[variant]])
    old_span = encode(old_rules)[1:-1].encode('utf-8')
    new_span = encode(new_rules)[1:-1].encode('utf-8')
    need(raw.count(old_span) == 1 and problem_text.count(old_rules) == 1,
         'unique rules byte span')
    output = raw.replace(old_span, new_span, 1)
    got = load(output)
    expected = json.loads(json.dumps(request, ensure_ascii=False))
    expected['messages'][0]['content'] = (prefix + '\n\nproblem: '
        + problem_text.replace(old_rules, new_rules, 1))
    need(canonical(got) == canonical(expected), 'unintended request change')
    return output


def reconstruct_reference(baseline, baseline_result):
    """Derive the v060 receipt from the verified raw v058 archive."""
    with zipfile.ZipFile(io.BytesIO(baseline)) as archive:
        names = archive.namelist()
        need(len(names) == len(set(names)), 'nested duplicate ZIP member')
        bp = load(archive.read('external_plan/v058.plan.json'))
        br = load(archive.read('run/summary.json'))
        candidates = [slot for slot in bp['slots']
                      if slot['model_key'] == 'candidate'
                      and slot['mode'] == 'choice'
                      and slot['sequence'] == 'graph_choice'
                      and all(slot[key] == value
                              for key, value in BOUNDARY_CELLS['candidate'].items())]
        need(len(candidates) == 10 and {slot['seed'] for slot in candidates}
             == set(bp['seeds']), 'v058 source choice cells')
        opposite = {(slot['seed'], slot['sequence']): slot for slot in bp['slots']
                    if slot['model_key'] == 'candidate' and slot['mode'] == 'choice'
                    and all(slot[key] == value
                            for key, value in BOUNDARY_CELLS['candidate'].items())}
        request_bank = {}
        for slot in candidates:
            source_name = f"run/calls/{slot['id']}/request.wire.json"
            raw = archive.read(source_name)
            other = opposite.get((slot['seed'], 'choice_graph'))
            need(other is not None, 'opposite sequence source absent')
            other_raw = archive.read(f"run/calls/{other['id']}/request.wire.json")
            need(raw == other_raw, 'opposite sequence request differs')
            transform_request(raw, 'deep_first')
            transform_request(raw, 'shallow_first')
            request_bank[slot['id']] = base64.b64encode(raw).decode('ascii')
    reference = {
        'contract': 'audited-v058-choice-r1',
        'bundle_sha256': sha(baseline),
        'plan_sha256': bp['plan_sha256'],
        'event_tip': br['event_tip'],
        'recorded_calls': 80,
        'selected_calls': 10,
        'evidence_kind': br['evidence_kind'],
        'config': bp['baseline']['config'],
        'identities': {'candidate': bp['identities']['candidate']},
        'seeds': bp['seeds'],
        'slots': candidates,
        'request_bank': request_bank,
        'independent_compared_fields': baseline_result['compared_fields'],
    }
    reference['receipt_sha256'] = sha(canonical(reference))
    return reference, bp


def independent_measure(problem, payload):
    """Measure a terminal-rule choice without importing a production scorer."""
    result = {'kind': 'terminal_rule_choice', 'format_valid': False,
              'choice_valid': None, 'selected_rule_id': None,
              'implied_depth': None, 'proof_valid': None,
              'strict_valid': None, 'D': None, 'errors': [],
              'selected_rule_position': None, 'actual_D': None,
              'goal_reachable_choice': None, 'instruction_fulfilled': None,
              'terminal_rank': None, 'shallow_success': None}
    valid_shape = (isinstance(payload, dict) and set(payload) == {'final_rule_id'}
                   and isinstance(payload['final_rule_id'], str)
                   and 1 <= len(payload['final_rule_id']) <= 128)
    if not valid_shape:
        if payload is not None:
            result['errors'] = ['invalid_payload_schema']
        return result
    result['format_valid'] = True
    rule_id = payload['final_rule_id']
    result['selected_rule_id'] = rule_id
    rules = problem['rules']
    ids = [rule['id'] for rule in rules]
    if rule_id in ids:
        result['selected_rule_position'] = ids.index(rule_id)
    by_id = {rule['id']: rule for rule in rules}
    result['choice_valid'] = False
    if rule_id not in by_id:
        result['errors'] = ['unknown_rule']
    elif by_id[rule_id]['conclusion'] != problem['goal']:
        result['errors'] = ['not_goal_concluding_rule']
    else:
        depths = problem_depths(problem)
        if rule_id not in depths:
            result['errors'] = ['unreachable_terminal_rule']
        else:
            result['choice_valid'] = True
            result['implied_depth'] = depths[rule_id]
    result['goal_reachable_choice'] = result['choice_valid']
    terminals = [r['id'] for r in rules if r['conclusion'] == problem['goal']]
    result['terminal_rank'] = terminals.index(rule_id) if rule_id in terminals else None
    depths = problem_depths(problem)
    result['shallow_success'] = bool(result['choice_valid'] is True
                                     and result['implied_depth'] == min(depths.values()))
    result['instruction_fulfilled'] = result['shallow_success']
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
    valid = (set(payload) == {'final_rule_id'}
             and isinstance(payload['final_rule_id'], str)
             and 1 <= len(payload['final_rule_id']) <= 128)
    return None, 'valid_payload' if valid else 'invalid_payload_schema', payload


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
    success_a, success_b = a['role_match'], b['role_match']
    rule_a = ma['selected_rule_id'] if ma else None
    rule_b = mb['selected_rule_id'] if mb else None
    outcome = ('unobserved' if not observed else
               'unmeasured' if success_a is None or success_b is None else
               'both_success' if success_a and success_b else
               'a_only' if success_a else 'b_only' if success_b else 'neither')
    return {'a_slot_id': a['id'], 'b_slot_id': b['id'],
            'both_observed': observed,
            'both_measured': bool(observed and success_a is not None and success_b is not None),
            'a_success': success_a, 'b_success': success_b,
            'a_selected_rule_id': rule_a, 'b_selected_rule_id': rule_b,
            'selected_rule_changed': rule_a != rule_b
                if rule_a is not None and rule_b is not None else None,
            'outcome': outcome,
            'b_minus_a': int(success_b) - int(success_a)
                if success_a is not None and success_b is not None else None}


def independent_summary(plan, trials, calls, complete):
    lookup = {(trial['seed'], trial['variant'], trial['repeat']): trial
              for trial in trials}
    need(len(lookup) == 40, 'independent trial key duplicates')
    pairs, repeats, seed_rows = [], [], []
    for seed in plan['seeds']:
        for repeat in (0, 1):
            a, b = (lookup[seed, variant, repeat] for variant in VARIANTS)
            pairs.append({'seed': seed, 'repeat': repeat, **compare_rows(a, b)})
        for variant in VARIANTS:
            a, b = (lookup[seed, variant, repeat] for repeat in (0, 1))
            repeats.append({'seed': seed, 'variant': variant, **compare_rows(a, b)})
        rows = [lookup[seed, variant, repeat]
                for variant in VARIANTS for repeat in (0, 1)]
        matches = [row['role_match'] for row in rows]
        selected = [row['measurement']['selected_rule_id']
                    if row['measurement'] else None for row in rows]
        seed_rows.append({
            'seed': seed, 'sequence': rows[0]['sequence'],
            'slot_ids': [row['id'] for row in rows],
            'selected_rule_ids_A0_A1_B0_B1': selected,
            'shallow_A0_A1_B0_B1': matches,
            'mean_B_minus_A': ((sum(matches[2:]) - sum(matches[:2])) / 2
                               if all(value is not None for value in matches) else None),
            'stable_within_both': ((selected[0] == selected[1]
                                    and selected[2] == selected[3])
                                   if all(value is not None for value in selected) else None),
        })

    def contrast_summary(rows):
        counts = collections.Counter(row['outcome'] for row in rows)
        count = len(rows)
        comparable = sum(row['selected_rule_changed'] is not None for row in rows)
        measured = sum(row['both_measured'] for row in rows)
        changes = sum(row['selected_rule_changed'] is True for row in rows)
        return {'assigned_pairs': count,
                'observed_pairs': sum(row['both_observed'] for row in rows),
                'measured_pairs': measured,
                'selected_rule_comparable_pairs': comparable,
                'selected_rule_changed_pairs': changes,
                'selected_rule_changed_rate': changes / count
                    if complete and comparable == count else None,
                'outcomes': {key: counts[key] for key in
                    ('both_success', 'a_only', 'b_only', 'neither',
                     'unmeasured', 'unobserved')},
                'mean_b_minus_a': (sum(row['b_minus_a'] for row in rows) / count
                    if complete and measured == count else None)}

    def group(rows):
        seen = [row for row in rows if row['observed']]
        measured = sum(row['role_match'] is not None for row in seen)
        success = sum(row['role_match'] is True for row in seen)
        return {'assigned_calls': len(rows), 'observed_calls': len(seen),
                'format_valid': sum(row['measurement']['format_valid'] for row in seen),
                'choice_valid': sum(row['measurement']['choice_valid'] is True for row in seen),
                'goal_reachable_choice': sum(row['measurement']['goal_reachable_choice'] is True for row in seen),
                'shallow_success': success, 'unmeasured': len(seen) - measured,
                'instruction_fulfilled': sum(row['measurement']['instruction_fulfilled'] is True for row in seen),
                'selected_rule_positions': dict(collections.Counter(
                    str(row['measurement']['selected_rule_position']) if row['measurement']['selected_rule_position'] is not None else 'unmeasured' for row in seen)),
                'terminal_ranks': dict(collections.Counter(
                    str(row['measurement']['terminal_rank']) if row['measurement']['terminal_rank'] is not None else 'unmeasured' for row in seen)),
                'shallow_rate': success / len(rows)
                    if complete and measured == len(rows) else None,
                'selected_rule_ids': dict(collections.Counter(
                    row['measurement']['selected_rule_id'] or 'unmeasured' for row in seen)),
                'implied_depths': dict(collections.Counter(
                    str(row['measurement']['implied_depth'])
                    if row['measurement']['implied_depth'] is not None else 'unmeasured'
                    for row in seen))}

    variants = {variant: group([row for row in trials if row['variant'] == variant])
                for variant in VARIANTS}
    strata = {}
    for axis in ('sequence', 'period', 'previous_variant', 'repeat_distance'):
        values = sorted({str(row[axis]) for row in trials})
        strata[axis] = {
            value: {variant: group([row for row in trials
                                    if str(row[axis]) == value
                                    and row['variant'] == variant])
                    for variant in VARIANTS
                    if any(str(row[axis]) == value and row['variant'] == variant
                           for row in trials)}
            for value in values}
    diffs = [row['mean_B_minus_A'] for row in seed_rows]
    return {'contract': 'v060-terminal-position-report-r1',
            'model': plan['identities']['candidate']['model'], 'problem_id': 'K01',
            'variants': variants, 'strata': strata, 'pairs': pairs,
            'within_variant_repeats': repeats, 'seed_rows': seed_rows,
            'cross_variant': contrast_summary(pairs),
            'repeat_instability': {variant: contrast_summary(
                [row for row in repeats if row['variant'] == variant])
                for variant in VARIANTS},
            'seed_mean_B_minus_A': sum(diffs) / 10
                if complete and all(value is not None for value in diffs) else None,
            'assigned_calls': 40, 'unique_seed_blocks': 10,
            'independent_problem_count': 1, 'actual_D': None,
            'selective_D_control': None, 'causal_effect_identified': False,
            'historical_responses_are_new_observations': False,
            'policy': plan['policy'], 'unique_execution_usage': execution_usage(calls)}


def independent_summary_ko(report):
    """Render the frozen human-readable contract from independently computed data."""
    lines = [
        '# v060 K01 terminal 위치 진단', '',
        f"무결성: {report['data_integrity']} / 완료: {report['data_complete']} / 호출: {report['inference_calls']}/40 / 출처: {report['evidence_kind']}", '',
        '10개 seed 블록에서 각 조건을 두 번 관측한다. 40호출은 독립 문제 40개가 아니다.',
        '선택 규칙의 implied_depth는 실제 생성 증명의 D가 아니다. 선택 ID·전체 위치·terminal 순위·goal 도달성·shallow 지시 이행을 분리한다.',
        '두 배열은 first-terminal과 absolute-second 가설에 반대 예측을 주지만 k10 후치, 캐시와 더 넓은 위치 기제는 식별하지 못한다.', '',
        '|조건|관측|형식 유효|goal 도달 선택|지시 이행|미측정|',
        '|---|---:|---:|---:|---:|---:|',
    ]
    for variant in VARIANTS:
        group = report['variants'][variant]
        lines.append(f"|{variant}|{group['observed_calls']}/20|{group['format_valid']}|{group['goal_reachable_choice']}|{group['instruction_fulfilled']}|{group['unmeasured']}|")
    lines.append('')
    for variant in VARIANTS:
        group = report['variants'][variant]
        lines.append(f"선택 위치 {variant}: {group['selected_rule_positions']} / terminal 순위: {group['terminal_ranks']}")
        lines.append('')
    lines.extend([
        f"seed별 평균 B−A: {report['seed_mean_B_minus_A']}",
        f"조건 간 선택 ID 변화: {report['cross_variant']['selected_rule_changed_pairs']}/20 대응 비교",
        '위 20개 비교는 seed 10개에 중첩된다. 조건별 반복 불일치와 sequence/period/직전 조건/반복 간격별 표는 summary.json에서 함께 확인한다.',
        '미완료이거나 해당 비교에 미측정이 있으면 전체 비율은 null이다. metadata는 캐시 초기화가 아니며 첫 호출도 과거 이력을 가질 수 있다.', '',
        f"계획 SHA-256: {report['plan_sha256']}", f"event tip: {report['event_tip']}",
    ])
    return ('\n'.join(lines) + '\n').encode('utf-8')


def verify(bundle):
    raw_bundle = bundle.read_bytes()
    data, manifest = unpack(raw_bundle)
    need(manifest.get('contract') == 'v060-evidence-bundle-r1', 'bundle contract')
    plan = load(data['external_plan/v060.plan.json'])
    report = load(data['run/summary.json'])
    status = load(data['run/status.json'])
    run_manifest = load(data['run/run_manifest.json'])
    plan_fields = {'contract', 'software_version', 'created_at', 'reference', 'baseline',
                   'identities', 'model_keys', 'modes', 'variants', 'schedule_seed',
                   'rule_orders', 'boundary_cells', 'seeds', 'max_calls', 'policy',
                   'slots', 'actions', 'source_fingerprint', 'request_hashes',
                   'plan_sha256'}
    run_fields = {'contract', 'plan_sha256', 'source_fingerprint', 'started_at',
                  'python', 'platform', 'endpoint', 'evidence_kind',
                  'new_model_inference', 'max_calls', 'retry_policy', 'warmup_calls'}
    status_fields = {'state', 'complete', 'recorded_actions', 'inference_calls',
                     'event_tip', 'active_action', 'failure_stage', 'failure_kind',
                     'failure_slot_id', 'error', 'finished_at'}
    need(set(plan) == plan_fields, 'plan exact fields')
    need(set(run_manifest) == run_fields, 'run manifest exact fields')
    need(set(status) == status_fields, 'status exact fields')
    need(plan == load(data['run/plan.snapshot.json']), 'plan snapshot')
    need(plan['contract'] == 'rule-order-v060-r1'
         and plan['software_version'] == '0.60.0'
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
    with tempfile.TemporaryDirectory(prefix='v060_independent_') as temporary:
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
    reference, baseline_plan = reconstruct_reference(baseline, baseline_result)
    need(canonical(plan['reference']) == canonical(reference),
         'reference receipt reconstruction')
    need(plan['baseline'] == {'config': reference['config']}
         and plan['identities'] == reference['identities']
         and plan['seeds'] == reference['seeds'], 'inherited config/identity/seeds')
    need(plan['model_keys'] == list(MODELS) and plan['modes'] == list(MODES)
         and plan['variants'] == list(VARIANTS), 'design axes')
    need(type(plan['schedule_seed']) is int
         and plan['schedule_seed'] == SCHEDULE_SEED, 'schedule seed')
    need(plan['rule_orders'] == RULE_ORDERS
         and plan['boundary_cells'] == BOUNDARY_CELLS, 'intervention definition')
    need(plan['policy'] == POLICY, 'frozen policy')
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
        expected = transform_request(source, slot['variant'])
        request_bytes[slot['id']] = expected
    expected_hashes = {slot_id: sha(raw) for slot_id, raw in request_bytes.items()}
    need(plan['request_hashes'] == expected_hashes, 'request hash plan')
    for seed in plan['seeds']:
        rows = [slot for slot in slots if slot['seed'] == seed]
        for variant in VARIANTS:
            raws = {request_bytes[slot['id']] for slot in rows
                    if slot['variant'] == variant}
            need(len(raws) == 1, 'same-condition request repeat differs')
        source = next(request_bytes[slot['id']] for slot in rows
                      if slot['variant'] == 'deep_first')
        changed = next(request_bytes[slot['id']] for slot in rows
                       if slot['variant'] == 'shallow_first')
        need(source != changed, 'variant request bytes equal')

    fingerprint = plan['source_fingerprint']
    trusted = {}
    for source_root, logical_root in ((V057_ROOT, 'v057_selection_probe'),
                                      (V058_ROOT, 'v058_order_replay'),
                                      (ROOT.parents[1] / 'v059' / 'probe', 'v059_rule_order'),
                                      (ROOT, 'v060_terminal_position')):
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

    need(run_manifest['contract'] == 'v060-run-manifest-r1'
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

    expected_files = {'external_plan/v060.plan.json', 'run/plan.snapshot.json',
                      'run/run_manifest.json', 'run/status.json', 'run/events.jsonl',
                      'run/baseline/v058_evidence.zip', 'run/summary.json',
                      'run/audit.json', 'run/summary.ko.md'}
    expected_files |= {'run/source_snapshot/' + name for name in fingerprint}
    observed = {}
    tip = plan['plan_sha256']
    failed = None
    metadata_count = 0
    call_rows = []
    independent_calls = []
    measurement_fields = {'kind', 'format_valid', 'choice_valid', 'selected_rule_id',
                          'implied_depth', 'proof_valid', 'strict_valid', 'D', 'errors',
                          'selected_rule_position', 'actual_D', 'goal_reachable_choice', 'instruction_fulfilled', 'terminal_rank',
                          'shallow_success'}
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
                 and [rule['id'] for rule in problem['rules']] == RULE_ORDERS[slot['variant']],
                 'request problem/order')
            failure, record_status, payload = call_status(
                response_raw, plan['identities']['candidate']['model'],
                event['http_status'], event['transport_error'])
            measurement = independent_measure(problem, payload)
            trial = stored[slot_id]
            need(set(trial['measurement']) == measurement_fields,
                 'measurement exact fields')
            eq(slot_id + '/slot', {key: trial[key] for key in slot}, slot)
            for key in ('kind', 'format_valid', 'choice_valid', 'selected_rule_id',
                        'selected_rule_position', 'implied_depth', 'actual_D',
                        'proof_valid', 'strict_valid', 'D', 'goal_reachable_choice', 'instruction_fulfilled', 'terminal_rank',
                        'shallow_success'):
                eq(slot_id + '/' + key, trial['measurement'][key], measurement[key])
            if measurement['format_valid']:
                eq(slot_id + '/errors', trial['measurement']['errors'],
                   measurement['errors'])
            else:
                need(isinstance(trial['measurement']['errors'], list)
                     and all(isinstance(value, str)
                             for value in trial['measurement']['errors']),
                     'measurement error type')
                # Schema-library diagnostic prose is not a scientific measure.
                # Keep it for exact report reconstruction after independently
                # checking every semantic field and the diagnostic value type.
                measurement['errors'] = trial['measurement']['errors']
            eq(slot_id + '/role_match', trial['role_match'],
               measurement['shallow_success'])
            eq(slot_id + '/observed', trial['observed'], True)
            eq(slot_id + '/status', trial['status'], record_status)
            need(trial['parse_error'] is None
                 or isinstance(trial['parse_error'], str), 'parse error type')
            if record_status in ('valid_payload', 'transport_error',
                                 'response_identity_error'):
                eq(slot_id + '/parse_error', trial['parse_error'], None)
            observed[slot_id] = {**slot, 'observed': True,
                                 'measurement': measurement,
                                 'role_match': measurement['shallow_success'],
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
            eq('call raw-derived metadata', report['calls'][len(independent_calls)],
               current)
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
        need(isinstance(status['error'], str) and bool(status['error']),
             'failure reason')
        need(len(observed) <= status['inference_calls'] <= len(observed) + 1,
             'partial call count')
        if failed:
            action, failure = failed
            need(status['failure_kind'] == failure
                 and status['failure_slot_id'] == action['id']
                 and status['failure_stage'] == action['kind']
                 and status['active_action'] == action['index']
                 and status['inference_calls'] == len(observed),
                 'recorded failure binding')
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
            trial = stored[slot['id']]
            eq(slot['id'] + '/unobserved', trial, expected)
            independent_trials.append(expected)

    summary = independent_summary(plan, independent_trials, independent_calls,
                                  status['complete'])
    for key, value in summary.items():
        eq('report/' + key, report[key], value)
    need(set(report) == set(summary) | {
        'data_integrity', 'data_complete', 'comparative_analysis_ready',
        'evidence_kind', 'new_model_inference', 'inference_calls',
        'max_inference_calls', 'plan_sha256', 'event_tip', 'run_state', 'run_error',
        'failure_stage', 'failure_kind', 'failure_slot_id', 'trials', 'calls',
        'source_fingerprint', 'reference_bundle_sha256'}, 'report exact fields')
    for key, value in {
        'data_integrity': True,
        'data_complete': status['complete'],
        'comparative_analysis_ready': status['complete'],
        'evidence_kind': run_manifest['evidence_kind'],
        'new_model_inference': run_manifest['new_model_inference'],
        'inference_calls': status['inference_calls'],
        'max_inference_calls': 40,
        'plan_sha256': plan['plan_sha256'],
        'event_tip': tip,
        'run_state': status['state'],
        'run_error': status['error'],
        'failure_stage': status['failure_stage'],
        'failure_kind': status['failure_kind'],
        'failure_slot_id': status['failure_slot_id'],
        'trials': trials,
        'calls': report['calls'],
        'source_fingerprint': fingerprint,
        'reference_bundle_sha256': sha(baseline),
    }.items():
        eq('report/' + key, report[key], value)
    eq('report/trials', report['trials'], independent_trials)
    eq('report/calls', report['calls'], independent_calls)

    human_report = {
        **summary,
        'data_integrity': True,
        'data_complete': status['complete'],
        'inference_calls': status['inference_calls'],
        'evidence_kind': run_manifest['evidence_kind'],
        'plan_sha256': plan['plan_sha256'],
        'event_tip': tip,
    }
    need(data['run/summary.ko.md'] == independent_summary_ko(human_report),
         'independent mismatch: Korean summary exact UTF-8/LF bytes')

    audit = load(data['run/audit.json'])
    audit_keys = ('contract', 'data_integrity', 'data_complete',
                  'comparative_analysis_ready', 'inference_calls',
                  'max_inference_calls', 'plan_sha256', 'event_tip', 'run_state',
                  'failure_stage', 'failure_kind', 'failure_slot_id', 'run_error')
    eq('audit summary', audit, {key: report[key] for key in audit_keys})
    return {'contract': 'independent-v060-r1',
            'bundle_sha256': sha(raw_bundle), 'complete': status['complete'],
            'observed_calls': len(observed), 'metadata_records': metadata_count,
            'compared_fields': fields, 'differences': [],
            'production_imports': False,
            'baseline_compared_fields': baseline_result['compared_fields'],
            'limitation': ('원문·계획·측정 일관성 검산이며 외부 실행 인증이나 '
                           '규칙 위치·캐시·내부 기제의 인과 검증은 아니다.')}


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
