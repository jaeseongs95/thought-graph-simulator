"""추론 전에 두 모델의 기존 식별값을 함께 확인한다. 실패 원문도 보존한다."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from layout_probe_v056.contracts import read_plan_json,write_json,require,utc_now
from layout_probe_v056.plan import validate_plan
from layout_probe_v056.runner import metadata_failure
from model_probe_v055.metadata import collect
from paired_probe_v049.runner import OllamaHTTP

def preflight(plan_path,out):
    require(not out.exists(),'기존 preflight 원문 보존')
    plan=read_plan_json(plan_path);validate_plan(plan);cfg=plan['baseline']['config'];http=OllamaHTTP(cfg['endpoint'],cfg.get('timeout_seconds',300))
    result={'contract':'v056-preflight-r1','plan_sha256':plan['plan_sha256'],'at':utc_now(),'inference_calls':0,'state':'incomplete','metadata':{},'failure':None}
    out.parent.mkdir(parents=True,exist_ok=True);write_json(out,result,exclusive=True)
    for key in plan['model_keys']:
        record=collect(http,plan['identities'][key]['model']);result['metadata'][key]=record
        kind,error=metadata_failure(record,plan['identities'][key]);write_json(out,result)
        if kind:
            result['failure']={'model_key':key,'kind':kind,'error':error};write_json(out,result)
            raise ValueError('추론 전 모델 확인 실패: '+json.dumps(result['failure'],ensure_ascii=False)+'; 증거: '+str(out))
    result['state']='complete';write_json(out,result);return result
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--plan',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    try:print(json.dumps(preflight(a.plan,a.out),ensure_ascii=False,indent=2))
    except (ValueError,OSError) as e:print(str(e),file=sys.stderr);raise SystemExit(2)
