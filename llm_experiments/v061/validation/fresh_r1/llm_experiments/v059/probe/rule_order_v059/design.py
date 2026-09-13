"""Fixed one-model, one-problem crossover; no answer computation."""
import hashlib
from .contracts import require

MODELS = ('candidate',)
MODES = ('choice',)
VARIANTS = ('original', 'terminal_swap')
SCHEDULE_SEED = 5902026
MAX_CALLS = 40
RULE_ORDERS = {'original': ['k10', 'k17', 'k03'], 'terminal_swap': ['k10', 'k03', 'k17']}
BOUNDARY_CELLS = {'candidate': {'problem_id': 'K01', 'arm': 'original', 'direction': 'shallow'}}
POLICY = {
    'question': 'Explore rule-list permutation sensitivity of Gemma K01 shallow terminal-rule choice.',
    'intervention': 'Swap only k17/k03 positions; preserve every rule, ID, fact, goal, prompt, schema and option.',
    'sampling': 'All 10 historical seeds; four dependent observations per seed, not 40 independent problems.',
    'schedule': 'SHA256-ranked seeds; five ABBA and five BAAB blocks, frozen schedule_seed=5902026.',
    'history': 'No state reset. Same-condition repeat distance and preceding calls remain possible explanations.',
    'interpretation': 'Exploratory permutation sensitivity only; no pure position, cache, internal heuristic or general model effect.',
    'measurement': 'Choice implied_depth is not actual proof D. Format, reachable choice and shallow success are separate.',
    'missing': 'Unobserved and unmeasured remain null; full rates require complete measured denominators.',
    'retry': False, 'repair': False, 'resume': False, 'download_models': False,
    'budget': '40 inference calls and 20 metadata records; no warmup.',
}


def rank(seed, purpose):
    return hashlib.sha256(f'{SCHEDULE_SEED}:{purpose}:{seed}'.encode('ascii')).hexdigest()


def schedule(reference):
    seeds = reference['seeds']
    require(len(seeds) == 10 and len(set(seeds)) == 10, 'Ten unique seeds required')
    cells = {s['seed']: s for s in reference['slots']}
    require(len(cells) == len(reference['slots']) == 10, 'Ten source choice requests required')
    abba = set(sorted(seeds, key=lambda s: rank(s, 'assignment'))[:5])
    result = []
    for block, seed in enumerate(sorted(seeds, key=lambda s: rank(s, 'blocks'))):
        seq = 'ABBA' if seed in abba else 'BAAB'
        counts = {v: 0 for v in VARIANTS}
        previous_same = {}
        for period, letter in enumerate(seq):
            variant = VARIANTS[letter == 'B']
            repeat = counts[variant]
            old = cells[seed]
            # Keep the original slot in reference.slots, not stale execution
            # labels from its historical graph/choice group in the new run.
            base = {k: v for k, v in old.items()
                    if k not in ('previous_call_mode', 'position_in_group')}
            previous = result[-1] if result else None
            slot = {**base, 'id': f'b{block:02d}_p{period}_{variant}_r{repeat}',
                    'reference_slot_id': old['id'], 'task': 'rule_order', 'stage': 'choice',
                    'position': len(result), 'block': block, 'period': period,
                    'seed_index': seeds.index(seed), 'variant': variant, 'repeat': repeat,
                    'sequence': seq,
                    'previous_call_id': previous['id'] if previous else None,
                    'previous_variant': previous['variant'] if previous else None,
                    'previous_same_variant_slot_id': previous_same.get(variant),
                    'repeat_distance': (period - next(s['period'] for s in result
                         if s['id'] == previous_same[variant])) if repeat else None}
            result.append(slot)
            previous_same[variant] = slot['id']
            counts[variant] += 1
    return result


def actions(slots):
    result = []
    for block in range(10):
        cells = [s for s in slots if s['block'] == block]
        require(len(cells) == 4, 'Four calls per block')
        result.append({'kind': 'metadata', 'id': f'b{block:02d}.before', 'block': block, 'model_key': 'candidate'})
        result.extend({'kind': 'call', 'id': s['id'], 'slot': s} for s in cells)
        result.append({'kind': 'metadata', 'id': f'b{block:02d}.after', 'block': block, 'model_key': 'candidate'})
    return [dict(a, index=i) for i, a in enumerate(result)]
