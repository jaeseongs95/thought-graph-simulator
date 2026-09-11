"""실행 순서: selftest→prepare→run→audit→bundle. prepare는 오프라인이다."""
from __future__ import annotations
import argparse,json,sys,unittest,zipfile
from pathlib import Path
from .contracts import ContractError,read_json,require

def main(argv=None):
    parser=argparse.ArgumentParser(description='v050 원문을 재감사하고 고정 문제·목표 A/D/M 조작 예비실험을 실행합니다.')
    sub=parser.add_subparsers(dest='cmd',required=True)
    p=sub.add_parser('prepare');p.add_argument('--baseline-bundle',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p=sub.add_parser('show');p.add_argument('--plan',type=Path,required=True)
    p=sub.add_parser('run');p.add_argument('--plan',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    for name in ('audit','bundle'):
        p=sub.add_parser(name);p.add_argument('--plan',type=Path,required=True);p.add_argument('--run',type=Path,required=True)
        if name=='bundle':p.add_argument('--out',type=Path,required=True)
    p=sub.add_parser('selftest');p.add_argument('--new-only',action='store_true')
    a=parser.parse_args(argv)
    try:
        if a.cmd in ('prepare','show'):
            from .plan import prepare,validate_plan
            p=prepare(a.baseline_bundle,a.out) if a.cmd=='prepare' else read_json(a.plan)
            validate_plan(p)
            print(json.dumps({'contract':p['contract'],'plan_sha256':p['plan_sha256'],'model':p['baseline']['config']['model'],
              'options':p['baseline']['config']['options'],'seeds':p['seeds'],'roles':len(p['roles']),'cycles':p['cycles'],
              'max_calls':p['max_calls'],'baseline_anchor':p['reference']['anchor'],'evidence_kind':p['baseline']['evidence_kind']},ensure_ascii=False,indent=2))
            print('prepare/show는 네트워크·모델 추론을 실행하지 않습니다.')
        elif a.cmd=='selftest':
            root=Path(__file__).resolve().parent.parent;suite=unittest.TestSuite()
            names=('tests_v051',) if a.new_only else ('tests_v047','tests_v048','tests_v049','tests_v050','tests_v051')
            for name in names:
                require((root/name).is_dir(),'시험 폴더 누락: '+name)
                tests=unittest.TestLoader().discover(str(root/name),pattern='test_*.py',top_level_dir=str(root))
                require(tests.countTestCases()>0,'빈 시험 모음 금지');suite.addTests(tests)
            return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
        else:
            if a.cmd=='run':
                from .runner import execute
                r=execute(a.plan,a.out)
            elif a.cmd=='audit':
                from .audit import audit_run
                r=audit_run(a.plan,a.run,write_report=True)
            else:
                from .evidence import bundle_run
                r=bundle_run(a.plan,a.run,a.out);print('증거 ZIP:',a.out)
            print(json.dumps({k:r[k] for k in ('data_integrity','data_complete','comparative_analysis_ready','evidence_kind','inference_calls','max_inference_calls')},ensure_ascii=False,indent=2))
            return 0 if a.cmd=='bundle' or r['comparative_analysis_ready'] else 3
    except (ContractError,OSError,KeyError,TypeError,ValueError,zipfile.BadZipFile) as exc:
        print('중단:',str(exc),file=sys.stderr);return 2
    return 0
if __name__=='__main__':raise SystemExit(main())
