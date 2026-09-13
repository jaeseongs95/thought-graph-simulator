"""단계별 형식 검사와 선언된 출력 결합. 정답 선택·증명 교정은 하지 않는다."""

def text(v):
    return isinstance(v,str) and 1<=len(v)<=128

def nodes_valid(v):
    if not isinstance(v,dict) or set(v)!={'nodes'}:return False
    ns=v['nodes']
    if not isinstance(ns,list) or not 1<=len(ns)<=16:return False
    for n in ns:
        if not isinstance(n,dict) or set(n)!={'id','atom','rule','parents'}:return False
        if not text(n['id']) or not text(n['atom']) or not (n['rule'] is None or text(n['rule'])):return False
        if not isinstance(n['parents'],list) or len(n['parents'])>16 or not all(text(x) for x in n['parents']):return False
    return True

def final_valid(v):
    return isinstance(v,dict) and set(v)=={'final_node_id'} and text(v['final_node_id'])

def assemble(nodes_payload,final_payload):
    if not nodes_valid(nodes_payload) or not final_valid(final_payload):return None
    # 두 모델이 각각 작성하도록 사전 배정한 필드만 합친다. 목록/ID를 수정하지 않는다.
    return {'nodes':nodes_payload['nodes'],'final_node_id':final_payload['final_node_id']}
