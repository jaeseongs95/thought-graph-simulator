"""합성 응답 전용. 실제 LLM 실행이나 모델 성과가 아니다."""
from copy import deepcopy
from pathlib import Path
import json,os,sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
import common,design,report

def baseline_path():
    p=os.environ.get('V075_BASELINE')
    if p:return Path(p)
    return Path('/mnt/data/v074_endtoend_20260914_070558_230235_evidence.zip')

def plan(name='v075_test'):
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
        self.calls+=1;self.all_requests.append(deepcopy(body));data=input_of(body)
        if 'candidates' in data:
            ds=[path_depth(data['problem'],c['rules']) for c in data['candidates']]
            index=ds.index(min(ds) if '작은' in data['requested_depth'] else max(ds))
            if self.mode=='always_first':index=0
            elif self.mode=='always_long':index=ds.index(max(ds))
            elif self.mode=='always_short':index=ds.index(min(ds))
            obj={'candidate_id':data['candidates'][index]['candidate_id']}
            if self.mode=='invalid_selector':obj={'candidate_id':'unmapped'}
            text=common.wire(obj).decode()
            if self.mode=='selector_whitespace':text='\n { "candidate_id" : "'+obj['candidate_id']+'" } \n'
        else:
            phase=data['operation']['stage'];p=data['problem'];model=data['selection_original']['source_type']=='model'
            if phase=='facts':
                obj={'nodes':[{'id':f'f{i}','atom':a,'rule':None,'parents':[]} for i,a in enumerate(p['facts'])]}
                if self.mode=='bad_fact' and model:obj['nodes'][0]['atom']='missing_fact'
                limited=body['format']['properties']['nodes']['items']['properties']['rule']=={'type':'null'}
                overflow=(self.mode=='fact_overflow' or self.mode=='schema_sensitive' and not limited or self.mode=='schema_harms' and limited)
                if overflow:
                    rr=next(r for r in p['rules'] if all(a in p['facts'] for a in r['premises']))
                    by={n['atom']:n['id'] for n in obj['nodes']}
                    obj['nodes'].append({'id':'premature','atom':rr['conclusion'],'rule':rr['id'],'parents':[by[a] for a in rr['premises']]})
                if self.mode=='wrong_atom_fact_only' and limited:obj['nodes'][0]['atom']='not_an_initial_fact'
                if self.mode=='duplicate_fact_ids':obj['nodes'][1]['id']=obj['nodes'][0]['id']

            else:
                nodes=[]
                for old in data['history']:
                    try:x=common.load(old['content'])
                    except (ValueError,TypeError):continue
                    nodes+=x.get('nodes',[]) if isinstance(x,dict) else []
                    if isinstance(x,dict) and 'node' in x:nodes.append(x['node'])
                if phase=='final':
                    targets=[n['id'] for n in nodes if n['atom']==p['goal']]
                    obj={'final_node_id':targets[-1] if targets else 'unavailable'}
                    if self.mode=='bad_final' and model or self.mode=='control_fails' and not model:obj['final_node_id']='absent'
                else:
                    rid=data['operation']['requested_rule_id']
                    if self.mode=='swap_valid_branches' and model and rid in ('n08','n91'):rid={'n08':'n91','n91':'n08'}[rid]
                    rule=next(r for r in p['rules'] if r['id']==rid)
                    parents=[]
                    for atom in rule['premises']:
                        found=[n['id'] for n in nodes if n['atom']==atom];parents.append(found[-1] if found else 'missing_'+atom)
                    obj={'node':{'id':f'n{data["operation"]["index"]}','atom':rule['conclusion'],'rule':rid,'parents':parents}}
                    if self.mode=='bad_parent' and model and parents:obj['node']['parents'][0]='absent'
            text=common.wire(obj).decode()
            if self.mode=='malformed_facts' and phase=='facts' and model:text='not json'
        response={'model':body['model'],'message':{'role':'assistant','content':text},'done':True,'done_reason':'stop',
                  'eval_count':32,'prompt_eval_count':400,'total_duration':1000,'prompt_eval_duration':200,'eval_duration':800}
        if self.mode=='length_selector' and 'candidates' in data:response['done_reason']='length'
        if self.mode=='missing_usage':
            for k in report.USAGE:response.pop(k,None)
        if self.mode=='wrong_identity':response['model']='different-model'
        if self.mode=='budget_exceeded':response['eval_count']=4097
        return common.wire(response)
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
    synth=Synth(mode);records={};raws={}
    for slot in p['slots']:
        if limit is not None and len(records)>=limit:break
        skip=design.disposition(p,slot,raws);sid=slot['id']
        if skip:records[sid]={'id':sid,'kind':'skip','reason':skip}
        else:
            request=common.wire(design.request_for(p,slot,raws));raw=synth.response(common.load(request));raws[sid]=raw
            import base64
            records[sid]={'id':sid,'kind':'call','http_status':200,'error':None,'elapsed_ns':100,
                          'request_sha256':common.sha(request),'response_sha256':common.sha(raw),'response_b64':base64.b64encode(raw).decode()}
    return records,raws,synth
