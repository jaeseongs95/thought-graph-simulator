"""python -m paired_probe_v049: selftest→prepare→run→audit→bundle."""
from __future__ import annotations
import argparse
import json
import sys
import unittest
import zipfile
from pathlib import Path
from .contracts import ContractError, read_json, require
from .plan import prepare, validate_plan

def print_plan(p):
    print(json.dumps({'contract':p['contract'],'plan_sha256':p['plan_sha256'],
        'model':p['baseline']['config']['model'],'endpoint':p['baseline']['config']['endpoint'],
        'options':p['baseline']['config']['options'],'reused_v048_seeds':p['seeds'],
        'expressions':p['analysis_policy']['expressions'],'cycles':p['cycles'],'max_inference_calls':p['max_calls'],
        'baseline_anchor':p['reference']['anchor'],'evidence_kind':p['baseline']['evidence_kind']},ensure_ascii=False,indent=2))
    print('prepare/show는 네트워크·추론을 실행하지 않습니다. run에서만 계획된 로컬 추론을 실행합니다.')

def print_report(r):
    print(json.dumps({k:r[k] for k in ('data_integrity','data_complete','comparative_analysis_ready','evidence_kind','inference_calls','max_inference_calls')},ensure_ascii=False,indent=2))

def main(argv=None):
    p=argparse.ArgumentParser(description='v048 원문을 수입하는 표현 2×2 대조. 기존 소스/결과를 변경하지 않습니다.')
    s=p.add_subparsers(dest='command',required=True)
    q=s.add_parser('prepare',help='v048 evidence ZIP 재감사 후 계획 동결. 네트워크 없음')
    q.add_argument('--baseline-bundle',type=Path,required=True);q.add_argument('--out',type=Path,required=True)
    q=s.add_parser('show');q.add_argument('--plan',type=Path,required=True)
    q=s.add_parser('run');q.add_argument('--plan',type=Path,required=True);q.add_argument('--out',type=Path,required=True)
    for name in ('audit','bundle'):
        q=s.add_parser(name);q.add_argument('--plan',type=Path,required=True);q.add_argument('--run',type=Path,required=True)
        if name=='bundle':q.add_argument('--out',type=Path,required=True)
    q=s.add_parser('selftest',help='합성 HTTP 및 기존 회귀. 실제 Ollama 접근 없음')
    q.add_argument('--new-only',action='store_true',help='v049 시험만 실행. 기본값은 기존 회귀 포함')
    a=p.parse_args(argv)
    try:
        if a.command=='prepare':print_plan(prepare(a.baseline_bundle,a.out))
        elif a.command=='show':
            plan=read_json(a.plan);validate_plan(plan);print_plan(plan)
        elif a.command=='run':
            from .runner import execute
            report=execute(a.plan,a.out);print_report(report);print('요약:',a.out/'summary.ko.md')
            return 0 if report['comparative_analysis_ready'] else 3
        elif a.command=='audit':
            from .audit import audit_run
            report=audit_run(a.plan,a.run,write_report=True);print_report(report)
            return 0 if report['comparative_analysis_ready'] else 3
        elif a.command=='bundle':
            from .evidence import bundle_run
            report=bundle_run(a.plan,a.run,a.out);print_report(report);print('증거 ZIP:',a.out)
        else:
            root=Path(__file__).resolve().parent.parent;suite=unittest.TestSuite()
            for name in (('tests_v049',) if a.new_only else ('tests_v047','tests_v048','tests_v049')):
                require((root/name).is_dir(),'시험 폴더 누락: '+name)
                tests=unittest.TestLoader().discover(str(root/name),pattern='test_*.py',top_level_dir=str(root))
                require(tests.countTestCases()>0,'빈 시험 모음 금지');suite.addTests(tests)
            return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
    except (ContractError,OSError,KeyError,TypeError,ValueError,zipfile.BadZipFile) as exc:
        print('중단:',str(exc),file=sys.stderr);return 2
    return 0
if __name__=='__main__':raise SystemExit(main())
