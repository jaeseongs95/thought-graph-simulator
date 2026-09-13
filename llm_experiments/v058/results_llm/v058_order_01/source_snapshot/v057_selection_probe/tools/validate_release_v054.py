"""합성 HTTP 전수실행·오프라인 재감사·독립 의미 재검사를 생성한다. 실제 LLM 호출 금지."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tools'))
from tests_v054.fixtures import shared, executed
from order_probe_v054.evidence import bundle_run
from order_probe_v054.audit import audit_run
from order_probe_v054.plan import prepare
from order_probe_v054.requests import request_bytes
from order_probe_v054.contracts import read_json, strict_json, unb64, sha
from independent_verify_v054 import verify

MODES=('perfect','ignore_roles','first_branch','bad_final','misspelled_rule','only_original_control','truncated')

def run(out: Path, baseline: Path | None):
    out.mkdir(parents=True,exist_ok=False);results={}
    for mode in MODES:
        with executed(mode) as (root,p,rr,r,state):
            z=out/(mode+'.zip');bundle_run(p,rr,z)
            replay=audit_run(p,rr,write_report=False)
            assert replay==r,mode
            independent=verify(z);assert not independent['discrepancies'],mode
            (out/(mode+'_independent.json')).write_text(json.dumps(independent,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            results[mode]={'calls':r['inference_calls'],'data_complete':r['data_complete'],'report_equal':r==replay,
                'valid_proofs':sum(x['measurement']['strict_valid'] for x in r['trials']),
                'selective_pairs':sum(x['direction_selective_success'] for x in r['core_results'].values()),
                'robust_groups':sum(x['both_orders_selective_success'] for x in r['robust_results'].values()),
                'order_changed_pairs':sum(x['depth_changed'] for x in r['order_results'].values()),
                'independent_fields':independent['semantic_fields_compared'],'discrepancies':independent['discrepancies'],
                'evidence_kind':r['evidence_kind'],'bundle_sha256':sha(z.read_bytes())}
            print(mode,results[mode],flush=True)
    if baseline:
        p=prepare(baseline,out/'actual_baseline_offline_only.plan.json')
        previous=strict_json(unb64(p['reference']['plan_b64']))
        import zipfile
        with zipfile.ZipFile(baseline) as z:
            oldslots={(s['problem_id'],s['seed'],s['direction']):s for s in previous['slots'] if s['arm']=='original'}
            exact=0;permuted=0
            for slot in p['slots']:
                old=oldslots[slot['problem_id'],slot['seed'],slot['direction']]
                actual=z.read('run/calls/'+old['id']+'/request.wire.json');current=request_bytes(p,slot)
                if slot['arm']=='original':assert current==actual;exact+=1
                else:
                    a=strict_json(actual);b=strict_json(current)
                    pa=strict_json(a['messages'][1]['content'][9:]);pb=strict_json(b['messages'][1]['content'][9:])
                    assert pa['rules']!=pb['rules'];pb['rules']=pa['rules'];assert pb==pa
                    b['messages'][1]=a['messages'][1];assert b==a;permuted+=1
        results['actual_baseline_compatibility']={'original_wire_matches':exact,'only_rule_order_changed':permuted,
            'baseline_bundle_sha256':sha(baseline.read_bytes()),'model_inference_calls':0,'source_files':len(p['source_fingerprint'])}
    (out/'summary.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return results

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--actual-baseline',type=Path)
    a=p.parse_args();run(a.out,a.actual_baseline)

if __name__=='__main__':main()
