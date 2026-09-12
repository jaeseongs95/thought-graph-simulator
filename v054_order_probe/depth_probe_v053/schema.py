"""모든 조건에 기존 GRAPH 형식을 쓴다. 요청 경로를 schema로 강제하지 않는다."""
from adm_diagnostic_v052.schema import GRAPH

def schema_for(slot):
    return GRAPH
