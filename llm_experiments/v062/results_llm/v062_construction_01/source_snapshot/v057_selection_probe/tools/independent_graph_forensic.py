"""프로젝트 모듈을 import하지 않는 v055 전수 원문 검산. 표준 라이브러리만 사용한다."""
from __future__ import annotations
import argparse,base64,collections,csv,hashlib,itertools,json,math,pathlib,zipfile

def need(ok,msg):
    if not ok: raise ValueError(msg)
def load(raw):
    def pairs(items):
        d={}
        for k,v in items: need(k not in d,'duplicate JSON key');d[k]=v
        return d
    def no(x): raise ValueError('non-finite number')
    def finite(x):
        v=float(x);need(math.isfinite(v),'non-finite float');return v
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=no,parse_float=finite)
def canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(x):return hashlib.sha256(x).hexdigest()
def unpack(z):
    with zipfile.ZipFile(z) as f:
        ns=f.namelist();need(len(ns)==len(set(ns)),'duplicate ZIP members')
        need(all(not pathlib.PurePosixPath(n).is_absolute() and '..' not in pathlib.PurePosixPath(n).parts and '\\' not in n for n in ns),'unsafe path')
        need(sum(i.file_size for i in f.infolist())<256*1024**2,'archive expansion limit')
        data={n:f.read(n) for n in ns}
    manifest=load(data.pop('BUNDLE_MANIFEST.json'))
    need(set(data)==set(manifest['file_hashes']),'manifest member set')
    for n,b in data.items():need(sha(b)==manifest['file_hashes'][n],f'manifest hash {n}')
    return data,manifest

def inspect(problem,payload):
    result={'format_valid':False,'proof_valid':None,'strict_valid':False,'D':None,'final_ref_valid':None,'structure':None,'faults':[]}
    if not isinstance(payload,dict):return result
    ns=payload.get('nodes');final=payload.get('final_node_id')
    if isinstance(ns,list):result['final_ref_valid']=isinstance(final,str) and bool(final) and sum(isinstance(n,dict) and n.get('id')==final for n in ns)==1
    def text(x):return isinstance(x,str) and 0<len(x)<=128
    shape=isinstance(ns,list) and 0<len(ns)<=16 and text(final)
    if shape:
        shape=all(isinstance(n,dict) and set(n)=={'id','atom','rule','parents'} and text(n['id']) and text(n['atom']) and (n['rule'] is None or text(n['rule'])) and isinstance(n['parents'],list) and len(n['parents'])<=16 and all(text(p) for p in n['parents']) for n in ns)
    result['format_valid']=bool(shape and set(payload)=={'nodes','final_node_id'})
    result['proof_valid']=False
    if not shape:result['faults']=['graph_schema'];return result
    rules={r['id']:r for r in problem['rules']};lookup={};depths={};anc={};sigs={};faults=[]
    # 국소 결함은 함께 기록하되, 전방 참조를 재정렬하거나 누락 사실을 채우지 않는다.
    for n in ns:
        k=n['id'];parents=n['parents'];rid=n['rule'];atom=n['atom']
        if k in lookup:faults.append('duplicate_node')
        if len(set(parents))!=len(parents):faults.append('duplicate_parent')
        if any(p not in lookup for p in parents):faults.append('missing_or_forward_parent')
        if rid is None:
            if parents or atom not in problem['facts']:faults.append('unsupported_fact')
        elif rid not in rules:faults.append('unknown_rule')
        else:
            rule=rules[rid]
            if atom!=rule['conclusion']:faults.append('rule_conclusion')
            if all(p in lookup for p in parents) and sorted(lookup[p]['atom'] for p in parents)!=sorted(rule['premises']):faults.append('rule_premises')
        lookup[k]=n
    if not result['final_ref_valid']:faults.append('final_reference')
    elif lookup[final]['atom']!=problem['goal']:faults.append('wrong_goal')
    # 별도 유효성 판정: 하나라도 잘못되면 유효 D를 생성하지 않는다.
    if not faults:
        for n in ns:
            k=n['id'];ps=n['parents']
            depths[k]=0 if n['rule'] is None else 1+max(depths[p] for p in ps)
            anc[k]={k}.union(*(anc[p] for p in ps))
            sigs[k]=[n['atom'],n['rule'],sorted((sigs[p] for p in ps),key=canonical)]
        if anc[final]!=set(lookup):faults.append('extraneous_path')
        else:result.update(proof_valid=True,strict_valid=result['format_valid'],D=depths[final],structure=sha(canonical(sigs[final])))
    result['faults']=sorted(set(faults));return result

def extract_payload(raw,model):
    try:
        e=load(raw);need(isinstance(e,dict) and e.get('model')==model and e.get('done') is True and e.get('done_reason')=='stop','envelope')
        m=e['message'];need(m.get('role')=='assistant' and not m.get('tool_calls') and not m.get('images'),'message')
        need(not m.get('thinking','').strip(),'thinking');text=m['content'];need('<think>' not in text and '</think>' not in text,'thinking tags')
        p=load(text);need(isinstance(p,dict),'payload object');return p
    except (ValueError,KeyError,TypeError,AttributeError):return None

def write_csv(path,rows):
    if not rows:return
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def main(bundle,out):
    out.mkdir(parents=True,exist_ok=True);data,manifest=unpack(bundle);p=load(data['external_plan/v055.plan.json']);report=load(data['run/summary.json']);status=load(data['run/status.json'])
    need(p==load(data['run/plan.snapshot.json']),'plan snapshot');need(p['plan_sha256']==sha(canonical({k:v for k,v in p.items() if k!='plan_sha256'})),'plan hash')
    events=[load(x) for x in data['run/events.jsonl'].splitlines()];tip=p['plan_sha256'];stored={t['id']:t for t in report['trials']};rows=[];diffs=[];fields=0
    def compare(name,a,b):
        nonlocal fields
        fields+=1
        if type(a)!=type(b) or a!=b:diffs.append({'field':name,'stored':a,'independent':b})
    for index,e in enumerate(events):
        need(e['action']==p['actions'][index],'schedule');need(e['previous_hash']==tip,'chain');need(e['event_hash']==sha(canonical({k:v for k,v in e.items() if k!='event_hash'})),'event hash');tip=e['event_hash']
        a=e['action']
        if a['kind']!='call':continue
        s=a['slot'];sid=s['id'];raw=data[f'run/calls/{sid}/response.raw.json'];wire=data[f'run/calls/{sid}/request.wire.json'];q=load(wire)
        need(sha(raw)==e['response_sha256'] and sha(wire)==e['request_sha256'],'raw hashes')
        need(e['http_status']==200 and e['transport_error'] is None,'complete HTTP');need(q['options']['seed']==s['seed'],'seed')
        problem=load(q['messages'][1]['content'][9:]);payload=extract_payload(raw,q['model']);m=inspect(problem,payload)
        for k in ('format_valid','proof_valid','strict_valid','D','final_ref_valid'):compare(sid+'/'+k,stored[sid]['measurement'][k],m[k])
        # 두 주어진 문제의 독립적으로 열거한 깊이 범위. 이 값은 요청을 만들지 않는다.
        lo,hi=(1,2) if s['problem_id']=='K01' else (1,4)
        match=None if s['direction']=='neutral' else bool(m['strict_valid'] and m['D']==(lo if s['direction']=='shallow' else hi))
        compare(sid+'/role_match',stored[sid]['role_match'],match)
        rows.append({k:s[k] for k in ('id','model_key','problem_id','arm','direction','seed')}|{k:m[k] for k in ('format_valid','proof_valid','strict_valid','D','final_ref_valid','structure')}|{'role_match':match,'faults':';'.join(m['faults']),'first_production_error':';'.join(stored[sid]['measurement']['errors'])})
    need(tip==status['event_tip']==report['event_tip'],'final tip');need(len(rows)==240 and status['complete'],'complete dimensions')
    pairs=[];lookup={(r['model_key'],r['problem_id'],r['arm'],r['seed'],r['direction']):r for r in rows}
    for key,pid,arm,seed in itertools.product(p['model_keys'],p['problems'],p['arms'],p['seeds']):
        sh,de=(lookup[key,pid,arm,seed,d] for d in ('shallow','deep'))
        pair={'model_key':key,'problem_id':pid,'arm':arm,'seed':seed,'shallow_depth':sh['D'],'deep_depth':de['D'],'both_valid':sh['strict_valid'] and de['strict_valid'],'selective_success':bool(sh['role_match'] and de['role_match'] and sh['D']!=de['D'])};pairs.append(pair)
        original=next(x for x in report['models'][key]['pairs'] if x['problem_id']==pid and x['arm']==arm and x['seed']==seed)
        compare(f'{key}/{pid}/{arm}/{seed}/selective',original['direction_selective_success'],pair['selective_success'])
    result={'bundle_sha256':sha(bundle.read_bytes()),'manifest_files':len(data),'responses':len(rows),'compared_fields':fields,'differences':diffs,'models':{}}
    for key in p['model_keys']:
        rs=[r for r in rows if r['model_key']==key]
        result['models'][key]={'responses':len(rs),'format_valid':sum(r['format_valid'] for r in rs),'proof_valid':sum(r['proof_valid'] is True for r in rs),'final_reference_exists':sum(r['final_ref_valid'] is True for r in rs),'selective_pairs':sum(x['selective_success'] for x in pairs if x['model_key']==key),'first_errors':dict(collections.Counter(r['first_production_error'] for r in rs if r['first_production_error'])),'overlapping_faults':dict(collections.Counter(k for r in rs for k in r['faults'].split(';') if k))}
    write_csv(out/'trials.csv',rows);write_csv(out/'D_pairs.csv',pairs)
    write_csv(out/'valid_gemma.csv',[r for r in rows if r['model_key']=='candidate' and r['strict_valid']])
    (out/'independent_fresh.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    need(not diffs,'semantic differences');print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('bundle',type=pathlib.Path);ap.add_argument('--out',type=pathlib.Path,required=True);a=ap.parse_args();main(a.bundle,a.out)
