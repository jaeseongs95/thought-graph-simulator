"""One-model K01 conditional-construction crossover; no depth directive."""
import hashlib

from .contracts import require

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


def rank(seed, purpose):
    return hashlib.sha256(f'{SCHEDULE_SEED}:{purpose}:{seed}'.encode('ascii')).hexdigest()


def schedule(reference):
    seeds = reference['seeds']
    require(len(seeds) == 10 and len(set(seeds)) == 10, 'Ten unique seeds required')
    cells = {slot['seed']: slot for slot in reference['slots']}
    require(len(cells) == len(reference['slots']) == 10, 'Ten source choice requests required')
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
            slot = {
                **base,
                'id': f'b{block:02d}_p{period}_{variant}_r{repeat}',
                'reference_slot_id': old['id'],
                'task': 'conditional_construction',
                'mode': 'graph',
                'stage': 'graph',
                'direction': 'neutral',
                'role_id': variant,
                'target_rule_id': TARGET_RULES[variant],
                'position': len(result), 'block': block, 'period': period,
                'seed_index': seeds.index(seed), 'variant': variant, 'repeat': repeat,
                'sequence': sequence,
                'previous_call_id': previous['id'] if previous else None,
                'previous_variant': previous['variant'] if previous else None,
                'previous_same_variant_slot_id': previous_same.get(variant),
                'repeat_distance': (period - next(item['period'] for item in result
                    if item['id'] == previous_same[variant])) if repeat else None,
            }
            result.append(slot)
            previous_same[variant] = slot['id']
            counts[variant] += 1
    return result


def actions(slots):
    result = []
    for block in range(10):
        cells = [slot for slot in slots if slot['block'] == block]
        require(len(cells) == 4, 'Four calls per block')
        result.append({'kind': 'metadata', 'id': f'b{block:02d}.before', 'block': block, 'model_key': 'candidate'})
        result.extend({'kind': 'call', 'id': slot['id'], 'slot': slot} for slot in cells)
        result.append({'kind': 'metadata', 'id': f'b{block:02d}.after', 'block': block, 'model_key': 'candidate'})
    return [dict(action, index=index) for index, action in enumerate(result)]
