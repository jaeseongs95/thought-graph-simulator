"""실제 LLM 없이 로컬 HTTP 테스트를 재현한다. 결과는 synthetic_fixture로 표시된다."""
from __future__ import annotations
import argparse,contextlib,io,shutil,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tests_v051.fixtures import shared,executed
from adm_pilot_v051.evidence import bundle_run
from adm_pilot_v051.contracts import write_json

def main(out):
    out.mkdir(parents=True,exist_ok=False)
    f=shared()
    shutil.copyfile(f['root']/'v51.plan',out/'v051.plan.json')
    shutil.copytree(f['root']/'v51.run',out/'run')
    r=bundle_run(out/'v051.plan.json',out/'run',out/'perfect_evidence.zip')
    write_json(out/'perfect_result.json',{'calls':r['inference_calls'],'evidence_kind':r['evidence_kind'],
        'all_roles_correct':r['all_requested_roles_succeeded'],'role_matches':sum(x['role_match'] for x in r['roles'].values())})
    with executed('wrong_m2') as (_,p,run,_,bad,_):
        bundle_run(p,run,out/'wrong_m2_evidence.zip')
        write_json(out/'wrong_m2_result.json',{'calls':bad['inference_calls'],'evidence_kind':bad['evidence_kind'],
           'role_matches':sum(x['role_match'] for x in bad['roles'].values()),
           'proof_valid':sum(x['proof_valid'] for x in bad['roles'].values()),
           'A_component_changes':sum(x['coordinate_change_observed'] for x in bad['paired'] if x['axis']=='A'),
           'A_fully_valid_changes':sum(x['clean_requested_axis_change'] for x in bad['paired'] if x['axis']=='A')})
    print('합성 HTTP 실행과 ZIP 생성 완료. 실제 모델 추론 아님.')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);main(p.parse_args().out)
