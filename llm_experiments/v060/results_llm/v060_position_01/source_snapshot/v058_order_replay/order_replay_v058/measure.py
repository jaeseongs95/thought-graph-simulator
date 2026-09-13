"""Separate parsing, graph validity, actual D and terminal-choice correctness."""
from selection_probe_v057.measure import measure as original_measure, match as original_match

def measure(problem, payload, slot):
    result = original_measure(problem, payload, slot)
    result['task_valid'] = (result['strict_valid'] if slot['mode'] == 'graph' else result['choice_valid']) if result['format_valid'] else None
    result['shallow_success'] = original_match(problem, result, slot) if result['format_valid'] else None
    return result

def match(problem, measurement, slot):
    return measurement['shallow_success']
