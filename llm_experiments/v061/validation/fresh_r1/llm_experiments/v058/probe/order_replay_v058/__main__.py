"""prepare → show → run → audit → bundle. 새 모델 다운로드/자동 추론 재시도 없음."""
from __future__ import annotations
import argparse,json,sys,unittest,zipfile
from pathlib import Path
from .contracts import ContractError,require,read_plan_json

def main(argv=None):
    ap=argparse.ArgumentParser(description='v058 선정된 경계 조건의 과제 순서 재실행: 80회')
    sub=ap.add_subparsers(dest='command',required=True)
    p=sub.add_parser('selftest')
    p=sub.add_parser('prepare');p.add_argument('--baseline-bundle',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p=sub.add_parser('show');p.add_argument('--plan',type=Path,required=True)
    p=sub.add_parser('run');p.add_argument('--plan',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    for name in ('audit','bundle'):
        p=sub.add_parser(name);p.add_argument('--plan',type=Path,required=True);p.add_argument('--run',type=Path,required=True)
        if name=='bundle':p.add_argument('--out',type=Path,required=True)
    a=ap.parse_args(argv)
    try:
        if a.command=='selftest':
            root=Path(__file__).resolve().parent.parent;loader=unittest.TestLoader();suite=unittest.TestSuite()
            names=['tests']
            for name in names:
                pattern='test_*.py'
                tests=loader.discover(str(root/name),pattern=pattern,top_level_dir=str(root));require(tests.countTestCases()>0,'빈 시험 모음 금지');suite.addTests(tests)
            return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
        if a.command in ('prepare','show'):
            from .plan import prepare,validate_plan
            p=prepare(a.baseline_bundle,a.out) if a.command=='prepare' else read_plan_json(a.plan);validate_plan(p)
            print(json.dumps({k:p[k] for k in ('contract','plan_sha256','model_keys','modes','boundary_cells','sequences','max_calls')},ensure_ascii=False,indent=2))
            print('오프라인 계획 확인 완료. 추론 실행 없음. v057 관측 후 선정한 경계 조건의 탐색적 순서 진단.');return 0
        if a.command=='run':
            from .runner import execute
            r=execute(a.plan,a.out)
        elif a.command=='audit':
            from .audit import audit_run
            r=audit_run(a.plan,a.run,write_report=True)
        else:
            from .evidence import bundle_run
            r=bundle_run(a.plan,a.run,a.out);print('증거 ZIP:',a.out)
        print(json.dumps({k:r[k] for k in ('data_integrity','data_complete','inference_calls','max_inference_calls','failure_stage','failure_kind','failure_slot_id','run_error')},ensure_ascii=False,indent=2))
        return 0 if a.command=='bundle' or r['data_complete'] else 3
    except (ContractError,OSError,ValueError,KeyError,TypeError,zipfile.BadZipFile) as e:
        print(type(e).__name__+': '+str(e),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
