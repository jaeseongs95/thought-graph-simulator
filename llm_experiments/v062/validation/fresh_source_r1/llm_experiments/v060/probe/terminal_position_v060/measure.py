"""Choice-only measurement. Never infer a generated proof from an ID."""
from selection_probe_v057.measure import choice_measure, terminal_depths


def measure(problem, payload, slot):
    out = choice_measure(problem, payload, slot)
    ids = [r['id'] for r in problem['rules']]
    terminal_ids = [r['id'] for r in problem['rules']
                    if r['conclusion'] == problem['goal']]
    rid = out['selected_rule_id']
    out['selected_rule_position'] = ids.index(rid) if rid in ids else None
    out['terminal_rank'] = terminal_ids.index(rid) if rid in terminal_ids else None
    out['actual_D'] = None
    out['goal_reachable_choice'] = out['choice_valid'] if out['format_valid'] else None
    out['shallow_success'] = (out['choice_valid'] is True and
        out['implied_depth'] == min(ds[0] for ds in terminal_depths(problem).values())) if out['format_valid'] else None
    out['instruction_fulfilled'] = out['shallow_success']
    return out


def match(problem, measurement, slot):
    return measurement['shallow_success']
