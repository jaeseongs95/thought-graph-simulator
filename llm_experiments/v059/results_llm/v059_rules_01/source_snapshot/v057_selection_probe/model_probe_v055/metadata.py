"""추론 없는 모델 식별. 부분 HTTP 실패도 응답 바이트와 함께 보존한다."""
from __future__ import annotations
import re
from pathlib import Path
from paired_probe_v049.runner import OllamaHTTP, check_identity
from .contracts import *
from .design import CANDIDATE, MODELS

STEPS = (('server','/api/version'),('tags','/api/tags'),('show','/api/show'))

def collect(http, model):
    record={'at':utc_now(),'model':model,'requests':[]}
    for name,path in STEPS:
        body=wire({'model':model}) if name=='show' else None
        response=http.request(path,body)
        record['requests'].append({'name':name,'path':path,'request_b64':b64(body) if body is not None else None,
            'response_b64':b64(response['raw']),'http_status':response['http_status'],
            'transport_error':response['error'],'elapsed_ns':response['elapsed_ns']})
        if response['http_status']!=200 or response['error'] is not None:break
        try:strict_json(response['raw'])
        except ContractError:break
    return record

def decode_metadata(record, model):
    require(isinstance(record,dict) and set(record)=={'at','model','requests'} and record['model']==model,'metadata 모델/필드 변경')
    require(isinstance(record['requests'],list) and 1<=len(record['requests'])<=3,'metadata 요청수 오류')
    raw={};data={}
    for i,r in enumerate(record['requests']):
        name,path=STEPS[i];body=wire({'model':model}) if name=='show' else None
        require(set(r)=={'name','path','request_b64','response_b64','http_status','transport_error','elapsed_ns'},'metadata 응답 필드 변경')
        require(r['name']==name and r['path']==path and r['request_b64']==(b64(body) if body is not None else None),'metadata endpoint/순서/모델 변경')
        require(type(r['http_status']) is int and 0<=r['http_status']<=599 and type(r['elapsed_ns']) is int and r['elapsed_ns']>=0,'metadata HTTP 자료형')
        require(r['transport_error'] is None or isinstance(r['transport_error'],str),'metadata 오류 자료형')
        require(r['http_status']==200 and r['transport_error'] is None,'metadata HTTP 실패: '+name+': '+str(r['transport_error']))
        raw[name]=r['response_b64'];data[name]=strict_json(unb64(raw[name]))
    require(len(record['requests'])==3,'metadata 조회 미완료')
    return {'at':record['at'],'raw_b64':raw,'data':data}

def identity(record, model):
    decoded=decode_metadata(record,model);data=decoded['data']
    require(isinstance(data['tags'],dict) and isinstance(data['tags'].get('models'),list),'모델 목록 형식')
    matches=[m for m in data['tags']['models'] if m.get('name')==model or m.get('model')==model]
    require(len(matches)==1,'모델 태그가 없거나 중복: '+model)
    tag=matches[0]
    require(isinstance(tag.get('digest'),str) and re.fullmatch(r'[0-9a-f]{64}',tag['digest']) is not None,'모델 digest 형식')
    require(isinstance(data['show'],dict) and isinstance(data['server'],dict),'show/server 형식')
    details=data['show'].get('details',tag.get('details',{}))
    require(isinstance(details,dict),'모델 details 형식')
    return {'model':model,'digest':tag['digest'],'show_sha256':digest(data['show']),
        'server':data['server'],'details':details,'template':data['show'].get('template'),
        'parameters':data['show'].get('parameters'),'model_info':data['show'].get('model_info',{})}

def validate_pair(records, baseline):
    require(isinstance(records,dict) and set(records)==set(MODELS),'두 모델 metadata 필요')
    qname=baseline['config']['model']
    q=identity(records['reference'],qname);g=identity(records['candidate'],CANDIDATE)
    check_identity(decode_metadata(records['reference'],qname),baseline)
    require(q['server']==g['server'],'두 모델 서버 버전이 다름')
    require(q['model']!=g['model'] and q['digest']!=g['digest'],'같은 모델을 대조군으로 중복 등록 금지')
    require(g['details'].get('family')=='gemma3','후보 모델이 gemma3 계열이 아님')
    size=g['details'].get('parameter_size','')
    require(isinstance(size,str) and re.fullmatch(r'\d+(?:\.\d+)?B',size) is not None and 3.5<=float(size[:-1])<=4.5,'gemma3 4B급 metadata 필요')
    require(q['details'].get('quantization_level')==g['details'].get('quantization_level')=='Q4_K_M','동일 Q4_K_M 양자화 필요')
    require(isinstance(g['template'],str) and bool(g['template']),'후보 native template 누락')
    return {'reference':q,'candidate':g}

def capture(bundle: Path, out: Path):
    from .evidence import import_v054
    require(not out.exists(),'기존 capture 자료 보존: '+str(out))
    baseline,reference=import_v054(bundle)
    cfg=baseline['config'];http=OllamaHTTP(cfg['endpoint'],cfg.get('timeout_seconds',300))
    out.mkdir(parents=True,exist_ok=False)
    result={'contract':'v055-metadata-capture-r1','state':'incomplete','created_at':utc_now(),
        'baseline_bundle_sha256':reference['bundle_sha256'],'endpoint':cfg['endpoint'],
        'source_fingerprint':source_fingerprint(),'metadata':{},'identities':None,'error':None,'inference_calls':0}
    try:
        for key,model in [('reference',cfg['model']),('candidate',CANDIDATE)]:
            result['metadata'][key]=collect(http,model)
            write_json(out/'capture.json',result)
            identity(result['metadata'][key],model)
        result['identities']=validate_pair(result['metadata'],baseline);result['state']='complete'
    except (ContractError,OSError,ValueError,TypeError,KeyError) as exc:
        result['error']=type(exc).__name__+': '+str(exc)
    finally:write_json(out/'capture.json',result)
    require(result['state']=='complete','모델 식별 실패. 원문 보존: '+str(out/'capture.json')+'; '+str(result['error']))
    return result
