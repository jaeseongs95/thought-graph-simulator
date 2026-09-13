"""Post-hoc boundary-cell replay; no shallow/deep control claim."""
from copy import deepcopy
from order_probe_v054.design import PROBLEMS, ARMS, DIRECTIONS, RULE_ORDERS
from .contracts import require
MODELS = ('reference', 'candidate')
MODES = ('graph', 'choice')
SEQUENCES = ('graph_choice', 'choice_graph')
BOUNDARY_CELLS = {'reference': {'problem_id': 'T02', 'arm': 'original', 'direction': 'shallow'},
                  'candidate': {'problem_id': 'K01', 'arm': 'original', 'direction': 'shallow'}}
MAX_CALLS = 80
POLICY = {
    'question': 'Explore whether two post-hoc selected v057 boundary cells differ when graph/choice group order is reversed within the same seed.',
    'scope': 'Exploratory boundary cells only; not a general model comparison or shallow/deep selective-control test.',
    'fixed': 'Exact v057 graph and choice request bytes, model identity/options, all 10 seeds, facts/rules/goal and shallow directive.',
    'intervention': 'Each model/seed receives graph-choice and choice-graph groups; group sequence and model block order alternate by seed parity.',
    'history': 'Group-first is not history-free. Metadata does not reset model/cache state. Record immediate preceding inference call.',
    'statistics': 'Within-seed paired descriptive outcomes; repeated seed is not a new independent problem sample.',
    'incomplete': 'Unexecuted and unmeasured remain null. Full comparison rates are null unless all actions complete.',
    'retry': False, 'repair': False, 'host_answer_fill': False, 'download_models': False,
    'budget': '80 new inference calls, 20 model-seed blocks, 40 metadata checks (three HTTP requests each).',
    'source': 'Historical v057 responses are provenance only, not newly observed outcomes.',
}

def schedule(reference):
    cells = {(s['model_key'], s['seed'], s['mode']): s for s in reference['slots']}
    require(len(cells) == 40 and len(reference['slots']) == 40, '40 boundary source requests required')
    result = []
    previous = None
    for i, seed in enumerate(reference['seeds']):
        for j, model in enumerate(MODELS if i % 2 == 0 else MODELS[::-1]):
            block = 2 * i + j
            for sequence in SEQUENCES if i % 2 == 0 else SEQUENCES[::-1]:
                modes = ('graph', 'choice') if sequence == 'graph_choice' else ('choice', 'graph')
                for position_in_group, mode in enumerate(modes):
                    old = cells[model, seed, mode]
                    slot = {**old, 'id': sequence + '__' + old['id'], 'reference_slot_id': old['id'],
                            'task': 'order_replay', 'stage': mode, 'block': block, 'seed_index': i,
                            'sequence': sequence, 'position_in_group': position_in_group, 'position': len(result),
                            'previous_call_id': None if previous is None else previous['id'],
                            'previous_call_mode': None if previous is None else previous['mode']}
                    result.append(slot)
                    previous = slot
    return result

def actions(slots):
    result = []
    for block in range(20):
        cells = [s for s in slots if s['block'] == block]
        require(len(cells) == 4, 'Each model-seed block has four calls')
        result.append({'kind': 'metadata', 'id': f'b{block:02d}.before', 'block': block, 'model_key': cells[0]['model_key']})
        result.extend({'kind': 'call', 'id': s['id'], 'slot': s} for s in cells)
        result.append({'kind': 'metadata', 'id': f'b{block:02d}.after', 'block': block, 'model_key': cells[0]['model_key']})
    for i, action in enumerate(result):
        action['index'] = i
    return result
