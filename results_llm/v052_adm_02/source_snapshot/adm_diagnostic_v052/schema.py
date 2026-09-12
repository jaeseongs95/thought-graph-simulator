"""직렬화만 명시화한다. 정답 노드·경로·finding은 schema에 고정하지 않는다."""
from copy import deepcopy
from adm_pilot_v051.contracts import OUTPUT_SCHEMA as LEGACY, obj, arr, STR, NODE, INSTANCE, SCHEMA, M1, M2

GENERAL = deepcopy(SCHEMA)
GENERAL['properties'].pop('binding')
GENERAL['properties']['bindings'] = arr(obj({'variable':STR,'atom':STR}),maximum=10,minimum=1)
GENERAL['required'] = list(GENERAL['properties'])
NODE_VIEW = obj({'node_id':STR,'representation':{'anyOf':[INSTANCE,GENERAL]}})
GRAPH = obj({'nodes':arr(NODE,maximum=16,minimum=1),'final_node_id':STR})
EXPLICIT = obj({'nodes':arr(NODE,maximum=16,minimum=1),'final_node_id':STR,
                'node_views':arr(NODE_VIEW,maximum=16,minimum=1),'reviews':arr({'anyOf':[M1,M2]},maximum=4)})

def schema_for(slot):
    if slot['arm']=='legacy': return LEGACY
    return GRAPH if slot['task']=='graph_only' else EXPLICIT
