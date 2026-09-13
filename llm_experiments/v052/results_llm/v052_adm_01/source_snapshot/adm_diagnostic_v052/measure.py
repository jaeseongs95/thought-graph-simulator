"""직렬화 투영과 의미 채점을 분리한다. 출력 경로·값을 고치지 않는다."""
from copy import deepcopy
from .contracts import ContractError,require,validate_payload,canonical,digest
from .schema import schema_for,GRAPH
from adm_pilot_v051.measure import measure as legacy_measure, inspect_graph

def project(payload,arm,task):
    """필드명/배열 표현만 변환. 정답 경로 선택·최종 참조 추정·중복 제거 금지."""
    if not isinstance(payload,dict):return payload,[]
    if arm=='legacy':return deepcopy(payload),[]
    out={'nodes':deepcopy(payload.get('nodes')),'final':payload.get('final_node_id'),
         'views':{},'reviews':deepcopy(payload.get('reviews',[]))};errors=[]
    if task=='graph_only':return out,errors
    try:
        require(isinstance(payload.get('node_views'),list),'node_views 배열 필요')
        for entry in payload['node_views']:
            require(isinstance(entry,dict) and isinstance(entry.get('node_id'),str),'node_view 참조 형식')
            key=entry['node_id'];require(key not in out['views'],'중복 node_view 참조')
            view=deepcopy(entry.get('representation'));require(isinstance(view,dict),'representation 객체 필요')
            if view.get('kind')=='universal_schema':
                bindings=view.pop('bindings',None);require(isinstance(bindings,list),'bindings 배열 필요');mapping={}
                for b in bindings:
                    require(isinstance(b,dict) and isinstance(b.get('variable'),str),'binding 변수 필요')
                    require(b['variable'] not in mapping,'중복 binding 변수')
                    mapping[b['variable']]=b.get('atom')
                view['binding']=mapping
            out['views'][key]=view
    except (ContractError,KeyError,TypeError) as exc:
        errors.append(str(exc));out['views']=None
    return out,errors

def depth_bounds(problem):
    """평가 전용. 규칙 원자성을 고정한 유한 acyclic 증명 깊이 집합."""
    def depths(atom,seen):
        if atom in seen:return set()
        values={0} if atom in problem['facts'] else set()
        from itertools import product
        for r in problem['rules']:
            if r['conclusion']!=atom:continue
            children=[depths(a,seen|{atom}) for a in r['premises']]
            for comb in product(*children):values.add(1+max(comb))
        return values
    vals=depths(problem['goal'],set());require(vals,'도달 불가 목표')
    return min(vals),max(vals)

def local_diagnostics(problem,trace):
    out={'local_nodes_valid':None,'node_total':None,'all_local_nodes_valid':None,
         'final_ref_valid':None,'goal_candidate_count':None,'candidate_depths':None,'proof_signature':None}
    if not isinstance(trace,dict) or not isinstance(trace.get('nodes'),list):return out
    lookup={};valid={};depth={};sig={};rules={r['id']:r for r in problem['rules']};oks=[]
    for n in trace['nodes']:
        try:
            require(isinstance(n,dict) and isinstance(n.get('id'),str),'node')
            k=n['id'];parents=n['parents'];rid=n['rule'];require(k not in lookup and isinstance(parents,list),'id/parents')
            require(all(isinstance(x,str) for x in parents) and len(set(parents))==len(parents),'parents')
            require(all(valid.get(x) for x in parents),'parent validity')
            if rid is None:require(not parents and n['atom'] in problem['facts'],'fact')
            else:
                require(isinstance(rid,str) and rid in rules,'rule')
                require(n['atom']==rules[rid]['conclusion'] and sorted(lookup[x]['atom'] for x in parents)==sorted(rules[rid]['premises']),'rule application')
            depth[k]=0 if rid is None else 1+max(depth[x] for x in parents)
            sig[k]=digest([n['atom'],rid,sorted(sig[x] for x in parents)])
            valid[k]=True;lookup[k]=n;oks.append(True)
        except (ContractError,KeyError,TypeError,ValueError):
            oks.append(False)
    final=trace.get('final')
    candidates=[k for k,n in lookup.items() if n['atom']==problem['goal']]
    out.update(local_nodes_valid=sum(oks),node_total=len(oks),all_local_nodes_valid=bool(oks) and all(oks),
               final_ref_valid=isinstance(final,str) and final in lookup,
               goal_candidate_count=len(candidates),candidate_depths=[depth[k] for k in candidates])
    if isinstance(final,str) and final in sig:out['proof_signature']=sig[final]
    return out

def measure(problem,payload,slot):
    """slot에서 task/arm만 읽는다. role_id나 요청 A/D/M은 측정에 쓰지 않는다."""
    format_ok=False;format_errors=[]
    try:validate_payload(payload,schema_for(slot));format_ok=True
    except (ContractError,KeyError,TypeError) as exc:format_errors.append(str(exc))
    trace,projection_errors=project(payload,slot['arm'],slot['task'])
    m=legacy_measure(problem,trace)
    m['format_valid']=format_ok and not projection_errors
    m['errors']=format_errors+projection_errors+m['errors']
    m.update(local_diagnostics(problem,trace))
    if slot['task']=='graph_only':
        m['representation_valid']=None;m['A']=None;m['M']=None;m['review_target_valid']=None;m['review_findings_valid']=None
        m['strict_valid']=m['format_valid'] and m['proof_valid'] is True
        # 그래프만 제출한 계약에는 view/review 오류를 전파하지 않는다.
        m['errors']=format_errors+([e for e in m['errors'] if e.startswith(('GOAL:','GRAPH:','PROOF:'))])
    else:m['strict_valid']=m['strict_valid'] and m['format_valid']
    if slot['task']=='copy_control':
        from .calibration import reference_record
        m['copy_exact']=canonical(payload)==canonical(reference_record(problem['id']))
    return m

def role_match(m,role,problem,*,coordinates_only=False):
    if m is None or role is None:return False
    if coordinates_only:
        if not all(m.get(k) is True for k in ('format_valid','proof_valid','representation_valid','review_target_valid')):return False
    elif not m['strict_valid']:return False
    lo,hi=depth_bounds(problem);target=[] if role['M']==0 else (['argument'] if role['M']==1 else ['acceptance_criterion'])
    return m['A']==role['A'] and m['D']==(lo if role['D']=='shallow' else hi) and m['M']==role['M'] and m['review_targets']==target
