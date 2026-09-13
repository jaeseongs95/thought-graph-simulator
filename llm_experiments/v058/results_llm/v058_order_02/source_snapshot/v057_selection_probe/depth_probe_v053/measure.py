"""증명 유효성·최종 참조 존재·요청된 깊이를 분리한다. 응답은 보정하지 않는다."""
from adm_diagnostic_v052.measure import measure as original_measure, depth_bounds

def final_reference_exists(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get('nodes'), list):
        return None
    final = payload.get('final_node_id')
    if not isinstance(final, str) or not final:
        return False
    return sum(isinstance(node, dict) and node.get('id') == final for node in payload['nodes']) == 1

def measure(problem, payload, slot=None):
    # 요청 direction/arm은 실제 깊이를 계산하는 데 사용하지 않는다.
    result = original_measure(problem, payload, {'task': 'graph_only', 'arm': 'explicit'})
    result['final_ref_valid'] = final_reference_exists(payload)
    return result

def role_match(measured, role, problem):
    if measured is None or role is None or not measured['strict_valid']:
        return False
    bounds = depth_bounds(problem)
    return measured['D'] == bounds[0 if role['D'] == 'shallow' else 1]
