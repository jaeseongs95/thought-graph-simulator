"""v066 원문용 독립 의미 분석기. 생산 평가기/요청 생성기를 import하지 않는다."""
from __future__ import annotations
import argparse,collections,csv,hashlib,itertools,json,math,zipfile
from pathlib import Path,PurePosixPath

def need(x,msg):
    if not x:raise ValueError(msg)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def load(raw):
    def pairs(xs):
        out={}
        for k,v in xs:need(k not in out,'duplicate JSON key');out[k]=v
        return out
    def no(x):raise ValueError('nonfinite number')
    def fl(x):v=float(x);need(math.isfinite(v),'nonfinite number');return v
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=no,parse_float=fl)
def wire(v):return json.dumps(v,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf-8')
def unpack(path):
    with zipfile.ZipFile(path) as z:
        infos=z.infolist();need(len(infos)==len({i.filename.casefold() for i in infos}),'duplicate archive member');need(sum(i.file_size for i in infos)<256*1024**2,'size limit')
        for i in infos:
            p=PurePosixPath(i.filename);need(not p.is_absolute() and '..' not in p.parts and '\\' not in i.filename and not i.is_dir() and ((i.external_attr>>16)&0o170000)!=0o120000,'unsafe path')
        return {i.filename:z.read(i) for i in infos}
def text(x):return isinstance(x,str) and 1<=len(x)<=128

def graph_assess(problem,p):
    out={'format_valid':False,'proof_valid':None,'strict_valid':None,'actual_D':None,'final_rule_id':None,'error_codes':[]}
    ok=isinstance(p,dict) and set(p)=={'nodes','final_node_id'} and text(p['final_node_id']) and isinstance(p['nodes'],list) and 1<=len(p['nodes'])<=16
    if ok:ok=all(isinstance(n,dict) and set(n)=={'id','atom','rule','parents'} and text(n['id']) and text(n['atom']) and (n['rule'] is None or text(n['rule'])) and isinstance(n['parents'],list) and len(n['parents'])<=16 and all(text(x) for x in n['parents']) for n in p['nodes'])
    if not ok:out['error_codes']=['schema_invalid'];return out
    out.update(format_valid=True,proof_valid=False,strict_valid=False);nodes={};errors=set();rules={r['id']:r for r in problem['rules']}
    for n in p['nodes']:
        if n['id'] in nodes:errors.add('duplicate_id')
        else:nodes[n['id']]=n
    goal=nodes.get(p['final_node_id'])
    if goal is None:errors.add('missing_final_node')
    else:
        out['final_rule_id']=goal['rule']
        if goal['atom']!=problem['goal']:errors.add('final_goal_mismatch')
    for n in nodes.values():
        parents=n['parents'];missing=any(x not in nodes for x in parents)
        if len(parents)!=len(set(parents)):errors.add('duplicate_parent')
        if missing:errors.add('missing_parent')
        if n['rule'] is None:
            if parents:errors.add('fact_with_parents')
            if n['atom'] not in problem['facts']:errors.add('unreachable_fact')
        elif n['rule'] not in rules:errors.add('unregistered_rule')
        else:
            r=rules[n['rule']]
            if r['conclusion']!=n['atom']:errors.add('wrong_atom')
            if not missing and sorted(nodes[x]['atom'] for x in parents)!=sorted(r['premises']):errors.add('premise_counter_mismatch')
    # 남아 있는 부모를 단계적으로 제거해 순환을 검사한다.
    remaining=set(nodes);order=[]
    while remaining:
        free=sorted(x for x in remaining if not(set(nodes[x]['parents'])&remaining))
        if not free:errors.add('cycle');break
        remaining.difference_update(free);order.extend(free)
    if errors:out['error_codes']=sorted(errors);return out
    out['proof_valid']=True;ancestors=set();pending=[p['final_node_id']]
    while pending:
        n=pending.pop()
        if n not in ancestors:ancestors.add(n);pending.extend(nodes[n]['parents'])
    if ancestors!=set(nodes):errors.add('extra_unused_node')
    positions={n['id']:i for i,n in enumerate(p['nodes'])}
    if any(positions[x]>=positions[n['id']] for n in p['nodes'] for x in n['parents']):errors.add('non_topological_order')
    if errors:out['error_codes']=sorted(errors);return out
    depth={}
    for n in order:depth[n]=0 if nodes[n]['rule'] is None else 1+max(depth[x] for x in nodes[n]['parents'])
    out.update(strict_valid=True,actual_D=depth[p['final_node_id']]);return out

def plan_assess(problem,p):
    out={'plan_valid':None,'planned_D':None,'selected_rule_ids':None,'plan_format_valid':False,'plan_error_codes':[]}
    if not(isinstance(p,dict) and set(p)=={'rule_ids'} and isinstance(p['rule_ids'],list) and 1<=len(p['rule_ids'])<=16 and all(text(x) for x in p['rule_ids'])):out['plan_error_codes']=['plan_schema'];return out
    ids=p['rule_ids'];out.update(plan_valid=False,plan_format_valid=True,selected_rule_ids=ids[:]);errors=set();rules={r['id']:r for r in problem['rules']}
    known={a:0 for a in problem['facts']};support={a:frozenset() for a in problem['facts']}
    if len(ids)!=len(set(ids)):errors.add('duplicate_rule')
    for rid in ids:
        if rid not in rules:errors.add('unregistered_rule');continue
        r=rules[rid];goal=r['conclusion']
        if goal in known:errors.add('rederived_atom')
        if any(a not in known for a in r['premises']):errors.add('plan_premise_unavailable');continue
        known[goal]=1+max([known[a] for a in r['premises']],default=-1);support[goal]=frozenset([rid]).union(*(support[a] for a in r['premises']))
    if ids[-1] not in rules or rules[ids[-1]]['conclusion']!=problem['goal']:errors.add('plan_final_goal')
    if problem['goal'] not in known:errors.add('plan_goal_unreachable')
    elif support[problem['goal']]!=set(ids):errors.add('plan_unused_rule')
    out['plan_error_codes']=sorted(errors)
    if not errors:out.update(plan_valid=True,planned_D=known[problem['goal']])
    return out

def write_csv(path,rows):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader()
        for r in rows:w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v for k,v in r.items()})

def main(bundle,out):
    import previous
    previous.inspect_prior(bundle.read_bytes())
    out.mkdir(parents=True,exist_ok=False);files=unpack(bundle);m=load(files['MANIFEST.json']);need(set(m['file_hashes'])==set(files)-{'MANIFEST.json'},'manifest names')
    for n,h in m['file_hashes'].items():need(sha(files[n])==h,'hash '+n)
    p=load(files['plan.json']);s=load(files['summary.json']);problemmap={v['id']:v for v in p['protocol']['problems']};saved={r['id']:r for r in s['rows']};rows=[];payloads={};checks=0;transfers=[]
    for slot in p['slots']:
        sid=slot['id'];env=load(files['wire/'+sid+'/response.raw.json']);q=load(files['wire/'+sid+'/request.wire.json'])
        need(env['model']==p['identity']['model'] and env['done'] is True and env['done_reason']=='stop','envelope');obj=load(env['message']['content']);payloads[sid]=obj
        pr=problemmap[slot['problem_id']];res=plan_assess(pr,obj) if slot['stage']=='plan' else graph_assess(pr,obj)
        for k,v in res.items():need(type(v)==type(saved[sid][k]) and v==saved[sid][k],sid+' field '+k);checks+=1
        if slot['stage']=='construct':
            pid=slot['parent_plan_id'];parent_raw=files['wire/'+pid+'/response.raw.json'];content=load(parent_raw)['message']['content'];carried=load(q['messages'][0]['content'].split('\nroute_plan_response: ',1)[1])
            need(carried=={'source_slot_id':pid,'response_sha256':sha(parent_raw),'content':content},'unfaithful transfer')
            follow=res['format_valid'] and [n['rule'] for n in obj['nodes'] if n['rule'] is not None]==payloads[pid]['rule_ids'];need(follow==saved[sid]['follows_actual_plan'],'plan adherence');checks+=1
            transfers.append({'planner':pid,'constructor':sid,'exact_content_transfer':True,'follows_plan_rules':follow,'planner_content':content,'planner_valid':plan_assess(pr,payloads[pid])['plan_valid'],'strict_graph':res['strict_valid']})
        row={k:slot[k] for k in ('id','problem_id','seed','direction','stage','arm')};row.update(res);row['response_sha256']=sha(files['wire/'+sid+'/response.raw.json']);rows.append(row)
    planrows=[r for r in rows if r['stage']=='plan'];graphrows=[r for r in rows if r['stage']!='plan'];groups=[]
    for pid in problemmap:
        rr=[r for r in planrows if r['problem_id']==pid];unique={tuple(r['selected_rule_ids']) for r in rr};groups.append({'problem_id':pid,'observations':len(rr),'unique_rule_lists':len(unique),'rule_lists':[list(x) for x in sorted(unique)],'all_four_directions_seeds_same':len(unique)==1,'valid':sum(r['plan_valid'] for r in rr),'errors':dict(collections.Counter(e for r in rr for e in r['plan_error_codes']))})
    metrics={}
    for arm in ('direct','staged'):
        rr=[r for r in graphrows if r['arm']==arm]
        metrics[arm]={'final_graph_count':len(rr),'format_valid':sum(r['format_valid'] for r in rr),'proof_valid':sum(r['proof_valid'] for r in rr),'strict_valid':sum(r['strict_valid'] for r in rr),'errors_overlapping':dict(collections.Counter(e for r in rr for e in r['error_codes']))}
    usage={}
    for arm in ('direct','staged'):
        er=[load(files['wire/'+x['id']+'/response.raw.json']) for x in p['slots'] if x['arm']==arm];usage[arm]={k:sum(x[k] for x in er) if all(type(x.get(k)) is int for x in er) else None for k in ('prompt_eval_count','eval_count','total_duration','prompt_eval_cached_count')};need(usage[arm]==s['arms'][arm]['usage'],'cost aggregate')
    result={'contract':'v066-raw-independent-analysis-r1','bundle_sha256':sha(bundle.read_bytes()),'manifest_files':len(m['file_hashes']),'observed_calls':len(rows),'semantic_fields_compared':checks,'differences':[],'exact_transfer_count':len(transfers),'input_plan_valid_count':sum(r['plan_valid'] for r in planrows),'input_plan_format_count':sum(r['plan_format_valid'] for r in planrows),'planner_groups':groups,'graph_groups':metrics,'usage':usage,'followed_invalid_plans':sum(t['follows_plan_rules'] and not t['planner_valid'] for t in transfers),'selective_D_pairs':{a:s['arms'][a]['selective_successes'] for a in ('direct','staged')},'new_model_calls':0}
    (out/'fresh_analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');write_csv(out/'planner_12.csv',planrows);write_csv(out/'graphs_24.csv',graphrows);write_csv(out/'transfers_12.csv',transfers)
    (out/'raw_payloads_36.json').write_text(json.dumps(payloads,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('bundle',type=Path);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();main(a.bundle,a.out)
