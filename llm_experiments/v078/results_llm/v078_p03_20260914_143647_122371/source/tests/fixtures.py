"""시험 전용 합성 모델. 실제 실행기는 이 모듈을 import하지 않는다."""
from copy import deepcopy
from pathlib import Path
import os, sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
import common,design,report


def baseline_path():
    path=os.environ.get('V078_BASELINE')
    if not path:raise RuntimeError('V078_BASELINE에 첨부 v077 evidence ZIP 경로를 지정하세요.')
    return Path(path)


def plan(name='v078_test'):
    return design.make_plan(baseline_path(),name,'synthetic',audit_previous=False)


def input_of(body):return common.load(body['messages'][0]['content'].split('\n\ninput: ',1)[1])


def path_depth(p,rules):
    depths={a:0 for a in p['facts']}
    for r in rules:depths[r['conclusion']]=1+max(depths[x] for x in r['premises'])
    return depths[p['goal']]


class Synth:
    def __init__(self,mode='correct'):
        self.mode=mode;self.calls=0;self.all_requests=[];self.metadata_requests=0
    def response(self,body):
        self.calls+=1;self.all_requests.append(deepcopy(body));d=input_of(body);phase='select'
        if 'candidates' in d:
            ds=[path_depth(d['problem'],c['rules']) for c in d['candidates']]
            ns=[len(c['rules']) for c in d['candidates']]
            shallow='작은' in d['requested_depth']
            index=ds.index(min(ds) if shallow else max(ds))
            if self.mode=='always_first':index=0
            elif self.mode=='always_long':index=ds.index(max(ds))
            elif self.mode=='always_short':index=ds.index(min(ds))
            elif self.mode=='max_rules':index=ns.index(max(ns))
            elif self.mode=='min_rules':index=ns.index(min(ns))
            elif self.mode=='rule_count_heuristic':index=ns.index(min(ns) if shallow else max(ns))
            obj={'candidate_id':d['candidates'][index]['candidate_id']}
            if self.mode=='invalid_selector':obj={'candidate_id':'unmapped'}
        else:
            phase=d['operation']['stage'];p=d['problem'];model=d['selection_original']['source_type']=='model'
            if phase=='facts':
                obj={'nodes':[{'id':f'f{i}','atom':a,'rule':None,'parents':[]} for i,a in enumerate(p['facts'])]}
                if self.mode=='bad_fact' and model:obj['nodes'][0]['atom']='missing_fact'
                if self.mode=='duplicate_fact_ids':obj['nodes'][1]['id']=obj['nodes'][0]['id']
                if self.mode=='fact_overflow':
                    rr=next(r for r in p['rules'] if all(a in p['facts'] for a in r['premises']))
                    by={n['atom']:n['id'] for n in obj['nodes']}
                    obj['nodes'].append({'id':'premature','atom':rr['conclusion'],'rule':rr['id'],'parents':[by[a] for a in rr['premises']]})
            else:
                nodes=[]
                for item in d['history']:
                    try:x=common.load(item['content'])
                    except (ValueError,TypeError):continue
                    if isinstance(x,dict):
                        nodes.extend(x.get('nodes',[]))
                        if isinstance(x.get('node'),dict):nodes.append(x['node'])
                if phase=='final':
                    ids=[n['id'] for n in nodes if n['atom']==p['goal']]
                    obj={'final_node_id':ids[-1] if ids else 'unavailable'}
                    if (self.mode=='bad_final' and model) or (self.mode=='control_fails' and not model):obj['final_node_id']='absent'
                else:
                    rid=d['operation']['requested_rule_id']
                    if self.mode=='swap_valid_branches' and model and p['id']=='H01':
                        rs=common.spec()['reference_plans']['H01']['reference_short']
                        if rid in rs[:2]:rid=rs[1-rs.index(rid)]
                    r=next(r for r in p['rules'] if r['id']==rid);parents=[]
                    for atom in r['premises']:
                        found=[n['id'] for n in nodes if n['atom']==atom]
                        parents.append(found[-1] if found else 'missing_'+atom)
                    obj={'node':{'id':'n'+str(d['operation']['index']),'atom':r['conclusion'],'rule':rid,'parents':parents}}
                    if self.mode=='bad_parent' and model and d['operation']['index']==1:obj['node']['parents'][0]='absent'
                    if self.mode=='wrong_existing_parent' and model:
                        other=next((n for n in nodes if n['atom']!=r['premises'][0]),None)
                        if other:obj['node']['parents'][0]=other['id']
                    if self.mode=='missing_parent' and model:obj['node']['parents']=parents[:-1]
                    if self.mode=='duplicate_parent' and parents:obj['node']['parents'].append(parents[0])
                    if self.mode=='extra_bindings':obj['bindings']=[]
        text=common.wire(obj).decode()
        if self.mode=='selector_whitespace' and phase=='select':text='\n { "candidate_id" : "'+obj['candidate_id']+'" } \n'
        if self.mode=='malformed_facts' and phase=='facts' and model:text='not json'
        if self.mode=='malformed_rule' and phase=='rule' and model:text='not json'
        o={'model':body['model'],'message':{'role':'assistant','content':text},'done':True,'done_reason':'stop',
           'eval_count':32,'prompt_eval_count':400,'total_duration':1000,'prompt_eval_duration':200,'eval_duration':800}
        if self.mode=='length_selector' and phase=='select':o['done_reason']='length'
        if self.mode=='length_rule' and phase=='rule':o['done_reason']='length'
        if self.mode=='missing_usage':
            for k in report.USAGE:o.pop(k,None)
        if self.mode=='wrong_identity':o['model']='different-model'
        if self.mode=='budget_exceeded':o['eval_count']=4097
        return common.wire(o)
    def exchange(self,endpoint,path,body,timeout):
        if path!='/api/chat':
            self.metadata_requests+=1;s=common.spec()['identity']
            if path=='/api/version':obj=s['server']
            elif path=='/api/tags':obj={'models':[{'name':s['model'],'model':s['model'],'digest':s['digest'],'details':s['tag_details']}]}
            else:
                obj=deepcopy(s['native'])
                if obj['parameters'] is not None:obj['parameters']='\n'.join(obj['parameters'])
            if self.mode=='metadata_mismatch' and path=='/api/tags':obj['models'][0]['digest']='wrong'
            return 200,common.wire(obj),None,100
        if self.mode=='http_error':return 500,b'failure',None,100
        if self.mode=='transport_error':return None,b'','ConnectionResetError',100
        if self.mode=='interrupt':raise KeyboardInterrupt('synthetic interruption')
        return 200,self.response(common.load(body)),None,100


def memory_run(p,mode='correct',limit=None):
    import base64
    synth=Synth(mode);records={};raws={}
    for slot in p['slots']:
        if limit is not None and len(records)>=limit:break
        skip=design.disposition(p,slot,raws);sid=slot['id']
        if skip:records[sid]={'id':sid,'kind':'skip','reason':skip}
        else:
            request=common.wire(design.request_for(p,slot,raws));raw=synth.response(common.load(request));raws[sid]=raw
            records[sid]={'id':sid,'kind':'call','http_status':200,'error':None,'elapsed_ns':100,
                          'request_sha256':common.sha(request),'response_sha256':common.sha(raw),'response_b64':base64.b64encode(raw).decode()}
    return records,raws,synth
